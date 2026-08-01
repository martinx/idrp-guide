# 08 合成成片：裁剪、配音混流、封面拼接、字幕烧录

06 章拿到了配音音频，07 章会拿到封面素材。本章是"总装车间"：把原始录像、配音、封面/封底、字幕，按 00 章 0.4 节讲的"录制优先"顺序合成为一条成片。核心难点不是 ffmpeg 命令本身，而是几个容易被忽略、但真实踩过坑的细节：录制起始的不安全空档要裁掉、配音的全局偏移要和字幕的偏移保持同步、BGM/封底不能因为文件恰好存在就默默启用。

## 8.1 合成的整体步骤

```
recording.mov ──┐
                ├─▶ 裁剪起始空档 ─▶ 混流配音(+全局偏移) ─▶ 拼接封面/正文/封底
ai_dub.wav ─────┘                                              │
                                                                ▼
                                                        混入BGM(如果显式开启)
                                                                │
                                                                ▼
                                                        内嵌封面帧(缩略图)
                                                                │
                                                                ▼
                                                    烧录字幕(时间戳同步偏移)
                                                                │
                                                                ▼
                                                             成片.mp4
```

## 8.2 裁剪录制起始的不安全空档

05 章 5.7 节讲了 ready/go 双信号握手，用来避免"ffmpeg 已经启动、浏览器还没准备好"这段空档被录进去。但即使有这个握手，从"ffmpeg 进程启动"到"编码真正稳定输出"之间仍然有零点几秒的天然延迟——稳妥的做法是把这段延迟的秒数记录下来（比如写进 `record-offset.txt`），在合成这一步**再裁一刀**，双重保险：

```bash
# compose 阶段读取 record-offset.txt，裁掉开头这一小段
if [ -f "$dir/record-offset.txt" ]; then
  offset=$(cat "$dir/record-offset.txt")
  # 再加 0.3 秒缓冲，宁可多裁一点，不可让不安全画面漏进成片
  safe_offset=$(python3 -c "print(round(float('$offset') + 0.3, 2))")
  trim_args=(-ss "$safe_offset")
fi
```

这条原则值得单独强调：**任何"理论上不会露出敏感画面"的时间窗口，只要有哪怕零点几秒的不确定性，都应该在录制和合成两个环节各设一道防线，而不是信任其中一道就够了**。10 章的检查清单是最后一道人工防线，这里是自动化流程里的倒数第二道。

## 8.3 配音混流与全局偏移微调

把裁剪后的录像和配音混流成一条视频，同时应用 00 章 0.4 节提到的**全局 `dub_offset`**——这是唯一一个需要人工感知"听感对不对得上"的调节点，粒度是整条配音轨，而不是逐句调整：

```bash
compose() {
  local rec="$1" dub="$2" out="$3" dub_offset="$4"

  local dub_input_args=() audio_filter_args=() pad_filter=""

  if python3 -c "exit(0 if $dub_offset < 0 else 1)"; then
    # 负偏移：配音整体提前，跳过配音开头对应的秒数
    local skip=$(python3 -c "print(-$dub_offset)")
    dub_input_args=(-ss "$skip")
  elif python3 -c "exit(0 if $dub_offset > 0.001 else 1)"; then
    # 正偏移：配音整体延后，用 adelay 滤镜整体延迟
    local delay_ms=$(python3 -c "print(int($dub_offset * 1000))")
    audio_filter_args=(-af "adelay=${delay_ms}|${delay_ms}")

    # 正偏移会让"配音总时长"变成"原配音时长 + 偏移"，如果这个值超过了录像本身
    # 的时长，直接 -shortest 会把超出部分的配音截掉——配音说到一半突然没声，
    # 而不是报错。用 tpad 冻结画面最后一帧，把画面垫长到能装下完整配音，
    # 不依赖 -shortest 兜底截断。
    local video_dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$rec")
    local dub_dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$dub")
    local needed=$(python3 -c "print($dub_dur + $dub_offset)")
    if python3 -c "exit(0 if $needed > $video_dur else 1)"; then
      local pad=$(python3 -c "print(round($needed - $video_dur + 0.3, 2))")
      pad_filter=",tpad=stop_mode=clone:stop_duration=${pad}"
    fi
  fi

  ffmpeg -i "$rec" "${dub_input_args[@]}" -i "$dub" \
    -c:v h264_videotoolbox -b:v 5M -r 30 \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black${pad_filter}" \
    -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 \
    -map 0:v:0 -map 1:a:0 "${audio_filter_args[@]}" -shortest "$out" -y
}
```

这段代码里"正偏移会导致配音被截断"是一个真实踩过的坑：`dub_offset` 调大之后配合较短的录像，`-shortest` 会悄悄吃掉最后几句配音而不报任何错误——加 `tpad` 冻结最后一帧垫时长，是唯一可靠的修复方式，比事后靠人工听感发现"最后一句没声音"要主动得多。

## 8.4 封面、正文、封底拼接

正文视频（8.3 节产出）只是成片的一部分。完整的合成还要按需拼接标题封面（可以是一张静态图，也可以用 07 章的方法现场生成一张带标题文字的卡片）和封底：

```bash
compose_final() {
  local content="$1" out="$2"
  local parts=()

  # 1. 标题封面（可选）
  if [ -n "$title" ]; then
    gen_title_card "$title" "$subtitle" "$cover_duration" "$tmp/cover.mp4"
    parts+=("$tmp/cover.mp4")
  fi

  # 2. 正文
  parts+=("$content")

  # 3. 封底（可选，见8.5节为什么必须显式开启）
  if [ "$outro_enabled" = "true" ]; then
    gen_outro "$outro_asset" "$outro_duration" "$tmp/outro.mp4"
    parts+=("$tmp/outro.mp4")
  fi

  # 4. 拼接：各片段编码参数已在生成阶段对齐，优先用 stream-copy 无损拼接，
  #    速度极快；参数万一没对齐导致 stream-copy 失败，再回退到重新编码
  printf "file '%s'\n" "${parts[@]}" > "$tmp/concat.txt"
  if ! ffmpeg -f concat -safe 0 -i "$tmp/concat.txt" -c copy "$out" -y 2>/dev/null; then
    ffmpeg -f concat -safe 0 -i "$tmp/concat.txt" -c:v libx264 -preset fast -crf 23 -c:a aac "$out" -y
  fi

  # 5. BGM（可选，见8.5节）
  if [ -n "$bgm_asset" ]; then
    ffmpeg -i "$out" -i "$bgm_asset" \
      -filter_complex "[1:a]volume=${bgm_volume:-0.15}[bgm];[0:a][bgm]amix=inputs=2:duration=first" \
      -c:v copy "$tmp/final.mp4" -y
    mv "$tmp/final.mp4" "$out"
  fi
}
```

**"优先 stream-copy、失败才重新编码"**这个小细节值得留意：只要前面每一段素材（封面卡片、正文、封底）在生成时就统一了分辨率/帧率/像素格式/编码参数，`-c copy` 无损拼接几乎瞬间完成；只有素材来源不一致（比如封面是外部随手做的一张图，编码参数没对齐）时才需要重新编码兜底，这个顺序能让绝大多数场景下的合成速度快一个数量级。

## 8.5 显式开关：BGM 和封底不能"自动探测到文件就启用"

这是一条用真实事故换来的教训：如果系统设计成"资源目录里放了 `bgm.mp3` 就自动给所有视频混上背景音乐"，看似省心，实际上非常危险——**BGM 和封底会实打实地改变成片的听感/结构，不应该被一个文件是否存在这种隐式信号决定**。真实发生过的情况是：项目的公共资源目录里一直放着一个占位用的 `bgm.mp3`（或者一张占位黑图当 outro），某次自动探测逻辑的 bug 修好之后，所有历史视频重新合成时全部意外多出了一段没人要的背景音乐/黑屏封底。

正确的设计原则是：**素材文件"存在"和"要不要用"必须是两个独立的信号**。配置里必须显式写 `bgm: true`（或者给出具体路径）才会真正启用，`bgm` 字段缺省或者显式设为 `false` 时，即使资源目录里确实有同名文件，也绝不自动套用：

```python
def resolve_asset(meta: dict, dir_: str, project_dir: str, key: str) -> str:
    val = meta.get(key)
    if val in (None, "None", "null", False, "false"):
        return ""  # 显式禁用或从未设置 —— 不使用，即使文件存在
    if isinstance(val, str):
        return val  # 显式给了路径，直接用
    # val 为 True：按约定文件名，先查 feature 目录，再查项目公共 resources 目录
    for base in (dir_, f"{project_dir}/resources"):
        for name in CONVENTION_NAMES[key]:
            path = f"{base}/{name}"
            if os.path.exists(path):
                return path
    return ""
```

这条经验同样适用于任何"约定优于配置"的自动探测设计——约定优于配置的前提是**用户明确选择了走约定路径**，而不是"文件恰好在那儿"就被系统当成了信号。

## 8.6 字幕烧录：时间戳要跟着同一个偏移量一起平移

字幕烧录本身用 ffmpeg 的 `subtitles` 滤镜（需要编译进 libass 支持）：

```bash
ffmpeg -i final.mp4 \
  -vf "subtitles=subtitles.srt:force_style='FontName=PingFang SC,FontSize=44,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,MarginV=45'" \
  -c:a copy final-with-subs.mp4
```

容易被漏掉的一点是：8.3 节的 `dub_offset` 真实挪动了配音在时间轴上的位置，8.4 节的标题封面也让正文整体后移了 `cover_duration` 秒——**字幕的时间戳必须跟着同样的方向、同样的量级一起平移，否则配音已经提前/延后了，字幕却还对着画面原本（未偏移）的节奏，两者会对不上**。这是配音偏移功能上线后必须同步处理的一环，很容易在第一版实现里漏掉：

```python
def shift_srt(srt_path: str, shift_sec: float, out_path: str) -> None:
    """把字幕的每个时间戳整体平移 shift_sec 秒，正数延后、负数提前。"""
    content = open(srt_path).read()

    def shift_match(m):
        return "".join(shift_timestamp(t, shift_sec) for t in [m.group(0)])

    pattern = r"\d{2}:\d{2}:\d{2},\d{3}"
    return open(out_path, "w").write(re.sub(pattern, lambda m: shift_timestamp(m.group(0), shift_sec), content))
```

带封面的版本和不带封面的版本，总偏移量不一样（前者要多算上 `cover_duration`），实践中建议两个版本分别烧录，而不是共用一份偏移后的字幕文件。同时建议保留一份"不带封面、不烧字幕"的纯净版本（画面+配音），方便后续需要二次剪辑或者只要正文片段时直接取用，不用从带封面的成片里裁。

## 8.7 缩略图：把第 0 帧内嵌为封面贴图

一个容易被忽略、但影响"看起来专不专业"的细节：视频文件在 Finder / 大多数播放器里显示的默认缩略图，通常是从视频**中段**随机抽的一帧，不是第 0 帧——即使第 0 帧就是精心设计的标题封面，也不代表播放器会拿它当缩略图用。解决办法是把第 0 帧显式提取出来，作为"专辑封面"同款机制（`attached_pic`）内嵌进视频容器：

```bash
ffmpeg -i final.mp4 -vframes 1 -f image2 poster.png -y
ffmpeg -i final.mp4 -i poster.png -map 0 -map 1 -c copy \
  -c:v:1 png -disposition:v:1 attached_pic with_poster.mp4 -y
```

这样不管播放器内部怎么选缩略图逻辑、也不管观众有没有拖动过播放进度，Finder / 大多数播放器都会稳定显示这张内嵌的封面图作为缩略图。这是一个几行代码就能解决、但如果不知道这个机制会以为"没办法"的细节。

## 8.8 小结

本章的核心不是 ffmpeg 参数本身（这些命令查文档都能查到），而是四条来自真实使用中的经验：起始空档要在录制和合成两处各裁一刀、正偏移必须配合定格垫时长防止配音被截断、BGM/封底类会改变成片结构的素材必须显式开关而不能靠文件探测、字幕的时间戳必须和配音偏移保持数学上的一致。下一章把本章和前面几章的每个步骤，串成一套可以按需单独重跑的命令流程。
