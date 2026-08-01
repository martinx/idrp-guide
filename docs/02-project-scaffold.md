# 02 项目脚手架与目录规范

本章把 01 章装好的工具组织进一个规范的仓库结构，后续所有代码示例都放在这个结构里，路径引用才能对得上。

## 2.1 顶层目录设计

```
idrp/                              # Intent-Driven Recording Pipeline 项目根目录
├── package.json
├── tsconfig.json
├── playwright.config.ts
├── .env.local                     # 密钥类环境变量，加入 .gitignore，绝不提交
├── .gitignore
├── config/
│   ├── rule.yaml                  # 全局录制规范：分辨率、码率、字体、品牌色、语速等
│   └── voices.yaml                # TTS 发音人配置（不同语言/角色）
├── specs/                         # 每个功能点一个 Feature Spec
│   ├── feature-01-login.yaml
│   └── feature-02-dashboard-card.yaml
├── src/
│   ├── spec/                      # 03 章：Feature Spec 的类型定义与解析
│   │   ├── schema.ts
│   │   └── loader.ts
│   ├── codegen/                   # 04 章：codegen 辅助与脚本清洗
│   │   ├── record-session.ts
│   │   └── sanitize-script.ts
│   ├── recorder/                  # 05 章：录制层（浏览器 + 屏幕级）
│   │   ├── browser-recorder.ts
│   │   └── screen-recorder.ts
│   ├── dub/                       # 06 章：配音层
│   │   ├── tts-provider.ts
│   │   ├── tts-azure.ts
│   │   ├── tts-edge.ts
│   │   └── audio-duration.ts
│   ├── cover/                     # 07 章：封面生成
│   │   ├── template.html
│   │   └── render-cover.ts
│   ├── mix/                       # 08 章：ffmpeg 合成
│   │   ├── concat.ts
│   │   ├── subtitle.ts
│   │   └── export.ts
│   ├── orchestrator/              # 09 章：总编排器
│   │   └── run-feature.ts
│   └── util/
│       ├── logger.ts
│       └── paths.ts
├── assets/
│   ├── fonts/                     # 从系统路径复制/软链过来的字体，保证跨机器一致
│   ├── bg/                        # 封面背景图
│   └── music/                     # 背景音乐（若使用）
├── work/                          # 运行期产物（临时文件），加入 .gitignore
│   └── <feature-id>/
│       ├── raw/                   # 分段原始录像
│       ├── audio/                 # 分段配音
│       ├── srt/                   # 字幕文件
│       └── cover.png
└── output/                        # 最终成片输出目录
    └── <feature-id>.mp4
```

## 2.2 为什么这样分层

- `specs/` 与 `src/` 分离：Feature Spec 是"数据"，随时间不断新增；`src/` 是"代码"，相对稳定。这样产品/运营也能直接编辑 `specs/*.yaml` 而不用碰代码。
- `config/rule.yaml` 承担"全局规范"的角色：分辨率、码率、字体路径、品牌色、语速、每步最短停留时间等，一处修改，全部功能点视频统一生效，避免不同人录制风格不一致。
- `work/` 与 `output/` 分离：`work/` 是可随时清空重跑的中间产物，`output/` 才是交付物，防止误删成片。
- 每个能力模块（codegen/recorder/dub/cover/mix）单独成目录，彼此只通过明确的输入输出文件/接口交互，方便单独测试、替换实现（比如把 TTS 从 edge-tts 换成 Azure，只改 `dub/` 目录内部）。

## 2.3 初始化命令

```bash
mkdir -p idrp/{config,specs,src/{spec,codegen,recorder,dub,cover,mix,orchestrator,util},assets/{fonts,bg,music},work,output}
cd idrp
npm init -y
npm install -D typescript ts-node @types/node
npm install -D playwright @playwright/test
npm install js-yaml
npm install -D @types/js-yaml
npx tsc --init
npx playwright install --with-deps chromium
```

`tsconfig.json` 建议关键配置：

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "moduleResolution": "node",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "resolveJsonModule": true
  },
  "include": ["src/**/*.ts"]
}
```

`.gitignore` 关键条目：

```
node_modules/
work/
output/
.env.local
dist/
*.aiff
*.wav
```

## 2.4 package.json 脚本约定

```json
{
  "scripts": {
    "codegen": "ts-node src/codegen/record-session.ts",
    "run:feature": "ts-node src/orchestrator/run-feature.ts",
    "clean:work": "rm -rf work/*"
  }
}
```

后续每一章新增的能力，都通过扩展 `src/` 下对应目录 + 在 `run-feature.ts` 里接线的方式集成，不引入额外的构建系统，保持"能看懂、能改"的朴素工程风格——这套流水线本身不需要发布成 npm 包或对外提供 API，过度工程化没有必要。

## 2.5 命名与编号规范

- Feature Spec 文件名：`feature-<序号>-<英文短横线slug>.yaml`，例如 `feature-07-export-report.yaml`。
- 产物目录/文件统一用 Feature Spec 里的 `id` 字段命名（03 章会定义），不要用中文或空格，避免 ffmpeg/shell 处理路径时转义出问题。
- 版本化：`specs/` 目录建议纳入 git 管理，`work/`、`output/` 不纳入（成片如需归档，走独立的制品存储，而不是塞进代码仓库）。

## 2.6 多环境隔离：本地开发 / 演示环境 / 生产云端

一个容易被低估的工程问题是：这套流水线本身会在至少三种不同的"环境"下运行，如果不提前把环境差异显式建模，代码里就会出现大量临时性的 if-else 判断，越写越乱。三种环境分别是：

**本地开发环境**：工程师在自己的笔记本上调试某一个 Feature Spec 或某一段 codegen 脚本，追求的是"跑得快、能反复试错、不产生额外费用"。这个环境下 TTS 应该默认走离线方案（`TTS_PROVIDER=edge` 或 `mac-say`），浏览器录制默认开 `headless: false` 方便肉眼观察，日志级别调到 `debug`。

**演示/预发环境**：录制的目标页面是 staging 环境而不是生产环境，使用的账号是专门的演示账号（10 章会细讲），这个环境下追求的是"画面和数据干净、可反复重录"，通常也是正式产出交付视频的环境。

**生产云端环境（CI）**：无人值守批量运行，追求的是"稳定、可重复、失败要能被自动感知"，TTS 必须走云端方案（离线方案的音质不适合正式对外交付），浏览器录制必须 `headless: true` 配合 Xvfb（11 章会讲），日志要结构化输出方便 CI 平台采集。

具体做法是用 `.env` 文件分层 + `dotenv` 库按环境加载，而不是把环境判断逻辑写进业务代码：

```
.env.local          # 本地开发，加入 .gitignore，人手一份，各自配置自己的密钥
.env.staging         # 演示环境公共配置（不含密钥，密钥仍走各自的 secret 管理）
.env.ci               # CI/生产云端配置
```

```typescript
// src/util/env.ts
import dotenv from "dotenv";
import path from "path";

const envName = process.env.IDRP_ENV ?? "local";
dotenv.config({ path: path.resolve(process.cwd(), `.env.${envName}`) });
dotenv.config({ path: path.resolve(process.cwd(), ".env.local"), override: false });
```

业务代码里永远只读 `process.env.TTS_PROVIDER` 这类逻辑变量，不直接判断"现在是不是本地"，这样切换环境只需要改一个 `IDRP_ENV` 值，不需要改任何一行 `src/` 下的模块代码，这也是 06 章 TTS 适配层能够"一次实现、三处复用"的前提。

## 2.7 团队协作下的目录约定补充

如果这套流水线会被多名工程师/产品经理共同使用，还建议补充两条约定：

1. **`specs/` 目录按业务模块二级分类**，避免几十个 Feature Spec 平铺在一层目录里难以检索，例如 `specs/reports/feature-07-export-report.yaml`、`specs/settings/feature-12-notification-rule.yaml`。
2. **功能点目录按业务模块分类存放**，比如 `feature-reports-export/`、`feature-settings-notification/`，而不是所有功能点平铺在同一层，长期积累后才不会难以检索。

这两条约定在项目早期（Feature Spec 数量个位数）看起来是多余的，但一旦规模上升到几十上百个功能点，会显著降低维护成本，建议从项目第一天就按这个结构组织，而不是等到目录混乱后再重构。

下一章正式定义 Feature Spec 的结构——这是整个系统里唯一需要人工输入"意图"的地方。
