# 06 自动配音 Dub 流程

本章实现"音频先行"策略（00 章 0.4 节）的具体代码：把 Feature Spec 里每一步的 `narration` 文案转成音频文件，测出精确时长，再把这个时长反馈给 05 章的录制层，驱动操作节奏。

## 6.1 TTS 适配层设计

不同 TTS 供应商的 API 形态差异很大（同步 REST、SDK、命令行工具），但对编排器来说，我们只关心一件事：**给一段文本和一个发音人，返回一个音频文件路径**。因此设计一个统一接口，屏蔽厂商差异：

```typescript
// src/dub/tts-provider.ts
export interface SynthesizeOptions {
  text: string;
  voice: string;
  speed: number;       // 1.0 为正常语速
  outputPath: string;  // 期望输出的音频文件路径（.wav）
}

export interface TtsProvider {
  synthesize(opts: SynthesizeOptions): Promise<string>; // 返回实际生成的文件路径
}
```

**离线兜底实现（edge-tts，跨平台，本地开发首选）**：

```typescript
// src/dub/tts-edge.ts
import { execFile } from "child_process";
import { promisify } from "util";
import { TtsProvider, SynthesizeOptions } from "./tts-provider";

const execFileAsync = promisify(execFile);

export class EdgeTtsProvider implements TtsProvider {
  async synthesize(opts: SynthesizeOptions): Promise<string> {
    const mp3Path = opts.outputPath.replace(/\.wav$/, ".mp3");
    const rateArg = `${opts.speed >= 1 ? "+" : ""}${Math.round((opts.speed - 1) * 100)}%`;

    await execFileAsync("edge-tts", [
      "--voice", opts.voice,
      "--rate", rateArg,
      "--text", opts.text,
      "--write-media", mp3Path,
    ]);

    // 统一转成 wav，方便后续 ffprobe 测时长和 ffmpeg 混音时格式一致
    await execFileAsync("ffmpeg", ["-y", "-i", mp3Path, "-ar", "44100", "-ac", "2", opts.outputPath]);
    return opts.outputPath;
  }
}
```

**macOS 原生实现（`say`，完全离线，适合无网络环境调试）**：

```typescript
// src/dub/tts-say.ts
import { execFile } from "child_process";
import { promisify } from "util";
import { TtsProvider, SynthesizeOptions } from "./tts-provider";

const execFileAsync = promisify(execFile);

export class MacSayTtsProvider implements TtsProvider {
  async synthesize(opts: SynthesizeOptions): Promise<string> {
    const aiffPath = opts.outputPath.replace(/\.wav$/, ".aiff");
    // say 的语速单位是"每分钟单词数"，175 约等于正常语速，按 speed 倍率换算
    const rateWpm = Math.round(175 * opts.speed);

    await execFileAsync("say", [
      "-v", opts.voice,       // 例如 "Tingting"（中文发音人）
      "-r", String(rateWpm),
      "-o", aiffPath,
      "--data-format=LEI16@44100",
      opts.text,
    ]);
    await execFileAsync("afconvert", [aiffPath, opts.outputPath, "-f", "WAVE", "-d", "LEI16"]);
    return opts.outputPath;
  }
}
```

**云端实现（以 Azure Speech 为例，生产环境推荐，音质与发音人选择明显优于离线方案）**：

```typescript
// src/dub/tts-azure.ts
import * as sdk from "microsoft-cognitiveservices-speech-sdk";
import fs from "fs";
import { TtsProvider, SynthesizeOptions } from "./tts-provider";

export class AzureTtsProvider implements TtsProvider {
  async synthesize(opts: SynthesizeOptions): Promise<string> {
    const speechConfig = sdk.SpeechConfig.fromSubscription(
      process.env.AZURE_SPEECH_KEY!,
      process.env.AZURE_SPEECH_REGION!
    );
    speechConfig.speechSynthesisVoiceName = opts.voice;
    speechConfig.speechSynthesisOutputFormat =
      sdk.SpeechSynthesisOutputFormat.Riff44100Hz16BitMonoPcm;

    const audioConfig = sdk.AudioConfig.fromAudioFileOutput(opts.outputPath);
    const synthesizer = new sdk.SpeechSynthesizer(speechConfig, audioConfig);

    // SSML 里通过 prosody 标签控制语速，比部分厂商 SDK 的独立参数更精细可控
    const ratePercent = Math.round((opts.speed - 1) * 100);
    const ssml = `
      <speak version="1.0" xml:lang="zh-CN">
        <voice name="${opts.voice}">
          <prosody rate="${ratePercent}%">${escapeXml(opts.text)}</prosody>
        </voice>
      </speak>`;

    return new Promise((resolve, reject) => {
      synthesizer.speakSsmlAsync(
        ssml,
        (result) => {
          synthesizer.close();
          if (result.reason === sdk.ResultReason.SynthesizingAudioCompleted) {
            resolve(opts.outputPath);
          } else {
            reject(new Error(`Azure TTS 合成失败: ${result.errorDetails}`));
          }
        },
        (err) => {
          synthesizer.close();
          reject(err);
        }
      );
    });
  }
}

function escapeXml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
```

**统一入口（根据环境变量选择供应商，业务代码不用关心具体是哪个）**：

```typescript
// src/dub/index.ts
import { TtsProvider } from "./tts-provider";
import { EdgeTtsProvider } from "./tts-edge";
import { MacSayTtsProvider } from "./tts-say";
import { AzureTtsProvider } from "./tts-azure";

export function createTtsProvider(): TtsProvider {
  switch (process.env.TTS_PROVIDER) {
    case "azure":
      return new AzureTtsProvider();
    case "mac-say":
      return new MacSayTtsProvider();
    case "edge":
    default:
      return new EdgeTtsProvider();
  }
}
```

这样，`.env.local` 里切换一个 `TTS_PROVIDER` 变量，就能在本地离线调试和生产云端合成之间切换，其余所有代码不需要改动——这是第 01 章强调"业务代码不用改，只切环境变量"的具体落地。

## 6.2 精确测量音频时长

生成音频之后，需要拿到精确到毫秒的时长，作为 05 章录制节奏的驱动依据。用 `ffprobe`（ffmpeg 套件自带）：

```typescript
// src/dub/audio-duration.ts
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function getAudioDurationSec(filePath: string): Promise<number> {
  const { stdout } = await execFileAsync("ffprobe", [
    "-v", "error",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1",
    filePath,
  ]);
  const seconds = parseFloat(stdout.trim());
  if (Number.isNaN(seconds)) {
    throw new Error(`无法解析音频时长: ${filePath}`);
  }
  return seconds;
}
```

## 6.3 时长与节奏的耦合逻辑

回到 03 章 Feature Spec 里每个步骤的 `pace.min_hold_sec`，真正驱动 05 章录制层"这一步该停留多久"的公式是：

```
该步骤实际时长 = max(配音音频时长, pace.min_hold_sec) + 首尾各 0.3~0.5 秒缓冲
```

取 `max` 而不是直接用配音时长，是为了兼容"配音很短但操作本身需要时间被看清"的情况（比如一句"点击确认"配音只需 1 秒，但页面弹窗动画本身需要 1.5 秒才能展示完整）；反过来配音明显长于操作耗时时（解说词写得比较详细），也要让画面停留够长，不能让操作画面在配音讲完之前就切走。

```typescript
// src/dub/pacing.ts
import { FeatureStep } from "../spec/schema";
import { getAudioDurationSec } from "./audio-duration";

export interface StepTiming {
  stepId: string;
  audioPath: string;
  audioDurationSec: number;
  holdSec: number;      // 最终该步骤在成片里占据的时长
}

const EDGE_PADDING_SEC = 0.4;

export async function computeStepTiming(
  step: FeatureStep,
  audioPath: string
): Promise<StepTiming> {
  const audioDurationSec = await getAudioDurationSec(audioPath);
  const minHold = step.pace?.min_hold_sec ?? 0;
  const holdSec = Math.max(audioDurationSec, minHold) + EDGE_PADDING_SEC * 2;

  return { stepId: step.id, audioPath, audioDurationSec, holdSec };
}
```

09 章编排器的执行顺序因此被固定为：**先为该 Feature 的每个步骤批量生成配音并测出时长 → 再驱动 04/05 章的操作脚本和录制，把 `holdSec` 作为该步骤录制完操作后要额外停留等待的时间**。这一步顺序不能颠倒，否则时长信息就无从获得。

具体到 05 章的录制循环，一个步骤的执行伪代码是：

```typescript
async function runActionStep(page: Page, step: FeatureStep, timing: StepTiming) {
  const stepFn = codegenSteps[step.codegen_ref!];
  await stepFn(page);                       // 04章的操作脚本，纯操作，不含等待

  if (step.pace?.wait_for) {
    await page.waitForSelector(step.pace.wait_for, { state: "visible" });
  }

  const elapsedSoFar = /* 操作本身耗费的时间，由调用方计时 */ 0;
  const remaining = Math.max(0, timing.holdSec - elapsedSoFar);
  await page.waitForTimeout(remaining * 1000); // 补足到 holdSec，保证与配音对齐
}
```

## 6.4 解说文案撰写的节奏建议

配音时长直接决定视频节奏，因此文案本身要按"每步一到两句、信息密度均匀"的原则撰写，避免出现某一步文案特别长（导致该步骤画面被迫停留很久，观众等得不耐烦）而另一步文案特别短（画面一闪而过）。经验数值：中文配音语速在 1.0 倍速下大约是每分钟 260～300 字，据此可以反推一段文案大概会占多长时间，提前把每步文案控制在 3～8 秒对应的字数区间（约 15～40 字）内，是比较舒适的观感节奏。

## 6.5 响度归一化

不同 TTS 供应商、不同发音人合成出来的音频，响度（音量感知大小）可能不一致，多段拼接后会出现"忽大忽小"的听感问题。用 ffmpeg 的 `loudnorm` 滤镜对每段配音统一归一化到广播级标准响度（EBU R128，-16 LUFS 是常见的网络视频标准）：

```bash
ffmpeg -i work/feature-07-export-report/audio/click-export.wav \
  -af loudnorm=I=-16:LRA=11:TP=-1.5 \
  -ar 44100 \
  work/feature-07-export-report/audio/click-export.norm.wav
```

```typescript
// src/dub/normalize.ts
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function normalizeLoudness(inputPath: string, outputPath: string): Promise<void> {
  await execFileAsync("ffmpeg", [
    "-y", "-i", inputPath,
    "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
    "-ar", "44100",
    outputPath,
  ]);
}
```

这一步放在"生成音频"和"测量时长"之间执行——响度归一化会略微改变音频总时长（通常在几十毫秒量级），所以时长测量必须以归一化之后的文件为准，顺序不能反过来。

## 6.6 批量生成入口

```typescript
// src/dub/synthesize-feature.ts
import path from "path";
import { FeatureSpec } from "../spec/schema";
import { createTtsProvider } from "./index";
import { normalizeLoudness } from "./normalize";
import { computeStepTiming, StepTiming } from "./pacing";

export async function synthesizeFeatureNarration(
  spec: FeatureSpec,
  workDir: string
): Promise<Record<string, StepTiming>> {
  const tts = createTtsProvider();
  const audioDir = path.join(workDir, "audio");
  const timings: Record<string, StepTiming> = {};

  for (const step of spec.steps) {
    const rawPath = path.join(audioDir, `${step.id}.raw.wav`);
    const finalPath = path.join(audioDir, `${step.id}.wav`);

    await tts.synthesize({
      text: step.narration,
      voice: spec.narration.voice,
      speed: spec.narration.speed,
      outputPath: rawPath,
    });
    await normalizeLoudness(rawPath, finalPath);

    timings[step.id] = await computeStepTiming(step, finalPath);
  }

  return timings;
}
```

这个函数是 09 章编排器调用的第一个"重"环节的产出——拿到 `timings` 之后，才具备驱动 04/05 章操作与录制节奏的全部信息。

下一章处理静态的封面/片头画面生成，为 08 章的最终合成提供另一路素材。
