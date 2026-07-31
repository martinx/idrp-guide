# 07 封面与素材生成

本章生成 Feature Spec 里 `kind: cover` 步骤（片头/片尾）所需的静态画面，以及贯穿全片的视觉规范（品牌色、字体、排版）。核心思路是：**用写 HTML/CSS 的方式设计封面模板，再用 Playwright 截图，而不是用 ImageMagick/Canvas 手写绘图代码**——前端团队写 HTML/CSS 的能力远高于手写像素绘图代码，复用这个能力成本最低、效果最可控。

## 7.1 为什么选 HTML 截图而不是 Canvas/ImageMagick

- **可维护性**：封面模板本质是一个静态网页，改样式就是改 CSS，任何会前端的人都能维护，不需要理解绘图 API 的坐标系统。
- **表现力**：渐变、阴影、Flex/Grid 布局、Web 字体、SVG 图标，这些 HTML/CSS 原生支持的能力，用 ImageMagick 命令行参数表达起来极其繁琐。
- **一致性**：如果产品本身有 Design Token（品牌色变量、间距规范），可以直接在封面模板里复用同一份 CSS 变量，保证封面视觉和产品实际界面风格统一。

## 7.2 全局视觉规范

在 `config/rule.yaml` 里集中定义品牌视觉规范，所有封面模板和字幕样式都引用这份配置，不在各处散落硬编码的颜色值：

```yaml
# config/rule.yaml
brand:
  primary_color: "#1A56DB"       # 主品牌色
  accent_color: "#FF7A00"        # 强调色（如"点击"高亮）
  bg_color: "#0B1220"            # 封面深色背景
  text_color: "#FFFFFF"
  font_family_cn: "PingFang SC"  # 对应01章确认的中文字体
  font_file_path: "/System/Library/Fonts/PingFang.ttc"  # ffmpeg drawtext/subtitles 使用的绝对路径

recording:
  viewport: { width: 1440, height: 900 }
  output_resolution: "1920x1080"
  fps: 30

narration:
  default_voice: "zh-CN-XiaoxiaoNeural"
  default_speed: 1.0
  wpm_estimate: 280              # 用于文案撰写阶段估算时长的经验值，见06章5.4节
```

```typescript
// src/util/rule.ts
import fs from "fs";
import yaml from "js-yaml";

export interface RuleConfig {
  brand: {
    primary_color: string;
    accent_color: string;
    bg_color: string;
    text_color: string;
    font_family_cn: string;
    font_file_path: string;
  };
  recording: {
    viewport: { width: number; height: number };
    output_resolution: string;
    fps: number;
  };
  narration: {
    default_voice: string;
    default_speed: number;
    wpm_estimate: number;
  };
}

export function loadRule(): RuleConfig {
  return yaml.load(fs.readFileSync("config/rule.yaml", "utf-8")) as RuleConfig;
}
```

## 7.3 封面 HTML 模板

```html
<!-- src/cover/template.html -->
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1920px;
    height: 1080px;
    background: linear-gradient(135deg, var(--bg-color) 0%, #050a14 100%);
    font-family: var(--font-family), sans-serif;
    color: var(--text-color);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 0 160px;
    position: relative;
    overflow: hidden;
  }
  .badge {
    display: inline-block;
    padding: 10px 28px;
    border-radius: 999px;
    background: var(--primary-color);
    font-size: 28px;
    letter-spacing: 2px;
    margin-bottom: 40px;
  }
  .title {
    font-size: 88px;
    font-weight: 700;
    line-height: 1.3;
    max-width: 1400px;
  }
  .accent-bar {
    width: 120px;
    height: 10px;
    background: var(--accent-color);
    margin-top: 48px;
    border-radius: 6px;
  }
  .glow {
    position: absolute;
    right: -200px;
    top: -200px;
    width: 800px;
    height: 800px;
    border-radius: 50%;
    background: radial-gradient(circle, var(--primary-color) 0%, transparent 70%);
    opacity: 0.25;
  }
</style>
</head>
<body>
  <div class="glow"></div>
  <div class="badge" id="badge">功能演示</div>
  <div class="title" id="title">报表导出功能</div>
  <div class="accent-bar"></div>
</body>
</html>
```

模板里的 CSS 变量（`--primary-color` 等）和 `#title`/`#badge` 的文本内容都通过截图脚本动态注入，模板文件本身不写死任何具体功能点的信息，保证一份模板服务所有 Feature Spec。

## 7.4 截图生成脚本

```typescript
// src/cover/render-cover.ts
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { RuleConfig } from "../util/rule";

export async function renderCover(opts: {
  title: string;
  badgeText: string;
  rule: RuleConfig;
  outputPath: string;
}): Promise<string> {
  const templatePath = path.resolve(__dirname, "template.html");
  let html = fs.readFileSync(templatePath, "utf-8");

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  await page.goto(`file://${templatePath}`);

  // 注入 CSS 变量与文案内容，而不是用字符串拼接生成 HTML，避免特殊字符转义问题
  await page.addStyleTag({
    content: `
      :root {
        --primary-color: ${opts.rule.brand.primary_color};
        --accent-color: ${opts.rule.brand.accent_color};
        --bg-color: ${opts.rule.brand.bg_color};
        --text-color: ${opts.rule.brand.text_color};
        --font-family: "${opts.rule.brand.font_family_cn}";
      }
    `,
  });
  await page.evaluate(
    ({ title, badgeText }) => {
      document.getElementById("title")!.textContent = title;
      document.getElementById("badge")!.textContent = badgeText;
    },
    { title: opts.title, badgeText: opts.badgeText }
  );

  await page.screenshot({ path: opts.outputPath });
  await browser.close();
  return opts.outputPath;
}
```

这里用 `page.evaluate` 设置 `textContent` 而不是拼接字符串生成整个 HTML 文档，是为了让功能标题里如果出现 `<`、`&` 等字符时不会破坏 HTML 结构或引发 XSS 类问题——虽然这是本地生成工具、不存在真正的安全边界，但养成"内容和结构分离"的习惯能避免很多低级的转义 bug。

## 7.5 封面转视频片段

07 章产出的是静态 PNG，08 章的合成阶段需要把它转成一段"持续 N 秒的视频片段"，才能和其他动态录制片段拼接。转换用 ffmpeg 的 `-loop` 参数：

```typescript
// src/cover/cover-to-clip.ts
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function coverImageToClip(opts: {
  imagePath: string;
  durationSec: number;
  fps: number;
  outputPath: string;
}): Promise<string> {
  await execFileAsync("ffmpeg", [
    "-y",
    "-loop", "1",
    "-i", opts.imagePath,
    "-t", String(opts.durationSec),
    "-r", String(opts.fps),
    "-vf", "scale=1920:1080,format=yuv420p",
    "-vcodec", "libx264",
    "-preset", "veryfast",
    "-crf", "18",
    opts.outputPath,
  ]);
  return opts.outputPath;
}
```

`durationSec` 直接来自 06 章为 `cover`/`outro` 步骤生成的配音时长（`kind: cover` 步骤同样要过一遍 06 章的配音流程，只是它的"操作"环节是空的，只有配音+静态画面）。

## 7.6 批量生成与素材复用

如果同一个产品线的多个 Feature Spec 共享同一套品牌规范（几乎总是如此），封面模板和 `render-cover.ts` 完全复用，唯一变化的输入只是 `title` 文本。可以写一个批量脚本，遍历 `specs/` 目录下所有 Spec，为每个 Spec 预生成封面图，作为 CI 里的一个独立、可缓存的步骤（封面生成不依赖任何浏览器操作录制，是全流程里最快、最适合提前批量跑的一环）：

```typescript
// src/cover/batch-render.ts
import fs from "fs";
import path from "path";
import { loadFeatureSpec } from "../spec/loader";
import { loadRule } from "../util/rule";
import { renderCover } from "./render-cover";

async function main() {
  const rule = loadRule();
  const specFiles = fs.readdirSync("specs").filter((f) => f.endsWith(".yaml"));

  for (const file of specFiles) {
    const spec = loadFeatureSpec(path.join("specs", file));
    const outDir = path.join("work", spec.id);
    fs.mkdirSync(outDir, { recursive: true });
    await renderCover({
      title: spec.title,
      badgeText: "功能演示",
      rule,
      outputPath: path.join(outDir, "cover.png"),
    });
    console.log(`✅ ${spec.id} 封面已生成`);
  }
}

main();
```

下一章把本章的封面片段、05 章的操作录制片段、06 章的配音音频，全部按时间轴合成为最终成片。
