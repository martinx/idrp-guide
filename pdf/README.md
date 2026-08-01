# PDF 电子书构建

把 `docs/` 下的 21 章 Markdown 合并、排版成一本印刷版式的 PDF（6×9 英寸开本，封面/扉页/版权页/目录/正文/封底齐全，仿 Manning 一类技术书的排版惯例）。

## 一次性环境准备

```bash
brew install weasyprint          # HTML/CSS 转印刷级 PDF 的渲染引擎
cd idrp-guide
source .venv/bin/activate        # 复用仓库里已有的 Python 虚拟环境
pip install markdown pymdown-extensions pygments
```

只需要做一次；`.venv` 已经在仓库里（跟 `mkdocs serve` 用的是同一个），不需要单独建。

## 生成 PDF

```bash
cd pdf
python3 build_book.py
```

产出在 `pdf/output/`：

- `意图驱动录制.pdf` —— 最终成品
- `book.html` —— 合并后的中间 HTML（调试排版问题时看这个更直接，用浏览器打开肉眼检查，
  比直接看 PDF 改起来快）
- `book.css` —— 中间产物的副本（真正维护改 `pdf/book.css`，`output/` 下这份是构建时自动复制的）

首次运行大约几十秒到一两分钟（章节多、要跑一遍完整的 Markdown 转换 + 排版），改完样式重新跑一遍会看到最新效果。

## 目录结构

```
pdf/
├── build_book.py     # 合并21章 + 生成封面/扉页/版权页/目录/封底 + 调用 weasyprint
├── book.css           # 全部排版样式：开本尺寸、页眉页码、字体、代码块、目录点线页码等
├── README.md          # 就是这份文档
└── output/            # 构建产物，已加入 .gitignore，不提交进仓库
```

## 常见自定义

**改书名/副标题/作者/出版日期**：改 `build_book.py` 顶部的几个常量：

```python
BOOK_TITLE = "意图驱动录制"
BOOK_SUBTITLE = "AI 协同的自动化演示流水线"
AUTHOR = "Martin Xu"
PUBLISH_DATE = datetime.now().strftime("%Y 年 %-m 月")   # 改成固定字符串也可以
```

**新增/调整章节**：改 `build_book.py` 里的 `PARTS` 列表，每个部分（Part）下面是
`(章节编号, 对应的 docs/ 文件名)` 元组列表，和 `mkdocs.yml` 的 `nav` 结构保持一致即可：

```python
PARTS = [
    {"title": "准备与基础", "desc": "...", "chapters": [("00", "00-overview.md"), ...]},
    ...
]
```

**改排版样式**（开本大小、字体、页边距、代码块颜色等）：全部在 `book.css` 里，用的是标准
CSS + WeasyPrint 支持的印刷扩展（`@page` 页眉页脚、`string-set`/`string()` 做左右页不同页眉、
`target-counter()` 做目录页码）。改完样式不需要碰 `build_book.py`，直接重新跑
`python3 build_book.py` 看效果。

**改封面图案**：封面上那组抽象图形（AI 节点连线 + 录制/播放按钮 + 音频波形 + 代码符号）是
`build_book.py` 里 `COVER_SVG` 这个变量，一段内联 SVG，改坐标/颜色/图形都直接改这段 SVG 源码，
不需要额外的设计工具。

## 排版细节说明（供调试参考）

- **开本**：6in × 9in，是主流技术书常见尺寸，比 A4 更适合长时间阅读，也是本书 `book.css`
  `@page { size: 6in 9in; }` 定义的地方。
- **字体**：标题用系统自带的 PingFang SC（黑体），正文用 Songti SC（宋体），代码用 Menlo
  等宽字体——都是 macOS 系统自带字体，直接用字体名引用即可被 WeasyPrint 通过 fontconfig
  找到并嵌入 PDF，不需要额外下载字体文件。**如果在非 macOS 机器上构建**，这几个字体名可能找
  不到，需要在 `book.css` 里换成目标机器上实际安装的中文黑体/宋体字体名。
- **目录页码**：用 CSS 的 `target-counter(attr(href), page)` 实现，不需要跑两遍构建、不需要
  手工数页码，WeasyPrint 排版时会自动算出每个锚点最终落在第几页。
- **页眉**：正文页左侧固定显示书名、右侧显示当前章节名，用 CSS 的 `string-set`（在每章开头
  设置一个字符串变量）配合 `@page { @top-right { content: string(chaptertitle); } }`（在页边距
  盒子里取出这个变量）实现，是 CSS 印刷排版规范里专门为书籍/报告设计的机制。
