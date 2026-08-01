# 19 用 AI 做自动化质检与防泄露检测

10 章给出了一份详尽的人工检查清单，本章要做的事情是：**把这份清单变成一个可以自动执行的 AI 审核步骤，插入编排器流程的末尾，让人工审片从"看完整条视频"压缩成"看 AI 标出来的几个风险点"**。这是本书要分享的所有 AI 应用里，安全把关意义最重要的一环。

## 19.1 设计目标与边界

在动手之前先讲清楚这一章不是要做什么：**这不是要用 AI 取代 10 章的人工签字环节**。16.3 节和 10.7 节都强调过，最终发布责任必须由人承担。这一章要做的是把"发现风险点"这个体力活自动化，把"确认风险点、决定是否发布"这个判断权留给人。二者的关系类似代码审查工具（lint/静态扫描）和人工 code review 的关系——工具负责不知疲倦地扫一遍，人负责对工具标出来的东西做最终判断。

## 19.2 整体流程

```
成片(output/<feature-id>.mp4)
        │
        ▼
┌───────────────────────┐
│ 1. 按固定间隔抽帧        │  ffmpeg -vf fps=1
│    (或按步骤边界抽帧)     │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ 2. 把字幕文件全文一起      │  10章清单原文作为系统提示
│    交给多模态模型批量审查  │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ 3. 模型输出结构化 JSON    │  每条风险: 帧号/时间点/描述/严重度
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ 4. 生成人类可读的审片报告  │  Markdown/HTML，附带风险帧截图
└──────────┬────────────┘
           ▼
      人工看报告，逐条确认
           │
     ┌─────┴─────┐
   全部通过      有需要处理的风险
     │              │
     ▼              ▼
   正式发布      回到对应章节修复后重新走一遍流程
```

## 19.3 抽帧实现

```typescript
// src/qa/extract-frames.ts
import { execFile } from "child_process";
import { promisify } from "util";
import path from "path";

const execFileAsync = promisify(execFile);

export async function extractFrames(opts: {
  videoPath: string;
  outputDir: string;
  fps?: number; // 默认每秒1帧，画面变化密集的片段可以调高
}): Promise<string[]> {
  const fps = opts.fps ?? 1;
  const pattern = path.join(opts.outputDir, "frame-%04d.jpg");

  await execFileAsync("ffmpeg", [
    "-y",
    "-i", opts.videoPath,
    "-vf", `fps=${fps}`,
    "-q:v", "3", // JPEG 质量，数值越小质量越高，3 已经足够识别文字细节
    pattern,
  ]);

  const fs = await import("fs");
  return fs
    .readdirSync(opts.outputDir)
    .filter((f) => f.startsWith("frame-"))
    .sort()
    .map((f) => path.join(opts.outputDir, f));
}
```

按固定间隔抽帧对大多数场景够用；如果想更精准地覆盖"页面切换的瞬间"这类 10.6 节场景二提到的高风险时刻（下拉菜单展开、页面跳转过渡），可以额外在每个 Feature Spec 步骤的边界前后各多抽 1～2 帧，实现上只需要结合 09 章编排器已经计算好的每步 `holdSec` 累加时间戳，对这些时间点单独跑一次 `-ss <时间点> -frames:v 1` 的单帧截取。

## 19.4 批量送审：把 10 章清单变成系统提示

```typescript
// src/qa/leak-scan.ts
import fs from "fs";
import path from "path";
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const CHECKLIST_PROMPT = `
你是一个视频发布前的安全审查员，请对下面这批视频截图逐张检查，参照以下清单：

1. 画面中是否出现真实客户名称、真实业务数据（而非演示/脱敏数据）
2. 系统菜单栏/任务栏是否出现个人化组件（股票、日历、剩余通知等，参考具体场景：
   菜单栏常驻组件全程可见）
3. 浏览器书签栏、标签页标题是否暴露与本次演示无关的内部信息
4. 终端窗口（如果画面中出现）是否残留历史命令、真实主机名、内网路径
5. 页面报错提示/Toast 是否泄露服务器内部路径、堆栈信息、框架版本
6. 页面上是否有一闪而过的、非本次演示主体但包含敏感信息的模块
   （如"最近登录设备"、真实用户列表等）

对每一张截图，如果发现任何一条命中，请按以下 JSON 格式输出一条记录；
如果没有发现问题，不需要为这张截图输出任何内容。

输出格式（JSON 数组，只输出 JSON，不要有其他文字）：
[
  {
    "frame": "frame-0012.jpg",
    "rule": "命中的清单条目编号",
    "description": "具体描述看到了什么",
    "severity": "high | medium | low"
  }
]
`;

export async function scanFramesForLeaks(framePaths: string[]): Promise<any[]> {
  const imageBlocks = framePaths.map((p) => ({
    type: "image" as const,
    source: {
      type: "base64" as const,
      media_type: "image/jpeg" as const,
      data: fs.readFileSync(p).toString("base64"),
    },
  }));

  const response = await client.messages.create({
    model: "claude-sonnet-5",
    max_tokens: 4096,
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: CHECKLIST_PROMPT },
          ...imageBlocks.map((img, i) => ({
            ...img,
            // 在图片前插入文件名标记，方便模型在输出里正确引用 frame 字段
          })),
        ],
      },
    ],
  });

  const text = response.content
    .filter((b: any) => b.type === "text")
    .map((b: any) => b.text)
    .join("");

  try {
    return JSON.parse(text);
  } catch {
    return [{ frame: "unknown", rule: "解析失败", description: text, severity: "medium" }];
  }
}
```

实践中一次请求塞入的截图数量要考虑模型的单次输入体积限制和成本，一个 3～5 分钟的功能演示视频按每秒1帧抽帧可能有几百张，建议分批（比如每批 20～30 张）调用，并在批次之间保留帧文件名的连续编号，方便最后把所有批次的结果合并成一份完整报告。

## 19.5 文本层面的检查：字幕全文送审

除了画面，08 章生成的 SRT 字幕文件本身也需要过一遍文本层面的检查（这对应 10.2 节"文案审阅"这一条，同样可以交给 AI 打前站）：

```typescript
// src/qa/scan-subtitle-text.ts
export async function scanSubtitleText(srtContent: string): Promise<any[]> {
  const prompt = `
请检查以下字幕全文，找出：
1. 任何真实客户名称、公司名称、内部代号
2. 语气/措辞不符合对外发布标准的表达（内部黑话、未完成功能的"剧透"）
3. 与画面描述明显不符的表述（如果你能从上下文判断）

字幕内容：
${srtContent}

按 JSON 数组格式输出问题列表，字段包括 line（对应字幕序号）、issue（问题描述）、
severity。没有问题则输出空数组。`;

  // 调用方式与19.4节相同，此处省略重复代码
  return [];
}
```

## 19.6 生成人类可读的审片报告

把画面风险和文本风险的检查结果合并，生成一份带截图缩略图的 Markdown 报告，方便人工快速浏览：

```typescript
// src/qa/generate-report.ts
import fs from "fs";
import path from "path";

export function generateQaReport(opts: {
  featureId: string;
  frameFindings: any[];
  textFindings: any[];
  frameDir: string;
  outputPath: string;
}): void {
  const lines: string[] = [`# ${opts.featureId} 审片报告`, ""];

  if (opts.frameFindings.length === 0 && opts.textFindings.length === 0) {
    lines.push("✅ AI 自动检查未发现风险点，仍需人工完整审阅一次后再发布。");
  } else {
    lines.push(`⚠️ 发现 ${opts.frameFindings.length + opts.textFindings.length} 个待人工确认的风险点：\n`);

    for (const f of opts.frameFindings) {
      lines.push(`## 画面风险：${f.frame}（严重度：${f.severity}）`);
      lines.push(`- 命中规则：${f.rule}`);
      lines.push(`- 描述：${f.description}`);
      lines.push(`- 截图：![${f.frame}](${path.join(opts.frameDir, f.frame)})`);
      lines.push("");
    }

    for (const t of opts.textFindings) {
      lines.push(`## 文本风险：字幕第 ${t.line} 条（严重度：${t.severity}）`);
      lines.push(`- 描述：${t.issue}`);
      lines.push("");
    }
  }

  fs.writeFileSync(opts.outputPath, lines.join("\n"), "utf-8");
}
```

## 19.7 接入编排器

在 09 章 `run-feature.ts` 的 `finalExport` 之后追加这个质检环节，作为交付前的最后一步自动化：

```typescript
// 追加在 09 章 main() 的 finalExport 之后
const frameDir = path.join(workDir, "qa-frames");
fs.mkdirSync(frameDir, { recursive: true });
const frames = await extractFrames({ videoPath: finalPath, outputDir: frameDir });
const frameFindings = await scanFramesForLeaks(frames);
const textFindings = await scanSubtitleText(fs.readFileSync(path.join(workDir, "subtitle.srt"), "utf-8"));

generateQaReport({
  featureId: spec.id,
  frameFindings,
  textFindings,
  frameDir,
  outputPath: path.join("output", `${spec.id}.qa-report.md`),
});

logger.info(`[${spec.id}] 审片报告已生成，请人工确认后再发布`);
```

这样每次运行编排器，`output/` 目录下除了成片本身，还会多一份同名的 `.qa-report.md`，人工审片时直接打开这份报告，如果报告是"未发现风险点"，仍然按 10 章的建议做一次完整人工审阅（AI 检查不能替代首次发布的完整人工审阅，参考 19.1 节的边界说明）；如果报告标出了具体风险点，人工只需要针对性地跳转到视频对应时间点确认，而不是从头看到尾。

## 19.8 关于误报与漏报

多模态模型的检查结果不会是完美的，需要接受两类错误同时存在：

**误报（把正常内容标记为风险）**：比如把演示账号里明显是脱敏占位数据的用户名误判为"真实客户信息"。这类误报的代价是人工多花几秒钟确认一下，成本很低，不需要特别优化。

**漏报（没发现真实存在的风险）**：这是需要认真对待的一类错误。缓解手段包括：定期把已知的历史真实泄露案例（10.6 节列出的四个典型场景）整理成测试用例，人为在测试视频里制造这些场景，验证当前的检查 prompt 是否能可靠识别出来，并根据结果持续迭代 19.4 节的清单 prompt 描述精度。这本质上是把"防泄露检查"当作一个需要持续验证、持续迭代的质量系统来对待，而不是写一次 prompt 就一劳永逸。

## 19.9 小结

本章展示了如何把 10 章的人工检查清单转换成一个自动化的 AI 审核步骤：抽帧 + 多模态模型批量审查 + 文本层面审查 + 生成结构化报告，接入编排器成为发布前的标准环节。这是全书对"AI 到底能替代人类做多少事"这个问题给出的最终答案：**AI 可以把发现风险的体力活全部接管，但确认风险、承担发布责任的判断权，仍然、也应该、留在人类手里**。下一章用一个完整案例，把 16～19 章讲的 AI 协同方式全部串起来，和 12 章的传统流程版本做直接对比。
