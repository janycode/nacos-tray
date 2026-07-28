# AGENTS.md

Windows 系统托盘小工具，监控 Nacos 服务注册中心。零外部 Python 依赖（纯标准库）。

## 运行

```bash
pythonw main.py          # 无控制台窗口
python main.py           # 调试模式
```

`start.bat` / `debug.bat` 在 PATH 或硬编码路径中查找 `pythonw.exe` / `python.exe`。

## 打包（两种互斥方式，不要同时使用）

1. **PyInstaller**（推荐）: `pyinstaller NacosTray_pyinstaller.spec` → `dist/NacosTray_pyinstaller.exe`

```sh
# 打包（带控制台，如不需要带控制台则去掉 --console 或者把它换成 --windowed）
pyinstaller --onefile --console --name NacosTray_v2 --add-data "nacos.ico;." main.py
# 命令窗内运行(带日志)
.\dist\NacosTray_v2.exe
```



2. **IExpress/SED**: `NacosTray.sed`（或 `_make.sed`，会加自定义 Python PATH）。需 `iexpress.exe`。生成 `output/NacosTray.exe`。
   `Launcher.cs` 是 C# 自解压启动器，从 exe 末尾读取 zip 解压到 `%TEMP%\NacosTray`，找 `pythonw.exe` 启动 `main.py`。



## 架构

| 文件 | 职责 |
|---|---|
| `main.py` | 入口。`NacosTrayApp` 编排登录、轮询、菜单、通知。内联定义了 `SettingsDialog`（tkinter）和 `NotesDialog`。 |
| `nacos_client.py` | Nacos **v3** Open API 客户端（`/v3/...`）。仅用 `urllib`。token 生命周期 20 分钟，硬编码于 line 47。403 时自动重登。 |
| `tray.py` | Win32 API 实现系统托盘。**隐藏窗口 + 守护线程 `GetMessageW` 消息循环。** |
| `tray_v2.py` | Win32 API 实现系统托盘。**用 tkinter 主窗口的 `winfo_id()` 作 hwnd + `PeekMessageW` 由 `tkinter.after()` 轮询。** |
| `config.py` | 读写 `data/config.json` 和 `data/notes.json`。管理 `HKCU\...\Run` 开机自启。配置路径相对于脚本文件（line 8）。 |
| `settings_gui.ps1` | 设置对话框（PowerShell Windows Forms）。子进程启动。 |
| `notes_gui.ps1` | IP 备注管理（PowerShell Windows Forms）。子进程启动。 |
| `settings.py` | 备选 tkinter 设置窗口。**`main.py` 未使用它**（内联了自己的 `SettingsDialog`）。 |

## 关键细节

- **入口选择**: `main.py:19-22` 优先 `from tray_v2 import ...`，失败则回退 `from tray import ...`。
- **字符串风格**: `main.py` 刻意用 `+` 拼接和 `chr(10)` 换行（避免特定构建环境下 f-string 解析问题）。`nacos_client.py` 不在此限制内，使用 f-string。
- **Token 过期**: 硬编码 20 分钟（`nacos_client.py:47`），默认 `login_interval` 30 分钟。实际重登由 token 过期触发，而非间隔到期。
- **菜单回调 lambda**: `lambda s=inst: ...` 默认参数捕获模式避免闭包晚绑定问题（`main.py:264,266`）。
- **线程安全**: `tray.py` 在守护线程中运行消息循环；`tray_v2.py` 在 tkinter 主线程轮询。`main.py` 用 `threading.Lock` 保护 `self.services`。
- **设置/备注对话框**: 通过 `CREATE_NEW_CONSOLE` 启动 PowerShell 子进程 — 即发即忘。
- **`data/` 目录**: 存放 `config.json` 和 `notes.json`。首次保存时自动创建。配置路径硬编码相对于脚本文件位置。
- **无测试、无 lint、无 CI** — 独立桌面工具。

## 构建/调试脚本

`_write_main.py` / `_write_cs.py` / `_write_tray.py` / `_update_nacos.py` / `_update_tray.py` / `_fix.py` / `_fix2.py` 是代码生成和修补脚本（通过字符串拼接生成源文件）。不属于应用本身 — 仅在需要重新生成时运行。
