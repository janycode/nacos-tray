# config.py - 配置管理模块
import json
import os
import shutil
import sys
from pathlib import Path

# 配置文件存放在 exe 同级目录下的 .tray-notify 文件夹
if getattr(sys, "frozen", False):
    _BASE = Path(os.path.dirname(os.path.abspath(sys.executable)))
else:
    _BASE = Path(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = _BASE / ".tray-notify"
LEGACY_CONFIG_DIR = _BASE / ".nacos-tray"
CONFIG_FILE = CONFIG_DIR / "config.json"
NOTES_FILE = CONFIG_DIR / "notes.json"
DND_FILE = CONFIG_DIR / "dnd.json"
JENKINS_STATE_FILE = CONFIG_DIR / "jenkins_state.json"

RUN_KEY = "TrayNotify"
LEGACY_RUN_KEY = "NacosTray"

# 外观默认风格的一次性迁移标记：缺少该键的配置首次启动会被切到岛仔风
STYLE_MIGRATION_KEY = "style_migration_v1"
DEFAULT_THEME_PRESET = "daozai"

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

DEFAULT_NACOS = {
    "enabled": True,
    "ip": "",
    "port": 8848,
    "username": "nacos",
    "password": "",
    "namespace": "",
    "cluster_name": "ShenZhen",
    "env": "",
    "login_interval": 1800,
    "poll_interval": 30,
}
DEFAULT_JENKINS = {
    "enabled": False,
    "url": "",
    "username": "",
    "password": "",
    "verify_ssl": True,
    "include": "",
    "exclude": "",
    "poll_interval": 30,
    "notify_start": True,
    "notify_success": True,
    "notify_failure": True,
}
DEFAULT_NOTIFY = {
    "style": "default",
    "daozai_enabled": False,
    "daozai_credentials": "",
}

_LEGACY_NACOS_KEYS = (
    "ip", "port", "username", "password", "namespace",
    "cluster_name", "login_interval", "poll_interval",
)


def _migrate_source_enabled(cfg):
    """兼容旧配置：enabled 缺省时按是否已填写连接信息推断"""
    nacos = cfg.get("nacos")
    if isinstance(nacos, dict) and "enabled" not in nacos:
        nacos["enabled"] = bool(nacos.get("ip"))
    jenkins = cfg.get("jenkins")
    if isinstance(jenkins, dict) and "enabled" not in jenkins:
        jenkins["enabled"] = bool(jenkins.get("url"))
    return cfg


def _ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_dir():
    """旧版 .nacos-tray 目录一次性复制到 .tray-notify，旧文件保留"""
    if CONFIG_DIR.exists() or not LEGACY_CONFIG_DIR.exists():
        return
    try:
        shutil.copytree(LEGACY_CONFIG_DIR, CONFIG_DIR)
    except Exception:
        _ensure_dir()


def _merge_defaults(stored, defaults):
    merged = dict(defaults)
    if isinstance(stored, dict):
        for key, value in stored.items():
            merged[key] = value
    return merged


def _default_config():
    return {
        "nacos": dict(DEFAULT_NACOS),
        "jenkins": dict(DEFAULT_JENKINS),
        "notify": dict(DEFAULT_NOTIFY),
        "auto_start": False,
        "theme_mode": "system",
        "theme_preset": DEFAULT_THEME_PRESET,
        "theme_custom": {"light": "#F0F8FF", "dark": "#2B2B2B"},
        "theme_custom_accent": DEFAULT_THEME_PRESET,
        "theme_frosted_glass": False,
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


def _migrate_source_config(cfg):
    """把旧版扁平 Nacos 字段迁移到 nacos 子对象"""
    if isinstance(cfg.get("nacos"), dict):
        return cfg, False
    nacos = {}
    for key in _LEGACY_NACOS_KEYS:
        if key in cfg:
            nacos[key] = cfg.pop(key)
    cfg["nacos"] = nacos
    cfg.setdefault("jenkins", {})
    cfg.setdefault("notify", {})
    return cfg, True


def load_config():
    _migrate_legacy_dir()
    _ensure_dir()
    cfg = None
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = None
    if not isinstance(cfg, dict):
        cfg = _default_config()
    cfg, migrated = _migrate_source_config(cfg)
    cfg["nacos"] = _merge_defaults(cfg.get("nacos"), DEFAULT_NACOS)
    cfg["jenkins"] = _merge_defaults(cfg.get("jenkins"), DEFAULT_JENKINS)
    cfg["notify"] = _merge_defaults(cfg.get("notify"), DEFAULT_NOTIFY)
    _migrate_source_enabled(cfg)
    cfg["nacos"]["password"] = _try_decrypt_legacy(cfg["nacos"].get("password", ""))
    cfg["jenkins"]["password"] = _try_decrypt_legacy(cfg["jenkins"].get("password", ""))
    cfg.setdefault("theme_mode", "system")
    cfg.setdefault("theme_preset", DEFAULT_THEME_PRESET)
    cfg.setdefault("theme_custom", {"light": "#F0F8FF", "dark": "#2B2B2B"})
    cfg.setdefault("theme_custom_accent", DEFAULT_THEME_PRESET)
    cfg.setdefault("theme_frosted_glass", False)
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
    if STYLE_MIGRATION_KEY not in cfg:
        cfg["theme_preset"] = DEFAULT_THEME_PRESET
        cfg[STYLE_MIGRATION_KEY] = True
        migrated = True
    if migrated:
        try:
            save_config(cfg)
        except Exception:
            pass
    return cfg


def save_config(config):
    _ensure_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _migrate_namespaced(raw):
    if not isinstance(raw, dict):
        raw = {}
    if "nacos" in raw or "jenkins" in raw:
        nacos = raw.get("nacos")
        jenkins = raw.get("jenkins")
        return {
            "nacos": dict(nacos) if isinstance(nacos, dict) else {},
            "jenkins": dict(jenkins) if isinstance(jenkins, dict) else {},
        }
    return {"nacos": dict(raw), "jenkins": {}}


def load_notes():
    """加载备注，按来源分为 nacos / jenkins"""
    _migrate_legacy_dir()
    _ensure_dir()
    raw = {}
    if NOTES_FILE.exists():
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
    notes = _migrate_namespaced(raw)
    if isinstance(raw, dict) and "nacos" not in raw and "jenkins" not in raw:
        try:
            save_notes(notes)
        except Exception:
            pass
    return notes


def save_notes(notes):
    _ensure_dir()
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def load_dnd():
    """加载免打扰，按来源分为 nacos / jenkins"""
    _migrate_legacy_dir()
    _ensure_dir()
    raw = {}
    if DND_FILE.exists():
        try:
            with open(DND_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
    dnd = _migrate_namespaced(raw)
    if isinstance(raw, dict) and "nacos" not in raw and "jenkins" not in raw:
        try:
            save_dnd(dnd)
        except Exception:
            pass
    return dnd


def save_dnd(dnd):
    _ensure_dir()
    with open(DND_FILE, "w", encoding="utf-8") as f:
        json.dump(dnd, f, ensure_ascii=False, indent=2)


def load_jenkins_state():
    _migrate_legacy_dir()
    _ensure_dir()
    if JENKINS_STATE_FILE.exists():
        try:
            with open(JENKINS_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if isinstance(state, dict):
                jobs = state.get("jobs")
                if not isinstance(jobs, dict):
                    jobs = {}
                state["jobs"] = {
                    key: value for key, value in jobs.items()
                    if isinstance(value, dict)
                }
                state.setdefault("last_success", "")
                state.setdefault("last_error", "")
                return state
        except Exception:
            pass
    return {"jobs": {}, "last_success": "", "last_error": ""}


def save_jenkins_state(state):
    _ensure_dir()
    with open(JENKINS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _read_run_value(name):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, name)
            return value
        finally:
            winreg.CloseKey(key)
    except Exception:
        return None


def _delete_run_value(name):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass


def is_auto_start():
    """检查是否已设置开机自启，兼容旧键名"""
    return _read_run_value(RUN_KEY) is not None or _read_run_value(LEGACY_RUN_KEY) is not None


def migrate_auto_start_key():
    """把旧版 NacosTray 键改名为 TrayNotify，保留原有启动路径"""
    old_value = _read_run_value(LEGACY_RUN_KEY)
    if old_value is None:
        return False
    if _read_run_value(RUN_KEY) is None:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            try:
                winreg.SetValueEx(key, RUN_KEY, 0, winreg.REG_SZ, old_value)
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
    _delete_run_value(LEGACY_RUN_KEY)
    return True


def set_auto_start(enable):
    """设置/取消开机自启，写入新键名并清理旧键名"""
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
            winreg.SetValueEx(key, RUN_KEY, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, RUN_KEY)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        _delete_run_value(LEGACY_RUN_KEY)
        return True
    except Exception as e:
        print(f"设置开机自启失败: {e}")
        return False
