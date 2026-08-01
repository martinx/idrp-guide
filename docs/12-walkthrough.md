# 12 端到端实战演练：从一句话到一条成片

前面几章分模块讲清楚了原理和代码，本章把所有环节串起来，完整走一遍"从产品经理提出一句话需求，到最终拿到一条可以对外发布的成片"的真实工作流程。这条流水线跑顺了之后，一条视频从发起到成稿真实耗时大约 **15～30 分钟**，本章会具体拆解这个时间花在哪里。假设我们要做的功能点是本书反复引用的例子："报表导出功能"。

## 12.1 需求提出

产品经理确认一个新功能已经上线到 staging 环境：用户在报表页面可以一键导出 Excel。产品经理不需要懂任何技术细节，只需要在共享文档里写下一句话：

> "报表页面加了导出功能，用户选好时间范围和维度后点导出，能选 Excel 格式，导出的时候有进度条，做个演示视频。"

这句话加上顺手截的几张页面截图，就是本次录制任务的全部原始输入。

**耗时：5 分钟**

## 12.2 Codegen：一次性走完整个操作路径

工程师打开目标页面，启动 codegen，**一口气把整个操作路径走完**（登录 → 报表页 → 选时间范围/维度 → 点导出 → 选 Excel → 确认），中途不关闭窗口：

```bash
npx playwright codegen --viewport-size=1440,900 \
  --output=feature-07-export-report/nav-draft.spec.js \
  https://staging.example.com/reports
```

Inspector 面板里实时生成的代码大致是：

```javascript
await page.getByRole('link', { name: '报表' }).click();
await page.getByLabel('时间范围').click();
await page.getByText('最近30天').click();
await page.getByLabel('数据维度').selectOption('按渠道');
await page.getByRole('button', { name: '导出报表' }).click();
await page.getByText('Excel').click();
await page.getByRole('button', { name: '确认' }).click();
```

**耗时：5 分钟（人工操作为主）**

## 12.3 Sync：把草稿和需求一起交给 AI

工程师把 `nav-draft.spec.js` 和产品经理的原始描述一起交给 AI（17 章 17.1 节的方法），AI 产出正式的 `record.spec.js`（补上必要的等待条件）和一份 `timeline.json` 草稿：

```javascript
// record.spec.js（AI 整理后，补上了异步等待）
await page.getByText('Excel').click();
await page.getByRole('button', { name: '确认' }).click();
await page.getByText('导出成功').waitFor({ state: 'visible', timeout: 15000 });
```

```json
[
  { "t": 0,  "text": "接下来，我们来看一下报表导出功能。" },
  { "t": 3,  "text": "首先进入报表页面，选择需要的时间范围和数据维度。" },
  { "t": 9,  "text": "点击右上角的导出按钮，会弹出导出格式选择。" },
  { "t": 14, "text": "选择 Excel 格式并确认，页面会显示导出进度直到完成。" },
  { "t": 20, "text": "报表导出功能介绍完毕，感谢观看。" }
]
```

工程师审阅了一遍：操作顺序符合真实业务语义，文案语气自然，没有提到任何真实客户信息，`t` 大致合理，予以确认。

**耗时：3 分钟（AI 生成 + 人工审阅）**

## 12.4 冒烟检查

正式录制前先跑一遍 headless 检查：

```bash
npx playwright test record.spec.js --headed=false
```

第一次运行报错：

```
Error: page.waitForSelector: Timeout 15000ms exceeded.
waiting for getByText('导出成功') to be visible
```

排查发现，实际页面上进度完成后的提示文案确实是"导出成功"——这次 AI 已经按真实页面文案写对了，报错原来是网络延迟导致弹窗渲染较慢，把超时时间从 15 秒调到 20 秒后重新跑通过。这类问题在正式录制前发现，成本是几十秒；如果没有这一步冒烟检查，同样的问题会在录制过程中才暴露，浪费的是一整条录像。

**耗时：2 分钟**

## 12.5 正式录制

冒烟检查通过后，运行真正的录制：

```bash
vt record feature-07-export-report
```

浏览器按 `record.spec.js` 的操作路径走一遍，ffmpeg 同步录屏，`timeline.json` 自动转换成 `subtitles.srt`。全程约 20 秒的操作，加上前后的准备/收尾，这一步实际耗时：

**耗时：2 分钟**

## 12.6 出片：srt → dub → mix 一次跑完

```bash
vt all feature-07-export-report
```

控制台输出大致是：

```
✅ 环境就绪 (ffmpeg + whisper)
✅ 字幕已存在且比录屏新（来自时间点文本），跳过语音识别
✅ AI 配音: ai_dub.wav
✅ feature-07-export-report.mp4
```

**耗时：1 分钟**

## 12.7 审片与微调

完整播放一遍成片，发现配音和画面整体感觉配音稍微快了半拍——在 `meta.json` 里把 `dub_offset` 从 `0` 调成 `0.4`，重新走一遍最后的合成步骤（不需要重新录制、不需要重新生成配音）：

```bash
vt mix feature-07-export-report
```

再看一遍，配音和画面对上了。按 10 章 10.4 节的清单走一遍：封面标题正确、字幕正确、音量正常、没有敏感信息（脱敏演示账号 + staging 环境）。审片通过，发布。

**耗时：5 分钟**

## 12.8 总耗时统计

| 阶段 | 耗时 |
|---|---|
| 需求提出 | 5 分钟 |
| Codegen（人工走一遍操作路径） | 5 分钟 |
| Sync（AI 整理脚本+时间点文本，人工审阅） | 3 分钟 |
| 冒烟检查与修正 | 2 分钟 |
| 正式录制 | 2 分钟 |
| 出片（srt→dub→mix） | 1 分钟 |
| 审片与微调 | 5 分钟 |
| **合计** | **约 23 分钟** |

这就是 00 章开篇提到的"15～30 分钟成稿"的真实构成：**真正需要人全程专注参与的环节只有 Codegen（走一遍操作）和最后的审片，加起来不到 10 分钟；其余时间大部分是 AI 处理和自动化流水线在跑，人只需要等结果**。

## 12.9 维护性重录：UI 改版之后

三个月后，产品对导出按钮的文案从"导出报表"改成了"一键导出"，弹窗位置也从右上角挪到了页面中间。工程师需要做的事情：

1. 冒烟检查直接报错（选择器 `getByRole('button', { name: '导出报表' })` 找不到元素），把报错交给 AI 按 17.2 节的自愈流程修一下，改成 `{ name: '一键导出' }`——2 分钟。
2. `timeline.json` 的文案本身不用改（解说词说的是"点击导出按钮"，语义没变）。
3. 重新 `vt record`（弹窗位置变了，画面需要重新录一遍，但操作还是自动化跑的，不需要人工重新摸索）——2 分钟。
4. `vt all` 重新出片——1 分钟。
5. 快速过一遍确认画面正确——2 分钟。

**总耗时约 7～10 分钟**，而且大部分是自动化在跑、人只需要间歇性确认。如果这次改动**只是解说词里的某个措辞想换一种说法**（画面完全不用变），流程还能进一步简化——直接编辑 `subtitles.srt`，跑 `vt redub` 重新生成配音和成片，全程**不碰录制**，几十秒出新版本。这正是 00 章 0.4 节"录制优先"架构要追求的收益：只有真正涉及界面变化的部分才需要重新录制，纯文案调整完全不需要碰视频。
