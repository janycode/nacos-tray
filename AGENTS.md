# AGENTS.md

Windows 系统托盘通知工具（Tray Notify Tool），包含 Nacos 与 Jenkins 两个通知源。零外部 Python 依赖（纯标准库）。

## 运行

```bash
pythonw main.py          # 无控制台窗口
python main.py           # 调试模式
```

`start.bat` / `debug.bat` 在 PATH 或硬编码路径中查找 `pythonw.exe` / `python.exe`。

## 打包（两种互斥方式，不要同时使用）

1. **PyInstaller**（推荐）: `pyinstaller TrayNotify_v2.0.spec` → `dist/TrayNotify_v2.0.exe`

```sh
# 打包（带控制台，如不需要带控制台则去掉 --console 或者把它换成 --windowed）
pyinstaller --onefile --console --name TrayNotify_v2.0 --add-data "nacos.ico;." main.py
# 命令窗内运行(带日志)
.\dist\TrayNotify_v2.0.exe
```



2. **IExpress/SED**: `NacosTray.sed`（或 `_make.sed`，会加自定义 Python PATH）。需 `iexpress.exe`。生成 `output/NacosTray.exe`。
   `Launcher.cs` 是 C# 自解压启动器，从 exe 末尾读取 zip 解压到 `%TEMP%\NacosTray`，找 `pythonw.exe` 启动 `main.py`。



## 架构

| 文件 | 职责 |
|---|---|
| `main.py` | 入口。`TrayNotifyApp` 编排两个通知源、主窗口来源切换、托盘、设置与通知中心。内联定义了 `SettingsDialog`（tkinter）和 `ServiceListPopup`。 |
| `nacos_client.py` | Nacos **v3** Open API 客户端（`/v3/...`）。仅用 `urllib`。token 生命周期 20 分钟，硬编码于 line 47。403 时自动重登。 |
| `jenkins_client.py` | Jenkins REST 客户端（Basic Auth）。递归展开文件夹/多分支，读取 `lastBuild` 与 `changeSet`，筛选有效提交。 |
| `jenkins_monitor.py` | Jenkins 独立轮询线程：基线、构建开始/结束事件、提交去重、连接失败降级，状态写 `jenkins_state.json`。 |
| `notifier.py` | 通知中心与三种自绘气泡（卡片浮窗、强调渐变、极简横幅）；默认样式走系统托盘气泡。跟随主题语义色。 |
| `tray.py` | Win32 API 实现系统托盘。**隐藏窗口 + 守护线程 `GetMessageW` 消息循环。** |
| `tray_v2.py` | Win32 API 实现系统托盘。**用 tkinter 主窗口的 `winfo_id()` 作 hwnd + `PeekMessageW` 由 `tkinter.after()` 轮询。** |
| `theme.py` | 主题模块。9 套亮暗配色预设（默认岛仔风）、自定义配色派生、系统明暗检测（每 5 秒读注册表）、ttk 样式、DWM 暗色标题栏与浮层毛玻璃、外观骨架 token 与补间动画。 |
| `config.py` | 读写 `.tray-notify/config.json`、`notes.json`、`dnd.json`、`jenkins_state.json`。管理 `HKCU\...\Run` 开机自启（键名 `TrayNotify`）。旧 `.nacos-tray` 自动迁移。 |
| `settings_gui.ps1` | 设置对话框（PowerShell Windows Forms）。子进程启动。 |
| `notes_gui.ps1` | IP 备注管理（PowerShell Windows Forms）。子进程启动。 |
| `settings.py` | 备选 tkinter 设置窗口。**`main.py` 未使用它**（内联了自己的 `SettingsDialog`）。 |

## 关键细节

- **入口选择**: `main.py` 优先 `from tray_v2 import ...`，失败则回退 `from tray import ...`。
- **字符串风格**: `main.py` 刻意用 `+` 拼接和 `chr(10)` 换行（避免特定构建环境下 f-string 解析问题）。`nacos_client.py` 不在此限制内，使用 f-string。
- **Token 过期**: 硬编码 20 分钟（`nacos_client.py:47`），默认 `login_interval` 30 分钟。实际重登由 token 过期触发，而非间隔到期。
- **菜单回调 lambda**: `lambda s=inst: ...` 默认参数捕获模式避免闭包晚绑定问题。
- **线程安全**: `tray.py` 在守护线程中运行消息循环；Nacos 与 Jenkins 各自独立轮询线程，UI 更新通过 `root.after` 回主线程。
- **配置分区**: `config.json` 内 `nacos` / `jenkins` / `notify` 子对象；备注与免打扰按 `nacos` / `jenkins` 命名空间存储。
- **`data/` 目录**: 旧版遗留；当前配置位于 `.tray-notify`。
- **无测试、无 lint、无 CI** — 独立桌面工具。
- **主题**: 配置项 `theme_mode` / `theme_preset` / `theme_custom` / `theme_custom_accent`；`COLORS` 是运行时可变字典，切换主题会重建主窗口内容并重开已打开的子窗口，设置窗口原地重建。

## 构建/调试脚本

`_write_main.py` / `_write_cs.py` / `_write_tray.py` / `_update_nacos.py` / `_update_tray.py` / `_fix.py` / `_fix2.py` 是代码生成和修补脚本（通过字符串拼接生成源文件）。不属于应用本身 — 仅在需要重新生成时运行。

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles, default strings, recorded as `Status:` lines. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
