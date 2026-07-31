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

## 1.4 Python 运行时（可选，用于部分离线 TTS / 素材处理脚本）

如果你打算用 Coqui TTS 等 Python 生态的语音合成方案（见 06 章备选方案），需要 Python 环境：

```bash
brew install python@3.11
python3 -m venv ~/.venvs/idrp
source ~/.venvs/idrp/bin/activate
pip install --upgrade pip
```

如果你只走"云端 TTS API + macOS say 兜底"的路线（本教程主线），Python 不是必须的，可以跳过本节。

## 1.5 浏览器自动化：Playwright

```bash
mkdir -p ~/idrp && cd ~/idrp
npm init -y
npm install -D typescript ts-node @types/node
npm install -D playwright @playwright/test

# 下载浏览器内核（Chromium/WebKit/Firefox）及系统依赖
npx playwright install --with-deps chromium
```

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

本教程的主线方案是"云端 TTS API 为主，离线 TTS 为本地调试兜底"。

**离线兜底（macOS 自带 `say`）**：不需要安装，直接可用：

```bash
say -v "?"          # 列出所有可用发音人
say -o test.aiff "你好，这是一个测试。" --data-format=LEI16@22050
afconvert test.aiff test.wav -f WAVE -d LEI16
```

**离线兜底（跨平台，edge-tts，基于微软 Edge 在线语音但免费无需 Key，适合快速起步）**：

```bash
python3 -m venv ~/.venvs/edge-tts && source ~/.venvs/edge-tts/bin/activate
pip install edge-tts
edge-tts --list-voices | grep zh-CN
edge-tts --voice zh-CN-XiaoxiaoNeural --text "你好，这是一个测试。" --write-media test.mp3
```

**云端 TTS（生产环境推荐）**：以阿里云智能语音交互 / Azure Speech / 腾讯云语音合成为例，共同点是需要：
1. 开通对应云服务的语音合成能力；
2. 获取 API Key / AccessKey；
3. 将密钥放入本地环境变量，**绝不硬编码进代码或提交进仓库**：

```bash
# 写入 ~/.zshrc 或专门的 .env.local（.env.local 加入 .gitignore）
export TTS_PROVIDER=azure
export AZURE_SPEECH_KEY=your_key_here
export AZURE_SPEECH_REGION=eastasia
```

06 章会给出统一的 TTS 适配层代码，屏蔽掉具体厂商差异，本地开发时可以直接用 `edge-tts` 或 `say`，生产环境切换成云端 API，业务代码不用改。

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

- [ ] Node.js 20.x（`node -v` 可用）
- [ ] Playwright + Chromium（`npx playwright codegen` 可弹窗）
- [ ] ffmpeg ≥ 5.0，且 `drawtext/subtitles/loudnorm/concat` 滤镜齐全
- [ ] 至少一种可用的中文字体路径已记录
- [ ] 至少一种可用的 TTS 方案（离线兜底优先跑通）
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
