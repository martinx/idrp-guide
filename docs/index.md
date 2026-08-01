# 意图驱动录制：AI 协同的自动化演示流水线

<p class="home-hero">
一份从"一台干净的机器"出发的完整教程：人只走一遍真实操作路径，AI 把它整理成可重放的脚本、
写好解说文案、生成配音、拼好成片；改一个字不用重录，字幕改完几十秒出新版本；
一个功能点定型之后，重新录制也是全自动、无人值守的。
</p>

**更重要的是**：0～15 章讲的是这套系统需要具备的"机制"，16～20 章讲的是实践中这些机制
**绝大部分是由 AI agent（如 Claude Code）执行的**——脚本整理、解说文案撰写、
录制后防泄露质检，几乎都不是人手工完成的，人类的角色收缩为走一遍真实操作、最终确认效果。
如果你只能读一部分，建议至少通读第 00 章和第 16 章。

<div class="home-grid" markdown>

<div class="home-card" markdown>
<span class="home-card-eyebrow">Part 1</span>
### 准备与基础
<p class="home-card-desc">环境怎么搭、项目怎么组织。</p>

- [00 前言与总体架构](00-overview.md)
- [01 环境准备](01-environment-setup.md)
- [02 项目脚手架与目录规范](02-project-scaffold.md)

</div>

<div class="home-card" markdown>
<span class="home-card-eyebrow">Part 2</span>
### 核心能力
<p class="home-card-desc">三份文件、录制、字幕配音、封面合成、命令行编排。</p>

- [03 一个功能点由哪几份文件描述](03-feature-spec.md)
- [04 浏览器自动化与 Codegen](04-codegen.md)
- [05 屏幕与浏览器录制](05-recording.md)
- [06 录制之后：字幕与自然语速配音](06-dubbing.md)
- [07 封面与素材生成](07-cover-assets.md)
- [08 合成成片：裁剪/混流/烧字幕](08-mixing.md)
- [09 命令行编排](09-orchestrator.md)

</div>

<div class="home-card" markdown>
<span class="home-card-eyebrow">Part 3</span>
### 质量与运维
<p class="home-card-desc">防泄露清单、故障排查、实战案例、值不值得做。</p>

- [10 质量检查与防泄露清单](10-quality-checklist.md)
- [11 故障排查、性能优化与扩展](11-troubleshooting.md)
- [12 端到端实战演练](12-walkthrough.md)
- [13 常见问题 FAQ](13-faq.md)
- [14 自动化边界与 ROI 考量](14-roi.md)
- [15 术语表与延伸阅读](15-glossary.md)

</div>

<div class="home-card" markdown>
<span class="home-card-eyebrow">Part 4</span>
### AI 协同实战
<p class="home-card-desc">全书最终想分享的经验：这一切在真实团队里是怎么被 AI 承接执行的。</p>

- [16 AI 是真正的操作者](16-ai-overview.md)
- [17 用 AI 设计与调试 Spec/Codegen](17-ai-spec-and-codegen.md)
- [18 用 AI 生成解说文案与字幕](18-ai-narration.md)
- [19 用 AI 做自动化质检与防泄露检测](19-ai-qa-leak-detection.md)
- [20 反过来看：不用 AI 要多久](20-ai-walkthrough.md)

</div>

</div>

## 如何使用

按章节顺序阅读：00～02 章是准备工作，03 章讲清楚一个功能点由哪三份文件描述，
04～09 章是核心能力模块和命令行编排，10～15 章是质量、运维、实战与决策参考，
16～20 章讲清楚这一切在真实团队里是如何被 AI agent 承接执行的——这是本书最终想要分享的核心经验。
每一章都是自包含的，可以单独打开阅读。所有代码片段均为教学示例，路径、包名、密钥等均为占位符，
请替换为你自己的真实值后再在目标机器上验证。

本书源码托管在 [GitHub](https://github.com/martinx/idrp-guide)，欢迎通过 Issue / PR 反馈问题或改进建议。
