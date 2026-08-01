# 11 故障排查、性能优化与扩展方向

本章收尾，整理长期运行这套流水线会遇到的典型故障、值得投入的性能优化方向，以及规模化之后自然会产生的扩展需求。

## 11.1 常见故障排查表

| 现象 | 最可能的原因 | 排查方向 |
|---|---|---|
| ffmpeg 屏幕录制画面全黑 | 系统权限未授予（01章1.9节） | 检查"屏幕录制"权限是否授予了实际运行录制命令的那个终端 App；注意每次终端 App 更新后 macOS 有时会要求重新授权 |
| Preflight 阶段选择器报错 | 目标页面 UI 改版，04章清洗后的脚本选择器失效 | 对照 4.4 节的选择器优先级原则，重新用 codegen 录一遍该步骤；若频繁发生，推动前端加 `data-testid` |
| 视频拼接后出现绿屏/花屏 | concat demuxer 模式下各分段编码参数不完全一致 | 检查是否所有分段都经过 8.2 节 `normalizeSegment` 处理，尤其注意像素格式（`yuv420p`）是否统一 |
| 字幕烧录后中文显示为方块 | `drawtext`/`subtitles` 滤镜没有正确找到中文字体文件 | 核对 07 章封面生成 / 08 章字幕烧录里用到的字体路径是否是当前机器上真实存在的绝对路径（01章1.7节） |
| 配音生成的音频时长为 0 或异常 | TTS 供应商调用失败但没有抛出异常（比如返回了空文件） | 在 `synthesize()` 实现里增加对输出文件大小的校验（生成后检查文件体积 > 0），避免静默失败 |
| 成片声音时大时小 | 响度归一化步骤被跳过，或跳过了某一路分段（比如混入背景音乐后忘记再做一次最终归一化） | 核对 09 章编排器主流程是否完整走到 `finalExport`（8.7节），不要在中间产物阶段就当作最终交付 |
| Playwright headless 下页面渲染与真实浏览器不一致（字体/动画） | headless Chromium 默认字体渲染与桌面 Chrome 有细微差异 | 录制阶段可以考虑 `headless: false`（配合 Xvfb 或真实显示器），仅 preflight 阶段用 headless 以求速度 |
| 长时间运行后磁盘占满 | `work/` 目录中间产物未清理（9.5节的清理开关被误设为保留） | 确认 `KEEP_WORK_DIR` 环境变量在批量生产环境下没有被设置为 `1` |

## 11.2 性能优化方向

**并行录制多个 Feature**：不同 Feature Spec 之间互不依赖，天然可以并行跑。实践中需要注意两个资源瓶颈：一是 TTS 云端 API 的并发限流（06 章的云端方案需要检查供应商的 QPS 限制，必要时加一层简单的并发队列）；二是屏幕级录制（路线二）在同一台机器上同时开多个 ffmpeg 采集同一块屏幕会互相冲突，路线二的任务建议串行执行，路线一（Playwright headless recordVideo）因为不占用真实屏幕，可以安全并行。

```typescript
// src/orchestrator/run-batch.ts 思路示意
import pLimit from "p-limit";

const limit = pLimit(3); // 最多3个Feature并行处理（浏览器录制部分）
const specFiles = ["specs/feature-01.yaml", "specs/feature-02.yaml", /* ... */];

await Promise.all(specFiles.map((f) => limit(() => runFeature(f))));
```

**封面/配音的缓存**：如果 Feature Spec 的 `title`/`narration` 文案没有变化，重新跑一遍编排器时可以跳过重新调用 TTS API 和重新截图封面（尤其云端 TTS 通常按调用次数计费）。做法是给每个待生成产物计算一个基于输入内容的哈希（比如 `narration` 文本 + `voice` + `speed` 拼接后取 SHA-256），产物文件名里带上这个哈希，命中缓存就跳过重新生成：

```typescript
import crypto from "crypto";

function contentHash(...parts: string[]): string {
  return crypto.createHash("sha256").update(parts.join("|")).digest("hex").slice(0, 12);
}

const cacheKey = contentHash(step.narration, spec.narration.voice, String(spec.narration.speed));
const audioPath = path.join(audioDir, `${step.id}.${cacheKey}.wav`);
if (!fs.existsSync(audioPath)) {
  // 才真正调用 TTS
}
```

这个思路同样适用于 07 章封面生成——只要 `title` 不变，封面截图可以复用。

**ffmpeg 编码速度与质量的权衡**：中间过程（8.2/8.3 节的分段归一化）用 `-preset veryfast` 追求速度，因为这些是一次性的中间产物，还会被再次转码；只有 8.7 节的最终导出才切换到 `-preset medium`（甚至更慢的 `slow`）追求质量，这个"中间快、最终精"的原则能显著缩短整体流水线耗时而不牺牲交付质量。

## 11.3 接入 CI，实现"Spec 合并即自动出片"

把 `specs/` 目录纳入 git 仓库管理之后，可以配置 CI（以 GitHub Actions 为例）在检测到 `specs/*.yaml` 变化时自动触发录制流程，产物上传到制品仓库或对象存储：

```yaml
# .github/workflows/record.yml 思路示意
name: Auto Record
on:
  push:
    paths:
      - "specs/**"
jobs:
  record:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg fonts-noto-cjk xvfb
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - name: 启动虚拟显示器
        run: |
          Xvfb :99 -screen 0 1440x900x24 &
          echo "DISPLAY=:99" >> $GITHUB_ENV
      - run: npm run run:feature -- specs/${{ github.event.head_commit.modified }}
        env:
          TTS_PROVIDER: azure
          AZURE_SPEECH_KEY: ${{ secrets.AZURE_SPEECH_KEY }}
          AZURE_SPEECH_REGION: eastasia
          DEMO_USERNAME: ${{ secrets.DEMO_USERNAME }}
          DEMO_PASSWORD: ${{ secrets.DEMO_PASSWORD }}
      - uses: actions/upload-artifact@v4
        with:
          name: feature-videos
          path: output/*.mp4
```

需要注意的是：CI 环境下（无头 Linux + Xvfb）路线二（系统级录屏，涉及终端/桌面演示）配置成本较高（11.1 节故障表中"headless 渲染差异"的问题在 CI 里更常见），建议 CI 自动化流程主要覆盖纯浏览器操作的 Feature（路线一），涉及终端/桌面演示的 Feature 保留人工在本地机器上触发录制，两条路径并存，不必强求所有类型的功能点都做到 CI 全自动。

## 11.4 多语言配音扩展

如果需要为同一个 Feature Spec 产出多语言版本的演示视频（比如中文/英文两版给不同市场使用），得益于 03 章 Feature Spec 里 `narration` 是独立于 `steps` 操作逻辑的字段，扩展方式是引入"语言变体"层，而不需要为每种语言复制一份完整 Spec：

```yaml
# specs/feature-07-export-report.yaml 扩展设计
narration_variants:
  zh-CN:
    voice: zh-CN-XiaoxiaoNeural
    texts:
      intro: "接下来，我们来看一下报表导出功能。"
      open-report-page: "首先进入报表页面，选择需要的时间范围和数据维度。"
      # ...
  en-US:
    voice: en-US-JennyNeural
    texts:
      intro: "Next, let's take a look at the report export feature."
      open-report-page: "First, go to the reports page and select the desired time range and dimensions."
      # ...
```

编排器只需要在 06 章配音生成阶段，遍历 `narration_variants` 的每个语言键分别生成一套配音和字幕，08 章合成阶段对每种语言各跑一遍（操作录制本身，即 04/05 章产出的分段视频，是语言无关的，可以被所有语言变体复用，只有配音和字幕层需要按语言各生成一份），显著降低了多语言扩展的边际成本。

## 11.5 扩展方向小结

到本章为止，从 00 章的架构设计到 09 章的完整编排器实现，已经具备一套可独立运行的、意图驱动的功能点录制自动化系统。后续可能的自然演进方向包括：

- 引入更精细的动态转场/动画效果（可以考虑接入 Remotion 这类基于 React 渲染视频的框架替代纯 ffmpeg 拼接，换取更强的视觉表现力，代价是渲染速度和学习成本更高）。
- 把 Feature Spec 的编写进一步"自然语言化"，允许直接输入一段自由文本描述，由 LLM 全自动生成结构化 Spec 草稿（03 章 3.4 节已经提到这个思路，可以进一步做成一个内部小工具/Slack Bot）。
- 建立成片的自动化质检（比如用视觉语言模型抽帧检测是否有异常内容），作为 10 章人工审片清单的辅助，而非替代。

这些都属于在本教程搭建的基础骨架之上的增量投入，具体投入优先级取决于团队实际的功能点录制量和对视频质感的要求，不需要在系统首次落地时就一次性做全。
