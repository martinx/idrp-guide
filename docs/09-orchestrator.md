# 09 命令行编排：让每一步都能单独重跑

前几章讲了每个环节自己的原理。本章讲这些环节怎么被组织成一套命令行工具——重点不是"用什么语言写编排器"，而是一个更重要的设计决定：**整条流水线的"状态"就是文件系统里那几个约定命名的文件，不是任何数据库或者内存里的状态机**。这个决定直接决定了"改一个字，几十秒出新片"能不能做到。

## 9.1 用文件名本身表达流水线状态

每个功能点对应一个目录，目录里几个约定命名的文件，就是这个功能点当前处于流水线的哪一步：

```
feature-07-export-report/
├── recording.mov       ← 有这个文件，说明"录制"这一步完成了
├── timeline.json        ← （可选）自动化脚本产出的时间点文本
├── subtitles.srt        ← 有这个文件，说明"字幕"这一步完成了
├── ai_dub.wav           ← 有这个文件，说明"配音"这一步完成了
├── record-offset.txt    ← 录制起始不安全空档的秒数（08章2节用到）
├── meta.json            ← 这个功能点的配置（标题、发音人、是否要封面/BGM）
└── feature-07-export-report.mp4   ← 有这个文件，说明"合成"这一步完成了
```

查看一个功能点当前进度，不需要读任何数据库，直接看这几个文件存不存在、新不新：

```bash
status() {
  local dir="$1"
  [ -f "$dir/recording.mov" ]  && echo "✅ recording.mov" || echo "⬜ recording.mov 缺失"
  [ -f "$dir/subtitles.srt" ]  && echo "✅ subtitles.srt ($(grep -c '^[0-9]' "$dir/subtitles.srt") 条)" || echo "⬜ subtitles.srt 缺失"
  [ -f "$dir/ai_dub.wav" ]     && echo "✅ ai_dub.wav" || echo "⬜ ai_dub.wav 缺失"
  [ -f "$dir/$(basename "$dir").mp4" ] && echo "✅ 成片已生成" || echo "⬜ 成片缺失"
}
```

这个"文件即状态"的设计带来一个关键好处：**任何一步都可以单独重跑，只要它依赖的上游文件还在**。改了字幕文本，只需要重新生成 `ai_dub.wav` 和成片，`recording.mov` 完全不用碰——这不是靠某个"任务依赖图"框架实现的，只是因为每一步的输入输出都是磁盘上明确的文件。

## 9.2 命令与它们依赖/产出的文件

> **关于 `vt` 这个命令名**：本书接下来会大量出现 `vt record`、`vt all`、`vt redub` 这样的命令。`vt` 不是需要单独安装的第三方软件，就是 9.1 节说的这个入口脚本（`video-toolkit.sh`）装好之后起的一个短别名——`alias vt=/path/to/video-toolkit.sh`，或者直接把这个脚本链接到 `PATH` 里某个目录、去掉 `.sh` 后缀。取这个名字纯粹是图打字方便，你自己实现时完全可以叫别的名字，本书统一用 `vt`只是为了后面所有命令示例整齐、便于对照阅读。

| 命令 | 依赖 | 产出 | 典型耗时 |
|---|---|---|---|

| 命令 | 依赖 | 产出 | 典型耗时 |
|---|---|---|---|
| `codegen` | 无（人工操作浏览器） | `nav-draft.spec.js`（选择器草稿） | 几分钟，人工操作为主 |
| `sync` | `nav-draft.spec.js` | 更新 `record.spec.js` + `timeline.json`（交给 AI 处理，见17章） | 1～2分钟 |
| `record` | `record.spec.js` | `recording.mov` + `timeline.json`→`subtitles.srt` + `record-offset.txt` | 1～3分钟（等于操作本身耗时） |
| `srt` | `recording.mov` | `subtitles.srt`（若已存在且更新则跳过，见6.1节） | 几秒～1分钟（ASR兜底时较慢） |
| `dub` | `subtitles.srt` | `ai_dub.wav` | 十几秒到1分钟 |
| `mix` | `recording.mov` + `ai_dub.wav` + `meta.json` | 成片 `.mp4` | 十几秒 |
| `redub` | 手改后的 `subtitles.srt` | 重新生成 `ai_dub.wav` + 成片 | 几十秒，**不碰录制** |
| `burn` | 成片 + `subtitles.srt` | 烧录字幕后的最终版本 | 几十秒 |
| `trans` | `subtitles.srt` | `subtitles_en.srt`（DeepSeek翻译） | 十几秒 |
| `en` | `subtitles_en.srt` | 英文配音 + 英文成片 | 几十秒 |
| `all` | `recording.mov` | 一次跑完 srt→dub→mix | 1～2分钟 |
| `status` | 无 | 打印当前功能点各文件的完成情况 | 秒级 |

`all` 是最常用的命令，把 `srt → dub → mix` 串起来一次跑完；但一旦某个环节要单独调整（最常见的是改字幕文案），直接用对应的单步命令（`redub`），不需要重新走 `all`。

## 9.3 主入口：类型判断 + 分发

编排器的主入口做两件事：判断这个功能点是"录屏类型"还是其他类型（比如 07 章会提到的截图幻灯片类型），然后分发到对应的处理流程：

```bash
main() {
  local cmd="$1"; local dir=$(resolve_dir "$2")

  case "$cmd" in
    record)  cmd_record "$dir" ;;
    codegen) cmd_codegen "$dir" ;;
    sync)    cmd_sync "$dir" ;;
    srt)     extract_srt "$dir" ;;
    dub)     srt_to_dub "$dir" ;;
    redub)   cmd_redub "$dir" ;;
    mix)     compose "$dir" ;;
    burn)    cmd_burn "$dir" ;;
    trans)   translate_srt "$dir" ;;
    en)      cmd_en "$dir" ;;
    all)     cmd_all "$dir" ;;
    status)  show_status "$dir" ;;
    *) echo "未知命令: $cmd"; exit 1 ;;
  esac
}
```

`cmd_all` 内部按类型分流，並且在真正开始 `srt → dub → mix` 之前，会先做一次环境自检（ffmpeg、语音识别依赖是否齐全），提前把"环境没装好"这类问题暴露出来，而不是跑到中途才报错：

```bash
cmd_all() {
  local dir="$1"
  check_env || return 1
  extract_srt "$dir" || return 1
  srt_to_dub "$dir" || return 1
  compose "$dir"
  show_status "$dir"
}
```

## 9.4 配置：三级合并的 meta.json，而不是一份扁平配置

每个功能点的展示层配置（标题、发音人、是否要封面/BGM、字幕样式、分辨率）用 `meta.json` 表达，采用**三级合并**：内置默认值 → 项目级 `meta.json`（放在所有功能点的共同父目录，团队统一规范放这里）→ 功能级 `meta.json`（只覆盖这一个功能点的个性化配置）。

```python
def load_meta(feature_dir: str) -> dict:
    project_dir = os.path.dirname(feature_dir)
    defaults = {
        "voice": "zh-CN-XiaoxiaoNeural", "voice_en": "en-US-AvaNeural",
        "cover": None, "outro": None, "cover_duration": 3, "outro_duration": 3,
        "bgm": None, "bgm_volume": 0.15,
        "resolution": "1920x1080", "fps": 30, "dub_offset": 0,
    }
    project_cfg = read_json(f"{project_dir}/meta.json")
    feature_cfg = read_json(f"{feature_dir}/meta.json")
    merged = deep_merge(defaults, project_cfg)
    merged = deep_merge(merged, feature_cfg)
    return merged
```

这个三级合并解决的实际问题是：**大部分配置项，一个项目里所有功能点都应该统一**（品牌字体、字幕样式、要不要加公司 logo），只有少数几项需要针对某个功能点单独调整（这一条视频的标题、要不要额外加背景音乐）。项目级配置承担"统一规范"的角色，功能级配置只用来处理例外，不需要每个功能点都把全部配置项抄一遍。

`resolve_asset`（8.5 节提到的"素材存在不代表要用"）也是这个配置系统的一部分——它同时查功能目录和项目级 `resources/` 目录，但只有配置里显式打开开关才会真正采用查到的文件。

## 9.5 幂等性与增量跳过

`vt all`（或者幻灯片模式下的合成命令）在重复运行时会做增量检查：如果所有输入素材（录像、字幕、配音、meta.json）都没有比上一次的成片更新，直接跳过合成，不重复消耗时间：

```bash
should_skip_rebuild() {
  local dir="$1"
  local out="$dir/$(basename "$dir").mp4"
  [ ! -f "$out" ] && return 1  # 还没生成过，不跳过

  for src in "$dir/recording.mov" "$dir/subtitles.srt" "$dir/ai_dub.wav" "$dir/meta.json"; do
    [ -f "$src" ] && [ "$src" -nt "$out" ] && return 1  # 有输入比成片新，不跳过
  done
  return 0  # 全部没变化，跳过
}
```

这个检查配合 `-u/--force` 一类的强制重跑开关（需要的时候可以绕过跳过逻辑），让批量处理多个功能点时（比如 CI 里跑一遍全部功能点检查是否都能正常出片）不会做无意义的重复工作。

## 9.6 小结

本章的编排器设计非常朴素：一个 `main` 函数按命令分发、几个字符串约定的文件名表达状态、一个三级合并的 JSON 做配置。没有引入任务队列、没有引入状态机框架、没有引入数据库——**朴素到几乎不需要文档就能读懂的实现，恰恰是它能被快速理解、快速改、快速排障的原因**。11 章会讲这套朴素设计在批量处理、CI 集成场景下要做哪些补充；16 章开始会讲清楚，这些命令背后，有多少工作其实是交给 AI 完成的。
