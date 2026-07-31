# 08 音视频合成 Cover-Mix

本章是整条流水线的"总装车间"：把 05 章的操作录制分段、06 章的配音音频、07 章的封面片段，按 Feature Spec 的步骤顺序合成为一条完整成片，同时处理字幕烧录、背景音乐混音、响度与分辨率的最终规范化。

## 8.1 合成的整体步骤

1. **统一分段视频的编码参数**（分辨率、帧率、像素格式），因为路线一（Playwright webm）和路线二（ffmpeg mp4）产出的编码参数可能不同，拼接前必须对齐，否则 `concat` 会失败或画面错乱。
2. **把每段操作视频与对应配音音频合并**，配音音频时长已经在 06 章驱动了该步骤的画面停留时长，此处只是简单地把音频轨"贴"到对应视频段上。
3. **按 Feature Spec 步骤顺序，用 concat demuxer 拼接所有分段**（cover → action... → outro）。
4. **生成字幕文件**（SRT），按每步的实际起止时间戳对齐。
5. **烧录字幕（可选）、叠加背景音乐（可选）、做最终响度与分辨率规范化**，导出成片。

## 8.2 统一分段编码参数

```typescript
// src/mix/normalize-segment.ts
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function normalizeSegment(opts: {
  inputPath: string;
  outputPath: string;
  resolution: string; // 例如 "1920x1080"
  fps: number;
}): Promise<string> {
  await execFileAsync("ffmpeg", [
    "-y",
    "-i", opts.inputPath,
    "-vf", `scale=${opts.resolution.replace("x", ":")}:force_original_aspect_ratio=decrease,pad=${opts.resolution.replace("x", ":")}:(ow-iw)/2:(oh-ih)/2,setsar=1`,
    "-r", String(opts.fps),
    "-vcodec", "libx264",
    "-pix_fmt", "yuv420p",
    "-preset", "veryfast",
    "-crf", "18",
    "-an", // 分段视频先剥离音轨，音频单独处理，避免声画不同步的编码问题
    opts.outputPath,
  ]);
  return opts.outputPath;
}
```

`scale...force_original_aspect_ratio=decrease,pad=...` 这一组合滤镜的作用是：把不同来源（浏览器录制视口 1440x900、系统录屏可能是其他分辨率）的画面等比缩放后居中填充到统一的 1920x1080 画布，多出的部分用黑边（或按 07 章品牌背景色）填充，而不是直接拉伸变形。

## 8.3 视频与音频合并

```typescript
// src/mix/attach-audio.ts
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function attachAudioToVideo(opts: {
  videoPath: string;
  audioPath: string;
  holdSec: number;      // 06章计算出的该步骤总时长
  outputPath: string;
}): Promise<string> {
  await execFileAsync("ffmpeg", [
    "-y",
    "-i", opts.videoPath,
    "-i", opts.audioPath,
    // 视频用 tpad 补齐/裁剪到 holdSec 长度（操作耗时可能略短或略长于配音+缓冲）
    "-vf", `tpad=stop_mode=clone:stop_duration=${opts.holdSec}`,
    "-t", String(opts.holdSec),
    "-map", "0:v:0",
    "-map", "1:a:0",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
    "-c:a", "aac", "-b:a", "160k",
    "-shortest",
    opts.outputPath,
  ]);
  return opts.outputPath;
}
```

`tpad=stop_mode=clone` 的作用是：如果操作录制的画面比 `holdSec` 短（比如页面提前完成了跳转，剩余时间画面已经静止），就复制最后一帧填满剩余时长，避免画面突然黑屏或跳变；`-t` 兜底截断超出部分。这样保证每一段视频的时长精确等于 06 章算出的 `holdSec`，后续拼接时不需要再做时间轴对齐计算。

## 8.4 使用 concat demuxer 拼接

ffmpeg 的 `concat` 有两种模式：filter 模式（灵活但对不同参数的流较敏感）和 demuxer 模式（要求所有输入流参数完全一致，但速度快、无损）。因为 8.2/8.3 两步已经把所有分段规范化到完全一致的编码参数，这里直接用 demuxer 模式：

```typescript
// src/mix/concat.ts
import fs from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function concatSegments(opts: {
  segmentPaths: string[]; // 按 Feature Spec steps 顺序排列
  outputPath: string;
  workDir: string;
}): Promise<string> {
  const listPath = path.join(opts.workDir, "concat-list.txt");
  const listContent = opts.segmentPaths
    .map((p) => `file '${path.resolve(p)}'`)
    .join("\n");
  fs.writeFileSync(listPath, listContent);

  await execFileAsync("ffmpeg", [
    "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", listPath,
    "-c", "copy", // 参数已统一，直接无损拼接，速度极快
    opts.outputPath,
  ]);
  return opts.outputPath;
}
```

## 8.5 字幕生成与烧录

字幕的起止时间戳直接来自 06 章为每步计算的 `holdSec` 累加，不需要另外做语音识别对齐（这也是"音频先行"策略的又一个红利：时间轴是我们自己算出来的，天然精确，不需要用 ASR 反向去猜字幕时间点）。

```typescript
// src/mix/subtitle.ts
import fs from "fs";
import { FeatureSpec } from "../spec/schema";
import { StepTiming } from "../dub/pacing";

function formatSrtTime(totalSec: number): string {
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = Math.floor(totalSec % 60);
  const ms = Math.round((totalSec - Math.floor(totalSec)) * 1000);
  const pad = (n: number, len = 2) => String(n).padStart(len, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)},${pad(ms, 3)}`;
}

export function generateSrt(spec: FeatureSpec, timings: Record<string, StepTiming>): string {
  let cursor = 0;
  let index = 1;
  const lines: string[] = [];

  for (const step of spec.steps) {
    const timing = timings[step.id];
    const start = cursor;
    const end = cursor + timing.holdSec;
    lines.push(
      String(index),
      `${formatSrtTime(start)} --> ${formatSrtTime(end)}`,
      step.narration,
      ""
    );
    cursor = end;
    index += 1;
  }

  return lines.join("\n");
}

export function writeSrtFile(spec: FeatureSpec, timings: Record<string, StepTiming>, outPath: string): string {
  fs.writeFileSync(outPath, generateSrt(spec, timings), "utf-8");
  return outPath;
}
```

**烧录字幕（硬字幕，兼容性最好，推荐作为对外分发的默认选项）**：

```typescript
// src/mix/burn-subtitle.ts
import { execFile } from "child_process";
import { promisify } from "util";
import { RuleConfig } from "../util/rule";

const execFileAsync = promisify(execFile);

export async function burnSubtitle(opts: {
  videoPath: string;
  srtPath: string;
  rule: RuleConfig;
  outputPath: string;
}): Promise<string> {
  // force_style 里的颜色格式是 &HBBGGRR&（ASS 颜色顺序与常见的 RRGGBB 相反，且是 BGR）
  const style = [
    `FontName=${opts.rule.brand.font_family_cn}`,
    "FontSize=20",
    "PrimaryColour=&HFFFFFF&",
    "OutlineColour=&H000000&",
    "BorderStyle=1",
    "Outline=2",
    "Alignment=2",
    "MarginV=60",
  ].join(",");

  await execFileAsync("ffmpeg", [
    "-y",
    "-i", opts.videoPath,
    "-vf", `subtitles=${opts.srtPath}:force_style='${style}':fontsdir=${escapeFontsDir(opts.rule.brand.font_file_path)}`,
    "-c:a", "copy",
    opts.outputPath,
  ]);
  return opts.outputPath;
}

function escapeFontsDir(fontFilePath: string): string {
  // subtitles 滤镜的 fontsdir 需要目录而非文件路径
  return fontFilePath.substring(0, fontFilePath.lastIndexOf("/"));
}
```

如果不想烧录（希望保留软字幕，方便观众自行开关/翻译），改用 `-c:s mov_text`（mp4 容器）把 SRT 作为独立字幕轨封装进输出文件，播放器需要支持字幕轨切换：

```bash
ffmpeg -i input.mp4 -i subtitle.srt -c:v copy -c:a copy -c:s mov_text output.mp4
```

Feature Spec 里 `output.subtitle` 字段（03 章定义）就是用来在这两种模式（以及完全不要字幕）之间做选择的开关，09 章编排器据此调用不同函数。

## 8.6 背景音乐混音（可选）

如果 Feature Spec 的 `output.background_music` 不是 `none`，需要把背景音乐轨和已经贴好的解说配音轨做混合，同时把背景音乐音量压低，避免盖过解说（这个技术叫"音频闪避/ducking"，简化版实现是直接把背景音乐音量固定调低，更精细的版本可以用 `sidechaincompress` 滤镜做动态闪避，此处给出简化版，已能满足大多数功能演示场景）：

```typescript
// src/mix/background-music.ts
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function mixBackgroundMusic(opts: {
  videoPath: string;      // 已经拼接好、带解说配音的视频
  musicPath: string;
  outputPath: string;
  musicVolume?: number;   // 默认 0.12，明显低于人声，只做氛围铺垫
}): Promise<string> {
  const volume = opts.musicVolume ?? 0.12;

  await execFileAsync("ffmpeg", [
    "-y",
    "-i", opts.videoPath,
    "-stream_loop", "-1",     // 背景音乐循环播放，长度不够时自动补齐
    "-i", opts.musicPath,
    "-filter_complex",
    `[1:a]volume=${volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]`,
    "-map", "0:v:0",
    "-map", "[aout]",
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "192k",
    "-shortest",
    opts.outputPath,
  ]);
  return opts.outputPath;
}
```

`duration=first` 保证混音后总时长以视频（第一个输入）为准，背景音乐不会把视频"拖长"。

## 8.7 最终导出规范化

拼接、字幕、混音都完成后，做最后一次统一的响度归一化和编码参数收敛，确保不管中间经过多少次 ffmpeg 调用（每次转码都会有微小的质量损耗累积），最终交付的文件质量和参数是可预期、可复核的：

```typescript
// src/mix/export.ts
import { execFile } from "child_process";
import { promisify } from "util";
import { RuleConfig } from "../util/rule";

const execFileAsync = promisify(execFile);

export async function finalExport(opts: {
  inputPath: string;
  outputPath: string;
  rule: RuleConfig;
}): Promise<string> {
  const [w, h] = opts.rule.recording.output_resolution.split("x");

  await execFileAsync("ffmpeg", [
    "-y",
    "-i", opts.inputPath,
    "-vf", `scale=${w}:${h}`,
    "-r", String(opts.rule.recording.fps),
    "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
    "-c:v", "libx264",
    "-profile:v", "high",
    "-pix_fmt", "yuv420p",
    "-preset", "medium",     // 最终导出用更高质量的 preset，不再追求编码速度
    "-crf", "16",
    "-c:a", "aac", "-b:a", "192k",
    "-movflags", "+faststart", // 支持网页播放器边下边播
    opts.outputPath,
  ]);
  return opts.outputPath;
}
```

`-movflags +faststart` 把 mp4 的元数据索引移到文件头部，是网页/内部培训平台在线播放（而不是先完整下载）的必要设置，很容易被忽略但影响很大。

## 8.8 转场（可选的观感优化）

分段之间如果想要比"硬切"更柔和的视觉效果，可以在 `concat` 之前用 `xfade` 滤镜给相邻片段加交叉淡化转场。因为 `xfade` 要求两两处理、且会略微改变总时长（转场部分是两段画面的重叠），实现复杂度比直接 `concat` 高不少，建议只在对成片质感有更高要求时再引入，功能性演示视频优先保证信息传达清晰，转场是锦上添花而非必需：

```bash
ffmpeg -i seg1.mp4 -i seg2.mp4 -filter_complex \
  "[0:v][1:v]xfade=transition=fade:duration=0.4:offset=4.6[v]" \
  -map "[v]" -c:v libx264 transition_1_2.mp4
```

## 8.9 本章产物

按顺序执行 8.2 → 8.3 → 8.4 → 8.5 → （可选 8.6）→ 8.7，最终在 `output/<feature-id>.mp4` 得到一条：分辨率/帧率统一、配音与画面精确对齐、字幕烧录或封装完成、响度归一化、支持网页快速播放的成片。

下一章把 03～08 章的所有模块，用一个编排器串成"一条命令跑完整个流程"。
