# config.py - 配置管理模块
import json
import os
import sys
from pathlib import Path

# 配置文件存放在 exe 同级目录下的 .nacos-tray 文件夹
if getattr(sys, "frozen", False):
    _BASE = Path(os.path.dirname(os.path.abspath(sys.executable)))
else:
    _BASE = Path(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = _BASE / ".nacos-tray"
CONFIG_FILE = CONFIG_DIR / "config.json"
NOTES_FILE = CONFIG_DIR / "notes.json"

def _ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    _ensure_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "ip": "dev.leaderrun.org",
        "port": 8848,
        "username": "dev",
        "password": "1234567",
        "namespace": "dev2v",
        "auto_start": False,
        "login_interval": 1800,
        "poll_interval": 30,
    }

def save_config(config):
    _ensure_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def load_notes():
    """加载 IP 备注"""
    _ensure_dir()
    if NOTES_FILE.exists():
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_notes(notes):
    _ensure_dir()
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)

def is_auto_start():
    """检查是否已设置开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, "NacosTray")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False

def set_auto_start(enable):
    """设置/取消开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE)
        if enable:
            exe_path = os.path.abspath(sys.argv[0])
            if exe_path.endswith(".py"):
                # 如果是 .py 文件，用 pythonw 运行
                pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                if not os.path.exists(pythonw):
                    pythonw = sys.executable
                value = f'"{pythonw}" "{exe_path}"'
            else:
                value = f'"{exe_path}"'
            winreg.SetValueEx(key, "NacosTray", 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, "NacosTray")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"设置开机自启失败: {e}")
        return False
