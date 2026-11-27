# 采用「岛仔风」作为默认外观

## Status

accepted

## Context

界面当前默认预设是「青蓝」（`theme.DEFAULT_PRESET`、`config._default_config()` 均为 `qinglan`），已有 8 套预设。整体观感特征：强调色偏冷（蓝/绿/紫）；顶部条在亮色下用强调色整条填充；圆角只出现在自绘气泡上；图标混用 `Segoe MDL2 Assets` 字形与 emoji；间距、字号没有统一标度；托盘弹窗、右键菜单、工具提示都是直角 `Toplevel`。

需求要求参考岛仔（<https://github.com/Renly1994/xiaotang-daozai>，Rust + egui 桌面小工具）的视觉语言做整体美化，并且**将该风格设为默认**，而不是新增一个可选项。

硬约束：零第三方 Python 依赖、纯 tkinter（ctypes 可调 DWM）、单文件 exe；监控工具的信息密度不能为造型让步。

命名提示：仓库已存在「岛仔推送」这一通知出口（`daozai_sink.py`、`notify.daozai_enabled` / `notify.daozai_credentials`），与外观风格同名但属于不同概念，落地时需要避免混淆。

## Decision

1. 新增配色预设 id `daozai`，显示名「岛仔风」，并**改为默认预设**：`theme.DEFAULT_PRESET` 与 `config._default_config()["theme_preset"]` 均改为 `daozai`。原有 8 套预设保留，仍可手动选择。**升级用户一次性强制迁移**：`config.load_config()` 检测到配置缺少一次性标记 `style_migration_v1` 时，把 `theme_preset` 覆写为 `daozai`，写入该标记后再保存；标记存在后不再干预，用户可自由改回其他预设。新装与旧装行为一致，且不会重复迁移。
2. 该预设同时定义亮、暗两套取值：暗 = 「经典黑」，亮 = 「奶油」。强调色由冷色改为**珊瑚红 `#E5484D`**。
3. 外观骨架为**所有预设共用**，不随预设切换而变：表面三级（`bg_main` / `bg_card` / `bg_row_alt`）、1px 发丝描边（`separator`）、圆角档位（控件 8 / 卡片 12 / 浮层 12–16）、统一字体层级、统一图标尺寸档位。切预设只换颜色，不改骨架。
4. 顶部条改为低饱和处理：亮、暗两种模式都使用表面色作底，强调色只用于选中项与动作，不再整条填充强调色。**此条修订 ADR-0001 第 6 条**（「顶部条亮色下沿用强调色填充」）。
5. 图标以 `Segoe MDL2 Assets` 线性字形为准（`main.py:_ICON_FONT` / `_ICON_GLYPHS`），把界面内的 emoji 字形收敛成一张固定的线性符号表；尺寸统一为 11 / 13 / 16 三档；字体缺失时用 Unicode 符号兜底。
6. 浮层材质默认走**高仿质感**：卡片面 + 发丝描边 + 圆角。真毛玻璃（Win11 `DWMWA_SYSTEMBACKDROP_TYPE` = MICA / ACRYLIC）作为**可选开关**，仅浮层启用，调用失败或 Win10 下自动关闭。
7. 形态边界：主窗口与设置面板**保持系统矩形外框**，不使用 `-transparentcolor` 抠色做 shaped window；胶囊感集中在浮层（托盘弹窗、自定义菜单、工具提示、气泡）。理由是主窗口承载密集表格，且 shaped window 对焦点、多屏、DPI 有已知风险。

### 预设取值

暗色（经典黑）：

| 语义色 | 取值 |
|---|---|
| primary | `#E5484D` |
| primary_dark | `#C93E43` |
| primary_darker | `#A93337` |
| secondary | `#23272D` |
| bg_main | `#0B0D10` |
| bg_card | `#15181D` |
| bg_row_alt | `#191D23` |
| text_primary | `#EDEFF2` |
| text_secondary | `#98A1AB` |
| separator | `#25292F` |
| header_text | `#FFFFFF` |

亮色（奶油）：

| 语义色 | 取值 |
|---|---|
| primary | `#D63A3F` |
| primary_dark | `#BC3035` |
| primary_darker | `#9E282C` |
| secondary | `#EFE6D8` |
| bg_main | `#F7F2E9` |
| bg_card | `#FFFDF7` |
| bg_row_alt | `#F0E9DC` |
| text_primary | `#22201E` |
| text_secondary | `#6E6960` |
| separator | `#E6DCCC` |
| header_text | `#FFFFFF` |

（`primary` 已按 `theme.ensure_contrast` 做过可读性校正的预期取值；实际实现由派生函数微调。）

### 字体与尺寸标度

| 用途 | 字号 |
|---|---|
| 指标数字 / 大标题 | 18–20 bold |
| 区块标题 / 卡片标题 | 12 bold |
| 正文 / 设置项 | 10 |
| 次要说明 / 表格 | 9 |
| 微型标签（来源、时间戳） | 8 |

圆角：控件 8、卡片 12、浮层 12–16、气泡 12。间距基准：4 / 8 / 12 / 16。

## Considered Options

- **只新增一套可选预设**：被「作为默认风格生效」直接否定。
- **主窗口也做成 shaped 胶囊**：需要 `overrideredirect` + 自绘标题栏 + 自绘最小化/关闭，且表格信息密度被圆角挤压；风险收益不匹配。
- **引入 ttkbootstrap / PySide**：视觉上限更高，但违背零依赖与单 exe 定位，且等于重写。
- **仅换配色不改骨架**：成本最低，但拿不到岛仔「克制、分层、圆角浮层」的主要观感，达不到需求。

## Consequences

- 已同步更新 [GLOSSARY.md](../../GLOSSARY.md)：「顶部条」「强调色」定义改为低饱和规则，并新增「浮层」词条。
- **强调色与状态色同为红系**：离线状态色（`#FF5252` / `#FF7B72`）与新强调色相邻。约定同一行内状态色优先，强调色退让——离线/告警行不使用珊瑚红文字，珊瑚红只出现在 chrome、选中态与主操作上。
- 迁移采用一次性标记键 `style_migration_v1`（见 Decision 1）：只影响升级后的首次启动，之后尊重用户显式选择。标记键缺失即视为未迁移，删掉该键可重新触发，便于验证。
- 预设 id 沿用 `daozai`，与既有「岛仔推送」（`notify.daozai_*`）分属不同设置页与配置路径；外观设置区通过显示名「岛仔风」区分。
- 更换默认预设不影响 `theme_mode`（跟随系统 / 亮色 / 暗色）与自定义配色能力。
