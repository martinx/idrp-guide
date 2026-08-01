#!/usr/bin/env python3
"""
把 docs/ 下的 21 章 Markdown 合并成一本印刷排版的 PDF 电子书。

用法：
    cd pdf
    python3 build_book.py

依赖：
    brew install weasyprint
    pip3 install markdown pymdown-extensions pygments

产出：
    pdf/output/意图驱动录制.pdf
"""
import re
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_DIR.mkdir(exist_ok=True)

BOOK_TITLE = "意图驱动录制"
BOOK_SUBTITLE = "AI 协同的自动化演示流水线"
AUTHOR = "Martin Xu"
PUBLISH_DATE = datetime.now().strftime("%Y 年 %-m 月")

# ---- 章节清单：与 mkdocs.yml 的 nav 结构保持一致 ----
PARTS = [
    {
        "title": "准备与基础",
        "desc": "环境怎么搭、项目怎么组织。",
        "chapters": [
            ("00", "00-overview.md"),
            ("01", "01-environment-setup.md"),
            ("02", "02-project-scaffold.md"),
        ],
    },
    {
        "title": "核心能力",
        "desc": "三份文件、录制、字幕配音、封面合成、命令行编排。",
        "chapters": [
            ("03", "03-feature-spec.md"),
            ("04", "04-codegen.md"),
            ("05", "05-recording.md"),
            ("06", "06-dubbing.md"),
            ("07", "07-cover-assets.md"),
            ("08", "08-mixing.md"),
            ("09", "09-orchestrator.md"),
        ],
    },
    {
        "title": "质量与运维",
        "desc": "防泄露清单、故障排查、实战案例、值不值得做。",
        "chapters": [
            ("10", "10-quality-checklist.md"),
            ("11", "11-troubleshooting.md"),
            ("12", "12-walkthrough.md"),
            ("13", "13-faq.md"),
            ("14", "14-roi.md"),
            ("15", "15-glossary.md"),
        ],
    },
    {
        "title": "AI 协同实战",
        "desc": "全书最终想分享的经验：这一切在真实团队里是怎么被 AI 承接执行的。",
        "chapters": [
            ("16", "16-ai-overview.md"),
            ("17", "17-ai-spec-and-codegen.md"),
            ("18", "18-ai-narration.md"),
            ("19", "19-ai-qa-leak-detection.md"),
            ("20", "20-ai-walkthrough.md"),
        ],
    },
]

MD_EXTENSIONS = [
    "toc", "admonition", "attr_list", "def_list", "footnotes", "md_in_html", "tables",
    "pymdownx.betterem", "pymdownx.caret", "pymdownx.mark", "pymdownx.tilde",
    "pymdownx.details", "pymdownx.superfences", "pymdownx.highlight",
    "pymdownx.inlinehilite", "pymdownx.snippets", "pymdownx.tabbed", "pymdownx.tasklist",
]
MD_EXT_CONFIG = {
    "pymdownx.highlight": {"pygments_style": "friendly", "noclasses": True},
    "pymdownx.tabbed": {"alternate_style": True},
    "toc": {"permalink": False},
}


# ---- 封面用的抽象矢量图：AI 节点图 + 录制/播放按钮 + 音频波形 + 代码符号 ----
COVER_SVG = """
<svg width="300" height="170" viewBox="0 0 300 170" xmlns="http://www.w3.org/2000/svg">
  <g stroke="#6b6f7a" stroke-width="1.1" opacity="0.85">
    <line x1="34" y1="34" x2="96" y2="18"/>
    <line x1="34" y1="34" x2="76" y2="66"/>
    <line x1="96" y1="18" x2="76" y2="66"/>
    <line x1="76" y1="66" x2="130" y2="44"/>
    <line x1="96" y1="18" x2="130" y2="44"/>
  </g>
  <g fill="#ff7a68">
    <circle cx="34" cy="34" r="4.5"/>
    <circle cx="96" cy="18" r="3.4"/>
    <circle cx="76" cy="66" r="5.4"/>
    <circle cx="130" cy="44" r="3.4"/>
  </g>
  <circle cx="220" cy="52" r="38" fill="none" stroke="#d42820" stroke-width="2"/>
  <circle cx="220" cy="52" r="30" fill="#d42820" opacity="0.16"/>
  <polygon points="208,35 208,69 238,52" fill="#ff9a86"/>
  <g stroke="#c8c5bd" stroke-width="2.6" stroke-linecap="round" opacity="0.9">
    <line x1="14" y1="128" x2="14" y2="144"/>
    <line x1="27" y1="116" x2="27" y2="156"/>
    <line x1="40" y1="104" x2="40" y2="168"/>
    <line x1="53" y1="122" x2="53" y2="150"/>
    <line x1="66" y1="98"  x2="66" y2="174"/>
    <line x1="79" y1="116" x2="79" y2="156"/>
    <line x1="92" y1="128" x2="92" y2="144"/>
  </g>
  <text x="140" y="150" font-family="Menlo, monospace" font-size="24" fill="#9a9eaa">&lt;/&gt;</text>
</svg>
""".strip()


def render_markdown(path: Path) -> tuple[str, str]:
    """返回 (章节标题, 去掉首个H1之后渲染出的HTML正文)。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = "未命名章节"
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        text = "\n".join(lines[1:])

    md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_EXT_CONFIG)
    html = md.convert(text)
    return title, html


def build_cover() -> str:
    return f"""
    <section class="cover">
      <div>
        <div class="cover-kicker">Intent-Driven Recording</div>
        <div class="cover-title">{BOOK_TITLE}</div>
        <div class="cover-subtitle">{BOOK_SUBTITLE}</div>
        <div style="margin-top:0.4in;">{COVER_SVG}</div>
      </div>
      <div class="cover-footer">
        <span class="author">{AUTHOR}</span>
        <span>{PUBLISH_DATE}</span>
      </div>
    </section>
    """


def build_title_page() -> str:
    return f"""
    <section class="frontmatter title-page">
      <div class="tp-title">{BOOK_TITLE}</div>
      <div class="tp-subtitle">{BOOK_SUBTITLE}</div>
      <div class="tp-author">{AUTHOR}
        <span class="role">{PUBLISH_DATE}</span>
      </div>
    </section>
    """


def build_copyright_page() -> str:
    return f"""
    <section class="frontmatter copyright-page">
      <div class="cp-title">{BOOK_TITLE}：{BOOK_SUBTITLE}</div>
      <p>作者：{AUTHOR}</p>
      <p>出版时间：{PUBLISH_DATE}</p>
      <p>本书内容为教学示例，路径、包名、密钥、URL 等均为占位符，请替换为你自己的真实值后
      再在目标机器上验证。书中出现的功能点案例已做脱敏处理，不含任何真实客户信息。</p>
      <p>在线版本持续更新：https://idrp.bitey.ai/</p>
      <p>源码仓库：https://github.com/martinx/idrp-guide</p>
    </section>
    """


def build_toc(chapters_meta) -> str:
    rows = []
    for part in PARTS:
        rows.append(f'<div class="toc-part">{part["title"]}</div>')
        for num, _, title, anchor in [c for c in chapters_meta if c[0] in [n for n, _ in part["chapters"]]]:
            rows.append(
                f'<a class="toc-entry" href="#{anchor}">'
                f'<span class="toc-num">{num}</span><span class="toc-title">{title}</span></a>'
            )
    return f"""
    <section class="toc-page">
      <h1>目录</h1>
      {''.join(rows)}
    </section>
    """


def build_part_divider(part) -> str:
    return f"""
    <section class="part-divider">
      <div class="part-kicker">Part</div>
      <div class="part-title">{part['title']}</div>
      <div class="part-desc">{part['desc']}</div>
    </section>
    """


def build_back_cover() -> str:
    return f"""
    <section class="back-cover">
      <h2>{BOOK_TITLE}</h2>
      <p>从一台干净的机器出发，人只走一遍真实操作路径，AI 把它整理成可重放的脚本、
      写好解说文案、生成配音、拼好成片——字幕改完几十秒出新版本，
      一个功能点定型之后，重新录制也是全自动、无人值守的。</p>
      <div class="bc-list">
        <div>00～02　准备与基础</div>
        <div>03～09　核心能力</div>
        <div>10～15　质量与运维</div>
        <div>16～20　AI 协同实战</div>
      </div>
    </section>
    """


def main():
    chapters_meta = []  # (num, file, title, anchor)
    chapter_html_blocks = []

    for part in PARTS:
        chapter_html_blocks.append(build_part_divider(part))
        for num, filename in part["chapters"]:
            path = DOCS / filename
            title, body_html = render_markdown(path)
            anchor = f"ch-{num}"
            chapters_meta.append((num, filename, title, anchor))
            chapter_html_blocks.append(f"""
            <section class="chapter" id="{anchor}" style="string-set: chaptertitle '{title}';">
              <div class="chapter-kicker">CHAPTER {num}</div>
              <div class="chapter-title">{title}</div>
              {body_html}
            </section>
            """)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{BOOK_TITLE}</title>
<link rel="stylesheet" href="book.css">
</head>
<body>
{build_cover()}
{build_title_page()}
{build_copyright_page()}
{build_toc(chapters_meta)}
{''.join(chapter_html_blocks)}
{build_back_cover()}
</body>
</html>"""

    shutil.copy(Path(__file__).resolve().parent / "book.css", OUT_DIR / "book.css")

    html_path = OUT_DIR / "book.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"✅ 已生成合并 HTML: {html_path}")

    pdf_path = OUT_DIR / f"{BOOK_TITLE}.pdf"
    print("⏳ 正在用 WeasyPrint 渲染 PDF（章节较多，可能需要几分钟）...")
    result = subprocess.run(["weasyprint", str(html_path), str(pdf_path)], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    if result.stderr:
        print("(WeasyPrint 警告，通常可忽略)")
        print(result.stderr[:2000])
    print(f"✅ PDF 已生成: {pdf_path}")


if __name__ == "__main__":
    main()
