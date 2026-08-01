# idrp-guide

《意图驱动录制：AI 协同的自动化演示流水线》—— Martin Xu 著

在线阅读：**https://idrp.bitey.ai/**

一份从"一台干净的机器"出发的完整教程：人只走一遍真实操作路径，AI 把它整理成可重放的脚本、
写好解说文案、生成配音、拼好成片；改一个字不用重录，字幕改完几十秒出新版本；一个功能点
定型之后，重新录制也是全自动、无人值守的。全书 21 章，分四部分：准备与基础、核心能力、
质量与运维、AI 协同实战。

## 仓库结构

```
idrp-guide/
├── docs/                # 唯一内容源：21 章 Markdown（00-overview.md ~ 20-ai-walkthrough.md）
│                        # 改文案永远只改这里，下面两套产出都从这里读取
├── html/                # 官网用的独立单页 HTML（暖白背景+赤陶橙点缀，"Claude 风格"）
│   ├── build_html.py     # 合并21章生成 html/output/index.html
│   ├── style.css
│   └── CNAME             # 自定义域名 idrp.bitey.ai
├── pdf/                 # 印刷版电子书（6x9开本，封面/扉页/目录/正文/封底）
│   ├── build_book.py     # 合并21章生成 pdf/output/意图驱动录制.pdf
│   ├── book.css
│   └── README.md         # PDF 构建的详细说明（字体安装、字号调整等）
├── mkdocs.yml            # 早期用过的 mkdocs Material 站点配置，现在只能本地 `mkdocs serve`
│                        # 预览用，不再驱动线上站点（线上站点走的是 html/ 这套）
└── .github/workflows/deploy.yml   # 推送到 main 后自动跑 html/build_html.py 并部署到 Pages
```

## 更新官网

改完 `docs/` 下的章节内容，直接 `git push`，GitHub Actions 会自动跑 `html/build_html.py`
重新生成并部署到 `idrp.bitey.ai`，不需要手动操作。

## 生成 PDF 电子书（本地）

```bash
brew install weasyprint
brew install --cask font-noto-serif-cjk-sc font-noto-sans-cjk-sc
python3 -m venv .venv && source .venv/bin/activate
pip install markdown pymdown-extensions pygments
cd pdf && python3 build_book.py
```

产出在 `pdf/output/意图驱动录制.pdf`，不会自动发布，需要的话自己分发。详细说明（改字号、
改封面、改书名作者等）见 `pdf/README.md`。

## 本地预览 HTML 版

```bash
cd html && python3 build_html.py
open output/index.html
```

## （可选）本地预览 Markdown 原文档站

早期版本用 mkdocs Material 搭过一版多页文档站，现在线上不再用它，但配置还留着，
本地想看这个版本效果的话：

```bash
pip install -r requirements.txt
mkdocs serve
```
