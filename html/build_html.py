#!/usr/bin/env python3
"""
把 docs/ 下的 21 章 Markdown 合并成一份独立的单页 HTML（"Claude 风格"：暖白背景 + 赤陶橙点缀）。
只在本地生成、查看效果，不依赖 mkdocs，也不会被部署。

用法：
    cd html
    source ../.venv/bin/activate
    python3 build_html.py

产出：
    html/output/index.html   —— 双击直接用浏览器打开查看
"""
import shutil
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


def render_markdown(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = "未命名章节"
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        text = "\n".join(lines[1:])
    md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_EXT_CONFIG)
    return title, md.convert(text)


def build_sidebar(chapters_meta) -> str:
    rows = [f'<div class="brand">{BOOK_TITLE}</div><div class="brand-sub">{BOOK_SUBTITLE}</div>']
    for part in PARTS:
        rows.append(f'<div class="part-label">{part["title"]}</div>')
        for num, _, title, anchor in [c for c in chapters_meta if c[0] in [n for n, _ in part["chapters"]]]:
            rows.append(f'<a href="#{anchor}">{num} {title}</a>')
    return f'<nav class="sidebar">{"".join(rows)}</nav>'


def build_hero(chapters_meta) -> str:
    cards = []
    for part in PARTS:
        items = []
        for num, _, title, anchor in [c for c in chapters_meta if c[0] in [n for n, _ in part["chapters"]]]:
            items.append(f'<a href="#{anchor}"><span class="lc-num">{num}</span>{title}</a>')
        cards.append(f"""
        <div class="landing-card">
          <div class="lc-title">{part['title']}</div>
          <div class="lc-desc">{part['desc']}</div>
          <div class="lc-links">{''.join(items)}</div>
        </div>
        """)

    return f"""
    <div class="hero">
      <div class="kicker">Intent-Driven Recording</div>
      <h1>{BOOK_TITLE}：{BOOK_SUBTITLE}</h1>
      <p class="subtitle">一份从"一台干净的机器"出发的完整教程：人只走一遍真实操作路径，
      AI 把它整理成可重放的脚本、写好解说文案、生成配音、拼好成片；改一个字不用重录，
      字幕改完几十秒出新版本；一个功能点定型之后，重新录制也是全自动、无人值守的。</p>
      <div class="meta">{AUTHOR} · {PUBLISH_DATE} · 全书 21 章一次看完，点卡片直接跳转</div>
    </div>
    <div class="landing-grid">{''.join(cards)}</div>
    <div class="landing-divider"></div>
    """


def build_part_divider(part) -> str:
    return f"""
    <div class="part-divider">
      <div class="part-kicker">Part</div>
      <h2>{part['title']}</h2>
      <p>{part['desc']}</p>
    </div>
    """


def main():
    chapters_meta = []
    chapter_blocks = []

    for part in PARTS:
        chapter_blocks.append(build_part_divider(part))
        for num, filename in part["chapters"]:
            title, body_html = render_markdown(DOCS / filename)
            anchor = f"ch-{num}"
            chapters_meta.append((num, filename, title, anchor))
            chapter_blocks.append(f"""
            <section class="chapter" id="{anchor}">
              <div class="chapter-kicker">CHAPTER {num}</div>
              <h1 class="chapter-title">{title}</h1>
              {body_html}
            </section>
            """)

    sidebar_html = build_sidebar(chapters_meta)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{BOOK_TITLE}：{BOOK_SUBTITLE}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="layout">
  {sidebar_html}
  <main class="content">
    {build_hero(chapters_meta)}
    {''.join(chapter_blocks)}
    <div class="footer-note">{BOOK_TITLE} · {AUTHOR} · {PUBLISH_DATE}</div>
  </main>
</div>
<script>
  // 滚动时高亮左侧目录当前章节（纯本地小效果，不依赖任何外部库）
  const links = Array.from(document.querySelectorAll('.sidebar a'));
  const sections = links.map(a => document.querySelector(a.getAttribute('href')));
  window.addEventListener('scroll', () => {{
    let idx = 0;
    sections.forEach((sec, i) => {{
      if (sec && sec.getBoundingClientRect().top < 120) idx = i;
    }});
    links.forEach(a => a.classList.remove('active'));
    if (links[idx]) links[idx].classList.add('active');
  }}, {{ passive: true }});
</script>
</body>
</html>"""

    shutil.copy(Path(__file__).resolve().parent / "style.css", OUT_DIR / "style.css")
    cname_src = Path(__file__).resolve().parent / "CNAME"
    if cname_src.exists():
        shutil.copy(cname_src, OUT_DIR / "CNAME")
    out_path = OUT_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ 已生成: {out_path}")
    print(f"   直接用浏览器打开这个文件查看效果: file://{out_path}")


if __name__ == "__main__":
    main()
