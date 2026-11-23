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
DND_FILE = CONFIG_DIR / "dnd.json"

DEFAULT_CARD_FIELDS = {
    "port": True,
    "online": True,
    "last_online": True,
    "note": True,
    "dnd": True,
}
DEFAULT_SHORTCUTS = {
    "refresh": "<F5>",
    "toggle_view": "<Control-Tab>",
    "open_settings": "<Control-comma>",
}

def _ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _try_decrypt_legacy(value):
    """尝试解密旧版 DPAPI 加密的密码，失败返回原值"""
    if not isinstance(value, str) or not value.startswith("::enc::"):
        return value
    try:
        import ctypes
        import ctypes.wintypes
        import base64

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        raw = base64.b64decode(value[6:])
        blob_in = DATA_BLOB()
        blob_out = DATA_BLOB()
        blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char))
        blob_in.cbData = len(raw)

        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return data.decode("utf-8")
    except Exception:
        pass
    return value


def load_config():
    _ensure_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["password"] = _try_decrypt_legacy(cfg.get("password", ""))
            cfg.setdefault("theme_mode", "system")
            cfg.setdefault("theme_preset", "qinglan")
            cfg.setdefault("theme_custom", {"light": "#F0F8FF", "dark": "#2B2B2B"})
            cfg.setdefault("theme_custom_accent", "qinglan")
            cfg.setdefault("view_mode", "table")
            cfg.setdefault("pinned_services", [])
            cfg.setdefault("card_columns", "auto")
            cfg.setdefault("card_density", "normal")
            cfg.setdefault("card_name_size", "normal")
            fields = cfg.get("card_fields")
            if not isinstance(fields, dict):
                fields = {}
            for field, default in DEFAULT_CARD_FIELDS.items():
                fields.setdefault(field, default)
            cfg["card_fields"] = fields
            cfg.setdefault("table_row_height", "normal")
            cfg.setdefault("table_striped", True)
            shortcuts = cfg.get("shortcuts")
            if not isinstance(shortcuts, dict):
                shortcuts = {}
            for action, default in DEFAULT_SHORTCUTS.items():
                shortcuts.setdefault(action, default)
            cfg["shortcuts"] = shortcuts
            return cfg
        except Exception:
            pass
    return {
        "ip": "your-nacos-server.com",
        "port": 8848,
        "username": "dev",
        "password": "1234567",
        "namespace": "dev2v",
        "cluster_name": "ShenZhen",
        "auto_start": False,
        "login_interval": 1800,
        "poll_interval": 30,
        "theme_mode": "system",
        "theme_preset": "qinglan",
        "theme_custom": {"light": "#F0F8FF", "dark": "#2B2B2B"},
        "theme_custom_accent": "qinglan",
        "view_mode": "table",
        "pinned_services": [],
        "card_columns": "auto",
        "card_density": "normal",
        "card_name_size": "normal",
        "card_fields": dict(DEFAULT_CARD_FIELDS),
        "table_row_height": "normal",
        "table_striped": True,
        "shortcuts": dict(DEFAULT_SHORTCUTS),
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


def load_dnd():
    _ensure_dir()
    if DND_FILE.exists():
        try:
            with open(DND_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_dnd(dnd):
    _ensure_dir()
    with open(DND_FILE, "w", encoding="utf-8") as f:
        json.dump(dnd, f, ensure_ascii=False, indent=2)


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
