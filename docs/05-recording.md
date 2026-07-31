# 05 屏幕与浏览器录制

04 章产出了可重放的操作脚本，本章解决"重放这些操作的同时，如何把画面录成视频文件"。这里有两条技术路线，实践中通常两条都要用到，各自负责不同场景。

## 5.1 两条录制路线的取舍

**路线一：Playwright 内置的 `recordVideo`**。浏览器上下文（BrowserContext）创建时声明录制选项，Playwright 会在浏览器进程内部把渲染帧编码成视频文件，不依赖操作系统级的屏幕采集。

- 优点：不需要处理系统权限（01 章 1.9 节的屏幕录制授权）；分辨率/帧率完全由代码控制，不受实际显示器状态影响；可以 headless 运行（适合放到 CI/云端无人值守批量录制）；天然只包含浏览器视口内容，不会误录到其他窗口/桌面通知。
- 缺点：只能录浏览器视口内容，如果 Feature Spec 里某一步需要展示终端命令行操作（比如产品既有涉及 CLI 演示的功能点），`recordVideo` 无能为力；鼠标指针默认不可见（真实用户鼠标移动不会被渲染进视频），需要额外注入自定义光标。

**路线二：系统级录屏（ffmpeg + 平台原生采集设备）**。直接捕获物理/虚拟显示器的画面。

- 优点：能录任何画面，包括终端、其他应用窗口、多窗口切换过程；鼠标指针是真实系统指针，天然可见。
- 缺点：依赖系统权限；分辨率/清晰度受实际显示器状态影响，多显示器/高 DPI 环境下配置更复杂；headless 服务器上需要虚拟显示器（Xvfb）模拟。

**结论**：默认优先用路线一（`recordVideo`），只有当 Feature Spec 的某个步骤明确需要跨越浏览器边界（展示终端、桌面通知、其他应用）时，才对那一段单独切换到路线二。09 章编排器会根据 Spec 里步骤是否标记 `capture: desktop` 来决定用哪条路线。

## 5.2 路线一实现：Playwright recordVideo

```typescript
// src/recorder/browser-recorder.ts
import { chromium, Browser, BrowserContext, Page } from "playwright";
import path from "path";

export interface BrowserRecordingSession {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  videoDir: string;
}

export async function startBrowserRecording(opts: {
  baseUrl: string;
  viewport: { width: number; height: number };
  videoDir: string;
  headless?: boolean;
}): Promise<BrowserRecordingSession> {
  const browser = await chromium.launch({ headless: opts.headless ?? true });
  const context = await browser.newContext({
    viewport: opts.viewport,
    recordVideo: {
      dir: opts.videoDir,
      size: opts.viewport, // 录制分辨率与视口保持一致，避免缩放模糊
    },
  });

  // 注入一个可见的自定义鼠标指针层，弥补 recordVideo 不渲染真实鼠标指针的缺陷
  await context.addInitScript(() => {
    const cursor = document.createElement("div");
    cursor.id = "__idrp_cursor__";
    Object.assign(cursor.style, {
      position: "fixed",
      zIndex: "2147483647",
      width: "18px",
      height: "18px",
      borderRadius: "50%",
      background: "rgba(255, 90, 0, 0.55)",
      border: "2px solid rgba(255,255,255,0.9)",
      pointerEvents: "none",
      transform: "translate(-50%, -50%)",
      transition: "left 0.08s linear, top 0.08s linear",
      left: "0px",
      top: "0px",
    });
    document.addEventListener("DOMContentLoaded", () => {
      document.body.appendChild(cursor);
      document.addEventListener("mousemove", (e) => {
        cursor.style.left = e.clientX + "px";
        cursor.style.top = e.clientY + "px";
      });
    });
  });

  const page = await context.newPage();
  await page.goto(opts.baseUrl);

  return { browser, context, page, videoDir: opts.videoDir };
}

export async function stopBrowserRecording(session: BrowserRecordingSession): Promise<string> {
  const videoPath = await session.page.video()?.path();
  await session.context.close();
  await session.browser.close();
  if (!videoPath) throw new Error("录制未生成视频文件，检查 recordVideo 配置");
  return videoPath; // 返回生成的 .webm 文件路径
}
```

关键点说明：

- `recordVideo.size` 显式指定和 `viewport` 一致，否则 Playwright 会按默认逻辑缩放，可能导致清晰度下降。
- 自定义鼠标指针通过 `addInitScript` 在每个页面加载前注入，用 CSS `transition` 做平滑跟随，视觉上比"瞬移"更接近真实录屏效果，这是弥补 headless 无法看到真实光标的常见技巧。
- 真实的 Playwright 鼠标移动 API 是 `page.mouse.move(x, y)`，如果 04 章清洗后的脚本里用的是 `locator.click()` 这种高层 API，Playwright 内部会自动移动虚拟鼠标到目标元素再点击，`mousemove` 事件依然会正常触发，因此上面注入的指针跟随逻辑对通过 `.click()` 触发的操作同样生效。

产出的 `.webm` 文件在 08 章会被 ffmpeg 转码/拼接，此处不需要关心格式转换。

## 5.3 路线二实现：系统级录屏

**macOS（avfoundation）**：

```bash
# 先列出可用的采集设备（屏幕/摄像头/麦克风），确认屏幕设备的索引号
ffmpeg -f avfoundation -list_devices true -i ""

# 假设屏幕是索引 1，不采集麦克风音频（配音在06章单独生成，录屏本身不需要真实拾音）
ffmpeg -f avfoundation -capture_cursor 1 -capture_mouse_clicks 1 \
  -framerate 30 -i "1:none" \
  -vcodec libx264 -pix_fmt yuv420p -preset veryfast -crf 18 \
  work/feature-07-export-report/raw/terminal-segment.mp4
```

- `-capture_cursor 1` 显式让 ffmpeg 把系统鼠标指针渲染进画面，这是路线二相对路线一的天然优势。
- `-capture_mouse_clicks 1` 会在点击处画一个短暂高亮圈，进一步提升观众可读性（对应 00 章里"意图驱动"的可理解性目标）。
- 用 `Ctrl+C` 结束录制，实践中编排器会用 Node.js 的 `child_process.spawn` 启动这个 ffmpeg 进程，并在步骤结束时发送 `SIGINT` 优雅终止（直接 `kill -9` 会导致 mp4 文件尾部损坏无法播放）。

**Linux（x11grab，含 Xvfb 虚拟显示器，用于无头服务器批量录制）**：

```bash
# 启动一个虚拟显示器，编号 :99，分辨率与 Feature Spec 的 viewport 一致
Xvfb :99 -screen 0 1440x900x24 &
export DISPLAY=:99

# 在这个虚拟显示器上跑浏览器/终端操作（此时路线一的 headless:false 也可以在这个虚拟显示器里运行）
ffmpeg -f x11grab -video_size 1440x900 -framerate 30 -i :99.0 \
  -vcodec libx264 -pix_fmt yuv420p -preset veryfast -crf 18 \
  work/feature-07-export-report/raw/terminal-segment.mp4
```

- Xvfb 环境下真实鼠标指针默认不显示，需要额外用 `unclutter -root &` 保证指针不因静止而被系统隐藏，或者用合成的方式（比如驱动一个真实的 `xdotool mousemove` 来源）保证光标可见——这是 Linux 路线二相比 macOS 更繁琐的地方，如果条件允许优先在 macOS 上完成正式录制，Linux/Xvfb 方案留给 CI 里做"冒烟级"验证性质的录制（确认流程能跑通，不追求画面质感）。

**Node.js 中对 ffmpeg 屏幕采集进程的封装**：

```typescript
// src/recorder/screen-recorder.ts
import { spawn, ChildProcessWithoutNullStreams } from "child_process";
import path from "path";

export interface ScreenRecordingHandle {
  proc: ChildProcessWithoutNullStreams;
  outputPath: string;
}

export function startScreenRecording(opts: {
  outputPath: string;
  fps: number;
  viewport: { width: number; height: number };
  deviceIndex: string; // macOS: avfoundation 设备索引; Linux: 传 ":99.0"
  platform: "darwin" | "linux";
}): ScreenRecordingHandle {
  const args =
    opts.platform === "darwin"
      ? [
          "-f", "avfoundation", "-capture_cursor", "1", "-capture_mouse_clicks", "1",
          "-framerate", String(opts.fps), "-i", `${opts.deviceIndex}:none`,
          "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
          opts.outputPath,
        ]
      : [
          "-f", "x11grab",
          "-video_size", `${opts.viewport.width}x${opts.viewport.height}`,
          "-framerate", String(opts.fps), "-i", opts.deviceIndex,
          "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
          opts.outputPath,
        ];

  const proc = spawn("ffmpeg", args);
  return { proc, outputPath: opts.outputPath };
}

export async function stopScreenRecording(handle: ScreenRecordingHandle): Promise<string> {
  return new Promise((resolve, reject) => {
    handle.proc.once("exit", (code) => {
      // ffmpeg 收到 SIGINT 后正常收尾退出码通常是 255，属于预期行为，不视为失败
      resolve(handle.outputPath);
    });
    handle.proc.stdin.write("q"); // 向 ffmpeg 发送 'q' 触发优雅停止，比 SIGINT 更可靠地写完文件尾
  });
}
```

用 `stdin` 写入 `"q"` 是 ffmpeg 官方推荐的优雅停止方式（等价于交互式运行时按 q 键），比直接 kill 进程更能保证输出文件的完整性。

## 5.4 混合场景：一个 Feature 内部路线一/路线二切换

回到 03 章 Feature Spec 的 `action` 步骤，扩展一个可选字段来声明该步骤走哪条路线：

```yaml
  - id: run-cli-export
    kind: action
    narration: "也可以通过命令行工具直接触发导出。"
    codegen_ref: null          # 该步骤不是浏览器操作，不需要 codegen 脚本
    capture: desktop           # 显式声明走路线二（系统级录屏）
    shell_ref: cli-export      # 对应一段预先写好的 shell 交互脚本，见09章终端录制说明
    pace:
      min_hold_sec: 3
```

编排器（09 章）读取到 `capture: desktop` 时，会在该步骤开始前调用 `startScreenRecording`，步骤结束后 `stopScreenRecording`，产出的分段视频和其他浏览器录制的分段视频用同样的命名规则放进 `work/<feature-id>/raw/` 目录，08 章的合成阶段对它们一视同仁地做拼接，不需要关心每一段究竟是哪条路线产出的。

## 5.5 终端录制的特殊处理

如果某个功能点确实需要展示命令行操作过程（比如用户既有实践中"先 cd 到项目目录再执行别名命令"这种习惯的通用道理是：**提前准备好终端环境和别名，录制时只敲简短命令，不要在镜头前现场调试**），实践建议：

1. 提前打开一个专用的终端窗口/标签页，设置好合适的字号（录制分辨率下要保证文字清晰可读，参考 01 章 1.6 节确认的分辨率）、配色主题（浅色/深色需要和整体视频风格统一，见 07 章品牌规范）。
2. 提前把要用到的长命令封装成简短的 shell 别名或脚本，录制时只敲短命令，避免因为打字速度不均匀导致画面节奏被打乱。
3. 录制这一段的窗口只保留这一个终端窗口置顶,并且提前清空历史 scrollback，避免露出之前调试时的敏感信息或者杂乱输出（这一条会在 10 章的检查清单里再次出现，是防泄露的重点场景之一）。
4. 录制完成后，若这个终端窗口是专门为录制新建的，编排器/操作者应该在该步骤结束后关闭它，不要让它常驻，避免历史命令、环境变量残留带来后续误用或信息暴露的风险。

## 5.6 分段产物命名约定

不论走哪条路线，本章的输出统一约定为：

```
work/<feature-id>/raw/<step-id>.mp4   # 或 .webm（路线一产出，08章合成前会统一转码）
```

`<step-id>` 直接取自 03 章 Spec 里每个 `steps[].id` 字段。`cover`/`outro` 这类 `kind: cover` 的步骤不经过本章流程，它们的"画面"是 07 章直接生成的静态图，本章只负责 `kind: action` 步骤的动态画面录制。

下一章讲配音层：如何为每个步骤生成配音音频，并用音频时长反向驱动本章录制/等待的节奏。
