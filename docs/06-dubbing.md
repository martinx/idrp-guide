# 06 录制之后：字幕来源与自然语速配音

00 章 0.4 节已经把核心结论摆出来了：**先有录像和字幕的时间戳，配音是后贴上去的**。本章把这个结论落到具体实现：字幕从哪来、配音怎么按字幕分段生成、怎么处理生成结果和原时间轴的微小误差，以及为什么这套做法能支撑"改一个字、几十秒出新片"的迭代速度。

## 6.1 字幕来源：时间点文本优先，语音识别兜底

录制完成后，第一件事是拿到一份 `subtitles.srt`。这份文件有两个可能的来源，系统会自动判断该用哪一个：

**来源一：录制脚本自带的时间点文本（首选，最准确）**。如果这次录制是由自动化脚本（04/05 章）驱动的，脚本本身在执行每一步操作时，就知道"现在是第几秒、这一步该说什么"——这份时间点文本（记录成 `timeline.json` 这样的结构：`[{ "t": 3.2, "text": "..." }, ...]`）在录制过程中或录制结束后，直接转换成标准 SRT 格式即可，不需要任何语音识别，因为文本本身就是原文，不是猜出来的。

```python
# scripts/timeline_to_srt.py
import json, sys

def to_srt_time(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    ms = int((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"

def timeline_to_srt(timeline_path: str, srt_path: str) -> None:
    timeline = json.load(open(timeline_path))
    lines = []
    for i, item in enumerate(timeline):
        start = item["t"]
        end = timeline[i + 1]["t"] if i + 1 < len(timeline) else start + 5
        lines.append(f"{i + 1}\n{to_srt_time(start)} --> {to_srt_time(end)}\n{item['text']}\n")
    open(srt_path, "w").write("\n".join(lines))

if __name__ == "__main__":
    timeline_to_srt(sys.argv[1], sys.argv[2])
```

**来源二：语音识别转写（兜底，用于非脚本驱动的手动录制）**。如果只是打开系统自带的屏幕录制工具，人工手动操作并对着话筒讲解一遍（这是最快的起步方式，完全不需要写自动化脚本），录出来的视频音轨里有真实的人声，这时候用本地语音识别模型（faster-whisper / SenseVoice 等）转写出字幕：

```python
# scripts/asr_to_srt.py
import sys
from faster_whisper import WhisperModel

def asr_to_srt(audio_path: str, srt_path: str) -> None:
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, language="zh")

    def fmt(t: float) -> str:
        h, m, s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
        ms = int((t % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(srt_path, "w") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n{fmt(seg.start)} --> {fmt(seg.end)}\n{seg.text.strip()}\n\n")

if __name__ == "__main__":
    asr_to_srt(sys.argv[1], sys.argv[2])
```

**两条路径怎么选**：判断逻辑很简单——如果 `subtitles.srt` 已经存在且比 `recording.mov` 新（说明是上一步从时间点文本生成的，是可信来源），就跳过语音识别，不要覆盖它；否则才跑语音识别兜底。这个先后关系很重要，因为录屏音轨往往没有真人说话（纯自动化操作是静音的），对着静音或者杂音跑语音识别只会得到一堆垃圾字幕。

```bash
if [ -f subtitles.srt ] && [ subtitles.srt -nt recording.mov ]; then
  echo "字幕已存在且比录屏新（来自时间点文本），跳过语音识别"
else
  python3 scripts/asr_to_srt.py recording.mov subtitles.srt
fi
```

## 6.2 按字幕分段生成配音：自然语速，不做时长强制拉伸

拿到 `subtitles.srt` 之后，逐条字幕调用 TTS 合成语音，**每一段都用它自然的语速生成，不去反向拉伸或压缩音频时长去匹配字幕原定的时间窗口**。这是和"音频先行"思路最大的实现差异——那种思路会强迫音频时长等于预设窗口，这里恰恰相反：音频多长就是多长，靠"下一段的起始间隔"去自然消化差异。

```python
# scripts/srt_to_dub.py
import re, subprocess, tempfile, os, sys

# edge-tts 拿不到 SSML <phoneme> 标签的官方支持（会被转义成字面文本整段读出来），
# 遇到多音字读错，唯一可靠的办法是换一种不触发歧义读音的措辞。
# 这份"问题词 → 安全替换词"表一次维护，对所有视频生效。
POLYPHONE_FIXES = {
    "命令行工具": "命令行",  # "行工具"这个搭配下偶尔把"行"读成 xíng，去掉"工具"更保险
}

def parse_srt(srt_path: str):
    content = open(srt_path).read()
    pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\Z)"
    return re.findall(pattern, content, re.DOTALL)

def to_sec(t: str) -> float:
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

def srt_to_dub(srt_path: str, out_wav: str, voice: str = "zh-CN-XiaoxiaoNeural") -> None:
    matches = parse_srt(srt_path)
    tmpdir = tempfile.mkdtemp()
    concat_list = os.path.join(tmpdir, "concat.txt")
    prev_end = 0.0

    with open(concat_list, "w") as cl:
        for idx, t1, t2, text in matches:
            text = text.strip().replace("\n", " ")
            if not text:
                continue
            for bad, good in POLYPHONE_FIXES.items():
                text = text.replace(bad, good)

            seg_start = to_sec(t1)
            # 段间静默：只在真的有空隙时插入，保持整体时间轴大致对齐原字幕节奏
            gap = seg_start - prev_end
            if gap > 0.3:
                gap_wav = os.path.join(tmpdir, f"gap_{idx}.wav")
                subprocess.run(
                    ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                     "-t", f"{gap:.2f}", gap_wav, "-y"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                cl.write(f"file '{gap_wav}'\n")

            mp3 = os.path.join(tmpdir, f"seg_{idx}.mp3")
            wav = os.path.join(tmpdir, f"seg_{idx}.wav")
            # 自然语速生成，不传任何速度/时长调整参数
            subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", mp3],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["ffmpeg", "-i", mp3, wav, "-y"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.remove(mp3)
            cl.write(f"file '{wav}'\n")

            # 用这一段实际生成的时长（而不是字幕原定的时长）累加，
            # 这样下一段的 gap 计算会自动吸收本段超出/不足的偏差
            actual_dur = probe_duration(wav)
            prev_end = prev_end + (gap if gap > 0.3 else 0) + actual_dur

    subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list,
                     "-c", "copy", out_wav, "-y"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def probe_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        stdout=subprocess.PIPE, text=True,
    )
    return float(result.stdout.strip() or 0)

if __name__ == "__main__":
    srt_to_dub(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "zh-CN-XiaoxiaoNeural")
```

几个关键设计点：

- **累计时间戳（`prev_end`）而不是每段独立对表**：如果某一段 TTS 生成的音频比原字幕窗口长（比如字幕给了 2 秒的窗口，但这句话自然读出来要 2.6 秒），不做任何截断或加速处理，就让它自然占用 2.6 秒；下一段开始前的静默间隔用"这一段实际结束时间"和"下一段字幕原定开始时间"的差值计算，如果差值变负（说明已经超出，没有空隙了），就直接跳过静默、紧接着播放下一段。整条配音轨会因为个别句子偏长而整体产生轻微的时间漂移，但相邻句子之间的相对顺序和大致节奏是保持住的。
- **为什么不用时长拉伸**：TTS 音频做时长拉伸（比如用 `atempo` 滤镜压缩/拉长）在偏差较大时会明显听出语速不自然，反而比"多几百毫秒的漂移"更影响观感。实践证明，容忍小幅漂移、靠 8.3 节的全局偏移做最后兜底，观感优于强行对齐每一句。
- **多音字问题表**：这是一个非常具体、容易被忽略但很实用的经验——国内主流 TTS（包括 edge-tts）不提供官方渠道让你用 SSML `<phoneme>` 标签强制指定某个字的读音（即使传了标签，也会被转义成字面文本整段读出来）。遇到读错的多音字，最可靠的解法不是找 TTS 的 hack 参数，而是维护一份"问题词 → 安全替换词"的替换表，换一种不触发歧义读音的表达方式。这个表随着使用积累会越来越完善，一次修复对所有视频生效。

## 6.3 英文（或其他语言）版本：翻译字幕，而不是翻译文案脚本

11.4 章讲多语言扩展时提到"操作录制和语言无关，只有文案层要多做一份"。具体做法是**批量翻译整份中文字幕，而不是分别为每种语言重新组织解说文案**：

```python
# scripts/translate_srt.py
import re, json, urllib.request, sys, os

def translate_srt(zh_srt: str, en_srt: str, api_key: str) -> None:
    content = open(zh_srt).read()
    pattern = r"(\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n)(.+?)(?=\n\n|\Z)"
    matches = re.findall(pattern, content, re.DOTALL)
    texts = [m[1].strip().replace("\n", " ") for m in matches]

    # 用一个不会出现在正文里的分隔符批量拼接，一次 API 调用翻译整份字幕，
    # 而不是每句话单独请求——既省调用次数，也让译文风格更一致
    combined = " ||| ".join(texts)
    body = json.dumps({
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "你是技术文档翻译专家。将以下中文逐句翻译成英文，"
                                           "每句用 ||| 分隔，保持原有顺序，只返回译文。"},
            {"role": "user", "content": combined},
        ],
        "temperature": 0.3,
    }).encode()

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    translated = resp["choices"][0]["message"]["content"].strip()
    en_texts = [t.strip() for t in translated.split("|||")]

    with open(en_srt, "w") as f:
        for i, (header, _) in enumerate(matches):
            if i < len(en_texts):
                f.write(f"{header}{en_texts[i]}\n\n")

if __name__ == "__main__":
    translate_srt(sys.argv[1], sys.argv[2], os.environ["DEEPSEEK_API_KEY"])
```

翻译出的英文 SRT 直接复用 6.2 节的 `srt_to_dub`（换一个英文发音人参数），录制、Codegen、时间点文本完全不用动第二遍——这正是"录制优先"架构在多语言场景下的直接收益：语言是配音/字幕层的属性，不是录制层的属性。

## 6.4 为什么这套做法能支撑"改一个字，几十秒出新片"

回到 00 章的核心承诺：录制是唯一慢的一步，其余全部可以快速重跑。原因现在可以说清楚了——**`subtitles.srt` 是一份纯文本文件，也是从这一步往后所有环节的唯一输入**。发现某句话措辞别扭、某个专有名词读错了，直接编辑这个文本文件，重新跑一遍 6.2 节的配音生成 + 08 章的合成，几十秒到一分钟就能拿到新的成片，全程不需要重新打开浏览器、不需要重新录制。这也是为什么 03 章会强调：**这份 SRT 文件（或者它的上游——时间点文本）是团队协作和 AI 介入的核心接口**，18 章会展开讲 AI 如何直接参与撰写和微调这份文本。

下一章讲封面/封底素材怎么生成，之后 08 章会把本章产出的配音、录像、封面素材全部合成为一条成片。
