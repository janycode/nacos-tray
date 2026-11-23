# Nacos Tray

[![Latest Release](https://img.shields.io/github/v/release/janycode/nacos-tray?display_name=tag&label=release)](https://github.com/janycode/nacos-tray/releases/latest)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![Nacos](https://img.shields.io/badge/Nacos-v3.x-00B4D8)

Windows 系统托盘小工具，用来监控 Nacos 注册中心的服务与实例状态，并在实例上线、下线或移除时弹出通知。运行时零第三方 Python 依赖，打包为单个 exe。

## 功能特性

- **服务监控**：定时轮询 Nacos，展示服务、实例、端口、在线状态与最近上线时间。
- **表格 / 卡片双视图**：表格按实例逐行展示；卡片按服务分组，一屏查看一个服务的全部实例。
- **置顶服务**：钉住日常关注的服务，表格、卡片和托盘弹窗统一置顶排序。
- **悬浮详情**：表格的信息列或卡片的信息图标上悬停，查看实例权重、集群、临时/持久、元数据等完整信息。
- **上下线管理**：右键菜单、双击表格行或点击卡片实例执行上线/下线，操作前确认。
- **IP 备注与免打扰**：为 IP 配置备注名，按 IP 维度开启通知免打扰。
- **主题系统**：跟随系统 / 亮色 / 暗色，内置 8 套配色预设，支持自定义亮暗背景色。
- **统一设置面板**：连接、行为、外观、快捷键、备注、关于六个页面集中在一个入口。
- **可配置快捷键**：刷新、切换视图、打开设置均可自定义。
- **托盘快捷弹窗**：右键托盘图标查看服务列表并直接切换状态。

## 适用版本

- Windows 10 / 11
- Nacos **v3.x**（基于 `/v3/...` Open API，推荐 v3.2.1+）

## 下载与运行

### 直接使用

从 [Releases](https://github.com/janycode/nacos-tray/releases/latest) 下载最新的 `NacosTray_vX.Y.exe`，双击运行即可，无需安装 Python。

首次启动后：

1. 托盘出现 Nacos Tray 图标。
2. 右键托盘图标，在弹窗底部点击 **设置**。
3. 填写 Nacos 地址、端口、命名空间、用户名和密码，点击 **测试连接**。
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
| 右键托盘图标 | 打开服务快捷弹窗，按服务分组展示实例 |
| 点击实例行 | 确认后执行上线 / 下线 |
| 弹窗底部按钮 | 还原窗口 / 设置 / 刷新 / 退出 |
| 气泡通知 | 实例上线、下线、移除时触发 |

置顶服务在托盘弹窗中带有钉标，并使用强调色和更大的服务名。

### 主窗口

顶部只保留 Nacos 地址标题和右上角齿轮入口，视图切换、备注、关于等都收在设置面板里。

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
| 连接 | Nacos IP、端口、命名空间、集群、用户名、密码；密码支持按住眼睛图标查看；测试连接 |
| 行为 | 开机自动启动、登录刷新间隔、状态轮询间隔 |
| 外观 | 主题模式、配色预设、自定义颜色、视图模式、卡片样式、表格样式 |
| 快捷键 | 刷新、切换表格/卡片、打开设置；支持捕获、清空、冲突提示和恢复默认 |
| 备注 | 内嵌 IP 备注管理，新增/编辑/删除后立即保存 |
| 关于 | 版本、兼容范围、作者、邮箱与更新记录 |

**外观设置**

- 主题：跟随系统 / 亮色 / 暗色。
- 配色：8 套预设 + 自定义亮暗背景色。
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

配置保存在 **exe 同级目录** 的 `.nacos-tray` 文件夹中；源码运行时位于项目根目录。

| 文件 | 说明 |
|---|---|
| `.nacos-tray/config.json` | Nacos 连接、轮询间隔、主题、视图、卡片/表格样式、快捷键 |
| `.nacos-tray/notes.json` | IP 备注 |
| `.nacos-tray/dnd.json` | 免打扰 IP 列表 |

- 配置随 exe 移动：换电脑或换目录时，把 `.nacos-tray` 一起带走即可。
- 启动时会自动识别本机 IP 并写入备注。
- `config.json` 中的 `pinned_services`、`view_mode`、`shortcuts` 等字段缺失时会自动补默认值。

## 构建

```bash
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean NacosTray_v1.7.spec
```

产物位于 `dist/NacosTray_v1.7.exe`。

不使用 spec 时也可以直接构建：

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name NacosTray_v1.7 --icon nacos.ico --add-data "nacos.ico;." main.py
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

Actions 会在 Windows runner 上构建单文件 exe，从 `CHANGELOG` 提取当前版本的更新内容，创建 GitHub Release 并上传 `NacosTray_vX.Y.exe`。

## 项目结构

| 文件 / 目录 | 职责 |
|---|---|
| `main.py` | 主窗口、表格/卡片视图、设置面板、托盘弹窗、悬浮详情 |
| `theme.py` | 明暗主题、配色预设、自定义配色、ttk 样式、暗色标题栏 |
| `config.py` | 配置、备注、免打扰与开机自启读写 |
| `nacos_client.py` | Nacos v3 Open API 客户端，token 过期自动重登 |
| `tray.py` / `tray_v2.py` | Win32 系统托盘实现 |
| `NacosTray_v1.7.spec` | 当前版本 PyInstaller 打包配置 |
| `.github/workflows/release.yml` | 标签触发的自动构建与发布 |
| `docs/adr/` | 架构决策记录 |
| `GLOSSARY.md` | 领域术语表 |

## 常见问题

**Q: 换了 exe 位置后配置丢了？**
A: 配置在 exe 同级的 `.nacos-tray` 目录，移动 exe 时请把该目录一起移动。

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
