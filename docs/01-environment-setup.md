# 01 环境准备

本章目标：在一台**全新的机器**（以 macOS 为主线，附 Linux / Windows 差异说明）上，把整套流水线所需的运行时、工具链、系统权限全部配置完成。全书后续章节的代码都假设本章已经完成。

## 1.1 操作系统的选择与理由

三大平台都能跑这套流水线，但难易度和稳定性不同：

- **macOS**：推荐首选。系统自带 `say`（离线 TTS，适合本地联调）、`avfoundation`（ffmpeg 屏幕采集设备）、`Screen Recording` 权限体系成熟，Playwright 对 WebKit/Chromium 支持都很好。绝大多数"功能演示录制"场景（浏览器 + 桌面终端）在 macOS 上最省心。
- **Linux（Ubuntu 22.04+）**：适合放在 CI / 云端无人值守批量录制。需要 `xvfb`（虚拟显示器）+ `x11grab`。没有真实显示器时也能跑，但**鼠标高亮**、**真实字体渲染**等细节需要额外配置（见 1.7）。
- **Windows**：可行，但 ffmpeg 的 `gdigrab` 采集在多显示器/高 DPI 下坑较多，不作为首选，本教程仅在关键步骤给出 Windows 命令，不展开。

本章后续以 macOS 命令为主线，Linux 差异用「Linux 备注」标出。

## 1.2 包管理器

macOS 上先装 Homebrew（如果还没有）：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Linux（Ubuntu）用 apt：

```bash
sudo apt update && sudo apt upgrade -y
```

## 1.3 Node.js 运行时

编排器、Playwright、codegen 都跑在 Node.js 上。推荐用版本管理器而不是直接装全局 Node，方便未来切换版本：

```bash
# 安装 nvm（Node Version Manager）
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.zshrc   # 或 ~/.bashrc

# 安装并使用 LTS 版本（建议 Node 20.x）
nvm install 20
nvm use 20
nvm alias default 20

node -v   # 确认版本 v20.x
npm -v
```

> 为什么是 Node 20 而不是更新的版本：Playwright、大多数 TTS SDK、以及 ffmpeg 的 Node 封装库在 20.x LTS 上生态最成熟，避免用最新的非 LTS 版本踩兼容性坑。

## 1.4 Python 运行时（必装，不是可选项）

和很多人的直觉相反，这套系统里 Python 不是"可选的辅助脚本语言"，而是核心依赖——06 章的字幕解析/生成、语音识别兜底、多语言翻译，都是用 Python 写的小脚本（配合 shell 编排器一起跑）：

```bash
brew install python@3.11
python3 -m venv ~/.venvs/idrp
source ~/.venvs/idrp/bin/activate
pip install --upgrade pip
pip install edge-tts faster-whisper
```

`edge-tts` 是 06 章配音的默认方案本体（不是可选项）；`faster-whisper` 是字幕来源兜底用的本地语音识别引擎（06 章 6.1 节），如果更偏好 SenseVoice，换成 `pip install funasr` 也可以。

## 1.5 浏览器自动化：Playwright

```bash
mkdir -p ~/idrp && cd ~/idrp
npm init -y
npm install -D playwright @playwright/test

# 下载浏览器内核（Chromium/WebKit/Firefox）及系统依赖
npx playwright install --with-deps chromium
```

自动化脚本（`record.spec.js`）用普通 JavaScript 写就够了，不需要 TypeScript 工具链——04 章会看到，这些脚本大多是 AI 生成的一次性代码，加一层 TS 编译反而增加不必要的构建步骤。

`--with-deps` 会在 Linux 上自动装好 Chromium 运行所需的系统库（字体、libnss、libatk 等），macOS/Windows 上这个参数基本是空操作，但保留无害。

验证安装：

```bash
npx playwright --version
npx playwright codegen https://example.com
```

如果能弹出一个 Chromium 窗口和一个 "Playwright Inspector" 录制面板，说明 Playwright + codegen 已经就绪（codegen 的详细用法见第 04 章）。

## 1.6 音视频处理：ffmpeg

```bash
brew install ffmpeg
ffmpeg -version
```

Linux：

```bash
sudo apt install -y ffmpeg
```

务必确认版本 ≥ 5.0（本教程用到的 `loudnorm`、`drawtext`、`subtitles` 滤镜在旧版本上参数略有差异）：

```bash
ffmpeg -version | head -1
# 期望输出类似: ffmpeg version 6.x ...
```

同时确认关键滤镜是否编译进当前 ffmpeg（用于封面文字绘制、字幕烧录）：

```bash
ffmpeg -filters 2>/dev/null | grep -E "drawtext|subtitles|loudnorm|concat"
```

四项都应该能匹配到。如果 `drawtext` 缺失，说明你的 ffmpeg 编译时没有启用 `--enable-libfreetype`，需要用 `brew reinstall ffmpeg` 重装官方完整版（Homebrew 默认公式已经带全部这些滤镜，通常不会遇到这个问题；如果是自行编译的 ffmpeg 才需要注意）。

**字幕烧录（08 章）额外需要 `libass` 支持**，Homebrew 默认的 `ffmpeg` 公式不一定带这个组件，需要装完整版：

```bash
brew install ffmpeg-full
```

如果机器上同时装了默认版和 `ffmpeg-full`，08 章烧字幕的命令要显式指定完整版的路径（通常在 `/usr/local/opt/ffmpeg-full/bin/ffmpeg`），不要依赖 `PATH` 里默认解析到的那个 `ffmpeg`，两个版本的滤镜集不一样，混用会导致"明明装了却提示缺 libass"这种困惑。

同时装一下 07 章封面生成要用的 ImageMagick：

```bash
brew install imagemagick
magick -version
```

## 1.7 字体（封面文字 / 字幕烧录必需）

`drawtext` 和 `subtitles` 滤镜都需要指定一个真实存在的字体文件路径，中文字幕/封面尤其要确认系统里有中文字体：

macOS 自带的常用中文字体路径：

```
/System/Library/Fonts/PingFang.ttc
/System/Library/Fonts/STHeiti Light.ttc
```

Linux（Ubuntu）通常需要手动装中文字体：

```bash
sudo apt install -y fonts-noto-cjk
fc-list | grep -i noto | grep -i cjk
```

记下你打算使用的字体文件绝对路径，07 章（封面生成）和 08 章（字幕烧录）会直接引用这个路径。

## 1.8 文本转语音（TTS）相关准备

本教程的主线方案是 **edge-tts 为默认**（免费、无需 Key、微软神经语音、中文自然度足够好），macOS 自带的 `say` 只作为完全离线场景下的兜底，云端付费 API 是可选的升级路径，不是默认必需项。

**默认方案：edge-tts**（1.4 节已经装过，这里补充验证）：

```bash
edge-tts --list-voices | grep zh-CN
edge-tts --voice zh-CN-XiaoxiaoNeural --text "你好，这是一个测试。" --write-media test.mp3
```

**完全离线兜底：macOS 自带 `say`**（没有网络、或者 edge-tts 服务临时不可用时用）：

```bash
say -v "?"          # 列出所有可用发音人
say -o test.aiff "你好，这是一个测试。" --data-format=LEI16@22050
afconvert test.aiff test.wav -f WAVE -d LEI16
```

**云端付费 TTS（可选，需要更多发音人/更强合规保障时再考虑）**：以阿里云智能语音交互 / Azure Speech 为例，开通语音合成能力、拿到 API Key 后，放进环境变量，**绝不硬编码进代码或提交进仓库**：

```bash
export AZURE_SPEECH_KEY=your_key_here
export AZURE_SPEECH_REGION=eastasia
```

06 章的配音逻辑默认调用 edge-tts，只有明确需要切换发音人/供应商时才会用到云端 API。

## 1.9 系统权限（macOS 尤其重要）

macOS 的隐私保护机制会拦截"屏幕录制"和"辅助功能"（Accessibility，用于模拟鼠标高亮/控制其他 App 窗口）两类操作，需要手动授权一次：

1. 系统设置 → 隐私与安全性 → 屏幕录制 → 把你要用来跑录制脚本的终端 App（Terminal.app / iTerm2）勾选打开。
2. 系统设置 → 隐私与安全性 → 辅助功能 → 同样勾选你的终端 App。
3. 如果录制脚本会控制多个显示器/窗口定位，还需要在"自动化"（Automation）里允许该终端 App 控制"系统事件"（System Events）。

未授权的典型报错是 ffmpeg 报 `Operation not permitted` 或截屏是全黑画面——遇到这个现象第一反应是检查这三处权限，而不是查代码逻辑。

## 1.10 关闭干扰源（勿扰模式 / 通知）

录制过程中系统通知弹窗、消息提醒会直接穿帮，录制前务必：

```bash
# macOS：通过快捷键或控制中心开启"专注模式/勿扰模式"
# 也可以用 shortcuts CLI 自动化（macOS 12+）：
shortcuts run "打开勿扰模式"   # 需要提前在"快捷指令"App 里建好这个同名快捷指令
```

这一项会在 10 章的"录制前检查清单"里再次出现，因为它是最容易被忽略但最容易穿帮的一步。

## 1.11 目录与环境变量小结

到本章结束，你的机器上应该具备：

- [ ] Node.js 20.x（`node -v` 可用），Playwright + Chromium（`npx playwright codegen` 可弹窗）
- [ ] Python3 + `edge-tts` + `faster-whisper`（或 `funasr`）已装好
- [ ] ffmpeg ≥ 5.0 且滤镜齐全；`ffmpeg-full`（带 libass）另外装好，字幕烧录专用
- [ ] ImageMagick（`magick -version` 可用），07 章封面生成要用
- [ ] 至少一种可用的中文字体路径已记录
- [ ] `edge-tts` 已跑通（默认配音方案），`say` 作为完全离线兜底
- [ ] 屏幕录制 + 辅助功能权限已授予终端 App
- [ ] 勿扰模式可以一键开启

## 1.12 Windows 环境的关键差异（非首选路径，仅供参考）

如果团队的目标机器只能是 Windows，以下是与 macOS 主线流程的关键差异点，其余步骤（Node.js/Playwright/ffmpeg 安装）基本一致，用 `winget` 或直接下载安装包替代 `brew` 即可：

```powershell
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg
```

系统级录屏使用 `gdigrab` 而不是 `avfoundation`/`x11grab`：

```powershell
ffmpeg -f gdigrab -framerate 30 -offset_x 0 -offset_y 0 -video_size 1440x900 -i desktop `
  -vcodec libx264 -pix_fmt yuv420p -preset veryfast -crf 18 output.mp4
```

`gdigrab` 在多显示器环境下需要用 `-offset_x`/`-offset_y` 手动指定要采集的显示器区域，且在高 DPI 缩放（如 150%/200% 缩放）下容易出现采集区域与实际显示不一致的问题，需要提前把目标显示器的缩放比例临时调整为 100% 再录制。鼠标指针默认可见，不需要像 macOS 那样额外传参。字体路径通常在 `C:\Windows\Fonts\` 下，中文字体常见的是 `msyh.ttc`（微软雅黑）。权限方面 Windows 没有 macOS 那样的隐私授权弹窗机制，`gdigrab` 通常开箱可用，但如果系统开启了某些安全软件的屏幕保护策略，可能需要额外在安全软件里放行 ffmpeg 进程。

由于以上差异点相对繁琐、且高 DPI 缩放问题的排查成本较高，本教程后续章节的代码示例仍以 macOS/Linux 路径为主，Windows 团队建议优先考虑用 WSL2（Windows Subsystem for Linux）跑本教程的 Linux 路径，只在必须使用真实 Windows 桌面画面（比如要演示一个 Windows 专属客户端软件）时才直接用原生 Windows + `gdigrab` 方案。

下一章（02）开始搭建项目骨架，把这些工具组织进一个规范的代码仓库结构里。
