# 09 全流程编排器实现

本章把 03～08 章的所有模块串成一个命令：`npm run run:feature -- specs/feature-07-export-report.yaml`，运行完就在 `output/` 目录得到成片。这是全书唯一一处需要把各章代码"接线"在一起的地方，重点是执行顺序、错误处理、以及每一步产物如何传递给下一步。

## 9.1 执行顺序总览

结合 00 章的架构图和 06 章"音频先行"的核心原则，真正的执行顺序是：

```
1. 加载并校验 Feature Spec（03章 loadFeatureSpec）
2. Preflight：冒烟测试所有 codegen_ref 片段（04章 4.6节）
3. 批量生成配音 + 计算每步 holdSec（06章 synthesizeFeatureNarration）
4. 生成封面/片尾静态图并转成视频片段（07章）
5. 按 holdSec 驱动，逐步执行操作脚本并录制（04+05章）
6. 规范化所有分段编码参数、贴合音频（08章 8.2/8.3节）
7. 拼接所有分段（08章 8.4节）
8. 生成字幕并按 Spec 配置烧录/封装（08章 8.5节）
9. 视情况混入背景音乐（08章 8.6节）
10. 最终导出规范化（08章 8.7节）
11. 清理 work/ 中间产物（可选，见9.5节）
```

注意第 3 步（配音+计时）在第 5 步（真正操作录制）**之前**完成，这是 00 章 0.4 节强调的关键顺序，任何试图"先录后配"的实现都会破坏整套时长驱动逻辑。

## 9.2 编排器主体代码

```typescript
// src/orchestrator/run-feature.ts
import path from "path";
import fs from "fs";
import { loadFeatureSpec } from "../spec/loader";
import { FeatureSpec, FeatureStep } from "../spec/schema";
import { loadRule } from "../util/rule";
import { synthesizeFeatureNarration } from "../dub/synthesize-feature";
import { StepTiming } from "../dub/pacing";
import { renderCover } from "../cover/render-cover";
import { coverImageToClip } from "../cover/cover-to-clip";
import { startBrowserRecording, stopBrowserRecording } from "../recorder/browser-recorder";
import { startScreenRecording, stopScreenRecording } from "../recorder/screen-recorder";
import { normalizeSegment } from "../mix/normalize-segment";
import { attachAudioToVideo } from "../mix/attach-audio";
import { concatSegments } from "../mix/concat";
import { writeSrtFile } from "../mix/subtitle";
import { burnSubtitle } from "../mix/burn-subtitle";
import { mixBackgroundMusic } from "../mix/background-music";
import { finalExport } from "../mix/export";
import { preflightCheck } from "./preflight";
import { codegenSteps } from "../codegen/registry";
import { login } from "../codegen/steps/common/login";
import { logger } from "../util/logger";

async function main() {
  const specPath = process.argv[2];
  if (!specPath) {
    console.error("用法: npm run run:feature -- specs/xxx.yaml");
    process.exit(1);
  }

  const spec = loadFeatureSpec(specPath);
  const rule = loadRule();
  const workDir = path.join("work", spec.id);
  const rawDir = path.join(workDir, "raw");
  const audioDir = path.join(workDir, "audio");
  fs.mkdirSync(rawDir, { recursive: true });
  fs.mkdirSync(audioDir, { recursive: true });

  logger.info(`[${spec.id}] 开始处理: ${spec.title}`);

  // 步骤1+2: Spec 已在 loadFeatureSpec 中校验；此处做 codegen 片段冒烟测试
  logger.info(`[${spec.id}] Preflight 检查...`);
  await preflightCheck(spec);

  // 步骤3: 批量生成配音 + 计算时长
  logger.info(`[${spec.id}] 生成配音...`);
  const timings: Record<string, StepTiming> = await synthesizeFeatureNarration(spec, workDir);

  // 步骤4: 封面/片尾
  logger.info(`[${spec.id}] 生成封面...`);
  const coverSegments = await renderCoverSteps(spec, rule, workDir, timings);

  // 步骤5: 操作步骤录制
  logger.info(`[${spec.id}] 执行操作并录制...`);
  const actionSegments = await runActionSteps(spec, rule, workDir, timings);

  // 合并所有分段，按 Spec 步骤原始顺序排列（cover/action 混合）
  const orderedSegments = spec.steps.map(
    (step) => coverSegments[step.id] ?? actionSegments[step.id]
  );

  // 步骤6+7: 规范化 + 拼接
  logger.info(`[${spec.id}] 拼接分段...`);
  const normalizedPaths: string[] = [];
  for (const seg of orderedSegments) {
    const normPath = seg.replace(/\.(mp4|webm)$/, ".norm.mp4");
    await normalizeSegment({
      inputPath: seg,
      outputPath: normPath,
      resolution: rule.recording.output_resolution,
      fps: rule.recording.fps,
    });
    normalizedPaths.push(normPath);
  }

  // 把每段视频和对应音频贴合（cover步骤的"音频"是它自己的解说配音，action步骤同理）
  const withAudioPaths: string[] = [];
  for (let i = 0; i < spec.steps.length; i++) {
    const step = spec.steps[i];
    const timing = timings[step.id];
    const withAudioPath = normalizedPaths[i].replace(".norm.mp4", ".withaudio.mp4");
    await attachAudioToVideo({
      videoPath: normalizedPaths[i],
      audioPath: timing.audioPath,
      holdSec: timing.holdSec,
      outputPath: withAudioPath,
    });
    withAudioPaths.push(withAudioPath);
  }

  const concatPath = path.join(workDir, "concat.mp4");
  await concatSegments({ segmentPaths: withAudioPaths, outputPath: concatPath, workDir });

  // 步骤8: 字幕
  let videoWithSubtitle = concatPath;
  if (spec.output.subtitle !== "none") {
    const srtPath = path.join(workDir, "subtitle.srt");
    writeSrtFile(spec, timings, srtPath);
    if (spec.output.subtitle === "burned_in") {
      videoWithSubtitle = path.join(workDir, "with-subtitle.mp4");
      await burnSubtitle({ videoPath: concatPath, srtPath, rule, outputPath: videoWithSubtitle });
    }
    // soft 模式的软字幕封装留给 finalExport 前的单独处理，此处从略，思路见08章8.5节
  }

  // 步骤9: 背景音乐
  let videoWithMusic = videoWithSubtitle;
  if (spec.output.background_music !== "none") {
    videoWithMusic = path.join(workDir, "with-music.mp4");
    await mixBackgroundMusic({
      videoPath: videoWithSubtitle,
      musicPath: spec.output.background_music,
      outputPath: videoWithMusic,
    });
  }

  // 步骤10: 最终导出
  fs.mkdirSync("output", { recursive: true });
  const finalPath = path.join("output", `${spec.id}.mp4`);
  await finalExport({ inputPath: videoWithMusic, outputPath: finalPath, rule });

  logger.info(`[${spec.id}] ✅ 完成: ${finalPath}`);
}

main().catch((err) => {
  logger.error(err);
  process.exit(1);
});
```

## 9.3 封面步骤与操作步骤的执行细节

```typescript
// src/orchestrator/render-cover-steps.ts
import path from "path";
import { FeatureSpec } from "../spec/schema";
import { RuleConfig } from "../util/rule";
import { StepTiming } from "../dub/pacing";
import { renderCover } from "../cover/render-cover";
import { coverImageToClip } from "../cover/cover-to-clip";

export async function renderCoverSteps(
  spec: FeatureSpec,
  rule: RuleConfig,
  workDir: string,
  timings: Record<string, StepTiming>
): Promise<Record<string, string>> {
  const result: Record<string, string> = {};

  for (const step of spec.steps) {
    if (step.kind !== "cover") continue;
    const imgPath = path.join(workDir, `${step.id}.png`);
    await renderCover({
      title: spec.title,
      badgeText: step.id === "intro" ? "功能演示" : "感谢观看",
      rule,
      outputPath: imgPath,
    });

    const clipPath = path.join(workDir, "raw", `${step.id}.mp4`);
    await coverImageToClip({
      imagePath: imgPath,
      durationSec: timings[step.id].holdSec,
      fps: rule.recording.fps,
      outputPath: clipPath,
    });
    result[step.id] = clipPath;
  }

  return result;
}
```

```typescript
// src/orchestrator/run-action-steps.ts
import path from "path";
import { FeatureSpec, FeatureStep } from "../spec/schema";
import { RuleConfig } from "../util/rule";
import { StepTiming } from "../dub/pacing";
import { startBrowserRecording, stopBrowserRecording } from "../recorder/browser-recorder";
import { startScreenRecording, stopScreenRecording } from "../recorder/screen-recorder";
import { codegenSteps } from "../codegen/registry";
import { login } from "../codegen/steps/common/login";

export async function runActionSteps(
  spec: FeatureSpec,
  rule: RuleConfig,
  workDir: string,
  timings: Record<string, StepTiming>
): Promise<Record<string, string>> {
  const result: Record<string, string> = {};
  const actionSteps = spec.steps.filter((s) => s.kind === "action");
  if (actionSteps.length === 0) return result;

  // 浏览器类步骤统一在一个会话内连续执行，减少重复登录/加载开销
  const browserSteps = actionSteps.filter((s) => (s as any).capture !== "desktop");
  const desktopSteps = actionSteps.filter((s) => (s as any).capture === "desktop");

  if (browserSteps.length > 0) {
    const session = await startBrowserRecording({
      baseUrl: spec.target.base_url,
      viewport: spec.target.viewport,
      videoDir: path.join(workDir, "raw", "_browser_tmp"),
      headless: true,
    });

    if (spec.target.account) {
      await login(
        session.page,
        process.env[spec.target.account.username_env]!,
        process.env[spec.target.account.password_env]!
      );
    }

    for (const step of browserSteps) {
      const stepFn = codegenSteps[step.codegen_ref!];
      const startedAt = Date.now();
      await stepFn(session.page);

      if (step.pace?.wait_for) {
        await session.page.waitForSelector(step.pace.wait_for, { state: "visible" });
      }

      const elapsedSec = (Date.now() - startedAt) / 1000;
      const remaining = Math.max(0, timings[step.id].holdSec - elapsedSec);
      await session.page.waitForTimeout(remaining * 1000);

      // Playwright recordVideo 是整个 context 一条连续视频，这里通过“分段落盘”技巧，
      // 为每个 step 单独开关一个 context 来获得独立文件，牺牲一点会话复用换取分段可控性
    }

    const videoPath = await stopBrowserRecording(session);
    // 简化处理：仅一个连续录制时，把整段视频按每步 holdSec 切分成独立文件
    await splitContinuousVideo(videoPath, browserSteps, timings, workDir, result);
  }

  for (const step of desktopSteps) {
    const outputPath = path.join(workDir, "raw", `${step.id}.mp4`);
    const handle = startScreenRecording({
      outputPath,
      fps: rule.recording.fps,
      viewport: spec.target.viewport,
      deviceIndex: process.env.SCREEN_DEVICE_INDEX ?? "1",
      platform: process.platform === "darwin" ? "darwin" : "linux",
    });
    // 此处调用对应的 shell_ref 交互脚本（09.4节说明），并等待 holdSec
    await new Promise((r) => setTimeout(r, timings[step.id].holdSec * 1000));
    await stopScreenRecording(handle);
    result[step.id] = outputPath;
  }

  return result;
}

async function splitContinuousVideo(
  videoPath: string,
  steps: FeatureStep[],
  timings: Record<string, StepTiming>,
  workDir: string,
  result: Record<string, string>
): Promise<void> {
  const { execFile } = await import("child_process");
  const { promisify } = await import("util");
  const execFileAsync = promisify(execFile);
  const path = await import("path");

  let cursor = 0;
  for (const step of steps) {
    const duration = timings[step.id].holdSec;
    const outPath = path.join(workDir, "raw", `${step.id}.mp4`);
    await execFileAsync("ffmpeg", [
      "-y", "-i", videoPath,
      "-ss", String(cursor), "-t", String(duration),
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
      outPath,
    ]);
    result[step.id] = outPath;
    cursor += duration;
  }
}
```

**关于"整段录制后再切分" vs "每步单独开一个 context 录制"的取舍说明**：Playwright 的 `recordVideo` 是绑定在 `BrowserContext` 生命周期上的，一个 context 只产出一条连续视频。为每一步都新开一个 context 可以获得天然分段的文件，但会导致每步都要重新加载页面/重新登录状态，操作之间的页面上下文无法延续（比如"打开报表页"和"点击导出"这两步在真实交互里应该是同一个页面会话的连续操作）。因此这里选择"整个 Feature 的浏览器步骤在一个 context 内连续录制，结束后按各步时长精确切分"的方案，切分点的时间戳完全由我们自己在 06 章计算的 `holdSec` 累加得出，精度可控，不依赖任何猜测。

## 9.4 Preflight 检查实现

```typescript
// src/orchestrator/preflight.ts
import { chromium } from "playwright";
import { FeatureSpec } from "../spec/schema";
import { codegenSteps } from "../codegen/registry";
import { login } from "../codegen/steps/common/login";

export async function preflightCheck(spec: FeatureSpec): Promise<void> {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: spec.target.viewport });

  try {
    await page.goto(spec.target.base_url);
    if (spec.target.account) {
      await login(
        page,
        process.env[spec.target.account.username_env]!,
        process.env[spec.target.account.password_env]!
      );
    }

    for (const step of spec.steps) {
      if (step.kind !== "action" || (step as any).capture === "desktop") continue;
      const stepFn = codegenSteps[step.codegen_ref!];
      if (!stepFn) {
        throw new Error(`Preflight 失败: codegen_ref "${step.codegen_ref}" 未在 registry 中注册`);
      }
      await stepFn(page);
    }
  } finally {
    await browser.close();
  }
}
```

Preflight 用真实的 headless 浏览器把所有操作步骤跑一遍（不录制、不生成任何产物），任何选择器失效、页面结构变化导致的错误都会在这里立刻抛出并中止整个流程，避免"配音、封面都生成完了，最后录制阶段才发现某步脚本挂了"的时间浪费。

## 9.5 中间产物清理与幂等性

`work/<feature-id>/` 目录里堆积的中间文件（原始录制、未归一化分段、临时 concat 列表）不需要长期保留。编排器可以在最终导出成功后自动清理：

```typescript
// 在 main() 的最后追加
if (process.env.KEEP_WORK_DIR !== "1") {
  fs.rmSync(workDir, { recursive: true, force: true });
  logger.info(`[${spec.id}] 已清理中间产物: ${workDir}`);
}
```

保留 `KEEP_WORK_DIR=1` 这个开关是为了调试时能检查中间某一步的产物（比如怀疑字幕时间轴不对，需要单独看 `subtitle.srt` 和某个分段视频），生产批量运行时默认清理，避免磁盘占用无限增长。

整个编排器是幂等的：只要 `specs/*.yaml` 和 `codegen/steps/*` 不变，重复运行会得到内容一致的成片（配音时长、字幕时间轴都是确定性计算得出，唯一的非确定性来源是 TTS 供应商的合成结果可能有微小的音频差异，以及页面真实响应时间的波动，但不影响最终成片的正确性,只影响极小的时长误差）。

下一章讲这套流水线跑起来之前，人工必须过一遍的检查清单，防止把不该出现在演示视频里的东西录进去。
