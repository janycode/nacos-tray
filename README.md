# Tray Notify Tool

[![Latest Release](https://img.shields.io/github/v/release/janycode/nacos-tray?display_name=tag&label=release)](https://github.com/janycode/nacos-tray/releases/latest)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![Nacos](https://img.shields.io/badge/Nacos-v3.x-00B4D8)
![Jenkins](https://img.shields.io/badge/Jenkins-2.x-D24939)

Windows 系统托盘通知工具，把多个外部系统的状态变化汇总成桌面通知。当前包含 Nacos 与 Jenkins 两个通知源：Nacos 关注服务实例上下线，Jenkins 关注构建开始、成功与失败。运行时零第三方 Python 依赖，打包为单个 exe。

## 功能特性

- **双通知源**：Nacos 与 Jenkins 各自拥有独立的连接、行为与备注配置，一个来源失败不影响另一个。
- **服务监控**：定时轮询 Nacos，展示服务、实例、端口、在线状态与最近上线时间。
- **Jenkins 构建通知**：递归展开文件夹与多分支，支持包含/排除过滤；通知构建开始、成功与失败，并展示起止时间、用时、分支与新提交。
- **四种气泡样式**：默认通知（Windows 系统）、卡片浮窗、强调渐变、极简横幅；自绘样式跟随当前主题与配色预设，并带朝下尖角指向托盘图标。
- **表格 / 卡片双视图**：Nacos 支持表格与卡片；Jenkins 使用表格视图，支持搜索、免打扰与打开构建页。
- **置顶服务**：钉住日常关注的服务，表格、卡片和托盘弹窗统一置顶排序。
- **悬浮详情**：表格的信息列或卡片的信息图标上悬停，查看实例权重、集群、临时/持久、元数据等完整信息。
- **上下线管理**：右键菜单、双击表格行或点击卡片实例执行上线/下线，操作前确认。
- **备注与免打扰**：Nacos 按 IP、Jenkins 按 Job 配置备注名与免打扰。
- **主题系统**：跟随系统 / 亮色 / 暗色，内置 9 套配色预设（默认「岛仔风」），支持自定义亮暗背景色。
- **统一设置面板**：侧边栏按通知源分组（Nacos、Jenkins 各自的连接 / 行为 / 备注）与通用分组（常规、外观、快捷键、关于）。
- **可配置快捷键**：刷新、切换视图、打开设置均可自定义。
- **托盘双栏弹窗**：右键托盘图标，左栏查看 Nacos 服务、右栏查看 Jenkins 构建，点击 Jenkins 行打开构建页。

## 适用版本

- Windows 10 / 11
- Nacos **v3.x**（基于 `/v3/...` Open API，推荐 v3.2.1+）
- Jenkins **2.x**（使用账号密码 Basic Auth，无需单独填写 API Token）

## Nacos 通知

在 **设置 → 通知源 → Nacos** 中填写 IP、端口、命名空间、集群名、环境、用户名与密码：

- **连接**：IP、端口、命名空间、集群名、环境（不填默认 dev）、用户名、密码（支持显示切换）；提供「测试连接」。
- **行为**：登录刷新间隔与状态轮询间隔。
- **备注**：按实例 IP 配置别名与免打扰。

通知内容：

- **服务上线 / 下线 / 手动下线**：标题包含服务名与环境；正文包含项目（服务 [端口] IP）与环境等字段。
- **环境取值**：优先取实例自带的集群名，其次取连接设置中的「环境」，两者都没有时为 dev。
- 状态相对基线变化才通知，相同状态重复出现不通知。

## Jenkins 通知

在 **设置 → 通知源 → Jenkins** 中填写 Jenkins 地址、账号与密码：

- **连接**：地址、用户名、密码（支持显示切换）、是否校验 HTTPS 证书；提供「测试连接」查看可见 Job 数量。
- **行为**：轮询间隔（最小 10 秒）、包含 / 排除 Job（逗号分隔、匹配完整路径、排除优先）、构建开始 / 成功 / 失败三个通知开关。
- **备注**：按 Job 全名配置别名与免打扰。
- **列表顺序**：按最近构建时间倒序（越近越靠前），主界面表格与托盘右键弹窗一致。

通知内容：

- **构建开始**：项目名、构建号、开始时间、分支。
- **构建成功 / 失败**：项目名、构建号、开始与结束时间、总用时、分支，以及本次的新提交（提交号、说明、作者）。非成功结果一律按失败通知。
- 提交按 commit id 去重，只展示上次通知之后的新提交；没有新提交时不显示提交段。
- 首次观察某个 Job 或过滤规则变更后新入选的 Job 只建立基线，不补发历史通知。

## 下载与运行

### 直接使用

从 [Releases](https://github.com/janycode/nacos-tray/releases/latest) 下载最新的 `TrayNotify_vX.Y.exe`，双击运行即可，无需安装 Python。

首次启动后：

1. 托盘出现 Tray Notify Tool 图标。
2. 右键托盘图标，在弹窗底部点击 **设置**。
3. 在 **通知源 → Nacos** 或 **通知源 → Jenkins** 填写连接信息，点击 **测试连接**。
4. 保存后自动登录并开始轮询。

### 从源码运行

```bash
# 调试模式（带控制台输出）
python main.py

# 无控制台窗口
pythonw main.py
```

源码运行时只需要 Python 3.12 标准库，不需要安装其他运行依赖。

## 使用指南

### 托盘

| 操作 | 行为 |
|---|---|
| 双击托盘图标 | 还原主窗口 |
| 右键托盘图标 | 打开双栏快捷弹窗：左栏 Nacos 服务、右栏 Jenkins 构建 |
| 点击 Nacos 实例行 | 确认后执行上线 / 下线 |
| 点击 Jenkins 构建行 | 打开对应构建页 |
| 弹窗底部按钮 | 还原窗口 / 设置 / 刷新 / 退出 |
| 气泡通知 | Nacos 实例上下线、Jenkins 构建开始/成功/失败时触发 |

置顶服务在托盘弹窗中带有钉标，并使用强调色和更大的服务名；未配置 Jenkins 时右栏整列隐藏。

### 主窗口

顶部为应用名、Nacos / Jenkins 来源切换与右上角齿轮入口，视图切换、备注、关于等都收在设置面板里。

- 来源切换一次只显示一个通知源：Nacos 支持表格与卡片，Jenkins 使用表格。
- Jenkins 表格支持搜索别名 / Job 路径 / 分支，双击或右键打开构建页，右键可切换免打扰。
- 搜索框、F5 刷新、状态栏与托盘提示同时覆盖两个来源。

**表格视图**

| 列 | 说明 |
|---|---|
| 置顶 | 点击切换置顶，已置顶显示钉标 |
| 信息 | 悬停显示该服务及全部实例的完整信息 |
| 服务名 | Nacos 服务名称 |
| 实例 | IP 地址，有备注时显示为 `IP(备注名)` |
| 端口 | 实例端口 |
| 状态 | 在线 / 离线；免打扰时带静音标记 |
| 最近上线时间 | 该实例最近一次变为在线的时间 |

- 右键行打开跟随主题配色的上下文菜单：上线、下线、置顶、管理备注、免打扰、刷新。
- 双击行快速切换上下线；置顶列和信息列不会触发双击切换。
- 搜索框按服务名、IP、备注名或端口过滤。

**卡片视图**

- 一张卡片对应一个服务，卡内列出全部实例。
- 标题右侧依次为信息图标和置顶图标。
- 点击实例确认后上线/下线；右键卡片或实例打开同一套主题化菜单。
- 外观设置可控制每行列数、密度、服务名字号和显示字段；固定列数会强制生效。
- 卡片过窄时自动隐藏最近上线时间，悬浮详情中仍可查看。

### 设置面板

设置窗口使用左侧竖向导航，当前页面字号更大并带强调色。

| 页面 | 内容 |
|---|---|
| Nacos → 连接 | Nacos IP、端口、命名空间、集群、环境（不填默认 dev）、用户名、密码；密码支持按住眼睛图标查看；测试连接 |
| Nacos → 行为 | 登录刷新间隔、状态轮询间隔 |
| Nacos → 备注 | IP 备注与免打扰管理，新增/编辑/删除后立即保存 |
| Jenkins → 连接 | Jenkins 地址、用户名、密码、HTTPS 证书校验；测试连接会返回可见 Job 数量 |
| Jenkins → 行为 | 构建轮询间隔、包含/排除 Job、构建开始/成功/失败通知开关、最近成功与错误 |
| Jenkins → 备注 | Job 别名与免打扰管理 |
| 常规 | 开机自动启动 |
| 外观 | 主题模式、配色预设、自定义颜色、气泡样式、视图模式、卡片样式、表格样式 |
| 快捷键 | 刷新、切换表格/卡片、打开设置；支持捕获、清空、冲突提示和恢复默认 |
| 关于 | 版本、通知源、作者、邮箱与更新记录 |

**外观设置**

- 主题：跟随系统 / 亮色 / 暗色。
- 配色：9 套预设（默认岛仔风）+ 自定义亮暗背景色。
- 通知：默认通知（Windows 系统）、卡片浮窗、强调渐变、极简横幅；自绘样式跟随当前主题与配色。
- 视图：表格 / 卡片，保存后立即切换并持久化。
- 卡片：每行列数（自动 / 1 / 2 / 3）、密度（紧凑 / 标准 / 宽松）、服务名字号（小 / 标准 / 大 / 特大）、显示字段。
- 表格：行高（紧凑 / 标准 / 宽松）、斑马纹开关。

### 默认快捷键

| 动作 | 默认快捷键 |
|---|---|
| 刷新 | `F5` |
| 切换表格 / 卡片 | `Ctrl+Tab` |
| 打开设置 | `Ctrl+,` |

快捷键只在主窗口获得焦点时生效，可在 **设置 → 快捷键** 中修改。清空表示禁用；两个动作不允许绑定同一个按键。

## 配置文件

配置保存在 **exe 同级目录** 的 `.tray-notify` 文件夹中；源码运行时位于项目根目录。

| 文件 | 说明 |
|---|---|
| `.tray-notify/config.json` | Nacos / Jenkins 连接与行为、气泡样式、主题、视图、卡片/表格样式、快捷键 |
| `.tray-notify/notes.json` | Nacos IP 与 Jenkins Job 备注 |
| `.tray-notify/dnd.json` | 按来源分开的免打扰列表 |
| `.tray-notify/jenkins_state.json` | Jenkins 构建基线与已通知提交 |

- 配置随 exe 移动：换电脑或换目录时，把 `.tray-notify` 一起带走即可；旧版 `.nacos-tray` 会在首次启动时自动迁移。
- 启动时会自动识别本机 IP 并写入备注。
- `config.json` 中的 `nacos`、`jenkins`、`notify` 与界面字段缺失时会自动补默认值。

## 构建

```bash
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean TrayNotify_v2.0.spec
```

产物位于 `dist/TrayNotify_v2.0.exe`。

不使用 spec 时也可以直接构建：

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name TrayNotify_v2.0 --icon nacos.ico --add-data "nacos.ico;." main.py
```

## 自动发布

仓库已配置标签触发的 Release 工作流：`.github/workflows/release.yml`。

发布新版本：

1. 更新 `main.py` 中的 `APP_VERSION` 和 `CHANGELOG`。
2. 提交并推送 `main`。
3. 创建并推送版本标签：

```bash
git tag vX.Y
git push origin vX.Y
```

Actions 会在 Windows runner 上构建单文件 exe，从 `CHANGELOG` 提取当前版本的更新内容，创建 GitHub Release 并上传 `TrayNotify_vX.Y.exe`。

## 项目结构

| 文件 / 目录 | 职责 |
|---|---|
| `main.py` | 主窗口、来源切换、Nacos 表格/卡片、Jenkins 表格、设置面板、托盘弹窗、悬浮详情 |
| `theme.py` | 明暗主题、配色预设、自定义配色、ttk 样式、暗色标题栏 |
| `config.py` | 配置、备注、免打扰、Jenkins 状态与开机自启读写 |
| `nacos_client.py` | Nacos v3 Open API 客户端，token 过期自动重登 |
| `jenkins_client.py` | Jenkins REST 客户端，递归 Job 发现、构建信息与提交筛选 |
| `jenkins_monitor.py` | Jenkins 独立轮询线程、基线、事件与降级 |
| `notifier.py` | 通知中心与三种自绘气泡，跟随主题语义色，尖角指向托盘图标 |
| `tray.py` / `tray_v2.py` | Win32 系统托盘实现（v2 含图标矩形查询） |
| `TrayNotify_v2.0.spec` | 当前版本 PyInstaller 打包配置 |
| `.github/workflows/release.yml` | 标签触发的自动构建与发布 |
| `docs/adr/` | 架构决策记录 |
| `GLOSSARY.md` | 领域术语表 |

## 常见问题

**Q: 换了 exe 位置后配置丢了？**
A: 配置在 exe 同级的 `.tray-notify` 目录，移动 exe 时请把该目录一起移动；旧版 `.nacos-tray` 会自动迁移。

**Q: 快捷键没有反应？**
A: 快捷键只在主窗口获得焦点时生效；请确认没有被清空，并检查设置中是否与其他动作冲突。

**Q: 支持 Nacos v2 吗？**
A: 不支持。客户端使用 Nacos v3 的 `/v3/...` Open API，建议 Nacos v3.2.1+。

**Q: 托盘图标消失了？**
A: 重新运行 exe。若频繁消失，先检查 Nacos 连接和程序日志。

**Q: 开机自启在哪里配置？**
A: 设置 → 行为 → 开机自动启动。程序会写入 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`。

**Q: exe 为什么有十几 MB？**
A: PyInstaller 单文件模式内置了 Python 运行时和 Tcl/Tk，因此体积较大，但无需额外安装环境。

## 作者

JiangYuan · yuan62387@qq.com
