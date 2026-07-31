# 03 意图驱动的 Feature Spec 设计

这是全书的核心抽象。人在整套流水线里唯一需要认真编写的产物就是 Feature Spec——一份描述"这个功能点是什么、有哪些步骤、每一步说什么"的 YAML 文件。理解并设计好这份数据结构，后面所有自动化才有依据。

## 3.1 设计目标

一个好的 Feature Spec 需要同时满足：

1. **对人友好**：产品经理/工程师不用学任何 DSL，几分钟就能写出一份初稿。
2. **对机器精确**：每个字段都要能被 codegen 层、dub 层、mix 层无歧义地消费。
3. **允许"意图"和"细节"分层**：顶层是一句话意图和粗粒度步骤（人写），细节（具体 DOM 选择器、操作序列）由 codegen 录制自动填充（机器写），两者合并成最终可执行的 Spec。

## 3.2 完整字段设计

```yaml
# specs/feature-07-export-report.yaml
id: feature-07-export-report          # 全局唯一，用作产物目录名/文件名前缀
title: "报表导出功能"                  # 展示用标题，会出现在封面上
intent: >
  用户在报表页面可以将当前筛选条件下的数据一键导出为 Excel，
  导出过程有进度提示，导出完成后可直接下载文件。

target:
  base_url: "https://staging.example.com"   # 录制时打开的起始地址
  viewport: { width: 1440, height: 900 }     # 统一分辨率，保证成片画面一致
  account:
    # 演示专用账号，绝不使用真实客户/生产账号，详见 10 章
    username_env: DEMO_USERNAME
    password_env: DEMO_PASSWORD

narration:
  voice: zh-CN-XiaoxiaoNeural          # 对应 06 章 TTS 发音人配置
  speed: 1.0                           # 语速倍率
  tone: "专业、简洁、面向企业客户"        # 供人工/LLM 撰写文案时参考的语气基调

steps:
  - id: intro
    kind: cover                        # 特殊步骤：不对应任何浏览器操作，只生成封面片头
    narration: "接下来，我们来看一下报表导出功能。"
    duration_hint_sec: 3               # 封面片头的期望时长（会被配音时长覆盖，见06章）

  - id: open-report-page
    kind: action                       # 对应一次 codegen 录制到的操作序列片段
    narration: "首先进入报表页面，选择需要的时间范围和数据维度。"
    codegen_ref: "open-report-page"    # 对应 04 章录制脚本里的一个具名片段
    pace:
      min_hold_sec: 2                  # 该步骤操作完成后至少停留 2 秒，参见用户既有的"详情页停留"规范

  - id: click-export
    kind: action
    narration: "点击右上角的导出按钮，系统会弹出导出格式选择。"
    codegen_ref: "click-export-button"
    pace:
      min_hold_sec: 2

  - id: choose-excel-and-confirm
    kind: action
    narration: "选择 Excel 格式并确认，页面会显示导出进度。"
    codegen_ref: "choose-excel-confirm"
    pace:
      min_hold_sec: 3
      wait_for: "text=导出完成"        # 显式等待条件，防止异步进度提前截断

  - id: outro
    kind: cover
    narration: "报表导出功能介绍完毕，感谢观看。"
    duration_hint_sec: 2

output:
  resolution: "1920x1080"              # 成片最终分辨率（可与录制分辨率不同，08章会做缩放）
  fps: 30
  subtitle: burned_in                  # burned_in | soft | none，见08章
  background_music: none               # none | assets/music/xxx.mp3
```

## 3.3 字段设计背后的取舍

**为什么 `steps` 里区分 `kind: cover` 和 `kind: action`？**
封面片头/片尾不涉及浏览器操作，只是"一张图 + 一段配音"，如果和真实操作步骤用同一套字段会引入大量可选字段和分支判断。拆成两种 `kind`，09 章的编排器可以用简单的 `switch` 分流处理，代码更清晰。

**为什么每个 `action` 步骤要有 `codegen_ref` 而不是直接在 Spec 里写选择器/操作？**
如果把 `page.click('#export-btn')` 这种底层操作写进 YAML，Feature Spec 就退化成了另一种自动化脚本语言，产品经理写不了，也失去了"描述意图"的初衷。正确的分工是：**Spec 只声明"这一步要做什么、说什么"，具体怎么做（选择器、点击顺序）交给 codegen 录制产出的脚本，两者通过 `codegen_ref` 这个 ID 关联**。这也是 04 章的核心内容。

**为什么 `pace.min_hold_sec` 和 `wait_for` 分开设计？**
`min_hold_sec` 解决"人眼来得及看清楚"的问题（配合 06 章配音时长，取两者较大值）；`wait_for` 解决"异步操作是否真的完成"的问题（比如导出进度条），二者语义不同，混在一个字段里会导致要么等太久要么截断太早。

**为什么每步都要有 `narration`，即使某步很短？**
这是"音频先行"策略（00 章 0.4 节）的直接体现——没有解说文案，就没有音频时长，也就没有依据决定这一步该录多久。哪怕某一步解说词只有一句"确认后点击提交"，也要显式写出来，不能省略。

## 3.4 从"一句话意图"到完整 Spec 的工作方法

实践中不建议让人从零手写上面这份完整 YAML，推荐两步法：

**第一步：人写"骨架"**（只有 `id`/`title`/`intent`/步骤的中文一句话列表，不含任何技术字段）：

```yaml
id: feature-07-export-report
title: 报表导出功能
intent: 用户在报表页面一键导出 Excel，带进度提示。
steps_outline:
  - 进入报表页面，选时间范围和维度
  - 点击导出按钮，弹出格式选择
  - 选 Excel 确认，显示进度直到完成
```

**第二步：用 LLM 辅助扩写为完整 Spec**。把"骨架" + 03.2 节的完整字段模板一起喂给 LLM（例如直接在编辑器里用 Claude Code/Cursor 这类工具），提示词类似：

> "根据下面的功能骨架，参考这份 Feature Spec 模板的字段结构，生成完整的 YAML，narration 文案要专业简洁，每个 action 步骤给一个英文 kebab-case 的 codegen_ref。"

这一步把"从大白话到结构化配置"的体力活交给 LLM，人工只需要审阅、微调解说词的措辞和语气，是本教程"最小化人工描述"设计哲学的具体落地方式。

## 3.5 Schema 校验：TypeScript 类型定义

把上面的 YAML 结构映射成 TypeScript 类型，并在加载时做运行时校验，可以在录制前就发现 Spec 里的低级错误（比如漏写 `codegen_ref`），而不是录了一半才报错。

```typescript
// src/spec/schema.ts
export interface Viewport {
  width: number;
  height: number;
}

export interface TargetAccount {
  username_env: string;
  password_env: string;
}

export interface FeatureTarget {
  base_url: string;
  viewport: Viewport;
  account?: TargetAccount;
}

export interface NarrationConfig {
  voice: string;
  speed: number;
  tone?: string;
}

export interface StepPace {
  min_hold_sec?: number;
  wait_for?: string;
}

export type StepKind = "cover" | "action";

export interface FeatureStep {
  id: string;
  kind: StepKind;
  narration: string;
  codegen_ref?: string;       // kind === "action" 时必填
  duration_hint_sec?: number; // kind === "cover" 时使用
  pace?: StepPace;
}

export type SubtitleMode = "burned_in" | "soft" | "none";

export interface FeatureOutput {
  resolution: string;
  fps: number;
  subtitle: SubtitleMode;
  background_music: string; // "none" 或相对路径
}

export interface FeatureSpec {
  id: string;
  title: string;
  intent: string;
  target: FeatureTarget;
  narration: NarrationConfig;
  steps: FeatureStep[];
  output: FeatureOutput;
}
```

```typescript
// src/spec/loader.ts
import fs from "fs";
import yaml from "js-yaml";
import { FeatureSpec, FeatureStep } from "./schema";

export class FeatureSpecError extends Error {}

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new FeatureSpecError(msg);
}

export function loadFeatureSpec(filePath: string): FeatureSpec {
  const raw = fs.readFileSync(filePath, "utf-8");
  const doc = yaml.load(raw) as FeatureSpec;

  assert(doc.id && /^[a-z0-9-]+$/.test(doc.id), `id 必须为小写字母数字短横线: ${filePath}`);
  assert(doc.title, `title 不能为空: ${doc.id}`);
  assert(doc.intent, `intent 不能为空: ${doc.id}`);
  assert(doc.target?.base_url, `target.base_url 不能为空: ${doc.id}`);
  assert(Array.isArray(doc.steps) && doc.steps.length > 0, `steps 不能为空: ${doc.id}`);

  doc.steps.forEach((step: FeatureStep, idx: number) => {
    assert(step.id, `steps[${idx}].id 不能为空`);
    assert(step.narration, `steps[${idx}].narration 不能为空 (id=${step.id})`);
    if (step.kind === "action") {
      assert(step.codegen_ref, `action 步骤必须有 codegen_ref (id=${step.id})`);
    }
  });

  assert(
    ["burned_in", "soft", "none"].includes(doc.output?.subtitle),
    `output.subtitle 取值非法: ${doc.id}`
  );

  return doc;
}
```

这个 loader 在 09 章的编排器里是第一个被调用的函数——任何 Spec 层面的错误都在录制真正开始之前就被拦截，避免"录了 10 分钟发现某一步配置错了"的浪费。

下一章开始讲如何把 `codegen_ref` 对应的"人工操作一遍"转成可重放的自动化脚本。
