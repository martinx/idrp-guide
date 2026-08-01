# 15 术语表与延伸阅读

## 15.1 术语表

| 术语 | 说明 | 对应章节 |
|---|---|---|
| IDRP（Intent-Driven Recording Pipeline） | 本教程自定义的名称，指代全书构建的"意图驱动录制流水线"系统 | 00 章 |
| Feature Spec | 描述一个功能点录制"意图"的结构化 YAML 文件，全系统唯一的人工输入产物 | 03 章 |
| Codegen | Playwright 提供的"操作即代码"录制工具，把人工操作转成可重放脚本 | 04 章 |
| 选择器（Locator/Selector） | 自动化脚本定位页面元素的方式，稳定性直接决定脚本的可维护性 | 04 章 |
| recordVideo | Playwright BrowserContext 内置的浏览器视口录制能力 | 05 章 |
| 系统级录屏 | 通过 ffmpeg + 操作系统原生采集设备（avfoundation/x11grab/gdigrab）捕获整个屏幕画面 | 05 章 |
| Xvfb | Linux 下的虚拟显示器（X Virtual Framebuffer），用于无真实显示器的服务器/CI 环境模拟图形界面 | 05 章、11 章 |
| TTS（Text-to-Speech） | 文本转语音，本系统用于自动生成解说配音 | 06 章 |
| 录制优先 | 本系统的核心节奏设计：先把操作按自然节奏录下来，字幕/配音在录制之后再适配这段固定的时间轴，而不是反过来用配音时长驱动录制节奏 | 00 章、06 章 |
| 响度归一化（Loudness Normalization） | 用 ffmpeg `loudnorm` 滤镜把音频统一调整到标准感知响度（如 -16 LUFS），保证多段拼接后音量一致 | 06 章、08 章 |
| concat demuxer | ffmpeg 的一种无损拼接模式，要求所有输入流编码参数完全一致 | 08 章 |
| SRT | 一种常见的字幕文件格式，包含序号、起止时间戳、文本三部分 | 08 章 |
| 硬字幕/软字幕（burned_in / soft） | 硬字幕是把字幕像素直接烧录进画面（兼容性最好但不可关闭），软字幕是作为独立字幕轨封装进容器（可开关/切换语言但依赖播放器支持） | 08 章 |
| Preflight | 正式录制前，用 headless 浏览器提前跑一遍所有操作脚本以确认可执行性的检查步骤 | 04 章、09 章 |
| 编排器（Orchestrator） | 把 Feature Spec 解析、配音生成、操作录制、音视频合成等各模块按顺序调用起来的总控程序 | 09 章 |
| 幂等性（Idempotency） | 指多次执行同一个 Feature Spec 的录制流程，只要输入不变，会得到内容一致的输出 | 09 章 |
| loudnorm / drawtext / subtitles | ffmpeg 中分别用于响度归一化、绘制文字（封面）、渲染字幕的滤镜 | 01 章、07 章、08 章 |
| ROI（投资回报率） | 本教程 14 章用来衡量"这套自动化系统是否值得为某个场景投入建设"的核心判断标准 | 14 章 |

## 15.2 全书代码模块速查

如果需要快速定位某个能力对应的代码文件，可以参考下表（路径基于 02 章约定的项目结构）：

| 能力 | 文件路径 |
|---|---|
| Feature Spec 类型定义 | `src/spec/schema.ts` |
| Feature Spec 加载与校验 | `src/spec/loader.ts` |
| codegen 清洗后的操作片段 | `src/codegen/steps/*.ts` |
| 浏览器录制 | `src/recorder/browser-recorder.ts` |
| 系统级录屏 | `src/recorder/screen-recorder.ts` |
| TTS 供应商适配层 | `src/dub/tts-provider.ts`、`tts-azure.ts`、`tts-edge.ts`、`tts-say.ts` |
| 音频时长测量与节奏计算 | `src/dub/audio-duration.ts`、`pacing.ts` |
| 响度归一化 | `src/dub/normalize.ts` |
| 封面生成 | `gen_title_card_png`/`gen_title_card`（ImageMagick 画图 + ffmpeg 转视频，见07章） |
| 封面转视频片段 | `src/cover/cover-to-clip.ts` |
| 分段规范化 | `src/mix/normalize-segment.ts` |
| 视频音频贴合 | `src/mix/attach-audio.ts` |
| 拼接 | `src/mix/concat.ts` |
| 字幕生成与烧录 | `src/mix/subtitle.ts`、`burn-subtitle.ts` |
| 背景音乐混音 | `src/mix/background-music.ts` |
| 最终导出 | `src/mix/export.ts` |
| 总编排入口 | `src/orchestrator/run-feature.ts` |
| Preflight 检查 | `src/orchestrator/preflight.ts` |

## 15.3 延伸阅读方向

本教程覆盖的是一条完整可用的主线方案，以下方向如果后续需要深入，可以作为独立的学习专题：

- **Playwright 官方文档中的 Auto-waiting 机制**：理解 Playwright 为什么大多数场景不需要手写 `waitForTimeout` 也能保证操作时序正确，这对 04 章清洗脚本时判断"哪些等待是必要的、哪些是多余的"很有帮助。
- **ffmpeg 滤镜图（Filter Graph）语法**：本教程用到的滤镜都是相对独立的单个调用，如果需要在一次 ffmpeg 命令里组合更复杂的多路输入输出处理（比如同时做转场+字幕+混音），需要理解 `-filter_complex` 里节点命名和连接的语法规则。
- **SSML（Speech Synthesis Markup Language）规范**：06 章用到的 `<prosody>` 标签只是 SSML 能力的一小部分，深入使用可以做到更精细的停顿、重音、多语言混读控制。
- **WCAG 无障碍可访问性规范**：04 章多次提到的"语义化选择器依赖前端可访问性基础"，如果希望从源头推动前端团队改善这一点，WCAG 规范里关于可交互元素语义角色（role）、可访问名称（accessible name）的章节是最直接的参考依据，同时这也是一项独立于本教程之外、对产品本身有价值的工程投入。
- **视频编码基础（H.264/H.265、码率控制、CRF 模式）**：如果对 08 章导出参数的选择想有更深入的理解（为什么用 CRF 而不是固定码率、不同 preset 之间具体的速度质量权衡曲线），可以专门学习视频编码的基础原理。

## 15.4 结语

从 00 章的架构设计到 09 章的完整实现，本教程用一台干净的机器为起点，构建了一套完整可运行的"意图驱动录制流水线"，覆盖了环境搭建、意图结构化、浏览器自动化、屏幕录制、自动配音、封面生成、音视频合成、全流程编排、质量把关、故障排查与规模化扩展的全部环节。14 章特别强调了这套系统并非在所有场景下都值得投入——技术方案的价值最终要放回具体的团队规模、录制频率、产品迭代节奏中去评估。希望这份教程能帮助你判断清楚这件事是否值得做，以及如果值得做，如何用最朴素、最可维护的方式把它做出来。
