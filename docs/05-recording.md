# 05 屏幕与浏览器录制

04 章产出了可重放的操作脚本，本章解决"重放这些操作的同时，如何把画面录成视频文件"。这里有两条技术路线，实践中通常两条都要用到，各自负责不同场景。

## 5.1 两条录制路线的取舍

**路线一：Playwright 内置的 `recordVideo`**。浏览器上下文（BrowserContext）创建时声明录制选项，Playwright 会在浏览器进程内部把渲染帧编码成视频文件，不依赖操作系统级的屏幕采集。

- 优点：不需要处理系统权限（01 章 1.9 节的屏幕录制授权）；分辨率/帧率完全由代码控制，不受实际显示器状态影响；可以 headless 运行（适合放到 CI/云端无人值守批量录制）；天然只包含浏览器视口内容，不会误录到其他窗口/桌面通知。
- 缺点：只能录浏览器视口内容，一个功能点如果既要演示浏览器操作又要展示终端命令行（很常见），`recordVideo` 覆盖不了后者；鼠标指针默认不可见（真实用户鼠标移动不会被渲染进视频），需要额外注入自定义光标。

**路线二：系统级录屏（ffmpeg + 平台原生采集设备）**。直接捕获物理/虚拟显示器的画面，Playwright 用有头模式（`headed`）正常打开真实浏览器窗口，ffmpeg 在旁边同步把整个屏幕录下来。

- 优点：能录任何画面，浏览器和终端切换全部自然覆盖，不用区分"这一段是浏览器内容还是桌面内容"；鼠标指针是真实系统指针，天然可见，不需要额外注入任何自定义光标层；不管这次操作是自动化脚本驱动的还是人工手动操作的，录制方式完全一样。
- 缺点：依赖系统权限（01 章 1.9 节）；分辨率/清晰度受实际显示器状态影响，多显示器/高 DPI 环境下配置更复杂；headless 服务器上需要虚拟显示器（Xvfb）模拟。

**结论**：实践中默认用路线二（系统级录屏），因为一个功能点几乎不需要提前判断"这段是不是纯浏览器内容"——不管是纯浏览器操作、纯终端操作，还是两者混合，系统级录屏用同一套机制就能覆盖，录出来是**一条连续的原始录像**，不需要在录制层面区分和切换路线。路线一（`recordVideo`）更适合另一种场景：只需要验证浏览器操作本身能不能跑通、不追求画面质感的无头批量冒烟测试（比如 04 章 4.6 节的冒烟检查），不是用来产出正式成片的。

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
# 启动一个虚拟显示器，编号 :99，分辨率与录制脚本里设置的 viewport 一致
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

## 5.4 混合场景：浏览器和终端切换，不需要特殊处理

因为路线二（系统级录屏）录的是整个屏幕，一个功能点里如果既有浏览器操作又有终端命令行演示，**不需要在脚本里做任何特殊标记去区分"这一段走哪条路线"**——`record.spec.js` 该怎么操作浏览器就怎么操作，需要展示终端的地方，脚本可以调用 `child_process` 切到一个提前准备好的终端窗口执行命令，ffmpeg 全程录的是同一块屏幕，画面自然跟着窗口焦点切换。05.5 节讲的终端录制注意事项（清干净历史命令、提前准备好别名）在这种混合场景下同样适用。

正因为不需要按"路线"拆分处理，00 章 0.3 节的架构图里"Record 层"只有一步，产出的也是**一条连续的原始录像**，不是多段视频文件——03 章已经强调过这一点：`record.spec.js` 是一份连续脚本，不是拼接起来的分段片段。

## 5.5 终端录制的特殊处理

如果某个功能点确实需要展示命令行操作过程（比如用户既有实践中"先 cd 到项目目录再执行别名命令"这种习惯的通用道理是：**提前准备好终端环境和别名，录制时只敲简短命令，不要在镜头前现场调试**），实践建议：

1. 提前打开一个专用的终端窗口/标签页，设置好合适的字号（录制分辨率下要保证文字清晰可读，参考 01 章 1.6 节确认的分辨率）、配色主题（浅色/深色需要和整体视频风格统一，见 07 章品牌规范）。
2. 提前把要用到的长命令封装成简短的 shell 别名或脚本，录制时只敲短命令，避免因为打字速度不均匀导致画面节奏被打乱。
3. 录制这一段的窗口只保留这一个终端窗口置顶,并且提前清空历史 scrollback，避免露出之前调试时的敏感信息或者杂乱输出（这一条会在 10 章的检查清单里再次出现，是防泄露的重点场景之一）。
4. 录制完成后，若这个终端窗口是专门为录制新建的，编排器/操作者应该在该步骤结束后关闭它，不要让它常驻，避免历史命令、环境变量残留带来后续误用或信息暴露的风险。

## 5.6 产物命名约定

本章的输出就是一个功能点目录下的一份文件：

```
feature-07-export-report/recording.mov
```

这是一条从开始操作到结束的完整连续录像，不做任何切分。封面/封底属于 07/08 章的静态素材合成范畴，不在这一步产出。

## 5.7 让系统级录屏真正做到无人值守：四个容易被忽略的工程细节

5.3 节给出的系统级录屏实现是"能跑"的最小版本，但要让它在没有人盯着的情况下稳定、安全地批量运行，还需要处理四类问题。这些问题不解决，轻则偶尔录出损坏文件需要重录，重则像下面第一条这样，**真实录到不该出现的画面**。

**问题一：录屏启动和自动化操作之间的时序空档，是最容易被忽视的泄露入口**。5.3 节的实现里，`startScreenRecording` 和后续开始操作之间如果直接顺序执行，中间会有一个短暂空档——ffmpeg 进程已经启动、但浏览器可能还没有导航到目标页面、还没有切到前台。这个空档期间屏幕上显示的是**别的窗口**（可能是你的代码编辑器、聊天软件、上一次调试留下的终端），如果这段时间恰好被 ffmpeg 录了进去，就是一次真实的敏感信息泄露，而且发生在录制的最开头，很容易被忽略着直接进入后续合成流程。

解决方法是用**跨进程的双信号握手**，而不是简单的顺序执行加延时等待：

1. 自动化脚本（Playwright）在完成"打开浏览器、导航到目标页面、窗口切到前台"这一整套准备动作后，写一个 `ready` 标记文件（或发一个进程间信号），表示"现在开始录屏是安全的"。
2. 外层负责启动 ffmpeg 的编排逻辑，轮询等待这个 `ready` 标记出现之后，才真正启动 ffmpeg 录屏进程。
3. ffmpeg 启动后需要一小段时间才能稳定写帧（通常一秒左右），编排逻辑等待这个稳定期过后，写一个 `go` 标记文件。
4. 自动化脚本轮询等到 `go` 标记出现，才开始执行真正的业务操作序列。

```typescript
// src/recorder/handshake.ts
import fs from "fs";

export function writeFlag(path: string): void {
  fs.writeFileSync(path, String(Date.now()));
}

export async function waitForFlag(path: string, timeoutMs = 60000): Promise<void> {
  const start = Date.now();
  while (!fs.existsSync(path)) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`等待信号文件超时: ${path}`);
    }
    await new Promise((r) => setTimeout(r, 200));
  }
}
```

编排器里的调用顺序变成：自动化脚本准备就绪 → `writeFlag(readyFlagPath)` → 主流程 `waitForFlag(readyFlagPath)` 后启动 ffmpeg → 等待约1秒让编码稳定 → `writeFlag(goFlagPath)` → 自动化脚本 `waitForFlag(goFlagPath)` 后才开始操作。这样"录屏开始"和"操作开始"之间不再依赖猜测的固定延时，而是由双方各自确认"我这边真的准备好了"来驱动，从工程上彻底消除了 5.3 节实现里潜在的时序空档。

**问题二：多显示器环境下，录屏设备序号不是稳定的**。macOS 的 `avfoundation` 给每块屏幕分配的采集设备序号，会在外接显示器插拔后重新编号——如果编排器把序号硬编码写死，接了外接屏之后完全可能录错屏幕（把外接屏内容录了进去，而实际操作发生在内置屏上，或者反过来）。稳妥的做法是每次录制前动态探测：枚举所有 `avfoundation` 采集设备，用系统显示器信息（分辨率、是否为主屏）逐一比对，找出真正对应内置/主屏的那个序号，而不是假设序号永远不变。这也是本书前言部分提到的"接外接屏后录制设备错位"这类问题的根本解法——探测一次、每次录制都重新探测，而不是配置一次就固定下来。

**问题三：录制环境本身要在每次录制前主动清理，而不是假设它一直是干净的**。5.5 节讲的终端窗口整洁，实践中应该做成录制流程里自动执行的一步，而不是仅仅写在人工检查清单里靠自觉执行：录制前自动关闭上一次残留的专用录制窗口、清除"下次启动恢复上次窗口"这类系统级的自动恢复行为（这类行为存在的意义是方便日常使用，但会导致录制窗口越攒越多，多个窗口边缘重叠会让画面显示错乱）、清空录制专用的历史命令文件（对应 10.6 节场景三提到的历史命令隔离）。把这些清理动作写成录制启动前自动执行的固定步骤，比指望"每个人每次都记得手动清理"可靠得多。

**问题四：录制产物要做完整性校验，损坏文件不能悄悄流入后续环节**。视频文件启动写入后如果录制进程被非正常终止（比如 ffmpeg 被强制杀死而不是优雅停止），常见后果是文件缺少正确的索引信息（moov atom），这样的文件在很多播放器/后续处理工具里表现为完全无法读取，但如果不主动校验，这个问题可能要等到 08 章合成阶段才会报错，那时候往往已经晚了——最好的做法是在 05 章录制结束的那一刻立刻用 `ffprobe` 校验一次产物完整性，发现问题立刻标记该分段需要重录，而不是让损坏文件带着"看似录制成功"的假象进入后续流程。同时，录制开始前也要检查并清理上一次异常退出可能残留的孤儿 ffmpeg 进程（比如通过进程名+目标文件路径匹配查找），避免新旧两个录制进程同时写入同一个文件导致的冲突。

这四类问题共同的特点是：**它们都不是"功能实现"层面的问题，而是"长期无人值守运行的健壮性"层面的问题**。5.1～5.6 节的实现能让你完成第一条视频的录制；本节这四个细节，才是让这套录制能力真正达到"完全自动化、可以放心批量跑"的关键。

下一章讲配音层：如何为每个步骤生成配音音频，并用音频时长反向驱动本章录制/等待的节奏。
