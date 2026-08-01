# 07 封面与素材生成

本章生成片头/片尾所需的静态画面。这些素材是否要用、用哪个文件，由 09 章讲的 `meta.json` 决定——记住 08 章 8.5 节的教训：素材文件存在不代表要启用，`meta.json` 里必须显式打开开关。核心工具是 **ImageMagick**，不是浏览器截图：白底画布上画标题、副标题、logo、公司名，直接合成一张图，再转成视频片段。

## 7.1 为什么用 ImageMagick 而不是浏览器截图 HTML 模板

用 HTML/CSS 写模板、拿 Playwright 截图，理论上表现力更强（渐变、阴影、Flex 布局这些 CSS 原生能力），但会给整条流水线多引入一个重量级依赖——只是为了生成一张标题卡片，代价是启动一次完整的浏览器。这套系统里 05/06/08/09 章的其余环节都是纯 shell + ffmpeg + Python，封面生成延用同一套朴素的技术栈，用 ImageMagick 的 `magick` 命令直接画：

- **依赖更轻**：`brew install imagemagick` 一行装完，不需要额外维护 Playwright 浏览器内核。
- **足够用**：功能演示视频的封面通常就是"白底 + 标题 + 副标题 + logo + 公司名"这几个元素，不需要 CSS 那种复杂布局能力。
- **和实时预览共用一套逻辑**：09 章会提到的可视化管理台，改标题/换配色能实时看到封面效果，预览和正式生成用的是同一个函数，不需要维护两套模板。

如果你的封面设计确实需要渐变、阴影、复杂排版这类 CSS 更擅长的效果，HTML 模板 + 无头浏览器截图仍然是一个合理的备选方案，只是不作为本书的默认路径。

## 7.2 封面生成：白底 + 标题 + 副标题 + logo + 公司名

```bash
# 生成封面静态图（不转视频）——实时预览和正式生成共用这一份逻辑，
# 避免同样的拼图代码在两处各写一遍，以后改一处忘了改另一处
gen_title_card_png() {
  local title="$1" subtitle="$2" out="$3" logo="$4" company="$5" accent="${6:-#222222}"
  [ -z "$title" ] && return 1

  # 按平台找一个能覆盖中文的字体，找不到就让 ImageMagick 用默认字体
  local font=""
  for f in "/System/Library/Fonts/Supplemental/Songti.ttc" \
           "/System/Library/Fonts/STHeiti Medium.ttc" \
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc" \
           "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"; do
    [ -f "$f" ] && { font="$f"; break; }
  done

  # 1. 白底 + 标题（accent 默认深灰，可以传成品牌色）+ 副标题
  magick -size 1920x1080 xc:'#FFFFFF' -gravity center \
    ${font:+-font "$font"} \
    -fill "$accent" -pointsize 60 -draw "text 0,-60 '$title'" \
    -fill '#666666' -pointsize 42 -draw "text 0,30 '$subtitle'" \
    -define png:color-type=2 "$out" 2>/dev/null || return 1

  # 2. logo（缩放到高度80px，叠加到左上角，保留原色）
  if [ -n "$logo" ] && [ -f "$logo" ]; then
    local logo_small="/tmp/_cover_logo_$$.png"
    magick "$logo" -resize x80 "$logo_small" 2>/dev/null
    magick "$out" "$logo_small" -geometry +40+30 -composite -colorspace sRGB \
      -define png:color-type=2 "$out" 2>/dev/null
    rm -f "$logo_small"
  fi

  # 3. 公司名（底部居中）
  if [ -n "$company" ] && [ -n "$font" ]; then
    magick "$out" -font "$font" -gravity south -fill '#999999' -pointsize 24 \
      -draw "text 0,50 '$company'" -colorspace sRGB -define png:color-type=2 "$out" 2>/dev/null
  fi
}
```

三步走：先画白底+文字，再叠 logo，最后加公司名——每一步都是对上一步产物的再加工，而不是一次性拼好所有图层，这样任何一步单独出问题都容易定位（比如 logo 没显示，只要看第2步的产物对不对）。

## 7.3 一个真实的坑：PNG 会被自动优化成灰阶，导致彩色 logo 被拍扁

上面代码里反复出现的 `-define png:color-type=2`，是一个真实踩过的坑：**如果画布上当前所有像素都是无彩色的**（比如默认的 `accent=#222222`、副标题灰色 `#666666`、背景纯白，三者的 R=G=B），ImageMagick 写 PNG 文件时会自动把颜色类型优化成灰阶（PNG 的 `IHDR color_type=0`），因为这样文件更小、看起来没有任何信息损失。

问题出在**下一步叠加彩色 logo 的时候**：合成操作是在这张已经被存成灰阶的 PNG 基础上进行的，`-composite` 会把新叠上去的彩色 logo 也一并拍扁成灰阶——观察到的现象是"logo 传的明明是彩色图片，合成出来的封面里 logo 却变成了黑白"。这个坑的诡异之处在于：**同样的代码，只要标题颜色换成一个真正的彩色（比如品牌红），就完全不会复现**，因为那种情况下画布从一开始就不是纯灰阶，不会触发 ImageMagick 的自动优化。也就是说默认配色（灰阶）反而是最容易触发问题的组合。

解决方法是显式强制每一步都用真彩色 RGB 编码（`png:color-type=2`），不管当前画布内容是不是碰巧全是灰阶，都不允许 ImageMagick 做这个"聪明"的自动优化。这类问题的规律值得记住：**图像处理工具的"自动优化"经常是根据当前像素内容做的启发式判断，样例测试时用的颜色恰好绕开了触发条件，上线后遇到另一种配色才暴出问题**——测试封面生成逻辑时，应该覆盖"全灰阶"和"含彩色"两种配色，而不是只用一套顺手的测试数据。

## 7.4 封面转视频片段

静态 PNG 需要转成一段"持续 N 秒的视频片段"，才能和其他动态录制片段拼接：

```bash
gen_title_card() {
  local title="$1" subtitle="$2" duration="${3:-3}" out="$4"
  local logo="$5" company="$6" accent="${7:-#222222}"
  [ -z "$title" ] && return 1

  local png="/tmp/_cover_$$.png"
  gen_title_card_png "$title" "$subtitle" "$png" "$logo" "$company" "$accent" || return 1

  # 转视频（带静音轨，编码参数与正文对齐，方便08章合成阶段用 -c copy 无损拼接）
  ffmpeg -loop 1 -i "$png" -f lavfi -i "anullsrc=r=48000:cl=stereo" \
    -c:v h264_videotoolbox -b:v 5M -r 30 \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black" \
    -pix_fmt yuv420p -t "$duration" -c:a aac -ar 48000 -ac 2 -shortest "$out" -y 2>/dev/null

  rm -f "$png"
}
```

时长（`duration`）从 `meta.json` 的 `cover_duration` 字段读取（09 章 9.4 节），默认 3 秒。编码参数（`h264_videotoolbox`/30fps/1920x1080/yuv420p/48kHz立体声）刻意和正文录像保持一致，这样 08 章拼接时才能用 `-c copy` 无损快速拼接，而不需要重新编码。

## 7.5 封底与外部素材：图片、视频都要能处理

封底（outro）不一定是生成出来的标题卡，也可能是一段现成的视频或者一张现成的图片（比如产品的固定结尾画面）。这里用文件扩展名简单判断走哪条处理路径，两条路径最终都对齐到同样的编码参数：

```bash
gen_cover() {
  local asset="$1" dur="$2" out="$3"
  if [[ "$asset" == *.mp4 || "$asset" == *.mov ]]; then
    ffmpeg -i "$asset" -f lavfi -i "anullsrc=r=48000:cl=stereo" \
      -c:v h264_videotoolbox -b:v 5M -r 30 \
      -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black" \
      -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 -map 0:v:0 -map 1:a:0 -shortest "$out" -y 2>/dev/null && echo "$out"
  else
    ffmpeg -loop 1 -i "$asset" -f lavfi -i "anullsrc=r=48000:cl=stereo" \
      -c:v h264_videotoolbox -b:v 5M -r 30 \
      -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black" \
      -pix_fmt yuv420p -t "$dur" -c:a aac -ar 48000 -ac 2 -shortest "$out" -y 2>/dev/null && echo "$out"
  fi
}
```

封底复用同一个函数（`gen_outro` 就是直接调用 `gen_cover`），因为"把一段素材统一成标准编码参数的视频片段"这件事，图片和视频只是输入格式不同，处理逻辑完全一样，没必要为封底单独写一份。

## 7.6 素材从哪读：还是那三份文件

回到 03 章的三份文件模型——封面用不用、标题写什么、logo 在哪，全部来自 `meta.json`（直接字段：`title`/`subtitle`/`cover_duration`/`company`/`cover_accent_color`，或者 08 章 8.5 节讲过的 `resolve_asset` 按约定文件名查找 `logo`/`cover`/`outro`）。这里不需要一份独立的"品牌规范"配置文件——`meta.json` 的三级合并（09 章 9.4 节：内置默认 → 项目级 → 功能级）本身就承担了"全项目统一视觉规范"的角色：项目级 `meta.json` 里定好 `cover_accent_color`、`company`，所有功能点的封面自动保持一致，个别功能点需要不同的标题/副标题时，功能级 `meta.json` 只覆盖这两个字段即可。

下一章把本章的封面片段、05 章的操作录像、06 章的配音，全部按时间轴合成为最终成片。
