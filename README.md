# idrp-guide

《意图驱动录制：AI 协同的自动化演示流水线》

在线阅读：**https://idrp.bitey.ai/**

本仓库只包含本书的 MkDocs Material 站点源码（`docs/` 下的 Markdown 章节 + 站点配置），
推送到 `main` 分支后由 GitHub Actions 自动构建并发布到 GitHub Pages。

## 本地预览

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdocs serve
```

打开 http://127.0.0.1:8000 预览。

## 目录结构

```
idrp-guide/
├── mkdocs.yml              # 站点配置（导航、主题、插件）
├── requirements.txt        # mkdocs + mkdocs-material
├── docs/
│   ├── index.md            # 首页/总目录
│   ├── CNAME                # 自定义域名 idrp.bitey.ai
│   └── 00-overview.md ~ 15-glossary.md   # 16 个章节
└── .github/workflows/deploy.yml   # 推送到 main 自动构建部署
```
