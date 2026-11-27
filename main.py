"""
main.py - Tray Notify Tool Main Application
"""
import sys
import os
import time
import threading
import json
import traceback
import ctypes
import ctypes.wintypes
import tkinter as tk
import webbrowser
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import theme as theme_mod
import notifier as notifier_mod
import daozai_sink
from nacos_client import NacosClient
from jenkins_client import (
    JenkinsClient, format_commit_line, format_duration, format_timestamp,
    normalize_base_url, select_display_commits,
)
from jenkins_monitor import JenkinsMonitor

APP_NAME = "Tray Notify Tool"
APP_VERSION = "v2.1"

SOURCE_NACOS = "nacos"
SOURCE_JENKINS = "jenkins"
SOURCE_LABELS = [(SOURCE_NACOS, "Nacos"), (SOURCE_JENKINS, "Jenkins")]

try:
    from tray_v2 import TrayIcon
except ImportError:
    from tray import TrayIcon


def show_error(msg):
    try:
        ctypes.windll.user32.MessageBoxW(0, str(msg), APP_NAME + " Error", 0x10)
    except:
        print("ERROR: " + str(msg))


def _icon_path():
    paths = []
    if getattr(sys, "frozen", False):
        paths.append(os.path.join(sys._MEIPASS, "nacos.ico"))
    paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nacos.ico"))
    paths.append(os.path.join(os.getcwd(), "nacos.ico"))
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def _set_icon(window):
    ipath = _icon_path()
    if ipath:
        try:
            window.iconbitmap(ipath)
        except:
            pass

def _center_on_parent(window, parent):
    window.update_idletasks()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    ww = window.winfo_width()
    wh = window.winfo_height()
    x = px + (pw - ww) // 2
    y = py + (ph - wh) // 2
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = max(0, min(x, screen_w - ww))
    y = max(0, min(y, screen_h - wh - 40))
    window.geometry("+" + str(x) + "+" + str(y))


def _center_on_screen(window):
    window.update_idletasks()
    w = window.winfo_width()
    h = window.winfo_height()
    x = (window.winfo_screenwidth() - w) // 2
    y = (window.winfo_screenheight() - h) // 2
    window.geometry(f"+{x}+{y}")


# ==================== 线性图标 ====================
# 集中符号表：每个键对应 (Segoe MDL2 Assets 字形, Unicode 线性回退)。
# 尺寸只取 theme.ICON_SIZE_TIERS 的 11 / 13 / 16 三档，与相邻文字保持同一层级。
_ICON_FONT = "Segoe MDL2 Assets"
_ICON_GLYPHS = {
    "settings": ("\uE713", "设置"),   # 齿轮
    "eye": ("\uE890", "显示"),        # 密码显隐
    "pin": ("\uE718", "◆"),           # 置顶
    "unpin": ("\uE77A", "◇"),         # 取消置顶
    "info": ("\uE946", "◎"),          # 信息
    "play": ("\uE768", "▲"),          # 快捷上线
    "pause": ("\uE769", "▼"),         # 快捷下线
    "restore": ("\uE923", "□"),       # 还原窗口
    "refresh": ("\uE72C", "刷新"),
    "power": ("\uE7E8", "退出"),
    "search": ("\uE721", "搜索"),
    "folder": ("\uE8B7", "浏览"),
    "close": ("\uE8BB", "×"),
    "copy": ("\uE8C8", "复制"),
}
_ICON_SIZE_SM = theme_mod.ICON_SIZE_TIERS[0]
_ICON_SIZE_MD = theme_mod.ICON_SIZE_TIERS[1]
_ICON_SIZE_LG = theme_mod.ICON_SIZE_TIERS[2]
_ICON_FONT_CACHE = []


def _normalize_shortcut(sequence):
    if not isinstance(sequence, str):
        return ""
    seq = sequence.strip()
    if not seq:
        return ""
    if not (seq.startswith("<") and seq.endswith(">")):
        seq = "<" + seq + ">"
    return seq


def _icon_font_available(widget):
    if not _ICON_FONT_CACHE:
        try:
            import tkinter.font as tkfont
            _ICON_FONT_CACHE.append(_ICON_FONT in tkfont.families(widget))
        except Exception:
            _ICON_FONT_CACHE.append(False)
    return _ICON_FONT_CACHE[0]


def _icon(widget, key, size):
    """返回线性图标的 (字形, 字体)：字体可用用 MDL2 字形，缺失时回退 Unicode 符号"""
    glyph, fallback = _ICON_GLYPHS.get(key, ("", ""))
    if _icon_font_available(widget):
        return glyph, (_ICON_FONT, size)
    return fallback, (theme_mod.FONT_FAMILY, size)


def _widget_bg(widget, fallback):
    """取父容器背景色；ttk 在某些主题下返回空或系统色，统一回落到语义表面色"""
    try:
        value = str(widget.cget("background"))
    except Exception:
        value = ""
    if not value or value.startswith("System"):
        return fallback
    return value


def _get_local_ips():
    """获取本机所有 IP 地址（纯标准库实现，兼容 VMware）"""
    import socket
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if not ip.startswith("127."):
            ips.add(ip)
        s.close()
    except:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.add(ip)
    except:
        pass
    return ips


# ==================== 主题配色 ====================
# 1. 由 theme.py 按当前配置生成语义色，主题切换时就地更新
# 2. 控件构造时读取这里的值，切换主题后需要重建控件
COLORS = {}

CARD_DENSITY_WIDTHS = {"compact": 300, "normal": 360, "comfortable": 420}
CARD_NAME_SIZES = {"small": 9, "normal": 10, "large": 12, "xlarge": 14}
TABLE_ROW_HEIGHTS = {"compact": 24, "normal": 28, "comfortable": 32}
DAOZAI_SOURCE_ID = "janycode.nacos-tray"
SHORTCUT_LABELS = {
    "refresh": "刷新",
    "toggle_view": "切换表格/卡片",
    "open_settings": "打开设置",
}
CARD_FIELD_LABELS = [
    ("port", "端口"),
    ("online", "在线数"),
    ("last_online", "最近上线时间"),
    ("note", "备注名"),
    ("dnd", "免打扰标记"),
]
CHANGELOG = [
    ("v2.1", "TrayNotify_v2.1.exe", [
        "构建环境按分支识别（main/master=生产，test=测试）",
        "首页来源地址完整展示，不再截断",
        "新增通知源开关，Nacos / Jenkins 可独立启停（至少保留一个）",
        "关闭的源不再轮询与通知，连接/行为/备注无需配置",
        "新增岛仔推送，可同步到「本机通知来源」，含凭据配置与连接测试",
        "托盘弹窗移除 Jenkins 行悬浮历史，列宽收窄 20%",
        "修复从托盘弹窗打开设置时窗口不可见",
        "通知展示延长到 11 秒",
        "Nacos 通知增加项目与环境字段，Jenkins 通知突出分支与环境",
        "Jenkins 支持读取构建参数中的 PROJECT，并展示在通知、表格与弹窗",
    ]),
    ("v2.0", "TrayNotify_v2.0.exe", [
        "升级为 Tray Notify Tool，统一承载 Nacos 与 Jenkins",
        "设置面板按通知源分组，各自拥有连接、行为与备注",
        "新增 Jenkins 通知：开始/成功/失败、分支、起止时间、用时与新提交",
        "Jenkins 支持递归文件夹与多分支、包含/排除过滤、任务级免打扰",
        "新增四种气泡样式：默认通知、卡片浮窗、强调渐变、极简横幅",
        "自绘气泡跟随主题与配色预设，支持堆叠、悬停暂停与点击跳转",
        "主窗口支持来源切换，Jenkins 使用表格视图",
        "托盘弹窗改为左右等宽双栏：Nacos / Jenkins",
        "配置目录迁移到 .tray-notify，旧配置自动迁移",
    ]),
    ("v1.8", "NacosTray_v1.8.exe", [
        "卡片实例行悬停时显示互斥的快捷上线/下线按钮",
        "快捷操作点击后立即执行并静默刷新服务列表",
        "实例行悬停增加浅底色，卡片悬停增加强调色边框",
        "托盘右键弹窗实例行增加同样的快捷上下线图标",
        "卡片快捷上下线只保留图标，悬停图标显示边框高亮",
        "主界面滚动条改为跟随主题的 6px 细滚动条",
        "快捷上下线处理中显示动态省略号，鼠标移出仍保留到刷新完成",
        "刷新进度条改为固定细线，不再改变窗口高度",
    ]),
    ("v1.7", "NacosTray_v1.7.exe", [
        "卡片服务名字号可在外观设置中调整，支持小/标准/大/特大",
        "悬浮详情同时支持表格与卡片，靠近屏幕右侧时自动翻到左侧",
        "设置中的勾选框统一显示为 √",
        "移除行为页的立即刷新，刷新仍可使用快捷键与托盘入口",
        "关于页增加作者邮箱",
        "配色预设改为紧凑三列，减少外观页滚动",
        "托盘右键弹窗按钮改为纯文字并移除关闭按钮",
        "卡片列数选择固定值时强制生效，不再按宽度降列",
        "重排悬浮详情，实例之间增加间距与分隔",
        "修复快捷键切换表格/卡片不生效的问题",
        "连接设置密码支持按住眼睛图标查看",
        "托盘右键弹窗的置顶服务增加钉标并突出服务名",
        "悬浮详情改为表格/卡片的信息图标触发，避免与右键菜单冲突",
        "置顶图标由星标改为钉标",
        "右键菜单改为跟随应用主题配色",
    ]),
    ("v1.6", "NacosTray_v1.6.exe", [
        "顶部只保留齿轮入口，备注、关于与全部设置统一收进设置面板",
        "设置改为侧边栏导航，新增卡片/表格样式与快捷键配置",
        "快捷键可配置刷新、切换表格/卡片、打开设置",
        "卡片增加悬浮详情，展示权重、集群、临时实例与元数据",
        "窗口标题只显示版本号，不再拼接作者",
    ]),
    ("v1.5", "NacosTray_v1.5.exe", [
        "新增表格、卡片两种视图，卡片按服务分组展示",
        "服务支持星标置顶，表格、卡片与托盘弹窗统一置顶优先",
        "顶部与托盘弹窗按钮增加图标，主窗口支持 F5 刷新",
        "优化表格选中行配色，保留在线、离线状态色",
    ]),
    ("v1.4", "NacosTray_v1.4.exe", [
        "新增亮色、暗色主题，默认跟随系统",
        "内置 8 套配色预设，含护眼米黄、护眼豆沙绿",
        "支持自定义亮色、暗色背景色",
    ]),
    ("v1.3", "NacosTray_v1.3.exe", [
        "主界面支持搜索",
        "Nacos API 请求频率限制",
        "界面和窗口的相对位置优化",
    ]),
    ("v1.2", "NacosTray_v1.2.exe", [
        "支持服务列表右键设置通知免打扰（IP 维度）",
    ]),
    ("v1.1", "NacosTray_v1.1.exe", [
        "简单美化外观",
        "添加关于",
    ]),
    ("v1.0", "NacosTray_v1.0.exe", [
        "纯素版本",
        "基于 Nacos 大版本为 v3+，如 v3.2.1",
        "连接 Nacos",
        "配置备注名",
        "托盘小图标",
        "一键上线、一键下线",
    ]),
]


class ThinScrollbar(tk.Canvas):
    """跟随主题的 6px 细滚动条；可外接 controller 处理虚拟滚动"""

    WIDTH = 6

    def __init__(self, parent, target, controller=None):
        # 必须显式给一个小高度：Canvas 默认请求高度很大，会把父容器的请求高度撑高
        super().__init__(parent, width=ThinScrollbar.WIDTH, height=10,
                         bg=COLORS["bg_main"], highlightthickness=0, bd=0)
        self._target = target
        self._controller = controller
        self._first = 0.0
        self._last = 1.0
        self._dragging = False
        self._drag_offset = 0
        self._hover = False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def set(self, first, last):
        try:
            self._first = float(first)
            self._last = float(last)
        except (TypeError, ValueError):
            return
        self._redraw()

    def _moveto(self, fraction):
        if self._controller is not None and hasattr(self._controller, "set_frac"):
            self._controller.set_frac(fraction)
            return
        self._target.yview_moveto(max(0.0, min(1.0, fraction)))

    def _thumb_range(self):
        height = self.winfo_height()
        if height <= 1:
            return None
        span = max(0.0, min(1.0, self._last - self._first))
        if span <= 0:
            return None
        thumb_height = max(24, int(height * span))
        top = int(self._first * height)
        top = max(0, min(height - thumb_height, top))
        return top, top + thumb_height

    def _redraw(self, hover=None):
        if hover is not None:
            self._hover = hover
        self.delete("track", "thumb")
        if self._last - self._first >= 0.999:
            return
        height = self.winfo_height()
        if height <= 1:
            return
        self.create_rectangle(0, 0, ThinScrollbar.WIDTH - 1, height - 1,
                              fill=theme_mod.blend(COLORS["bg_main"],
                                                   COLORS["text_primary"], 0.12),
                              outline="", tags="track")
        bounds = self._thumb_range()
        if not bounds:
            return
        top, bottom = bounds
        if self._hover or self._dragging:
            color = COLORS["primary"]
        else:
            color = theme_mod.blend(COLORS["bg_main"], COLORS["text_primary"], 0.45)
        self.create_rectangle(1, top, ThinScrollbar.WIDTH - 2, bottom,
                              fill=color, outline="", tags="thumb")

    def _on_enter(self, event=None):
        self._redraw(hover=True)

    def _on_leave(self, event=None):
        self._redraw(hover=False)

    def _on_press(self, event):
        bounds = self._thumb_range()
        if not bounds:
            return
        top, bottom = bounds
        if top <= event.y <= bottom:
            self._dragging = True
            self._drag_offset = event.y - top
        else:
            height = self.winfo_height()
            if height > 1:
                self._moveto(event.y / height)
        self._redraw()

    def _on_motion(self, event):
        if not self._dragging:
            return
        height = self.winfo_height()
        if height > 1:
            self._moveto((event.y - self._drag_offset) / height)

    def _on_release(self, event=None):
        self._dragging = False
        self._redraw()

    def _on_wheel(self, event):
        if event.delta:
            if self._controller is not None and hasattr(self._controller, "scroll"):
                self._controller.scroll(event.delta)
            else:
                self._target.yview_scroll(int(-event.delta / 120) * 3, "units")
            return "break"


class SettingsDialog:
    PAGE_NACOS_CONNECTION = 0
    PAGE_NACOS_BEHAVIOR = 1
    PAGE_NACOS_NOTES = 2
    PAGE_JENKINS_CONNECTION = 3
    PAGE_JENKINS_BEHAVIOR = 4
    PAGE_JENKINS_NOTES = 5
    PAGE_GENERAL = 6
    PAGE_APPEARANCE = 7
    PAGE_SHORTCUTS = 8
    PAGE_ABOUT = 9
    PAGE_TITLES = ["连接", "行为", "备注", "连接", "行为", "备注",
                   "常规", "外观", "快捷键", "关于"]
    NAV_GROUPS = [
        ("通知源", [
            ("Nacos", None),
            ("连接", PAGE_NACOS_CONNECTION),
            ("行为", PAGE_NACOS_BEHAVIOR),
            ("备注", PAGE_NACOS_NOTES),
            ("Jenkins", None),
            ("连接", PAGE_JENKINS_CONNECTION),
            ("行为", PAGE_JENKINS_BEHAVIOR),
            ("备注", PAGE_JENKINS_NOTES),
        ]),
        ("通用", [
            ("常规", PAGE_GENERAL),
            ("外观", PAGE_APPEARANCE),
            ("快捷键", PAGE_SHORTCUTS),
            ("关于", PAGE_ABOUT),
        ]),
    ]

    def __init__(self, parent, cfg, on_save=None, app=None, geometry=None, page=None):
        self.cfg = dict(cfg)
        self.base_cfg = dict(cfg)
        self.on_save = on_save
        self.app = app
        self.result = False
        self._page_index = page if page is not None else self.PAGE_NACOS_CONNECTION
        if self._page_index not in range(len(self.PAGE_TITLES)):
            self._page_index = self.PAGE_NACOS_CONNECTION
        self._scroll_pos = 0.0
        self._appearance_canvas = None
        self._about_canvas = None
        self._notes_trees = {}
        self._capture_action = None
        self._shortcut_widgets = {}
        self._preview_job = None
        self.notes = self.app.notes if self.app else config.load_notes()
        self.dnd = self.app.dnd if self.app else config.load_dnd()
        import tkinter as tk
        self._mode_var = tk.StringVar(value=self.base_cfg.get("theme_mode", theme_mod.MODE_SYSTEM))
        self._preset_var = tk.StringVar(value=self.base_cfg.get("theme_preset", theme_mod.DEFAULT_PRESET))
        custom = self.base_cfg.get("theme_custom") or {}
        self._custom_light_var = tk.StringVar(value=custom.get("light", theme_mod.DEFAULT_CUSTOM["light"]))
        self._custom_dark_var = tk.StringVar(value=custom.get("dark", theme_mod.DEFAULT_CUSTOM["dark"]))
        self._custom_accent = self.base_cfg.get("theme_custom_accent", theme_mod.DEFAULT_PRESET)
        if self._custom_accent == theme_mod.CUSTOM_ID:
            self._custom_accent = theme_mod.DEFAULT_PRESET
        frosted_default = bool(self.base_cfg.get("theme_frosted_glass", False))
        if not theme_mod.is_win11_or_newer():
            frosted_default = False
        self._frosted_var = tk.BooleanVar(value=frosted_default)

        self.nacos_cfg = dict(self.base_cfg.get("nacos") or {})
        self.jenkins_cfg = dict(self.base_cfg.get("jenkins") or {})
        self.notify_cfg = dict(self.base_cfg.get("notify") or {})
        self.ip_var = tk.StringVar(value=self.nacos_cfg.get("ip", ""))
        self.port_var = tk.StringVar(value=str(self.nacos_cfg.get("port", 8848)))
        self.namespace_var = tk.StringVar(value=self.nacos_cfg.get("namespace", ""))
        self.cluster_name_var = tk.StringVar(value=self.nacos_cfg.get("cluster_name", "ShenZhen"))
        self.env_var = tk.StringVar(value=self.nacos_cfg.get("env", ""))
        self.username_var = tk.StringVar(value=self.nacos_cfg.get("username", "nacos"))
        self.password_var = tk.StringVar(value=self.nacos_cfg.get("password", ""))
        self.login_interval_var = tk.StringVar(value=str(self.nacos_cfg.get("login_interval", 1800)))
        self.nacos_poll_interval_var = tk.StringVar(value=str(self.nacos_cfg.get("poll_interval", 30)))
        self.jenkins_url_var = tk.StringVar(value=self.jenkins_cfg.get("url", ""))
        self.jenkins_username_var = tk.StringVar(value=self.jenkins_cfg.get("username", ""))
        self.jenkins_password_var = tk.StringVar(value=self.jenkins_cfg.get("password", ""))
        self.jenkins_verify_ssl_var = tk.BooleanVar(
            value=bool(self.jenkins_cfg.get("verify_ssl", True)))
        self.jenkins_include_var = tk.StringVar(value=self.jenkins_cfg.get("include", ""))
        self.jenkins_exclude_var = tk.StringVar(value=self.jenkins_cfg.get("exclude", ""))
        self.jenkins_poll_interval_var = tk.StringVar(
            value=str(self.jenkins_cfg.get("poll_interval", 30)))
        self.jenkins_notify_start_var = tk.BooleanVar(
            value=bool(self.jenkins_cfg.get("notify_start", True)))
        self.jenkins_notify_success_var = tk.BooleanVar(
            value=bool(self.jenkins_cfg.get("notify_success", True)))
        self.jenkins_notify_failure_var = tk.BooleanVar(
            value=bool(self.jenkins_cfg.get("notify_failure", True)))
        self._nacos_enabled_var = tk.BooleanVar(
            value=bool(self.nacos_cfg.get("enabled", True)))
        self._jenkins_enabled_var = tk.BooleanVar(
            value=bool(self.jenkins_cfg.get("enabled", False)))
        self.auto_start_var = tk.BooleanVar(value=config.is_auto_start())
        view_mode = self.base_cfg.get("view_mode", "table")
        if view_mode not in ("table", "card"):
            view_mode = "table"
        self._view_mode_var = tk.StringVar(value=view_mode)
        card_columns = self.base_cfg.get("card_columns", "auto")
        if card_columns not in ("auto", 1, 2, 3):
            card_columns = "auto"
        self._card_columns_var = tk.StringVar(value=str(card_columns))
        density = self.base_cfg.get("card_density", "normal")
        if density not in CARD_DENSITY_WIDTHS:
            density = "normal"
        self._card_density_var = tk.StringVar(value=density)
        name_size = self.base_cfg.get("card_name_size", "normal")
        if name_size not in CARD_NAME_SIZES:
            name_size = "normal"
        self._card_name_size_var = tk.StringVar(value=name_size)
        fields = self.base_cfg.get("card_fields") or {}
        self._card_field_vars = {
            field: tk.BooleanVar(value=bool(fields.get(field, default)))
            for field, default in config.DEFAULT_CARD_FIELDS.items()
        }
        row_height = self.base_cfg.get("table_row_height", "normal")
        if row_height not in TABLE_ROW_HEIGHTS:
            row_height = "normal"
        self._table_row_height_var = tk.StringVar(value=row_height)
        self._table_striped_var = tk.BooleanVar(value=bool(self.base_cfg.get("table_striped", True)))
        style_value = self.notify_cfg.get("style", notifier_mod.STYLE_DEFAULT)
        if style_value not in dict(notifier_mod.STYLE_OPTIONS):
            style_value = notifier_mod.STYLE_DEFAULT
        self._notify_style_var = tk.StringVar(value=style_value)
        self._daozai_enabled_var = tk.BooleanVar(
            value=bool(self.notify_cfg.get("daozai_enabled")))
        self._daozai_cred_var = tk.StringVar(
            value=self.notify_cfg.get("daozai_credentials", ""))
        self._daozai_status_var = tk.StringVar(value="")
        shortcuts = self.base_cfg.get("shortcuts") or {}
        self._shortcut_vars = {}
        for action, default in config.DEFAULT_SHORTCUTS.items():
            value = shortcuts.get(action, default)
            value = _normalize_shortcut(value) or _normalize_shortcut(default)
            self._shortcut_vars[action] = tk.StringVar(value=value)
        self._shortcut_status_var = tk.StringVar(value="")
        self.window = tk.Toplevel(parent)
        self.window.title("设置")
        if geometry:
            self.window.geometry(geometry)
        else:
            self.window.geometry("780x700")
            _center_on_parent(self.window, parent)
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()
        _set_icon(self.window)
        self._build()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        if self.app:
            self.app._register_dialog("settings", self.window, dialog=self)

    def _settings_style(self):
        """设置面板 ttk 样式：沿用主窗口语义色，套用统一字号与间距标度"""
        from tkinter import ttk
        row_height = TABLE_ROW_HEIGHTS.get(
            self.base_cfg.get("table_row_height", "normal"), TABLE_ROW_HEIGHTS["normal"])
        theme_mod.apply_ttk_style(self.window, COLORS, row_height)
        style = ttk.Style(self.window)
        sp_xs, sp_sm, sp_md, sp_lg = theme_mod.SPACING_SCALE
        style.configure("TFrame", background=COLORS["bg_main"])
        style.configure("TLabel", background=COLORS["bg_main"],
                        foreground=COLORS["text_primary"],
                        font=theme_mod.font("secondary"))
        style.configure("TButton", padding=(sp_md, sp_sm // 2 + 2))
        style.configure("TEntry", padding=(sp_sm // 2 + 2, sp_xs))
        style.configure("TCombobox", padding=(sp_sm // 2 + 2, sp_xs))
        style.configure("TCheckbutton", background=COLORS["bg_main"],
                        foreground=COLORS["text_primary"], font=theme_mod.font("body"),
                        padding=(0, sp_xs))
        style.configure("TLabelframe", background=COLORS["bg_card"],
                        bordercolor=COLORS["separator"], padding=sp_md)
        style.configure("TLabelframe.Label", background=COLORS["bg_card"],
                        foreground=COLORS["text_secondary"],
                        font=theme_mod.font("secondary", True))

    def _build(self):
        import tkinter as tk
        from tkinter import ttk
        for child in self.window.winfo_children():
            child.destroy()
        self._shortcut_widgets = {}
        self._appearance_canvas = None
        self._about_canvas = None
        self._notes_trees = {}
        self._nav_source_labels = {}
        self._disabled_pages = {}
        self._settings_style()
        self.window.configure(bg=COLORS["bg_main"])
        sp_xs, sp_sm, sp_md, sp_lg = theme_mod.SPACING_SCALE
        header = tk.Frame(self.window, bg=COLORS["header_bg"], height=46)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=" 设置", bg=COLORS["header_bg"],
                fg=COLORS["header_fg"],
                font=theme_mod.font("title", True),
                anchor=tk.W, padx=sp_lg).pack(side=tk.LEFT, fill=tk.Y)
        body = tk.Frame(self.window, bg=COLORS["bg_main"])
        body.pack(fill=tk.BOTH, expand=True, padx=sp_md, pady=(sp_sm, sp_xs))
        sidebar = tk.Frame(body, bg=COLORS["bg_card"], width=176,
                           highlightthickness=1, highlightbackground=COLORS["separator"])
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        self._nav_labels = []
        for group_title, entries in self.NAV_GROUPS:
            tk.Label(sidebar, text=group_title, anchor=tk.W, padx=sp_sm,
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=theme_mod.font("micro", True)).pack(fill=tk.X, pady=(sp_sm, 0))
            for title, index in entries:
                if index is None:
                    src = {name: s for s, name in SOURCE_LABELS}.get(title)
                    heading = tk.Label(sidebar, text=title, anchor=tk.W, padx=sp_sm + 2,
                                       bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                                       font=theme_mod.font("body", True))
                    heading.pack(fill=tk.X, pady=(sp_sm, 0))
                    if src:
                        self._nav_source_labels[src] = heading
                    continue
                row = tk.Frame(sidebar, bg=COLORS["bg_card"], cursor="hand2")
                row.pack(fill=tk.X)
                bar = tk.Frame(row, bg=COLORS["bg_card"], width=3)
                bar.pack(side=tk.LEFT, fill=tk.Y, padx=(sp_sm, 0))
                label = tk.Label(row, text=title, anchor=tk.W, padx=sp_sm, pady=4,
                                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                                 font=theme_mod.font("secondary"))
                label.pack(side=tk.LEFT, fill=tk.X, expand=True)
                for widget in (row, bar, label):
                    widget.bind("<Button-1>", lambda e, i=index: self._select_page(i))
                self._nav_labels.append((index, row, bar, label))
        content = tk.Frame(body, bg=COLORS["bg_main"])
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(sp_md, 0))
        self._content_frame = content
        self._pages = [
            self._build_connection_page(content, SOURCE_NACOS),
            self._build_behavior_page(content, SOURCE_NACOS),
            self._build_notes_page(content, SOURCE_NACOS),
            self._build_connection_page(content, SOURCE_JENKINS),
            self._build_behavior_page(content, SOURCE_JENKINS),
            self._build_notes_page(content, SOURCE_JENKINS),
            self._build_general_page(content),
            self._build_appearance_page(content),
            self._build_shortcuts_page(content),
            self._build_about_page(content),
        ]
        btn_frame = ttk.Frame(self.window, padding=(sp_md, 0, sp_md, sp_md))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT, padx=(sp_sm, 0))
        ttk.Button(btn_frame, text="取消", command=self._cancel).pack(side=tk.RIGHT)
        self.window.bind("<KeyPress>", self._on_shortcut_key)
        self.window.bind("<MouseWheel>", self._on_settings_wheel)
        self._nacos_enabled_var.trace_add("write", lambda *a: self._refresh_source_nav())
        self._jenkins_enabled_var.trace_add("write", lambda *a: self._refresh_source_nav())
        self._refresh_source_nav()
        self._select_page(self._page_index)
        if self.app:
            theme_mod.set_dark_titlebar(self.window, COLORS.get("mode") == theme_mod.MODE_DARK)

    def _source_switch_var(self, source):
        if source == SOURCE_NACOS:
            return self._nacos_enabled_var
        return self._jenkins_enabled_var

    def _page_source(self, index):
        if self.PAGE_NACOS_CONNECTION <= index <= self.PAGE_NACOS_NOTES:
            return SOURCE_NACOS
        if self.PAGE_JENKINS_CONNECTION <= index <= self.PAGE_JENKINS_NOTES:
            return SOURCE_JENKINS
        return None

    def _build_disabled_placeholder(self, parent, source):
        import tkinter as tk
        from tkinter import ttk
        frame = ttk.Frame(parent)
        sp_sm, sp_md, sp_lg = theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2], theme_mod.SPACING_SCALE[3]
        name = "Nacos" if source == SOURCE_NACOS else "Jenkins"
        ttk.Label(frame, text=name + " 通知源已关闭",
                  font=theme_mod.font("title", True),
                  foreground=COLORS["text_primary"]).pack(pady=(sp_lg * 3, sp_sm))
        ttk.Label(frame, text="开启后才能配置连接、行为与备注。\n请在下方前往「常规」页的「通知源」中启用。",
                  foreground=COLORS["text_secondary"], justify=tk.CENTER,
                  font=theme_mod.font("secondary")).pack()
        ttk.Button(frame, text="前往常规",
                   command=lambda: self._select_page(self.PAGE_GENERAL)).pack(pady=sp_md)
        return frame

    def _refresh_source_nav(self):
        names = dict(SOURCE_LABELS)
        for source, label in getattr(self, "_nav_source_labels", {}).items():
            on = self._source_switch_var(source).get()
            label.configure(
                text=names.get(source, source) + ("" if on else "（未启用）"),
                fg=COLORS["text_primary"] if on else COLORS["text_secondary"])

    def _select_page(self, index):
        import tkinter as tk
        if index not in range(len(self.PAGE_TITLES)):
            return
        if self._page_index == self.PAGE_APPEARANCE and self._appearance_canvas:
            try:
                self._scroll_pos = self._appearance_canvas.yview()[0]
            except Exception:
                pass
        self._page_index = index
        accent_fg = theme_mod.ensure_contrast(COLORS["primary"], COLORS["selection_bg"], 3.0)
        for page_index, row, bar, label in self._nav_labels:
            active = page_index == index
            bg = COLORS["selection_bg"] if active else COLORS["bg_card"]
            row.configure(bg=bg)
            bar.configure(bg=COLORS["primary"] if active else bg)
            label.configure(
                bg=bg,
                fg=accent_fg if active else COLORS["text_secondary"],
                font=theme_mod.font("body", True) if active
                else theme_mod.font("secondary"))
        source = self._page_source(index)
        blocked = bool(source) and not self._source_switch_var(source).get()
        for i, page in enumerate(self._pages):
            if i == index and not blocked:
                page.pack(fill=tk.BOTH, expand=True)
            else:
                page.pack_forget()
        for placeholder in self._disabled_pages.values():
            placeholder.pack_forget()
        if blocked:
            placeholder = self._disabled_pages.get(index)
            if placeholder is None:
                placeholder = self._build_disabled_placeholder(self._content_frame, source)
                self._disabled_pages[index] = placeholder
            placeholder.pack(fill=tk.BOTH, expand=True)
            return
        if index == self.PAGE_NACOS_NOTES:
            self._notes_refresh(SOURCE_NACOS)
        if index == self.PAGE_JENKINS_NOTES:
            self._notes_refresh(SOURCE_JENKINS)
        if index == self.PAGE_APPEARANCE and self._appearance_canvas:
            self.window.update_idletasks()
            if self._scroll_pos > 0:
                self._appearance_canvas.yview_moveto(self._scroll_pos)

    def _build_connection_page(self, parent, source):
        from tkinter import ttk
        page = ttk.Frame(parent, padding=theme_mod.SPACING_SCALE[0])
        self._build_connection(page, source)
        return page

    def _build_behavior_page(self, parent, source):
        from tkinter import ttk
        page = ttk.Frame(parent, padding=theme_mod.SPACING_SCALE[0])
        self._build_behavior(page, source)
        return page

    def _build_appearance_page(self, parent):
        import tkinter as tk
        from tkinter import ttk
        page = tk.Frame(parent, bg=COLORS["bg_main"])
        outer = tk.Frame(page, bg=COLORS["bg_main"])
        outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, bg=COLORS["bg_main"], highlightthickness=0, bd=0,
                           yscrollincrement=20)
        scroll = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        inner = tk.Frame(canvas, bg=COLORS["bg_main"])
        window_id = canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        self._appearance_canvas = canvas

        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]

        def caption(text):
            tk.Label(inner, text=text, bg=COLORS["bg_main"], fg=COLORS["text_primary"],
                     font=theme_mod.font("body")).pack(anchor=tk.W)

        self._section(inner, "主题模式")
        self._segmented(inner, theme_mod.MODE_OPTIONS, self._mode_var,
                        on_change=self._change_mode)
        self._section(inner, "配色预设")
        grid = tk.Frame(inner, bg=COLORS["bg_main"])
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=1)
        entries = [(pid, theme_mod.PRESETS[pid]["name"]) for pid in theme_mod.PRESET_ORDER]
        entries.append((theme_mod.CUSTOM_ID, theme_mod.CUSTOM_NAME))
        self._preset_card_draws = []
        for index, (preset_id, name) in enumerate(entries):
            light, dark = self._preview_colors(preset_id)
            card = self._make_card(grid, preset_id, name, light, dark)
            card.grid(row=index // 3, column=index % 3, padx=sp_xs, pady=sp_xs, sticky="nsew")
        self._custom_area = tk.Frame(inner, bg=COLORS["bg_main"])
        self._custom_area.pack(fill=tk.X)
        self._build_custom_inputs()

        self._section(inner, "浮层材质")
        if theme_mod.is_win11_or_newer():
            self._check_button(inner, "毛玻璃背板（仅浮层）",
                               self._frosted_var).pack(anchor=tk.W)
            tk.Label(inner, text="开启后托盘弹窗、右键菜单与悬浮详情尝试使用 Windows 11 MICA/ACRYLIC 背板；调用失败时自动回到卡片面 + 发丝边 + 圆角。",
                     bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                     font=theme_mod.font("micro"), justify=tk.LEFT,
                     wraplength=520).pack(anchor=tk.W, pady=(0, sp_sm))
        else:
            frost_row = tk.Frame(inner, bg=COLORS["bg_main"])
            frost_row.pack(anchor=tk.W)
            frost_box = tk.Canvas(frost_row, width=16, height=16, bg=COLORS["bg_main"],
                                  highlightthickness=0, bd=0)
            frost_box.pack(side=tk.LEFT)
            theme_mod.rounded_rect(frost_box, 1, 1, 15, 15,
                                   theme_mod.RADIUS_CONTROL // 2,
                                   fill=COLORS["bg_card"],
                                   outline=COLORS["separator"], width=1)
            tk.Label(frost_row, text="毛玻璃背板（仅浮层）", bg=COLORS["bg_main"],
                     fg=COLORS["text_secondary"],
                     font=theme_mod.font("body")).pack(
                side=tk.LEFT, padx=(sp_xs + 2, 0))
            tk.Label(inner, text="当前系统不是 Windows 11，毛玻璃背板不可用；浮层保持卡片面 + 发丝边 + 圆角的高仿质感。",
                     bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                     font=theme_mod.font("micro"), justify=tk.LEFT,
                     wraplength=520).pack(anchor=tk.W, pady=(0, sp_sm))

        self._section(inner, "通知")
        caption("气泡样式")
        self._segmented(inner, notifier_mod.STYLE_OPTIONS, self._notify_style_var)
        tk.Label(inner, text="自绘气泡跟随当前主题与配色预设；默认通知使用 Windows 系统样式。",
                 bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro"), justify=tk.LEFT,
                 wraplength=520).pack(anchor=tk.W, pady=(0, sp_sm))

        self._section(inner, "视图")
        caption("视图模式")
        self._segmented(inner, [("table", "表格"), ("card", "卡片")], self._view_mode_var)

        self._section(inner, "卡片")
        caption("每行列数")
        self._segmented(inner, [("auto", "自动"), ("1", "1"), ("2", "2"), ("3", "3")],
                        self._card_columns_var)
        caption("密度")
        self._segmented(inner, [("compact", "紧凑"), ("normal", "标准"), ("comfortable", "宽松")],
                        self._card_density_var)
        caption("服务名字号")
        self._segmented(inner, [("small", "小"), ("normal", "标准"), ("large", "大"), ("xlarge", "特大")],
                        self._card_name_size_var)
        caption("显示字段")
        fields_wrap = tk.Frame(inner, bg=COLORS["bg_main"])
        fields_wrap.pack(fill=tk.X, pady=(0, sp_sm))
        for field, label in CARD_FIELD_LABELS:
            self._check_button(fields_wrap, label,
                               self._card_field_vars[field]).pack(side=tk.LEFT, padx=(0, sp_md))

        self._section(inner, "表格")
        caption("行高")
        self._segmented(inner, [("compact", "紧凑"), ("normal", "标准"), ("comfortable", "宽松")],
                        self._table_row_height_var)
        self._check_button(inner, "斑马纹", self._table_striped_var).pack(anchor=tk.W)

        foot = tk.Frame(inner, bg=COLORS["bg_main"])
        foot.pack(fill=tk.X, pady=(sp_md, sp_sm))
        self._icon_button(foot, "restore", "恢复默认", self._restore_default).pack(side=tk.LEFT)
        self.window.update_idletasks()
        if self._scroll_pos > 0:
            canvas.yview_moveto(self._scroll_pos)
        return page

    def _group(self, parent, title):
        """圆角分组卡片：返回内部内容框架（内部只能用 pack 布局）"""
        import tkinter as tk
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        outer = tk.Frame(parent, bg=COLORS["bg_main"])
        outer.pack(fill=tk.X, pady=(0, sp_md))
        canvas = tk.Canvas(outer, bg=COLORS["bg_main"], highlightthickness=0, bd=0)
        canvas.pack(fill=tk.X)
        inner = tk.Frame(canvas, bg=COLORS["bg_card"])
        win = canvas.create_window((1, 1), window=inner, anchor=tk.NW)
        tk.Label(inner, text=title, bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("secondary", True), anchor=tk.W).pack(
            fill=tk.X, padx=sp_md, pady=(sp_sm, sp_xs))
        tk.Frame(inner, bg=COLORS["separator"], height=1).pack(fill=tk.X, padx=sp_md)
        body = tk.Frame(inner, bg=COLORS["bg_card"])
        body.pack(fill=tk.X, padx=sp_md, pady=(sp_xs, sp_sm))

        def sync(_event=None):
            inner.update_idletasks()
            width = inner.winfo_reqwidth() + 2
            height = inner.winfo_reqheight() + 2
            canvas.configure(width=width, height=height)
            canvas.coords(win, 1, 1)
            canvas.itemconfigure(win, width=width - 2, height=height - 2)
            canvas.delete("card")
            theme_mod.rounded_rect(canvas, 0.5, 0.5, width - 0.5, height - 0.5,
                                   theme_mod.RADIUS_CARD, fill=COLORS["bg_card"],
                                   outline=COLORS["separator"], width=1, tags="card")
            canvas.tag_lower("card")

        inner.bind("<Configure>", sync)
        sync()
        return body

    def _section(self, parent, text):
        import tkinter as tk
        sp_xs, sp_sm = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1]
        tk.Label(parent, text=text, bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("secondary", True)).pack(anchor=tk.W, pady=(sp_sm, sp_xs))

    def _segmented(self, parent, options, var, on_change=None):
        """分段药丸选择条：轨道用次级表面，选中段用强调色"""
        import tkinter as tk
        import tkinter.font as tkfont
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        height = 30
        gap = 2
        active_font = tkfont.Font(font=theme_mod.font("body", True))
        idle_font = tkfont.Font(font=theme_mod.font("secondary"))
        bar = tk.Canvas(parent, height=height, bg=COLORS["bg_main"],
                        highlightthickness=0, bd=0, cursor="hand2")
        bar.pack(fill=tk.X, pady=(sp_xs, sp_sm))
        widths = [active_font.measure(title) + sp_md * 2 for _value, title in options]
        total = sum(widths) + gap * (len(options) - 1)
        bar.configure(width=max(total, 1))

        def refresh():
            bar.delete("seg")
            theme_mod.rounded_rect(bar, 0.5, 0.5, total - 0.5, height - 0.5,
                                   theme_mod.RADIUS_CONTROL,
                                   fill=COLORS["header_hover_bg"],
                                   outline=COLORS["separator"], width=1, tags="seg")
            x = 0
            for (value, title), width in zip(options, widths):
                selected = var.get() == value
                if selected:
                    theme_mod.rounded_rect(bar, x + 1, 1, x + width - 1, height - 1,
                                           theme_mod.RADIUS_CONTROL - 1,
                                           fill=COLORS["primary"], outline="", tags="seg")
                    fill = theme_mod.readable_text(COLORS["primary"])
                    font = active_font
                else:
                    fill = COLORS["text_primary"]
                    font = idle_font
                bar.create_text(x + width // 2, height // 2, text=title,
                                fill=fill, font=font, tags="seg")
                x += width + gap

        def choose(value):
            var.set(value)
            refresh()
            if on_change is not None:
                on_change(value)

        def on_click(event):
            x = 0
            for (value, _title), width in zip(options, widths):
                if x <= event.x < x + width:
                    if var.get() != value:
                        choose(value)
                    return
                x += width + gap

        bar.bind("<Button-1>", on_click)
        refresh()
        return bar

    def _check_button(self, parent, text, var):
        import tkinter as tk
        sp_xs = theme_mod.SPACING_SCALE[0]
        size = 16
        radius = theme_mod.RADIUS_CONTROL // 2
        bg = _widget_bg(parent, COLORS["bg_main"])
        frame = tk.Frame(parent, bg=bg, cursor="hand2")
        canvas = tk.Canvas(frame, width=size, height=size, bg=bg,
                           highlightthickness=0, bd=0)
        canvas.pack(side=tk.LEFT)
        label = tk.Label(frame, text=text, bg=bg,
                         fg=COLORS["text_primary"], font=theme_mod.font("body"))
        label.pack(side=tk.LEFT, padx=(sp_xs + 2, 0))

        def refresh():
            canvas.delete("box")
            if var.get():
                theme_mod.rounded_rect(canvas, 1, 1, size - 1, size - 1, radius,
                                       fill=COLORS["primary"], outline=COLORS["primary"],
                                       tags="box")
                canvas.create_text(size // 2, size // 2, text="√",
                                   fill=theme_mod.readable_text(COLORS["primary"]),
                                   font=theme_mod.font("micro", True), tags="box")
            else:
                theme_mod.rounded_rect(canvas, 1, 1, size - 1, size - 1, radius,
                                       fill=COLORS["bg_card"],
                                       outline=COLORS["separator"], width=1, tags="box")

        def toggle(event=None):
            var.set(not var.get())
            refresh()

        for widget in (frame, canvas, label):
            widget.bind("<Button-1>", toggle)
        refresh()
        return frame

    def _icon_button(self, parent, key, text, command):
        """带线性图标的文字按钮：用于浏览、测试、恢复默认等入口"""
        import tkinter as tk
        bg = _widget_bg(parent, COLORS["bg_main"])
        icon_text, icon_font = _icon(self.window, key, _ICON_SIZE_SM)
        frame = tk.Frame(parent, bg=bg, cursor="hand2")
        icon = tk.Label(frame, text=icon_text, bg=bg, fg=COLORS["text_secondary"],
                        font=icon_font)
        icon.pack(side=tk.LEFT)
        label = tk.Label(frame, text=text, bg=bg, fg=COLORS["text_primary"],
                         font=theme_mod.font("secondary"))
        label.pack(side=tk.LEFT, padx=(theme_mod.SPACING_SCALE[0] + 2, 0))
        for widget in (frame, icon, label):
            widget.bind("<Button-1>", lambda e: command())
            widget.bind("<Enter>", lambda e: (icon.configure(fg=COLORS["primary"]),
                                              label.configure(fg=COLORS["primary"])))
            widget.bind("<Leave>", lambda e: (icon.configure(fg=COLORS["text_secondary"]),
                                              label.configure(fg=COLORS["text_primary"])))
        return frame

    def _build_shortcuts_page(self, parent):
        import tkinter as tk
        from tkinter import ttk
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        page = ttk.Frame(parent, padding=sp_md)
        tk.Label(page, text="快捷键只在主窗口获得焦点时生效；清空表示禁用。",
                 bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro")).pack(anchor=tk.W, pady=(0, sp_sm))
        group = self._group(page, "按键绑定")
        for action, label in SHORTCUT_LABELS.items():
            row = tk.Frame(group, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=sp_xs)
            tk.Label(row, text=label, bg=COLORS["bg_card"],
                     fg=COLORS["text_primary"],
                     font=theme_mod.font("body")).pack(side=tk.LEFT)
            btn = ttk.Button(row, width=18,
                             text=self._shortcut_display(self._shortcut_vars[action].get()),
                             command=lambda a=action: self._begin_capture(a))
            btn.pack(side=tk.RIGHT)
            self._shortcut_widgets[action] = btn
        tk.Label(group, textvariable=self._shortcut_status_var,
                 bg=COLORS["bg_card"], fg=COLORS["warning"],
                 font=theme_mod.font("micro")).pack(anchor=tk.W, pady=(sp_sm, 0))
        self._icon_button(group, "restore", "恢复默认", self._reset_shortcuts).pack(
            anchor=tk.W, pady=(sp_sm, 0))
        tk.Label(page, text="提示：字母、数字和符号需要配合 Ctrl / Alt / Shift；F1-F12 可单独使用。",
                 bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro"), wraplength=440).pack(
            anchor=tk.W, pady=(sp_sm, 0))
        return page

    def _build_general_page(self, parent):
        import tkinter as tk
        from tkinter import ttk
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        page = ttk.Frame(parent, padding=sp_md)
        group = self._group(page, "应用")
        self._check_button(group, "开机自动启动",
                           self.auto_start_var).pack(anchor=tk.W, pady=sp_xs)
        tk.Label(group, text="应用级设置，Nacos 与 Jenkins 共用。",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro")).pack(anchor=tk.W, pady=(sp_xs, 0))
        source_group = self._group(page, "通知源")
        self._check_button(source_group, "启用 Nacos 通知源",
                           self._nacos_enabled_var).pack(anchor=tk.W, pady=sp_xs)
        self._check_button(source_group, "启用 Jenkins 通知源",
                           self._jenkins_enabled_var).pack(anchor=tk.W, pady=sp_xs)
        tk.Label(source_group,
                 text="至少启用一个通知源；关闭的源不再产生通知，其连接/行为/备注无需配置。",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro"), wraplength=520,
                 justify=tk.LEFT).pack(anchor=tk.W, pady=(sp_xs, 0))
        daozai_group = self._group(page, "岛仔推送")
        self._check_button(daozai_group, "同步通知到岛仔（需先在岛仔授权来源）",
                           self._daozai_enabled_var).pack(anchor=tk.W, pady=sp_xs)
        cred = tk.Frame(daozai_group, bg=COLORS["bg_card"])
        cred.pack(fill=tk.X, pady=sp_xs)
        tk.Label(cred, text="凭据文件", bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"],
                 font=theme_mod.font("secondary")).pack(side=tk.LEFT)
        entry = ttk.Entry(cred, textvariable=self._daozai_cred_var,
                          font=theme_mod.font("body"))
        entry.pack(side=tk.LEFT, padx=sp_sm, fill=tk.X, expand=True)
        self._icon_button(cred, "folder", "浏览...", self._browse_daozai).pack(side=tk.LEFT)
        self._icon_button(cred, "refresh", "测试", self._test_daozai).pack(
            side=tk.LEFT, padx=(sp_sm, 0))
        self._daozai_status_label = tk.Label(
            daozai_group, textvariable=self._daozai_status_var,
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            font=theme_mod.font("micro"))
        self._daozai_status_label.pack(anchor=tk.W, pady=(sp_xs, 0))
        desc = tk.Frame(daozai_group, bg=COLORS["bg_card"])
        desc.pack(fill=tk.X)
        tk.Label(desc, text="在岛仔「设置 → 消息提醒 → 本机通知来源」授权填写：",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro"), justify=tk.LEFT).pack(anchor=tk.W)
        id_row = tk.Frame(desc, bg=COLORS["bg_card"])
        id_row.pack(fill=tk.X, pady=(sp_xs, 0))
        tk.Label(id_row, text="来源 ID「" + DAOZAI_SOURCE_ID + "」",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro")).pack(side=tk.LEFT)
        copy_text, copy_font = _icon(self.window, "copy", _ICON_SIZE_SM)
        copy_id = tk.Label(id_row, text=copy_text, bg=COLORS["bg_card"],
                           fg=COLORS["text_secondary"], font=copy_font,
                           cursor="hand2")
        copy_id.pack(side=tk.LEFT, padx=(sp_xs, 0))
        copy_id.bind("<Button-1>", self._copy_daozai_source_id)
        copy_id.bind("<Enter>", lambda e: copy_id.configure(fg=COLORS["primary"]))
        copy_id.bind("<Leave>", lambda e: copy_id.configure(fg=COLORS["text_secondary"]))
        tk.Label(desc, text="显示名称「随意填」。点「授权来源」→「复制凭据路径」，把路径粘贴到此处。",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro"), justify=tk.LEFT).pack(anchor=tk.W)
        return page

    def _build_notes_page(self, parent, source):
        import tkinter as tk
        from tkinter import ttk
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        page = ttk.Frame(parent, padding=sp_md)
        toolbar = tk.Frame(page, bg=COLORS["bg_main"])
        toolbar.pack(fill=tk.X, pady=(0, sp_sm))
        buttons = [
            ("新增", lambda: self._notes_add(source)),
            ("编辑", lambda: self._notes_edit(source)),
            ("删除", lambda: self._notes_delete(source)),
            ("免打扰", lambda: self._notes_toggle_dnd(source)),
        ]
        for text, command in buttons:
            btn = tk.Label(toolbar, text=text, bg=COLORS["secondary"],
                           fg=COLORS["text_primary"],
                           font=theme_mod.font("body"),
                           padx=sp_md, pady=sp_xs, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, sp_sm))
            btn.bind("<Button-1>", lambda e, c=command: c())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(
                bg=COLORS["primary"], fg=theme_mod.readable_text(COLORS["primary"])))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(
                bg=COLORS["secondary"], fg=COLORS["text_primary"]))
        tree_wrap = ttk.Frame(page)
        tree_wrap.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(tree_wrap, columns=("key", "note", "muted"),
                            show="headings", selectmode="browse")
        if source == SOURCE_NACOS:
            tree.heading("key", text="IP 地址")
        else:
            tree.heading("key", text="Job 名称")
        tree.heading("note", text="备注名")
        tree.heading("muted", text="免打扰")
        tree.column("key", width=260)
        tree.column("note", width=210)
        tree.column("muted", width=60, anchor=tk.CENTER)
        scrollbar = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.bind("<Double-1>", lambda e: self._notes_edit(source))
        self._notes_trees[source] = tree
        tk.Label(page, text="备注与免打扰修改会立即保存，无需点击下方保存按钮",
                 bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro")).pack(anchor=tk.W, pady=(sp_sm, 0))
        return page

    def _build_about_page(self, parent):
        import tkinter as tk
        from tkinter import ttk
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        page = ttk.Frame(parent, padding=sp_md)
        basic = ttk.Frame(page)
        basic.pack(fill=tk.X)
        for i, (label, value) in enumerate([
            ("应用名称", APP_NAME),
            ("当前版本", APP_VERSION),
            ("通知源", "Nacos v3.x / Jenkins 2.x"),
            ("作者", "JiangYuan"),
            ("邮箱", "yuan62387@qq.com"),
        ]):
            ttk.Label(basic, text=label + "：",
                      font=theme_mod.font("secondary"),
                      foreground=COLORS["text_secondary"]).grid(row=i, column=0, sticky=tk.E,
                                                               pady=1, padx=(0, sp_sm))
            ttk.Label(basic, text=value,
                      font=theme_mod.font("body" if label != "应用名称" else "title",
                                         label == "应用名称"),
                      foreground=COLORS["text_primary"]).grid(row=i, column=1, sticky=tk.W, pady=1)
        ttk.Separator(page, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(sp_sm, sp_xs))
        ttk.Label(page, text="更新记录", font=theme_mod.font("secondary", True),
                  foreground=COLORS["text_secondary"]).pack(anchor=tk.W)
        container = tk.Frame(page, bg=COLORS["bg_main"])
        container.pack(fill=tk.BOTH, expand=True, pady=(sp_xs, 0))
        canvas = tk.Canvas(container, bg=COLORS["bg_main"], highlightthickness=0,
                           yscrollincrement=20)
        scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=COLORS["bg_main"])
        window_id = canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._about_canvas = canvas
        for version, name, items in CHANGELOG:
            tk.Label(inner, text=version + "  " + name, bg=COLORS["bg_main"],
                     fg=COLORS["text_primary"],
                     font=theme_mod.font("body", True), anchor=tk.W,
                     justify=tk.LEFT, wraplength=520).pack(fill=tk.X, pady=(sp_sm, sp_xs))
            for item in items:
                tk.Label(inner, text="• " + item, bg=COLORS["bg_main"],
                         fg=COLORS["text_secondary"],
                         font=theme_mod.font("secondary"), anchor=tk.W,
                         justify=tk.LEFT, wraplength=520).pack(
                    fill=tk.X, padx=(sp_md, 0))
        return page

    def _password_row(self, parent, label, var):
        from tkinter import ttk
        import tkinter as tk
        sp_xs, sp_sm = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1]
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=sp_xs)
        tk.Label(row, text=label, width=8, anchor=tk.E, bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"], font=theme_mod.font("secondary")).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var, width=30, show="*",
                          font=theme_mod.font("body"))
        entry.pack(side=tk.LEFT, padx=(sp_sm, 0), fill=tk.X, expand=True)
        eye_text, eye_font = _icon(self.window, "eye", _ICON_SIZE_SM)
        eye = tk.Label(row,
                       text=eye_text,
                       bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                       font=eye_font,
                       padx=sp_xs, cursor="hand2")
        eye.pack(side=tk.LEFT)

        def show_password(event=None):
            entry.configure(show="")
            eye.configure(fg=COLORS["primary"])

        def hide_password(event=None):
            entry.configure(show="*")
            eye.configure(fg=COLORS["text_secondary"])

        eye.bind("<ButtonPress-1>", show_password)
        eye.bind("<ButtonRelease-1>", hide_password)
        eye.bind("<Leave>", hide_password)
        return entry

    def _build_connection(self, page, source):
        from tkinter import ttk
        import tkinter as tk
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        is_nacos = source == SOURCE_NACOS
        title = "Nacos 连接设置" if is_nacos else "Jenkins 连接设置"
        conn_group = self._group(page, title)

        def field(label, var):
            row = tk.Frame(conn_group, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=sp_xs)
            tk.Label(row, text=label, width=8, anchor=tk.E, bg=COLORS["bg_card"],
                     fg=COLORS["text_secondary"],
                     font=theme_mod.font("secondary")).pack(side=tk.LEFT)
            entry = ttk.Entry(row, textvariable=var, width=30,
                              font=theme_mod.font("body"))
            entry.pack(side=tk.LEFT, padx=(sp_sm, 0), fill=tk.X, expand=True)
            return entry

        if is_nacos:
            field("IP:", self.ip_var)
            field("端口:", self.port_var)
            field("命名空间:", self.namespace_var)
            field("集群名:", self.cluster_name_var)
            field("环境:", self.env_var)
            env_hint = tk.Frame(conn_group, bg=COLORS["bg_card"])
            env_hint.pack(fill=tk.X)
            tk.Label(env_hint, text="", width=8, bg=COLORS["bg_card"],
                     font=theme_mod.font("secondary")).pack(side=tk.LEFT)
            tk.Label(env_hint, text="不填默认 dev", bg=COLORS["bg_card"],
                     fg=COLORS["text_secondary"],
                     font=theme_mod.font("micro")).pack(side=tk.LEFT, padx=(sp_sm, 0))
            field("用户名:", self.username_var)
            self._password_row(conn_group, "密码:", self.password_var)
        else:
            field("地址:", self.jenkins_url_var)
            field("用户名:", self.jenkins_username_var)
            self._password_row(conn_group, "密码:", self.jenkins_password_var)
            self._check_button(conn_group, "校验 HTTPS 证书（取消勾选可忽略）",
                               self.jenkins_verify_ssl_var).pack(anchor=tk.W, pady=(sp_xs, 0))
            tk.Label(conn_group,
                     text="使用账号密码做 Basic Auth，无需单独填写 API Token。",
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=theme_mod.font("micro"), justify=tk.LEFT,
                     wraplength=440).pack(anchor=tk.W, pady=(sp_xs, 0))
        test_row = tk.Frame(page, bg=COLORS["bg_main"])
        test_row.pack(fill=tk.X, pady=(sp_md, 0))
        self._icon_button(test_row, "refresh", "测试连接",
                          (self._test_nacos_connection if is_nacos
                           else self._test_jenkins_connection)).pack(side=tk.LEFT)
        test_status_var = tk.StringVar(value="")
        test_status = tk.Label(test_row, textvariable=test_status_var,
                               bg=COLORS["bg_main"], font=theme_mod.font("micro"))
        test_status.pack(side=tk.LEFT, padx=(sp_sm, 0))
        if is_nacos:
            self._nacos_test_status = (test_status_var, test_status)
        else:
            self._jenkins_test_status = (test_status_var, test_status)
        tk.Label(page,
                 text=("保存后立即重新登录并刷新服务列表" if is_nacos
                       else "保存后按新的连接与过滤规则重新轮询 Jenkins"),
                 bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro")).pack(anchor=tk.W, pady=(sp_sm, 0))

    def _build_behavior(self, page, source):
        from tkinter import ttk
        import tkinter as tk
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        if source == SOURCE_NACOS:
            group = self._group(page, "Nacos 行为设置")
            for label, var in (("登录刷新间隔(秒):", self.login_interval_var),
                               ("状态轮询(秒):", self.nacos_poll_interval_var)):
                row = tk.Frame(group, bg=COLORS["bg_card"])
                row.pack(fill=tk.X, pady=sp_xs)
                tk.Label(row, text=label, bg=COLORS["bg_card"],
                         fg=COLORS["text_primary"],
                         font=theme_mod.font("body")).pack(side=tk.LEFT)
                ttk.Entry(row, textvariable=var, width=10,
                          font=theme_mod.font("body")).pack(side=tk.LEFT, padx=sp_sm)
            tk.Label(page, text="登录刷新间隔用于主动重登，实际以 token 过期为主。",
                     bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                     font=theme_mod.font("micro")).pack(anchor=tk.W, pady=(sp_sm, 0))
            return
        group = self._group(page, "Jenkins 行为设置")
        row = tk.Frame(group, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=sp_xs)
        tk.Label(row, text="构建轮询(秒):", bg=COLORS["bg_card"],
                 fg=COLORS["text_primary"],
                 font=theme_mod.font("body")).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.jenkins_poll_interval_var, width=10,
                  font=theme_mod.font("body")).pack(side=tk.LEFT, padx=sp_sm)
        tk.Label(row, text="最小 10 秒", bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro")).pack(side=tk.LEFT)
        for label, var in (("包含 Job:", self.jenkins_include_var),
                           ("排除 Job:", self.jenkins_exclude_var)):
            row = tk.Frame(group, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=sp_xs)
            tk.Label(row, text=label, bg=COLORS["bg_card"],
                     fg=COLORS["text_primary"],
                     font=theme_mod.font("body")).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=var, width=30,
                      font=theme_mod.font("body")).pack(side=tk.LEFT, padx=sp_sm)
        tk.Label(group, text="逗号分隔，匹配完整 Job 路径，排除优先；留空表示全部。",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=theme_mod.font("micro"), justify=tk.LEFT,
                 wraplength=440).pack(anchor=tk.W, pady=(sp_xs, 0))
        tk.Label(group, text="通知事件", bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"],
                 font=theme_mod.font("secondary", True)).pack(
            anchor=tk.W, pady=(sp_sm, sp_xs))
        events_wrap = tk.Frame(group, bg=COLORS["bg_card"])
        events_wrap.pack(fill=tk.X)
        self._check_button(events_wrap, "构建开始",
                           self.jenkins_notify_start_var).pack(side=tk.LEFT, padx=(0, sp_md))
        self._check_button(events_wrap, "构建成功",
                           self.jenkins_notify_success_var).pack(side=tk.LEFT, padx=(0, sp_md))
        self._check_button(events_wrap, "构建失败",
                           self.jenkins_notify_failure_var).pack(side=tk.LEFT)
        status = getattr(self.app, "_jenkins_status", {}) if self.app else {}
        last_success = status.get("last_success") or "暂无"
        last_error = status.get("last_error") or ""
        status_text = "最近成功：" + str(last_success)
        if last_error:
            status_text += "\n最近错误：" + str(last_error)
        tk.Label(group, text=status_text, bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"], font=theme_mod.font("micro"),
                 wraplength=440, justify=tk.LEFT).pack(anchor=tk.W, pady=(sp_sm, 0))

    def _preview_colors(self, preset_id):
        if preset_id == theme_mod.CUSTOM_ID:
            base = {
                "theme_preset": theme_mod.CUSTOM_ID,
                "theme_custom": {
                    "light": self._custom_light_var.get(),
                    "dark": self._custom_dark_var.get(),
                },
                "theme_custom_accent": self._custom_accent,
            }
            light = theme_mod.build_palette(dict(base, theme_mode=theme_mod.MODE_LIGHT))
            dark = theme_mod.build_palette(dict(base, theme_mode=theme_mod.MODE_DARK))
            return light, dark
        return theme_mod.preset_preview(preset_id, theme_mod.MODE_LIGHT), theme_mod.preset_preview(preset_id, theme_mod.MODE_DARK)

    def _draw_preview(self, canvas, light, dark, box=None):
        if box is None:
            box = (0, 0, 120, 28)
        x0, y0, width, height = box
        gap = 4
        half = (width - gap) // 2

        def draw_block(px, palette):
            x1 = px + half
            strip = max(3, int(height * 0.2))
            line_h = max(2, int(height * 0.12))
            canvas.create_rectangle(px, y0, x1, y0 + height,
                                    fill=palette["bg_card"], outline=palette["separator"])
            canvas.create_rectangle(px, y0, x1, y0 + strip,
                                    fill=palette["primary"], outline=palette["primary"])
            canvas.create_rectangle(px + 4, y0 + int(height * 0.36),
                                    x1 - 8, y0 + int(height * 0.36) + line_h,
                                    fill=palette["text_primary"], outline=palette["text_primary"])
            canvas.create_rectangle(px + 4, y0 + int(height * 0.58),
                                    x1 - 4, y0 + int(height * 0.58) + line_h,
                                    fill=palette["text_secondary"], outline=palette["text_secondary"])
            canvas.create_rectangle(px + 4, y0 + int(height * 0.78),
                                    x1 - 12, y0 + int(height * 0.78) + line_h,
                                    fill=palette["secondary"], outline=palette["secondary"])

        draw_block(x0, light)
        draw_block(x0 + half + gap, dark)

    def _make_card(self, parent, preset_id, name, light, dark):
        import tkinter as tk
        sp_xs, sp_sm = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1]
        card = tk.Canvas(parent, width=1, height=76, bg=COLORS["bg_main"],
                         highlightthickness=0, bd=0, cursor="hand2")

        def draw(_event=None):
            selected = self._preset_var.get() == preset_id
            card.delete("all")
            width = card.winfo_width()
            height = card.winfo_height()
            if width < 10 or height < 10:
                return
            theme_mod.rounded_rect(card, 1, 1, width - 1, height - 1,
                                   theme_mod.RADIUS_CARD,
                                   fill=COLORS["bg_card"],
                                   outline=COLORS["primary"] if selected else COLORS["separator"],
                                   width=2 if selected else 1)
            pad = sp_sm
            block_w = (width - pad * 2 - sp_xs) // 2
            block_h = 30
            self._draw_preview(card, light, dark, (pad, pad, block_w, block_h))
            self._draw_preview(card, dark, dark,
                               (pad + block_w + sp_xs, pad, block_w, block_h))
            name_font = theme_mod.font("micro", True) if selected else theme_mod.font("micro")
            card.create_text(pad, height - 20, text=name, anchor=tk.NW,
                             fill=COLORS["text_primary"], font=name_font)
            if selected:
                card.create_text(width - pad, height - 20, text="使用中", anchor=tk.NE,
                                 fill=COLORS["primary"], font=theme_mod.font("micro"))

        card.bind("<Configure>", draw)
        card.bind("<Button-1>", lambda e, p=preset_id: self._select_preset(p))
        if hasattr(self, "_preset_card_draws"):
            self._preset_card_draws.append(draw)
        draw()
        return card

    def _build_custom_inputs(self):
        import tkinter as tk
        from tkinter import ttk
        sp_xs, sp_sm = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1]
        for var, trace_id in getattr(self, "_swatch_traces", []):
            try:
                var.trace_remove("write", trace_id)
            except Exception:
                pass
        self._swatch_traces = []
        for child in self._custom_area.winfo_children():
            child.destroy()
        self._custom_hint = None
        if self._preset_var.get() != theme_mod.CUSTOM_ID:
            tk.Label(self._custom_area, text="选择自定义后，可填写亮色与暗色背景色",
                     bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                     font=theme_mod.font("micro")).pack(anchor=tk.W, pady=(sp_xs, 0))
            return
        for label, var in (("亮色背景", self._custom_light_var), ("暗色背景", self._custom_dark_var)):
            row = tk.Frame(self._custom_area, bg=COLORS["bg_main"])
            row.pack(fill=tk.X, pady=sp_xs)
            tk.Label(row, text=label + ":", bg=COLORS["bg_main"],
                     fg=COLORS["text_secondary"],
                     font=theme_mod.font("secondary")).pack(side=tk.LEFT)
            entry = ttk.Entry(row, textvariable=var, width=12,
                              font=theme_mod.font("body"))
            entry.pack(side=tk.LEFT, padx=sp_sm)
            swatch = tk.Canvas(row, width=28, height=18, bg=COLORS["bg_main"],
                               highlightthickness=0, bd=0)
            swatch.pack(side=tk.LEFT, padx=(sp_xs, 0))
            trace_id = var.trace_add("write", lambda *a, c=swatch, v=var: self._refresh_swatch(c, v))
            self._swatch_traces.append((var, trace_id))
            self._refresh_swatch(swatch, var)
            entry.bind("<FocusOut>", lambda e: self._preview_theme())
            entry.bind("<Return>", lambda e: self._preview_theme())
        self._custom_hint = tk.Label(self._custom_area, text="格式 #RRGGBB，例如 #2B2B2B",
                                     bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                                     font=theme_mod.font("micro"))
        self._custom_hint.pack(anchor=tk.W, pady=(sp_xs, 0))

    def _refresh_swatch(self, canvas, var):
        try:
            if not canvas.winfo_exists():
                return
        except Exception:
            return
        value = var.get().strip()
        color = theme_mod.normalize_hex(value, COLORS["bg_card"])
        canvas.delete("sw")
        theme_mod.rounded_rect(canvas, 1, 1, 27, 17,
                               theme_mod.RADIUS_CONTROL // 2,
                               fill=color, outline=COLORS["separator"], width=1, tags="sw")
        if self._custom_hint is not None:
            if value and not theme_mod.is_valid_hex(value):
                self._custom_hint.configure(text="格式应为 #RRGGBB，例如 #2B2B2B",
                                            fg=COLORS["offline"])
            elif value:
                self._custom_hint.configure(text="格式正确", fg=COLORS["online"])

    def _on_settings_wheel(self, event):
        canvas = None
        if self._page_index == self.PAGE_APPEARANCE:
            canvas = self._appearance_canvas
        elif self._page_index == self.PAGE_ABOUT:
            canvas = self._about_canvas
        if canvas is None:
            return
        try:
            x, y = self.window.winfo_pointerxy()
            if not (canvas.winfo_rootx() <= x <= canvas.winfo_rootx() + canvas.winfo_width()
                    and canvas.winfo_rooty() <= y <= canvas.winfo_rooty() + canvas.winfo_height()):
                return
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
                return "break"
        except Exception:
            return

    def _shortcut_display(self, sequence):
        if not sequence:
            return "未设置"
        names = {"Control": "Ctrl", "comma": ",", "period": ".", "space": "空格"}
        parts = []
        for part in sequence.strip("<>").split("-"):
            text = names.get(part, part)
            if len(text) == 1 and text.isalpha():
                text = text.upper()
            parts.append(text)
        return "+".join(parts)

    def _begin_capture(self, action):
        self._capture_action = action
        self._shortcut_status_var.set("请按下新的快捷键：Esc 取消，Delete 清空")
        for name, widget in self._shortcut_widgets.items():
            text = "按下按键…" if name == action else self._shortcut_display(self._shortcut_vars[name].get())
            widget.configure(text=text)
        self.window.focus_force()

    def _finish_capture(self):
        self._capture_action = None
        self._shortcut_status_var.set("")
        for name, widget in self._shortcut_widgets.items():
            widget.configure(text=self._shortcut_display(self._shortcut_vars[name].get()))

    def _apply_capture(self, sequence):
        action = self._capture_action
        if action is None:
            return
        self._shortcut_vars[action].set(sequence)
        self._finish_capture()

    def _on_shortcut_key(self, event):
        if not self._capture_action:
            return
        import re
        keysym = event.keysym
        if keysym == "Escape":
            self._finish_capture()
            return "break"
        if keysym in ("BackSpace", "Delete"):
            self._apply_capture("")
            return "break"
        if keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R",
                      "Alt_L", "Alt_R", "Super_L", "Super_R"):
            return "break"
        mods = []
        if event.state & 0x4:
            mods.append("Control")
        if event.state & 0x20000:
            mods.append("Alt")
        if event.state & 0x1:
            mods.append("Shift")
        if not mods and not re.match(r"^F([1-9]|1[0-2])$", keysym):
            self._shortcut_status_var.set("字母、数字和符号键需要配合 Ctrl/Alt/Shift")
            return "break"
        sequence = "<" + "-".join(mods + [keysym]) + ">"
        for action, var in self._shortcut_vars.items():
            if action != self._capture_action and var.get() == sequence:
                self._shortcut_status_var.set("与「" + SHORTCUT_LABELS[action] + "」冲突")
                return "break"
        self._apply_capture(sequence)
        return "break"

    def _reset_shortcuts(self):
        for action, default in config.DEFAULT_SHORTCUTS.items():
            self._shortcut_vars[action].set(default)
        self._finish_capture()

    def _notes_source_data(self, source):
        if not isinstance(self.notes.get(source), dict):
            self.notes[source] = {}
        if not isinstance(self.dnd.get(source), dict):
            self.dnd[source] = {}
        return self.notes[source], self.dnd[source]

    def _notes_refresh(self, source):
        tree = self._notes_trees.get(source)
        if not tree:
            return
        tree.delete(*tree.get_children())
        notes, dnd = self._notes_source_data(source)
        for key in sorted(set(notes) | set(dnd)):
            tree.insert("", "end", values=(
                key, notes.get(key, ""), "是" if key in dnd else ""))

    def _notes_save(self):
        config.save_notes(self.notes)
        config.save_dnd(self.dnd)
        if self.app:
            self.app._update_window()
            self.app._update_tray_tooltip()

    def _notes_selection(self, source):
        tree = self._notes_trees.get(source)
        if not tree:
            return None
        selection = tree.selection()
        if not selection:
            return None
        values = tree.item(selection[0])["values"]
        return str(values[0]) if values else None

    def _notes_add(self, source):
        self._notes_dialog(source, None)

    def _notes_edit(self, source, event=None):
        key = self._notes_selection(source)
        if key is None:
            return
        self._notes_dialog(source, key)

    def _notes_delete(self, source):
        key = self._notes_selection(source)
        if key is None:
            return
        from tkinter import messagebox
        if not messagebox.askyesno("确认删除", "确定删除 " + key + " 的备注与免打扰吗？",
                                   parent=self.window):
            return
        notes, dnd = self._notes_source_data(source)
        notes.pop(key, None)
        dnd.pop(key, None)
        self._notes_save()
        self._notes_refresh(source)

    def _notes_toggle_dnd(self, source):
        key = self._notes_selection(source)
        if key is None:
            return
        notes, dnd = self._notes_source_data(source)
        if key in dnd:
            dnd.pop(key, None)
        else:
            dnd[key] = True
        self._notes_save()
        self._notes_refresh(source)

    def _notes_dialog(self, source, key):
        import tkinter as tk
        from tkinter import ttk
        notes, dnd = self._notes_source_data(source)
        dialog = tk.Toplevel(self.window)
        dialog.title("编辑备注" if key else "添加备注")
        dialog.geometry("420x230")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        _set_icon(dialog)
        _center_on_parent(dialog, self.window)
        theme_mod.apply_ttk_style(dialog, COLORS)
        ttk.Style(dialog).configure("TFrame", background=COLORS["bg_main"])
        sp_xs, sp_sm, sp_md = theme_mod.SPACING_SCALE[0], theme_mod.SPACING_SCALE[1], theme_mod.SPACING_SCALE[2]
        frame = ttk.Frame(dialog, padding=sp_md)
        frame.pack(fill=tk.BOTH, expand=True)
        if source == SOURCE_NACOS:
            key_label = "IP 地址:"
            values = self.app._get_all_ips() if self.app else []
        else:
            key_label = "Job 名称:"
            values = [job["name"] for job in getattr(self.app, "jenkins_jobs", [])] if self.app else []
        tk.Label(frame, text=key_label, bg=COLORS["bg_main"],
                 fg=COLORS["text_secondary"],
                 font=theme_mod.font("secondary")).pack(anchor=tk.W)
        key_var = tk.StringVar(value=key or "")
        if key:
            key_entry = ttk.Entry(frame, textvariable=key_var, width=40, state="readonly",
                                  font=theme_mod.font("body"))
        else:
            key_entry = ttk.Combobox(frame, textvariable=key_var, values=sorted(values),
                                     width=38, font=theme_mod.font("body"))
        key_entry.pack(fill=tk.X, pady=(sp_xs, sp_sm))
        key_entry.focus_set()
        tk.Label(frame, text="备注名:", bg=COLORS["bg_main"],
                 fg=COLORS["text_secondary"],
                 font=theme_mod.font("secondary")).pack(anchor=tk.W)
        note_var = tk.StringVar(value=notes.get(key, "") if key else "")
        ttk.Entry(frame, textvariable=note_var, width=40,
                  font=theme_mod.font("body")).pack(fill=tk.X, pady=(sp_xs, sp_sm))
        mute_var = tk.BooleanVar(value=bool(key and key in dnd))
        self._check_button(frame, "免打扰", mute_var).pack(anchor=tk.W, pady=(sp_xs, 0))
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(sp_md, 0))

        def on_ok():
            selected = key_var.get().strip()
            if not selected:
                return
            note = note_var.get().strip()
            if note:
                notes[selected] = note
            else:
                notes.pop(selected, None)
            if mute_var.get():
                dnd[selected] = True
            else:
                dnd.pop(selected, None)
            self._notes_save()
            self._notes_refresh(source)
            dialog.destroy()

        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)

    def _set_mode(self, value):
        if self._mode_var.get() == value:
            return
        self._mode_var.set(value)
        self._preview_theme()

    def _change_mode(self, value):
        """分段条切换主题模式：直接落值并实时预览（分段条已完成自身重绘）"""
        self._mode_var.set(value)
        self._preview_theme()


    def _refresh_preset_selection(self):
        """只重绘预设卡片的选中态，不重建整个页面"""
        for draw in getattr(self, "_preset_card_draws", []):
            try:
                draw()
            except Exception:
                pass

    def _select_preset(self, preset_id):
        previous = self._preset_var.get()
        if preset_id == theme_mod.CUSTOM_ID and previous != theme_mod.CUSTOM_ID:
            self._custom_accent = previous
        self._preset_var.set(preset_id)
        self._refresh_preset_selection()
        self._preview_theme()

    def _theme_values(self):
        return {
            "theme_mode": self._mode_var.get(),
            "theme_preset": self._preset_var.get(),
            "theme_custom": {
                "light": self._custom_light_var.get().strip().upper(),
                "dark": self._custom_dark_var.get().strip().upper(),
            },
            "theme_custom_accent": self._custom_accent,
            "theme_frosted_glass": bool(self._frosted_var.get()),
        }

    def _theme_valid(self):
        values = self._theme_values()
        if values["theme_preset"] != theme_mod.CUSTOM_ID:
            return True
        return (theme_mod.is_valid_hex(values["theme_custom"]["light"])
                and theme_mod.is_valid_hex(values["theme_custom"]["dark"]))

    def _preview_theme(self):
        if not self.app or not self._theme_valid():
            return
        candidate = dict(self.base_cfg)
        candidate.update(self._theme_values())
        self.app._apply_theme(candidate)

    def _restore_default(self):
        self._mode_var.set(theme_mod.MODE_SYSTEM)
        self._preset_var.set(theme_mod.DEFAULT_PRESET)
        self._custom_light_var.set(theme_mod.DEFAULT_CUSTOM["light"])
        self._custom_dark_var.set(theme_mod.DEFAULT_CUSTOM["dark"])
        self._custom_accent = theme_mod.DEFAULT_PRESET
        self._frosted_var.set(False)
        self._view_mode_var.set("table")
        self._card_columns_var.set("auto")
        self._card_density_var.set("normal")
        self._card_name_size_var.set("normal")
        for var in self._card_field_vars.values():
            var.set(True)
        self._table_row_height_var.set("normal")
        self._table_striped_var.set(True)
        self._notify_style_var.set(notifier_mod.STYLE_DEFAULT)
        self._scroll_pos = 0.0
        self._preview_theme()

    def rebuild(self):
        if not self.window.winfo_exists():
            return
        try:
            if self._appearance_canvas and self._appearance_canvas.winfo_exists():
                self._scroll_pos = self._appearance_canvas.yview()[0]
        except Exception:
            pass
        self._build()

    def _cancel(self):
        if self.app:
            self.app._unregister_dialog("settings", self.window)
            self.app._apply_theme(dict(self.base_cfg))
        self.window.destroy()

    def _run_async(self, work, done):
        import queue
        results = queue.Queue()

        def runner():
            try:
                results.put(("ok", work()))
            except Exception as exc:
                results.put(("error", str(exc)))

        threading.Thread(target=runner, daemon=True).start()

        def poll():
            try:
                status, payload = results.get_nowait()
            except queue.Empty:
                try:
                    self.window.after(200, poll)
                except Exception:
                    pass
                return
            if self.window.winfo_exists():
                done(status, payload)

        self.window.after(200, poll)

    def _set_conn_status(self, source, ok, message):
        """连接测试结果就地显示：成功绿色、失败红色"""
        attr = "_nacos_test_status" if source == SOURCE_NACOS else "_jenkins_test_status"
        pair = getattr(self, attr, None)
        if not pair:
            return
        status_var, status_label = pair
        status_var.set(("√ 连接成功" if ok else "× 连接失败：") + message)
        status_label.configure(fg=COLORS["online"] if ok else COLORS["offline"])

    def _test_nacos_connection(self):
        try:
            ip = self.ip_var.get().strip()
            if not ip:
                raise ValueError("请填写 Nacos IP")
            client = NacosClient(
                ip=ip,
                port=int(self.port_var.get().strip()),
                username=self.username_var.get().strip(),
                password=self.password_var.get().strip(),
                namespace=self.namespace_var.get().strip(),
                cluster_name=self.cluster_name_var.get().strip() or "ShenZhen")
        except Exception as exc:
            self._set_conn_status(SOURCE_NACOS, False, str(exc))
            return

        def done(status, payload):
            if status == "error":
                self._set_conn_status(SOURCE_NACOS, False, str(payload))
            elif payload:
                self._set_conn_status(SOURCE_NACOS, True, "")
            else:
                self._set_conn_status(SOURCE_NACOS, False, "登录失败，请检查配置")

        self._run_async(client.login, done)

    def _test_jenkins_connection(self):
        url = self.jenkins_url_var.get().strip()
        username = self.jenkins_username_var.get().strip()
        password = self.jenkins_password_var.get()
        verify_ssl = bool(self.jenkins_verify_ssl_var.get())
        if not url or not username or not password:
            self._set_conn_status(SOURCE_JENKINS, False,
                                  "请填写 Jenkins 地址、账号和密码")
            return

        def work():
            client = JenkinsClient(url, username, password, verify_ssl)
            return client.test_connection()

        def done(status, payload):
            if status == "error":
                self._set_conn_status(SOURCE_JENKINS, False, str(payload))
                return
            count = payload.get("count", 0) if isinstance(payload, dict) else 0
            self._set_conn_status(SOURCE_JENKINS, True,
                                  "，共发现 " + str(count) + " 个 Job")

        self._run_async(work, done)

    def _browse_daozai(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="选择岛仔凭据文件", filetypes=[("JSON 文件", "*.json")],
            parent=self.window)
        if path:
            self._daozai_cred_var.set(path)
            self._daozai_status_var.set("")

    def _set_daozai_status(self, ok, message):
        self._daozai_status_var.set(message)
        label = getattr(self, "_daozai_status_label", None)
        if label is not None:
            label.configure(fg=COLORS["online"] if ok else COLORS["offline"])

    def _copy_daozai_source_id(self, _event=None):
        self.window.clipboard_clear()
        self.window.clipboard_append(DAOZAI_SOURCE_ID)

    def _test_daozai(self):
        path = self._daozai_cred_var.get().strip()
        if not path:
            self._set_daozai_status(False, "请先填写或选择凭据文件路径")
            return

        def work():
            ok, message = daozai_sink.test_connection(path)
            if not ok:
                raise RuntimeError(message)
            return message

        def done(status, payload):
            self._set_daozai_status(status == "ok",
                                    str(payload) if status == "ok"
                                    else "连接失败: " + str(payload))

        self._run_async(work, done)

    def _save(self):
        from tkinter import messagebox
        if not self._theme_valid():
            messagebox.showerror("错误", "自定义颜色格式应为 #RRGGBB，例如 #2B2B2B", parent=self.window)
            return
        nacos_enabled = bool(self._nacos_enabled_var.get())
        jenkins_enabled = bool(self._jenkins_enabled_var.get())
        if not nacos_enabled and not jenkins_enabled:
            messagebox.showerror("错误", "请至少启用一个通知源（Nacos 或 Jenkins）",
                                 parent=self.window)
            return
        try:
            nacos_port = int(self.port_var.get().strip())
            if nacos_port < 1 or nacos_port > 65535:
                raise ValueError("Nacos 端口应在 1-65535 之间")
            nacos_login = max(60, int(self.login_interval_var.get().strip()))
            nacos_poll = max(5, int(self.nacos_poll_interval_var.get().strip()))
            jenkins_poll = int(self.jenkins_poll_interval_var.get().strip())
            jenkins_poll = max(10, min(jenkins_poll, 3600))
        except ValueError as e:
            messagebox.showerror("错误", "输入格式错误: " + str(e), parent=self.window)
            return
        shortcut_values = [var.get() for var in self._shortcut_vars.values() if var.get()]
        if len(shortcut_values) != len(set(shortcut_values)):
            messagebox.showerror("错误", "快捷键不能重复，请先修改冲突项", parent=self.window)
            return
        nacos_cfg = dict(self.nacos_cfg)
        nacos_cfg.update({
            "enabled": nacos_enabled,
            "ip": self.ip_var.get().strip(),
            "port": nacos_port,
            "username": self.username_var.get().strip(),
            "password": self.password_var.get(),
            "namespace": self.namespace_var.get().strip(),
            "cluster_name": self.cluster_name_var.get().strip() or "ShenZhen",
            "env": self.env_var.get().strip(),
            "login_interval": nacos_login,
            "poll_interval": nacos_poll,
        })
        jenkins_cfg = dict(self.jenkins_cfg)
        jenkins_cfg.update({
            "enabled": jenkins_enabled,
            "url": normalize_base_url(self.jenkins_url_var.get()),
            "username": self.jenkins_username_var.get().strip(),
            "password": self.jenkins_password_var.get(),
            "verify_ssl": bool(self.jenkins_verify_ssl_var.get()),
            "include": self.jenkins_include_var.get().strip(),
            "exclude": self.jenkins_exclude_var.get().strip(),
            "poll_interval": jenkins_poll,
            "notify_start": bool(self.jenkins_notify_start_var.get()),
            "notify_success": bool(self.jenkins_notify_success_var.get()),
            "notify_failure": bool(self.jenkins_notify_failure_var.get()),
        })
        notify_cfg = dict(self.notify_cfg)
        notify_cfg["style"] = self._notify_style_var.get()
        notify_cfg["daozai_enabled"] = bool(self._daozai_enabled_var.get())
        notify_cfg["daozai_credentials"] = self._daozai_cred_var.get().strip()
        new_cfg = dict(self.base_cfg)
        new_cfg.update({
            "nacos": nacos_cfg,
            "jenkins": jenkins_cfg,
            "notify": notify_cfg,
            "auto_start": bool(self.auto_start_var.get()),
        })
        new_cfg.update(self._theme_values())
        columns_value = self._card_columns_var.get()
        new_cfg.update({
            "view_mode": self._view_mode_var.get(),
            "card_columns": "auto" if columns_value == "auto" else int(columns_value),
            "card_density": self._card_density_var.get(),
            "card_name_size": self._card_name_size_var.get(),
            "card_fields": {field: bool(var.get())
                            for field, var in self._card_field_vars.items()},
            "table_row_height": self._table_row_height_var.get(),
            "table_striped": bool(self._table_striped_var.get()),
            "shortcuts": {action: _normalize_shortcut(var.get())
                          for action, var in self._shortcut_vars.items()},
        })
        config.save_config(new_cfg)
        config.set_auto_start(new_cfg["auto_start"])
        if self.app:
            self.app._unregister_dialog("settings", self.window)
        if self.on_save:
            self.on_save(new_cfg)
        messagebox.showinfo("成功", "配置已保存！", parent=self.window)
        self.result = True
        self.window.destroy()


class _VirtualColumn:
    """按可视区渲染的列表列：只创建可见行，滚动时重绘"""

    def __init__(self, canvas, entries, heights, owner):
        self.canvas = canvas
        self.entries = entries
        self.heights = heights
        self._owner = owner
        self.starts = []
        self.view_h = 300
        self.offset = 0
        acc = 0
        for height in heights:
            self.starts.append(acc)
            acc += height
        self.total_h = acc

    def set_entries(self, entries, heights):
        """复用列时只换数据，不重建控件"""
        self.entries = entries
        self.heights = heights
        self.starts = []
        acc = 0
        for height in heights:
            self.starts.append(acc)
            acc += height
        self.total_h = acc

    def apply(self, view_h):
        """记录可视高度并设置滚动区域；宽度固定，避免未映射时取到 1"""
        self.view_h = max(view_h, 1)
        width = ServiceListPopup.COLUMN_WIDTH - 4
        self.canvas.configure(scrollregion=(0, 0, width, max(self.total_h + 8, 1)))
        self.offset = min(self.offset, self.max_offset())

    def max_offset(self):
        return max(self.total_h + 8 - self.view_h, 0)

    def scroll(self, delta, step=60):
        if not delta:
            return
        if (self.offset <= 0 and delta > 0) or (self.offset >= self.max_offset() and delta < 0):
            return
        self.set_offset(self.offset - int(-delta / 120) * step)

    def set_offset(self, value):
        self.offset = max(0, min(value, self.max_offset()))
        span = max(self.max_offset(), 1)
        self.canvas.yview_moveto(self.offset / span)
        self.render()

    def set_frac(self, fraction):
        """按可视比例跳转，供细滚动条拖动使用"""
        try:
            self.set_offset(float(fraction) * self.max_offset())
        except (TypeError, ValueError):
            pass

    def render(self):
        import tkinter as tk
        from bisect import bisect_right
        canvas = self.canvas
        entries = self.entries
        width = ServiceListPopup.COLUMN_WIDTH - 4
        owner = self._owner
        owner._begin_job_render()
        canvas.delete("all")
        if not entries:
            empty = tk.Frame(canvas, bg=COLORS["bg_card"])
            tk.Label(empty, text="", bg=COLORS["bg_card"]).pack(pady=16)
            canvas.create_window((0, 4), window=empty, anchor=tk.NW, width=width)
            owner._after_job_render()
            return
        view_h = self.view_h
        first_y = self.offset
        last_y = first_y + view_h
        start = max(0, bisect_right(self.starts, first_y) - 1)
        end = min(len(entries), bisect_right(self.starts, last_y) + ServiceListPopup.OVERSCAN)
        for index in range(max(0, start - ServiceListPopup.OVERSCAN), end):
            entry = entries[index]
            if entry["kind"] == "group":
                row = owner._make_group_row(canvas, entry)
            elif entry["kind"] == "instance":
                row = owner._make_instance_row(canvas, entry)
            else:
                row = owner._make_job_row(canvas, entry)
            canvas.create_window((0, self.starts[index]), window=row,
                                 anchor=tk.NW, width=width)
            owner._track_job_row(entry, row)
        owner._after_job_render()


class CommitHistoryPanel:
    """Jenkins 最近成功构建提交历史：托盘弹窗内嵌浮层 / 右键菜单独立窗口"""

    WIDTH = 380
    MAX_HEIGHT = 380

    def __init__(self, parent, app, hover=False):
        self.parent = parent
        self.app = app
        self.hover = hover
        C = COLORS
        if hover:
            self.window = parent
            self.container = tk.Frame(parent, bg=C["bg_card"], relief=tk.SOLID,
                                      borderwidth=1,
                                      highlightbackground=C["separator"],
                                      highlightthickness=1)
            self.container.place_forget()
        else:
            self.window = tk.Toplevel(parent)
            self.window.overrideredirect(True)
            self.window.attributes('-topmost', True)
            self.container = tk.Frame(self.window, bg=C["bg_card"], relief=tk.SOLID,
                                      borderwidth=1,
                                      highlightbackground=C["separator"],
                                      highlightthickness=1)
            self.container.pack(fill=tk.BOTH, expand=True)
            self.window.withdraw()
        header = tk.Frame(self.container, bg=C["header_bg"])
        header.pack(fill=tk.X)
        self.header = header
        self.title_label = tk.Label(header, text="", bg=C["header_bg"],
                                    fg=C["header_fg"],
                                    font=("Microsoft YaHei UI", 9, "bold"),
                                    anchor=tk.W, padx=10, pady=7,
                                    wraplength=CommitHistoryPanel.WIDTH - 60,
                                    justify=tk.LEFT)
        self.title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        close_text, close_font = _icon(self.window, "close", _ICON_SIZE_SM)
        self._close_label = tk.Label(header, text=close_text, bg=C["header_bg"],
                                     fg=C["header_fg"],
                                     font=close_font,
                                     cursor="hand2", padx=10)
        self._close_label.pack(side=tk.RIGHT)
        self._close_label.bind("<Button-1>", lambda e: self.close())
        body = tk.Frame(self.container, bg=C["bg_card"])
        body.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(body, bg=C["bg_card"], highlightthickness=0, bd=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ThinScrollbar(body, self.canvas).pack(side=tk.RIGHT, fill=tk.Y)
        self.inner = tk.Frame(self.canvas, bg=C["bg_card"])
        self._window_id = self.canvas.create_window((0, 0), window=self.inner,
                                                     anchor=tk.NW)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._window_id, width=e.width))
        self._hide_job = None
        self._anchor_xy = None
        self._height = 200
        if hover:
            self.container.bind("<Button-1>", lambda e: "break")
            self.container.bind("<Enter>", lambda e: self._cancel_hide())
        else:
            self.window.focus_force()

    def show_for_job(self, job, anchor=None):
        self._anchor_xy = anchor or self._pointer_xy()
        name = job.get("name", "")
        alias = (self.app.notes.get("jenkins") or {}).get(name, "")
        title = alias or name
        self.title_label.configure(text=title)
        self._render_message("加载中…")
        if self.hover:
            self.container.place(x=0, y=0, width=self.WIDTH, height=self._height)
            self._apply_geometry()
        else:
            self.window.deiconify()
            self.window.lift()
        self.app._load_commit_history(name, self._on_data)

    def _on_data(self, result):
        if self.window is None or not self.window.winfo_exists():
            return
        error = result.get("error")
        if error:
            self._render_message("读取失败：" + str(error))
            return
        builds = result.get("builds") or []
        if not builds:
            self._render_message("该 Job 暂无成功构建记录")
            return
        self._render_builds(builds)

    def _clear_inner(self):
        for child in self.inner.winfo_children():
            child.destroy()

    def _block_clicks(self):
        """悬浮态点击内容区不抢焦点（关闭按钮除外）"""
        if not self.hover:
            return

        def block(widget):
            if widget is self._close_label:
                return
            try:
                widget.bind("<Button-1>", lambda e: "break")
            except Exception:
                pass
            for child in widget.winfo_children():
                block(child)

        block(self.container)

    def _render_message(self, text):
        self._clear_inner()
        tk.Label(self.inner, text=text, bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"], font=("Microsoft YaHei UI", 9),
                 justify=tk.LEFT, wraplength=CommitHistoryPanel.WIDTH - 30,
                 anchor=tk.W).pack(fill=tk.X, padx=10, pady=12)
        self.inner.update_idletasks()
        self._fit_height()

    def _render_builds(self, builds):
        C = COLORS
        self._clear_inner()
        for build in builds:
            head = tk.Frame(self.inner, bg=C["bg_card"])
            head.pack(fill=tk.X, padx=10, pady=(10, 2))
            line = "#" + str(build.get("number") or "-") + "  " + \
                format_timestamp(build.get("timestamp", 0))
            branch = build.get("branch") or "-"
            if branch != "-":
                line += "  ·  " + branch
            tk.Label(head, text=line, bg=C["bg_card"], fg=C["online"],
                     font=("Microsoft YaHei UI", 9, "bold"),
                     anchor=tk.W).pack(side=tk.LEFT)
            commits = select_display_commits(build.get("commits") or [])
            if not commits:
                tk.Label(self.inner, text="无提交记录", bg=C["bg_card"],
                         fg=C["text_secondary"], font=("Microsoft YaHei UI", 8),
                         anchor=tk.W, padx=22).pack(fill=tk.X)
                continue
            for commit in commits:
                tk.Label(self.inner, text=format_commit_line(commit),
                         bg=C["bg_card"], fg=C["text_primary"],
                         font=("Microsoft YaHei UI", 8), anchor=tk.W,
                         justify=tk.LEFT,
                         wraplength=CommitHistoryPanel.WIDTH - 44,
                         padx=22).pack(fill=tk.X)
        self.inner.update_idletasks()
        self._fit_height()

    def _fit_height(self):
        self.container.update_idletasks()
        head_h = self.header.winfo_reqheight()
        height = min(self.inner.winfo_reqheight() + head_h + 10,
                     CommitHistoryPanel.MAX_HEIGHT)
        self._height = max(80, height)
        self._apply_geometry()
        self._block_clicks()

    def _apply_geometry(self):
        if self.hover:
            host_w = max(1, self.window.winfo_width())
            host_h = max(1, self.window.winfo_height())
            ax, ay = self._anchor_xy or (0, 0)
            x = int(ax) - self.WIDTH // 2
            x = max(4, min(x, max(4, host_w - self.WIDTH - 4)))
            y = int(ay) + 28
            y = max(4, min(y, max(4, host_h - self._height - 4)))
            self.container.place(x=x, y=y, width=self.WIDTH, height=self._height)
            return
        self.window.geometry(str(self.WIDTH) + "x" + str(self._height))
        left, top, right, bottom = notifier_mod.work_area(self.parent)
        x, y = self._anchor_xy or (right - self.WIDTH, top)
        x = max(left, min(int(x), right - self.WIDTH - 2))
        y = max(top, min(int(y), bottom - self._height - 2))
        self.window.geometry("+" + str(x) + "+" + str(y))

    def _pointer_xy(self):
        try:
            return (self.parent.winfo_pointerx(), self.parent.winfo_pointery())
        except Exception:
            return (0, 0)

    def move_to(self, anchor):
        """跟随鼠标更新浮窗位置（仅悬浮态）"""
        self._anchor_xy = anchor
        if not self.hover:
            return
        try:
            if self.container.winfo_ismapped():
                self._apply_geometry()
        except Exception:
            pass

    def cancel_hide(self):
        self._cancel_hide()

    def hide(self):
        self._cancel_hide()
        if self.hover:
            try:
                self.container.place_forget()
            except Exception:
                pass
            return
        if self.window is not None:
            try:
                self.window.withdraw()
            except Exception:
                pass

    def hide_soon(self):
        self._cancel_hide()
        if self.window is None:
            return
        self._hide_job = self.window.after(150, self._hide_if_outside)

    def _cancel_hide(self):
        if self._hide_job is not None and self.window is not None:
            try:
                self.window.after_cancel(self._hide_job)
            except Exception:
                pass
        self._hide_job = None

    def _hide_if_outside(self):
        self._hide_job = None
        if self._pointer_inside():
            return
        self.hide()

    def _pointer_inside(self):
        try:
            x, y = self.app.root.winfo_pointerxy()
            widget = self.app.root.winfo_containing(x, y)
        except Exception:
            return False
        target = self.container if self.hover else self.window
        while widget is not None:
            if widget is target:
                return True
            try:
                widget = widget.master
            except Exception:
                break
        return False

    def close(self):
        self._cancel_hide()
        if self.hover:
            self.hide()
            return
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None


class ServiceListPopup:
    """托盘右键弹窗：左栏 Nacos 服务、右栏 Jenkins 构建任务，等宽等高。

    两栏只渲染当前可视区内的行，服务或任务数量很大时也能即时弹出。
    """

    COLUMN_WIDTH = 264
    HEADER_HEIGHT = 36
    OVERSCAN = 6

    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.window = None
        self._canvas = None
        self._host = None
        self._host_item = None
        self._columns = []
        self._group_height = 34
        self._row_height = 23
        self._job_dot_phase = 0
        self._job_dots_job = None
        self._building_job_labels = {}
        self._hover_timer = None
        self._history_panel = None
        self._signature = None
        self._visible = False
        self._modal_open = False
        self._transparent_key = None
        self._total_w = 0
        self._total_h = 0
        self._measure_heights()
        self._create_window()

    def _source_signature(self):
        return (
            self.app._source_enabled(SOURCE_NACOS),
            self.app._source_enabled(SOURCE_JENKINS)
            and bool((self.app.jenkins_cfg or {}).get("url")),
        )

    def show(self):
        """单例入口：结构按需重建，数据每次刷新，位置与过渡每次更新"""
        if self.window is None or not self.window.winfo_exists():
            self._create_window()
        if self._signature != self._source_signature() or not self._columns:
            self._build_content()
            self._signature = self._source_signature()
        self._refresh_data()
        self._layout()
        self._present()

    def _create_window(self):
        import tkinter as tk
        C = COLORS
        self.window = tk.Toplevel(self.parent)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.withdraw()
        self._transparent_key = theme_mod.transparent_key(C)
        self.window.configure(bg=self._transparent_key)
        try:
            self.window.attributes("-transparentcolor", self._transparent_key)
        except tk.TclError:
            pass
        self._canvas = tk.Canvas(self.window, bg=self._transparent_key,
                                 highlightthickness=0, bd=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self.app._apply_float_material(self.window, self._transparent_key)
        self._host = None
        self._host_item = None
        self._columns = []
        self._signature = None
        self._visible = False
        self.window.bind("<MouseWheel>", self._on_wheel)
        self.window.bind("<FocusOut>", self._on_focus_out)
        self.window.bind("<Escape>", lambda e: self._close())

    def _build_content(self):
        import tkinter as tk
        C = COLORS
        if self._host is not None:
            try:
                self._host.destroy()
            except Exception:
                pass
            self._host = None
            self._host_item = None
        self._host = tk.Frame(self._canvas, bg=C["bg_card"])
        body = tk.Frame(self._host, bg=C["bg_card"])
        body.pack(fill=tk.BOTH, expand=True)
        self._columns = []
        if self.app._source_enabled(SOURCE_NACOS):
            self._columns.append(self._add_nacos_column(body))
        jenkins_configured = (self.app._source_enabled(SOURCE_JENKINS)
                             and bool((self.app.jenkins_cfg or {}).get("url")))
        if jenkins_configured:
            if self._columns:
                tk.Frame(body, bg=C["separator"], width=1).pack(side=tk.LEFT,
                                                                 fill=tk.Y)
            self._columns.append(self._add_jenkins_column(body))
        content_h = self._content_height()
        for col in self._columns:
            col["canvas"].configure(height=content_h)
            col["virtual"].apply(content_h)
            # 先放滚动条再放画布，保证滚动条占据整列右侧高度
            scrollbar = ThinScrollbar(col["frame"], col["canvas"],
                                      controller=col["virtual"])
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            col["canvas"].pack(fill=tk.BOTH, expand=True)
            col["scrollbar"] = scrollbar
        btn_frame = tk.Frame(self._host, bg=C["header_bg"])
        btn_frame.pack(fill=tk.X)
        btns = [
            ("还原窗口", self._on_restore, "restore"),
            ("设置", self._on_settings, "settings"),
            ("刷新", self._on_refresh, "refresh"),
            ("退出", self._on_quit, "power"),
        ]
        use_icon = _icon_font_available(self.parent)
        for label, cmd, glyph_key in btns:
            btn = tk.Frame(btn_frame, bg=C["header_bg"], cursor="hand2")
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
            if use_icon:
                icon_text, icon_font = _icon(self.parent, glyph_key, _ICON_SIZE_MD)
                icon = tk.Label(btn, text=icon_text, bg=C["header_bg"],
                                fg=C["header_fg"], font=icon_font, cursor="hand2")
                icon.pack(side=tk.LEFT, padx=(10, 1), pady=6)
            text = tk.Label(btn, text=label, bg=C["header_bg"], fg=C["header_fg"],
                            font=("Microsoft YaHei UI", 9), cursor="hand2")
            text.pack(side=tk.LEFT, padx=(1, 10), pady=6)
            for widget in (btn, icon, text) if use_icon else (btn, text):
                widget.bind("<Button-1>", lambda e, c=cmd: c())
                widget.bind("<Enter>",
                            lambda e, ws=(btn, text): self._hover_button(ws, True))
                widget.bind("<Leave>",
                            lambda e, ws=(btn, text): self._hover_button(ws, False))

    def _refresh_data(self, reset_scroll=True):
        """只换虚拟列的数据与标题摘要，不重建列结构；静默刷新时保留滚动位置"""
        offsets = [col["virtual"].offset for col in self._columns]
        for col in self._columns:
            virtual = col["virtual"]
            if col["kind"] == "nacos":
                entries = self._nacos_entries()
                heights = [self._group_height if e["kind"] == "group"
                           else self._row_height for e in entries]
                col["title_label"].configure(text=self._nacos_title())
                col["summary_label"].configure(text=self._nacos_summary())
            else:
                jobs = list(getattr(self.app, "jenkins_jobs", []) or [])
                entries = [{"kind": "job", "job": job} for job in jobs]
                heights = [self._row_height] * len(jobs)
                col["summary_label"].configure(text=self._jenkins_summary(jobs))
            virtual.set_entries(entries, heights)
            if reset_scroll:
                virtual.offset = 0
        content_h = self._content_height()
        for index, col in enumerate(self._columns):
            virtual = col["virtual"]
            col["canvas"].configure(height=content_h)
            if not reset_scroll and index < len(offsets):
                max_offset = max(0, virtual.total_h - content_h)
                virtual.offset = max(0, min(offsets[index], max_offset))
            virtual.apply(content_h)
            if reset_scroll:
                try:
                    col["canvas"].yview_moveto(0.0)
                except Exception:
                    pass

    def _layout(self):
        import tkinter as tk
        radius = theme_mod.RADIUS_FLOAT
        self._host.update_idletasks()
        width = self._host.winfo_reqwidth()
        height = self._host.winfo_reqheight()
        self._total_w = width + 2 * radius
        self._total_h = height + 2 * radius
        canvas = self._canvas
        canvas.configure(width=self._total_w, height=self._total_h)
        canvas.delete("all")
        self._host_item = None
        theme_mod.rounded_rect(canvas, 1, 1, self._total_w - 1, self._total_h - 1,
                               radius, fill=COLORS["bg_card"],
                               outline=COLORS["separator"])
        self._host_item = canvas.create_window(
            radius, radius, window=self._host, anchor=tk.NW,
            width=width, height=height)
        for col in self._columns:
            col["virtual"].render()

    def _present(self):
        left, top, right, bottom = notifier_mod.work_area(self.parent)
        px = self.parent.winfo_pointerx()
        py = self.parent.winfo_pointery()
        total_w = self._total_w
        total_h = self._total_h
        x = px - total_w // 2
        x = max(left, min(x, right - total_w))
        y = py - total_h - 8
        if y < top:
            y = py + 20
        y = max(top, min(y, bottom - total_h - 5))
        if self._visible:
            theme_mod.stop_alpha(self.window)
            try:
                self.window.attributes("-alpha", 1.0)
            except Exception:
                pass
            self.window.geometry("+" + str(x) + "+" + str(y))
            return
        # 从靠近的屏幕边缘方向滑入 8px，与淡入同步
        theme_mod.stop_alpha(self.window)
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        box_cx = x + total_w // 2
        box_cy = y + total_h // 2
        start_x, start_y = x, y
        if abs(box_cx - center_x) >= abs(box_cy - center_y):
            start_x = x - 8 if box_cx < center_x else x + 8
        else:
            start_y = y - 8 if box_cy < center_y else y + 8
        try:
            self.window.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.window.geometry(str(total_w) + "x" + str(total_h)
                             + "+" + str(start_x) + "+" + str(start_y))
        self.window.deiconify()
        self.window.lift()
        self._visible = True

        def on_frame(ratio):
            frame_x = int(round(start_x + (x - start_x) * ratio))
            frame_y = int(round(start_y + (y - start_y) * ratio))
            try:
                self.window.geometry("+" + str(frame_x) + "+" + str(frame_y))
            except Exception:
                pass

        theme_mod.animate_alpha(self.window, 1.0, theme_mod.POPUP_FADE_MS,
                                on_frame=on_frame)
        self.window.focus_force()

    def _close(self):
        """收起但保留单例窗口，下次打开复用"""
        self._cancel_hover_history()
        if self.window is not None:
            theme_mod.stop_alpha(self.window)
        if self._job_dots_job is not None and self.window is not None:
            try:
                self.window.after_cancel(self._job_dots_job)
            except Exception:
                pass
            self._job_dots_job = None
        self._visible = False
        if self.window is not None:
            try:
                self.window.withdraw()
            except Exception:
                pass

    def _pointer_in_bounds(self):
        try:
            x = self.parent.winfo_pointerx() - self.window.winfo_rootx()
            y = self.parent.winfo_pointery() - self.window.winfo_rooty()
            return (0 <= x < self.window.winfo_width()
                    and 0 <= y < self.window.winfo_height())
        except Exception:
            return False

    def _content_height(self):
        """按最高一栏的内容高度决定弹窗可视高度，不构建全部控件"""
        left, top, right, bottom = notifier_mod.work_area(self.parent)
        cap = max(120, int((bottom - top) * 0.6) - self.HEADER_HEIGHT - 40)
        tallest = max(col["virtual"].total_h for col in self._columns)
        return max(120, min(tallest + 8, cap))

    def _measure_heights(self):
        """用样例行实测行高，避免写死像素导致行错位"""
        import tkinter as tk
        probe = tk.Frame(self.parent)
        head = tk.Frame(probe, bg=COLORS["secondary"], padx=8, pady=3)
        head.pack(fill=tk.X)
        tk.Label(head, text="sample (1/1 在线) 端口: 8080", bg=COLORS["secondary"],
                 fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor=tk.W).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        row = tk.Frame(probe, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="○", bg=COLORS["bg_card"], fg=COLORS["offline"],
                 font=("Consolas", 9), width=2, anchor=tk.W).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(row, text="10.0.0.1", bg=COLORS["bg_card"], fg=COLORS["offline"],
                 font=("Consolas", 9), anchor=tk.W).pack(side=tk.LEFT)
        probe_text, probe_font = _icon(self.parent, "pause", _ICON_SIZE_SM)
        tk.Label(row, text=probe_text, bg=COLORS["bg_card"], fg=COLORS["offline"],
                 font=probe_font, padx=6).pack(side=tk.RIGHT, padx=(4, 8))
        probe.update_idletasks()
        self._group_height = max(head.winfo_reqheight(), 20)
        self._row_height = max(row.winfo_reqheight(), 16)
        probe.destroy()

    def _make_column(self, parent, title, summary):
        import tkinter as tk
        C = COLORS
        frame = tk.Frame(parent, bg=C["bg_card"])
        frame.pack(side=tk.LEFT, fill=tk.BOTH)
        header = tk.Frame(frame, bg=C["header_bg"], height=self.HEADER_HEIGHT)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        title_label = tk.Label(header, text=title, bg=C["header_bg"],
                               fg=C["header_fg"],
                               font=("Microsoft YaHei UI", 9, "bold"),
                               anchor=tk.W)
        title_label.pack(side=tk.LEFT, padx=(10, 4))
        summary_label = tk.Label(header, text=summary, bg=C["header_bg"],
                                 fg=C["header_fg"],
                                 font=("Microsoft YaHei UI", 8), anchor=tk.E)
        summary_label.pack(side=tk.RIGHT, padx=(4, 10))
        canvas = tk.Canvas(frame, bg=C["bg_card"], highlightthickness=0, bd=0,
                           width=self.COLUMN_WIDTH, height=100)
        return frame, canvas, title_label, summary_label

    def _nacos_entries(self):
        """把服务列表拍平成"分组标题 + 实例行"的模型，O(N) 且不建控件"""
        services = self.app.services
        groups = {}
        for svc in services:
            groups.setdefault(svc["service_name"], []).append(svc)
        pins = self.app.cfg.get("pinned_services") or []
        entries = []
        for svc_name in self.app._ordered_service_names(list(groups)):
            instances = groups[svc_name]
            entries.append({
                "kind": "group", "name": svc_name, "instances": instances,
                "online": sum(1 for i in instances if i["online"]),
                "total": len(instances), "port": instances[0]["port"],
                "pinned": svc_name in pins,
            })
            for inst in instances:
                entries.append({"kind": "instance", "inst": inst})
        return entries

    def _nacos_title(self):
        ip = self.app.nacos_cfg.get("ip", "")
        port = self.app.nacos_cfg.get("port", 8848)
        title = ("Nacos: " + str(ip) + ":" + str(port)) if ip else "Nacos: 未配置"
        if len(title) > 30:
            title = title[:27] + "..."
        return title

    def _nacos_summary(self):
        services = self.app.services
        online = sum(1 for s in services if s["online"])
        return str(online) + "/" + str(len(services))

    def _jenkins_summary(self, jobs):
        failures = sum(1 for job in jobs if job.get("failure"))
        return (str(failures) + " 失败") if failures else (str(len(jobs)) + " 个任务")

    def _add_nacos_column(self, parent):
        frame, canvas, title_label, summary_label = self._make_column(
            parent, self._nacos_title(), self._nacos_summary())
        entries = self._nacos_entries()
        return {
            "kind": "nacos",
            "frame": frame,
            "canvas": canvas,
            "empty_text": "暂无服务数据",
            "title_label": title_label,
            "summary_label": summary_label,
            "virtual": _VirtualColumn(
                canvas, entries,
                [self._group_height if e["kind"] == "group" else self._row_height
                 for e in entries], self),
        }

    def _add_jenkins_column(self, parent):
        from urllib.parse import urlparse
        jobs = list(getattr(self.app, "jenkins_jobs", []) or [])
        url = (self.app.jenkins_cfg or {}).get("url", "")
        host = urlparse(url).netloc or url
        if len(host) > 26:
            host = host[:23] + "..."
        frame, canvas, title_label, summary_label = self._make_column(
            parent, "Jenkins: " + (host or "未配置"), self._jenkins_summary(jobs))
        return {
            "kind": "jenkins",
            "frame": frame,
            "canvas": canvas,
            "empty_text": "暂无构建数据",
            "title_label": title_label,
            "summary_label": summary_label,
            "virtual": _VirtualColumn(
                canvas, [{"kind": "job", "job": job} for job in jobs],
                [self._row_height] * len(jobs), self),
        }

    # ---------- 行绘制 ----------

    def _make_group_row(self, parent, entry):
        import tkinter as tk
        C = COLORS
        frame = tk.Frame(parent, bg=C["secondary"], padx=8, pady=3)
        head = tk.Frame(frame, bg=C["secondary"])
        head.pack(fill=tk.X)
        if entry["pinned"]:
            pin_text, pin_font = _icon(self.parent, "pin", _ICON_SIZE_SM)
            tk.Label(head, text=pin_text, bg=C["secondary"], fg=C["primary"],
                     font=pin_font).pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(head,
                 text="%s (%d/%d 在线) 端口: %s" % (
                     entry["name"], entry["online"], entry["total"], entry["port"]),
                 bg=C["secondary"],
                 fg=C["primary"] if entry["pinned"] else C["text_primary"],
                 font=("Microsoft YaHei UI", 10 if entry["pinned"] else 9, "bold"),
                 anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)
        return frame

    def _make_instance_row(self, parent, entry):
        import tkinter as tk
        C = COLORS
        inst = entry["inst"]
        display = self.app._get_display_name(inst["ip"])
        tag = "online" if inst["online"] else "offline"
        action_color = C["offline"] if inst["online"] else C["online"]
        action_glyph, action_font = _icon(self.parent,
                                          "pause" if inst["online"] else "play",
                                          _ICON_SIZE_SM)
        row = tk.Frame(parent, bg=C["bg_card"], cursor="hand2")
        dot = tk.Label(row, text="●" if inst["online"] else "○",
                       bg=C["bg_card"], fg=C[tag],
                       font=("Consolas", 9), width=2, anchor=tk.W,
                       cursor="hand2")
        dot.pack(side=tk.LEFT, padx=(8, 0))
        name = tk.Label(row, text=display, bg=C["bg_card"], fg=C[tag],
                        font=("Consolas", 9), anchor=tk.W, cursor="hand2")
        name.pack(side=tk.LEFT, fill=tk.X, expand=True)
        action = tk.Label(row, text=action_glyph, bg=C["bg_card"],
                          fg=action_color,
                          font=action_font,
                          cursor="hand2", padx=6, bd=0,
                          highlightthickness=1,
                          highlightbackground=C["bg_card"])
        action.pack(side=tk.RIGHT, padx=(4, 8))
        widgets = (row, dot, name, action)

        def paint(color, ws=widgets):
            for widget in ws:
                try:
                    widget.configure(bg=color)
                except Exception:
                    pass

        def on_enter(event, p=paint, a=action):
            p(C["secondary"])
            a.configure(highlightbackground=C["secondary"])

        def on_leave(event, p=paint, r=row, a=action):
            try:
                x, y = self.parent.winfo_pointerxy()
                if (r.winfo_rootx() <= x <= r.winfo_rootx() + r.winfo_width()
                        and r.winfo_rooty() <= y <= r.winfo_rooty() + r.winfo_height()):
                    return
            except Exception:
                pass
            p(C["bg_card"])
            a.configure(highlightbackground=C["bg_card"])

        for widget in widgets:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
        for widget in (row, dot, name):
            widget.bind("<Button-1>", lambda e, s=inst: self._on_service_click(s))
        action.bind("<Button-1>", lambda e, s=inst: self._on_quick_action(s))
        action.bind("<Enter>", lambda e, a=action: a.configure(
            highlightbackground=C["primary"]), add="+")
        action.bind("<Leave>", lambda e, a=action, r=row: self._restore_action_border(a, r),
                    add="+")
        return row

    def _make_job_row(self, parent, entry):
        import tkinter as tk
        C = COLORS
        job = entry["job"]
        job_name = job.get("name", "")
        alias = (self.app.notes.get("jenkins") or {}).get(job_name, "")
        project = str(job.get("project") or "").strip()
        name = project or alias or job_name
        if job_name in (self.app.dnd.get("jenkins") or {}):
            name = "[勿扰] " + name
        number = job.get("number") or 0
        status_base = "#" + str(number) + " "
        if job.get("building"):
            status_base += "构建中"
            color = C["warning"]
        elif job.get("success"):
            status_base += "成功"
            color = C["online"]
        elif job.get("failure"):
            status_base += "失败"
            color = C["offline"]
        else:
            status_base += "未构建"
            color = C["text_secondary"]
        row = tk.Frame(parent, bg=C["bg_card"], cursor="hand2")
        dot = tk.Label(row, text="●", bg=C["bg_card"], fg=color,
                       font=("Consolas", 9), width=2, anchor=tk.W,
                       cursor="hand2")
        dot.pack(side=tk.LEFT, padx=(8, 0))
        label = tk.Label(row, text=name, bg=C["bg_card"],
                         fg=C["text_primary"], font=("Microsoft YaHei UI", 9),
                         anchor=tk.W, cursor="hand2")
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        status = tk.Label(row, text=status_base + "." * (self._job_dot_phase + 1)
                          if job.get("building") else status_base,
                          bg=C["bg_card"], fg=color,
                          font=("Microsoft YaHei UI", 8), anchor=tk.E,
                          cursor="hand2")
        status.pack(side=tk.RIGHT, padx=(4, 8))
        row.job_status = status
        row.status_base = status_base
        widgets = (row, dot, label, status)

        def paint(color_value, ws=widgets):
            for widget in ws:
                try:
                    widget.configure(bg=color_value)
                except Exception:
                    pass

        def on_enter(event, p=paint):
            p(C["secondary"])

        def on_leave(event, p=paint):
            p(C["bg_card"])

        for widget in widgets:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", lambda e, j=job: self._on_jenkins_click(j))
        return row

    def _on_wheel(self, event):
        """按指针所在栏分发滚轮，避免给每个行控件绑定"""
        for col in self._columns:
            canvas = col["canvas"]
            try:
                x = event.x_root - canvas.winfo_rootx()
                y = event.y_root - canvas.winfo_rooty()
            except Exception:
                continue
            if (-24 <= x <= canvas.winfo_width() + 24
                    and -24 <= y <= canvas.winfo_height() + 24):
                col["virtual"].scroll(event.delta)
                return "break"

    # ---------- 行中间态与提交历史 ----------

    def _hover_button(self, widgets, hovered):
        bg = COLORS["header_hover_bg"] if hovered else COLORS["header_bg"]
        for widget in widgets:
            try:
                widget.configure(bg=bg)
            except Exception:
                pass

    def _begin_job_render(self):
        self._building_job_labels = {}

    def _track_job_row(self, entry, row):
        if not isinstance(entry, dict) or entry.get("kind") != "job":
            return
        job = entry.get("job") or {}
        if not job.get("building"):
            return
        status = getattr(row, "job_status", None)
        base = getattr(row, "status_base", "")
        if status is not None:
            self._building_job_labels[id(row)] = (status, base)

    def _after_job_render(self):
        self._cancel_hover_history()
        if self._history_panel is not None:
            self._history_panel.hide()
        self._ensure_job_dots()

    def _ensure_job_dots(self):
        if self.window is None:
            return
        if not self._building_job_labels:
            if self._job_dots_job is not None:
                try:
                    self.window.after_cancel(self._job_dots_job)
                except Exception:
                    pass
                self._job_dots_job = None
            return
        if self._job_dots_job is None:
            self._job_dot_phase = 0
            self._job_dots_job = self.window.after(300, self._animate_job_dots)

    def _animate_job_dots(self):
        self._job_dots_job = None
        labels = self._building_job_labels
        if not labels or self.window is None or not self.window.winfo_exists():
            return
        self._job_dot_phase = (self._job_dot_phase + 1) % 3
        dots = "." * (self._job_dot_phase + 1)
        for status, base in list(labels.values()):
            try:
                status.configure(text=base + dots)
            except Exception:
                pass
        self._job_dots_job = self.window.after(300, self._animate_job_dots)

    def _on_job_row_leave(self, job):
        pass

    def _cancel_hover_history(self):
        pass

    def _show_history_panel(self, job, anchor=None):
        pass

    def _on_focus_out(self, event):
        if self._modal_open:
            return
        # 圆角外沿是透明抠色，点击会落到下层窗口；若指针仍在弹窗矩形内且
        # 前台已切回主窗口，视为沿角点击，收回焦点而不是收起。
        if self._pointer_in_bounds() and self.app._foreground_is_root():
            try:
                self.window.focus_force()
            except Exception:
                pass
            return
        self._close()

    def _destroy(self):
        self._close()
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
        self._canvas = None
        self._host = None
        self._host_item = None
        self._columns = []
        self._signature = None

    def _on_jenkins_click(self, job):
        url = job.get("url") or ""
        self._close()
        if url:
            webbrowser.open(url)
        else:
            self.app._switch_source(SOURCE_JENKINS)
            self.app._show_window()

    def _on_service_click(self, service):
        """点击 IP 行，弹出上线/下线确认"""
        action = "下线" if service["online"] else "上线"
        note = self.app.notes["nacos"].get(service["ip"], "")
        ip_port = f"{service['ip']}:{service['port']}"
        if note:
            ip_port += f" ({note})"
        msg = f"确定要{action}服务？\n\n{service['service_name']}\n{ip_port}"
        import tkinter.messagebox
        self._modal_open = True
        self._close()
        try:
            confirmed = tkinter.messagebox.askyesno(
                "确认" + action, msg, parent=self.parent)
        finally:
            self._modal_open = False
        if confirmed:
            if service["online"]:
                self.app._take_offline(service)
            else:
                self.app._bring_online(service)

    def _restore_action_border(self, action, row):
        try:
            x, y = self.parent.winfo_pointerxy()
            inside = (row.winfo_rootx() <= x <= row.winfo_rootx() + row.winfo_width()
                      and row.winfo_rooty() <= y <= row.winfo_rooty() + row.winfo_height())
        except Exception:
            inside = False
        action.configure(
            highlightbackground=COLORS["secondary"] if inside else COLORS["bg_card"])

    def _on_quick_action(self, service):
        self._close()
        self.app._quick_toggle_instance(service)

    def _on_restore(self):
        self._close()
        self.app._show_window()

    def _on_settings(self):
        self._close()
        self.app._show_settings()

    def _on_refresh(self):
        self._close()
        self.app._manual_refresh()

    def _on_quit(self):
        self._destroy()
        self.app.quit()


class TrayNotifyApp:
    def __init__(self):
        self.cfg = config.load_config()
        self.nacos_cfg = self.cfg.setdefault("nacos", {})
        self.jenkins_cfg = self.cfg.setdefault("jenkins", {})
        if not isinstance(self.cfg.get("pinned_services"), list):
            self.cfg["pinned_services"] = []
        self._view_mode = self.cfg.get("view_mode", "table")
        if self._view_mode not in ("table", "card"):
            self._view_mode = "table"
        self.client = None
        self.services = []
        self.previous_services = {}
        self.notes = config.load_notes()
        self.dnd = config.load_dnd()
        self.tray = None
        self.running = False
        self._last_login_time = 0
        self._lock = threading.Lock()
        self.root = None
        self._service_tree = None
        self._status_var = None
        self._context_menu = None
        self._menu_canvas = None
        self._menu_host = None
        self._menu_host_item = None
        self._menu_transparent_key = None
        self._service_popup = None
        self._notified = set()
        self._last_online_time = {}
        self._search_var = None
        self._list_frame = None
        self._nacos_container = None
        self._jenkins_container = None
        self._last_menu_fingerprint = None
        self._source = SOURCE_NACOS
        self.jenkins_jobs = []
        self._jenkins_tree = None
        self._jenkins_rows = {}
        self._jenkins_status = {
            "state": "unconfigured", "configured": False, "error": "",
            "jobs": [], "last_success": "", "last_error": "",
        }
        self._jenkins_monitor = None
        self._notifier = None
        self._daozai = None
        self._source_segments = []
        self._source_canvas = None
        self._source_boxes = []
        active = [s for s in (SOURCE_NACOS, SOURCE_JENKINS)
                  if bool((self.cfg.get(s) or {}).get("enabled", True))]
        if not active:
            # 未显式关闭时保留旧行为：有连接信息即视为开启
            active = []
            if self.nacos_cfg.get("ip"):
                active.append(SOURCE_NACOS)
            if self.jenkins_cfg.get("url"):
                active.append(SOURCE_JENKINS)
        if self._source not in active and active:
            self._source = active[0]
        self._cards_canvas = None
        self._cards_frame = None
        self._cards_window = None
        self._card_states = {}
        self._card_order = []
        self._card_cols = 0
        self._cards_empty = None
        self._menu_service = None
        self._menu_service_name = None
        self._last_pin_click = None
        self._poll_in_progress = False
        self._dialogs = {}
        self._theme_job = None
        self._shortcut_sequences = []
        self._last_refresh_time = None
        self._hover_job = None
        self._hover_window = None
        self._hover_service = None
        self._hover_table_item = None
        self._cards_compact = False
        self._quick_pending = set()
        self._pending_dots_job = None
        self._pending_dot_phase = 0
        self._jenkins_dots_job = None
        self._jenkins_dot_phase = 0
        self._commit_history_cache = {}
        self._progress_canvas = None
        self._progress_active = False
        self._progress_job = None
        self._progress_pos = 0
        self._system_light = theme_mod.system_uses_light()
        self._frosted_float = bool(self.cfg.get("theme_frosted_glass")) and theme_mod.is_win11_or_newer()
        COLORS.clear()
        COLORS.update(theme_mod.build_palette(self.cfg))

    def _register_dialog(self, key, window, reopen=None, dialog=None):
        self._dialogs[key] = {"window": window, "reopen": reopen, "dialog": dialog}

    def _unregister_dialog(self, key, window=None):
        entry = self._dialogs.get(key)
        if entry and (window is None or entry.get("window") is window):
            self._dialogs.pop(key, None)

    def _source_enabled(self, source):
        cfg = self.cfg.get(source) if isinstance(self.cfg.get(source), dict) else {}
        return bool(cfg.get("enabled", True))

    def _active_sources(self):
        return [s for s in (SOURCE_NACOS, SOURCE_JENKINS)
                if self._source_enabled(s)]

    def _enabled_sources_map(self):
        """通知中心据此过滤已关闭来源的通知"""
        return {
            SOURCE_NACOS: self._source_enabled(SOURCE_NACOS),
            SOURCE_JENKINS: self._source_enabled(SOURCE_JENKINS),
        }

    def _apply_theme(self, cfg=None, structural=False):
        """立即切换主题：主窗口默认原地换色；structural=True 时仍走整窗重建

        structural 供设置保存等会改变视图模式 / 通知源结构的路径复用旧行为。
        """
        target = cfg if cfg is not None else self.cfg
        old_palette = dict(COLORS)
        COLORS.clear()
        COLORS.update(theme_mod.build_palette(target))
        # 浮层材质取自本次生效配置，保证设置页实时预览与保存后一致
        self._frosted_float = bool(target.get("theme_frosted_glass")) and theme_mod.is_win11_or_newer()
        dark = COLORS.get("mode") == theme_mod.MODE_DARK
        # 浮层颜色在创建时固化，切主题必须销毁单例后按新色重建
        self._destroy_service_popup()
        self._discard_context_menu()
        if self.root:
            if structural:
                self._rebuild_root_ui()
            else:
                self._restyle_root_ui(old_palette)
            theme_mod.set_dark_titlebar(self.root, dark)
        for key, entry in list(self._dialogs.items()):
            window = entry.get("window")
            if window is None or not window.winfo_exists():
                self._dialogs.pop(key, None)
                continue
            if key == "settings":
                if entry.get("dialog"):
                    entry["dialog"].rebuild()
                theme_mod.set_dark_titlebar(window, dark)
                continue
            geometry = window.geometry()
            window.destroy()
            self._dialogs.pop(key, None)
            if entry.get("reopen"):
                entry["reopen"](geometry)

    # 只重配这些 tk 控件类：ttk 由 apply_ttk_style 统一处理，避免逐个覆盖样式
    _THEME_BG_WIDGETS = ("Tk", "Toplevel", "Frame", "Label", "Canvas", "Button",
                         "LabelFrame", "Entry", "Text", "Listbox", "Spinbox",
                         "Menubutton", "Message", "Checkbutton", "Radiobutton",
                         "Scale", "Scrollbar")
    _THEME_FG_WIDGETS = ("Label", "Button", "Entry", "Text", "Listbox", "Spinbox",
                         "Menubutton", "Message", "Checkbutton", "Radiobutton",
                         "Scale")

    # 语义键优先级：旧值被多个键共用且新值不一致时，按此顺序取最可能的新值
    _THEME_BG_KEY_ORDER = ("bg_main", "bg_card", "header_bg", "bg_row_alt",
                           "bg_hover", "selection_bg", "separator",
                           "header_hover_bg", "secondary", "primary",
                           "primary_dark")
    _THEME_FG_KEY_ORDER = ("text_primary", "header_fg", "header_text",
                           "text_secondary", "online", "offline", "warning",
                           "primary", "primary_dark")

    def _theme_choose_target(self, pairs, order):
        """pairs 为 (语义键, 新值) 列表；先按多数新值，平票再按语义键优先级"""
        counts = {}
        for _key, dst in pairs:
            counts[dst] = counts.get(dst, 0) + 1
        best = max(counts.values())
        leaders = [dst for dst, count in counts.items() if count == best]
        if len(leaders) == 1:
            return leaders[0]
        rank = {}
        for idx, key in enumerate(order):
            rank[key] = idx
        chosen = None
        chosen_rank = None
        for key, dst in pairs:
            value = rank.get(key, len(order))
            if chosen_rank is None or value < chosen_rank:
                chosen_rank = value
                chosen = dst
        return chosen

    def _theme_slot_maps(self, old_palette, new_palette):
        """按背景 / 前景两个槽位分别生成 旧值 -> 新值 映射。

        同一旧值被多个语义键共用时，按槽位分开解析（如白底与白字不会互相污染），
        槽位内仍冲突则取多数新值、平票按语义键优先级。
        """
        groups = {}
        for key, value in old_palette.items():
            if not isinstance(value, str) or not value.startswith("#"):
                continue
            target = new_palette.get(key)
            if not isinstance(target, str) or not target.startswith("#"):
                continue
            groups.setdefault(value.upper(), []).append((key, target.upper()))
        bg_map = {}
        fg_map = {}
        for src, pairs in groups.items():
            for mapping, order in ((bg_map, self._THEME_BG_KEY_ORDER),
                                   (fg_map, self._THEME_FG_KEY_ORDER)):
                role_pairs = [(k, d) for k, d in pairs if k in order]
                if not role_pairs:
                    continue
                dst = self._theme_choose_target(role_pairs, order)
                if dst != src:
                    mapping[src] = dst
        return bg_map, fg_map

    def _recolor_canvas_items(self, canvas, bg_map, fg_map):
        try:
            items = canvas.find_all()
        except Exception:
            return
        for item in items:
            opts = {}
            try:
                itype = canvas.type(item)
            except Exception:
                continue
            mapping = fg_map if itype == "text" else bg_map
            try:
                fill = canvas.itemcget(item, "fill")
            except Exception:
                fill = None
            if isinstance(fill, str) and fill.upper() in mapping:
                opts["fill"] = mapping[fill.upper()]
            if itype in ("rectangle", "oval", "polygon", "arc"):
                try:
                    outline = canvas.itemcget(item, "outline")
                except Exception:
                    outline = None
                if isinstance(outline, str) and outline.upper() in mapping:
                    opts["outline"] = mapping[outline.upper()]
            if opts:
                try:
                    canvas.itemconfigure(item, **opts)
                except Exception:
                    pass

    def _recolor_widget(self, widget, bg_map, fg_map):
        """递归把仍在用旧调色板的 tk 控件换成新值；未识别颜色保持不变"""
        if not bg_map and not fg_map:
            return
        try:
            cls = widget.winfo_class()
            children = widget.winfo_children()
        except Exception:
            return
        if cls in self._THEME_BG_WIDGETS:
            for opt in ("background", "highlightbackground"):
                try:
                    current = widget.cget(opt)
                except Exception:
                    current = None
                if isinstance(current, str) and current.upper() in bg_map:
                    try:
                        widget.configure(**{opt: bg_map[current.upper()]})
                    except Exception:
                        pass
        if cls in self._THEME_FG_WIDGETS:
            try:
                current = widget.cget("foreground")
            except Exception:
                current = None
            if isinstance(current, str) and current.upper() in fg_map:
                try:
                    widget.configure(foreground=fg_map[current.upper()])
                except Exception:
                    pass
        if isinstance(widget, ThinScrollbar):
            # 滚动条滑块是 blend 出来的派生色，重画一次才会跟上
            try:
                widget._redraw()
            except Exception:
                pass
        if cls == "Canvas":
            self._recolor_canvas_items(widget, bg_map, fg_map)
        for child in children:
            self._recolor_widget(child, bg_map, fg_map)

    def _restyle_tree_tags(self, tree, bg_map, fg_map):
        """Treeview 标签色随调色板更新（选中色由 ttk 样式的 map 负责）"""
        if tree is None or (not bg_map and not fg_map):
            return
        try:
            if not tree.winfo_exists():
                return
        except Exception:
            return
        for tag in tree.tag_names():
            opts = {}
            try:
                current = tree.tag_configure(tag, "foreground")
            except Exception:
                current = None
            if isinstance(current, str) and current.upper() in fg_map:
                opts["foreground"] = fg_map[current.upper()]
            try:
                current = tree.tag_configure(tag, "background")
            except Exception:
                current = None
            if isinstance(current, str) and current.upper() in bg_map:
                opts["background"] = bg_map[current.upper()]
            if opts:
                try:
                    tree.tag_configure(tag, **opts)
                except Exception:
                    pass

    def _reset_card_row_colors(self):
        """卡片行的悬停色是绘制时固化的，换主题后按新调色板重画"""
        for state in list(getattr(self, "_card_states", {}).values()):
            for row in list((state.get("rows_map") or {}).values()):
                base = row.get("base_bg", COLORS["bg_card"])
                color = COLORS["bg_hover"] if row.get("hovered") else base
                if row.get("action_hovered"):
                    try:
                        row["action"].configure(highlightbackground=COLORS["primary"])
                    except Exception:
                        pass
                try:
                    self._paint_card_row(row, color)
                except Exception:
                    pass

    def _restyle_root_ui(self, old_palette):
        """原地换色：不销毁主窗口，保留来源容器、滚动位置与选中项"""
        if not self.root or not self.root.winfo_exists():
            return
        self._cancel_hover_job()
        self._hide_tooltip()
        self._close_context_menu()
        bg_map, fg_map = self._theme_slot_maps(old_palette, COLORS)
        theme_mod.apply_ttk_style(self.root, COLORS, self._table_row_height())
        self._recolor_widget(self.root, bg_map, fg_map)
        cards_frame = getattr(self, "_cards_frame", None)
        if cards_frame is not None:
            try:
                if cards_frame.winfo_exists():
                    self._recolor_widget(cards_frame, bg_map, fg_map)
            except Exception:
                pass
        self._restyle_tree_tags(getattr(self, "_service_tree", None), bg_map, fg_map)
        self._restyle_tree_tags(getattr(self, "_jenkins_tree", None), bg_map, fg_map)
        self._update_source_buttons()
        self._update_window()
        self._reset_card_row_colors()
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _apply_float_material(self, window, transparent_key=None):
        """给浮层窗口套 DWM 毛玻璃背板；不支持或调用失败时静默保持高仿质感。

        透明抠色的 shaped window 始终保留（圆角优先）：背板生效后重新确认抠色，
        避免背板铺满整个窗口把圆角压成方角或产生杂边；开关或主题切换时浮层单例
        会被销毁重建，下一次打开即生效，避免残影。
        """
        if not self._frosted_float:
            return False
        try:
            applied = theme_mod.set_frosted_glass(window, True)
        except Exception:
            return False
        if applied and transparent_key:
            try:
                window.attributes("-transparentcolor", transparent_key)
            except Exception:
                pass
        return applied

    def _ensure_theme_poll(self):
        if not self.root or not self.running:
            return
        if self.cfg.get("theme_mode") != theme_mod.MODE_SYSTEM:
            return
        if self._theme_job is None:
            self._theme_job = self.root.after(5000, self._poll_theme)

    def _poll_theme(self):
        self._theme_job = None
        if not self.running or not self.root:
            return
        if self.cfg.get("theme_mode") != theme_mod.MODE_SYSTEM:
            return
        light = theme_mod.system_uses_light()
        if light != self._system_light:
            self._system_light = light
            self._apply_theme()
        self._theme_job = self.root.after(5000, self._poll_theme)

    def _init_client(self):
        if not self.nacos_cfg.get("ip"):
            self.client = None
            return False
        self.client = NacosClient(
            ip=self.nacos_cfg["ip"],
            port=self.nacos_cfg.get("port", 8848),
            username=self.nacos_cfg.get("username", "nacos"),
            password=self.nacos_cfg.get("password", "nacos"),
            namespace=self.nacos_cfg.get("namespace", ""),
            cluster_name=self.nacos_cfg.get("cluster_name", "ShenZhen"))
        return True

    def _do_login(self):
        if not self.client:
            if not self._init_client():
                return False
        success = self.client.login()
        if success:
            self._last_login_time = time.time()
        return success

    def _ensure_login(self):
        if self.client and self.client.is_token_valid():
            return True
        return self._do_login()

    def _refresh_login_if_needed(self):
        interval = self.nacos_cfg.get("login_interval", 1800)
        if time.time() - self._last_login_time >= interval:
            self._do_login()

    def _fetch_services(self):
        """返回实例列表；获取失败返回 None，与"确实没有服务"区分"""
        if not self._ensure_login():
            return None
        try:
            return self.client.get_all_services_with_status()
        except Exception as e:
            print("Fetch failed: " + str(e))
            if self.client:
                self.client.token = None
            return None

    def _mark_fetch_failed(self, label="Nacos 获取失败"):
        if self._status_var and self._source == SOURCE_NACOS:
            self._status_var.set(label + "，保留上一次数据")

    def _detect_changes(self, current_services):
        changes = []
        current_map = {}
        for svc in current_services:
            key = svc["service_name"] + ":" + svc["ip"] + ":" + str(svc["port"])
            current_map[key] = svc
        for key, svc in current_map.items():
            if key in self.previous_services:
                prev = self.previous_services[key]
                if not prev["online"] and svc["online"]:
                    changes.append(("up", svc))
                    self._last_online_time[key] = time.strftime("%Y-%m-%d %H:%M:%S")
                elif prev["online"] and not svc["online"]:
                    changes.append(("offline", svc))
            else:
                if svc["online"]:
                    changes.append(("up", svc))
                    self._last_online_time[key] = time.strftime("%Y-%m-%d %H:%M:%S")
        for key, prev in self.previous_services.items():
            if key not in current_map:
                changes.append(("removed", prev))
        self.previous_services = current_map
        return changes

    def _get_display_name(self, ip):
        note = self.notes["nacos"].get(ip, "")
        if note:
            return ip + "(" + note + ")"
        return ip

    def _notify_change(self, event_type, service):
        if service["ip"] in self.dnd["nacos"]:
            return None
        svc_name = service["service_name"]
        ip = service["ip"]
        note = self.notes["nacos"].get(ip, "")
        port = str(service["port"])
        line = svc_name + "[" + port + "] " + ip + ("(" + note + ")" if note else "")
        cluster = str(service.get("cluster_name") or "").strip()
        env = cluster or str(self.nacos_cfg.get("env") or "").strip() or "dev"
        env_tag = " " + env
        lines_extra = ["环境：" + env]
        if event_type == "up":
            title = svc_name + env_tag + " 服务上线"
            level = "success"
            msg = "项目：" + line
        elif event_type == "offline":
            title = svc_name + env_tag + " 注意下线"
            level = "warning"
            msg = "服务被手动下线！" + chr(10) + "项目：" + line
        else:
            title = svc_name + env_tag + " 服务下线"
            level = "error"
            msg = "项目：" + line
        if lines_extra:
            msg += chr(10) + chr(10).join(lines_extra)
        return {
            "source": "nacos",
            "level": level,
            "title": title,
            "body": msg,
            "url": "",
            "key": "nacos:" + svc_name + ":" + ip + ":" + port,
            "time": time.time(),
        }

    def _update_tray_tooltip(self):
        if not self.tray:
            return
        total = len(self.services)
        online = sum(1 for s in self.services if s["online"])
        ip = self.nacos_cfg.get("ip", "")
        port = self.nacos_cfg.get("port", 8848)
        tooltip = APP_NAME + chr(10)
        if ip:
            tooltip += "Nacos: " + str(ip) + ":" + str(port)
            tooltip += " " + str(online) + "/" + str(total)
        else:
            tooltip += "Nacos: 未配置"
        jenkins_url = self.jenkins_cfg.get("url", "")
        if jenkins_url:
            host = urlparse(jenkins_url).netloc or jenkins_url
            failures = sum(1 for job in self.jenkins_jobs if job.get("failure"))
            tooltip += chr(10) + "Jenkins: " + host
            if self._jenkins_status.get("state") == "error":
                tooltip += " 连接异常"
            else:
                tooltip += " " + str(len(self.jenkins_jobs)) + " 任务"
                if failures:
                    tooltip += " " + str(failures) + " 失败"
        self.tray.set_tooltip(tooltip)

    def _build_menu(self):
        if not self.tray:
            return
        items = []
        if self._source_enabled(SOURCE_NACOS):
            items.append({"text": "Nacos: " + self.nacos_cfg.get("ip", "未配置"),
                          "enabled": False})
            items.append(None)
            if not self.services:
                items.append({"text": "(未获取到服务)", "enabled": False})
            else:
                service_groups = {}
                for svc in self.services:
                    name = svc["service_name"]
                    if name not in service_groups:
                        service_groups[name] = []
                    service_groups[name].append(svc)
                for svc_name, instances in sorted(service_groups.items()):
                    for inst in instances:
                        status = "[在线]" if inst["online"] else "[离线]"
                        if inst["ip"] in self.dnd["nacos"]:
                            status = "[勿扰]" + status
                        display_name = self._get_display_name(inst["ip"])
                        text = "  " + status + " " + display_name + ":" + str(inst["port"])
                        if inst["online"]:
                            items.append({"text": text, "callback": lambda s=inst: self._take_offline(s)})
                        else:
                            items.append({"text": text, "callback": lambda s=inst: self._bring_online(s)})
                    online_count = sum(1 for i in instances if i["online"])
                    total_count = len(instances)
                    items.append({"text": "  -> " + svc_name + " (" + str(online_count) + "/" + str(total_count) + " 在线)", "enabled": False})
        if self._source_enabled(SOURCE_JENKINS) and self.jenkins_cfg.get("url"):
            items.append(None)
            failures = sum(1 for job in self.jenkins_jobs if job.get("failure"))
            status = "连接异常" if self._jenkins_status.get("state") == "error" else (
                str(len(self.jenkins_jobs)) + " 个任务"
                + (("，" + str(failures) + " 个失败") if failures else ""))
            host = urlparse(self.jenkins_cfg.get("url", "")).netloc or self.jenkins_cfg.get("url", "")
            items.append({"text": "Jenkins: " + host, "enabled": False})
            items.append({"text": "  -> " + status, "enabled": False})
        items.append(None)
        items.append({"text": "还原窗口", "callback": self._show_window})
        items.append({"text": "设置...", "callback": self._show_settings})
        items.append(None)
        items.append({"text": "立即刷新", "callback": self._manual_refresh})
        items.append({"text": "退出", "callback": self.quit})
        # 内容指纹：服务名/在线态/勿扰/置顶与 Jenkins 摘要不变时跳过原生菜单重建
        parts = ["pins=" + ",".join(self.cfg.get("pinned_services") or [])]
        for item in items:
            if item is None:
                parts.append("-")
            else:
                parts.append(str(item.get("text", ""))
                              + "|" + ("1" if item.get("enabled", True) else "0")
                              + "|" + ("1" if item.get("checked") else "0"))
        fingerprint = chr(31).join(parts)
        if fingerprint == self._last_menu_fingerprint:
            return
        self._last_menu_fingerprint = fingerprint
        self.tray.set_menu_items(items)

    def _notify(self, title, body, level="info", url="", source=""):
        if self._notifier:
            self._notifier.notify(title, body, level=level, url=url, source=source)
        self._refresh_popup_data()

    def _take_offline(self, service):
        if not self._ensure_login():
            self._notify("错误", "未连接到 Nacos", "error")
            return
        try:
            self.client.update_instance_status(service["service_name"], service["ip"], service["port"], enabled=False)
            self._notify("成功", "已下线: " + service["service_name"], "success")
            time.sleep(1)
            self._manual_refresh()
        except Exception as e:
            self._notify("失败", "下线失败: " + str(e), "error")

    def _bring_online(self, service):
        if not self._ensure_login():
            self._notify("错误", "未连接到 Nacos", "error")
            return
        try:
            self.client.update_instance_status(service["service_name"], service["ip"], service["port"], enabled=True)
            self._notify("成功", "已上线: " + service["service_name"], "success")
            time.sleep(1)
            self._manual_refresh()
        except Exception as e:
            self._notify("失败", "上线失败: " + str(e), "error")

    def _show_settings(self, geometry=None, page=None):
        # 设置窗口是主窗口的 transient，从托盘弹窗打开时若主窗口仍被隐藏会看不到
        self._show_window()
        if not self.root:
            return
        entry = self._dialogs.get("settings")
        if entry and entry.get("window") and entry["window"].winfo_exists():
            if page is not None and entry.get("dialog"):
                entry["dialog"]._select_page(page)
            entry["window"].lift()
            entry["window"].focus_force()
            return
        if page is None and self._source == SOURCE_JENKINS:
            page = SettingsDialog.PAGE_JENKINS_CONNECTION

        def on_save(new_cfg):
            prev_view = self._view_mode
            prev_sources = (self._source_enabled(SOURCE_NACOS),
                            self._source_enabled(SOURCE_JENKINS))
            self.cfg = new_cfg
            self.nacos_cfg = new_cfg.get("nacos", {})
            self.jenkins_cfg = new_cfg.get("jenkins", {})
            self._view_mode = new_cfg.get("view_mode", "table")
            if self._view_mode not in ("table", "card"):
                self._view_mode = "table"
            # 只有视图模式或通知源结构变化才需要整窗重建，纯主题保存走原地换色
            structural = (self._view_mode != prev_view
                          or (self._source_enabled(SOURCE_NACOS),
                              self._source_enabled(SOURCE_JENKINS)) != prev_sources)
            if self._notifier:
                self._notifier.dismiss_all()
            self._apply_theme(structural=structural)
            if self._source_enabled(SOURCE_NACOS) and self.nacos_cfg.get("ip"):
                self._init_client()
                self._do_login()
            self._restart_jenkins_monitor()
            self._manual_refresh()
            self._ensure_theme_poll()
            notify_cfg = new_cfg.get("notify") or {}
            if self._daozai:
                self._daozai.configure(notify_cfg.get("daozai_credentials", ""),
                                       bool(notify_cfg.get("daozai_enabled")))

        SettingsDialog(self.root, self.cfg, on_save=on_save, app=self,
                       geometry=geometry, page=page)

    def _get_all_ips(self):
        ips = set()
        for svc in self.services:
            ips.add(svc["ip"])
        return sorted(ips)

    def _show_notes(self, geometry=None):
        self._show_settings(page=SettingsDialog.PAGE_NACOS_NOTES)

    def _show_window(self):
        print("[APP] _show_window called, root:", self.root is not None)
        if self.root:
            try:
                print("[APP] state before:", self.root.state())
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
                self.root.update_idletasks()
                print("[APP] state after:", self.root.state())
            except Exception as e:
                print("[APP] error:", e)

    def _show_service_list_popup(self):
        """显示服务列表弹窗（单例复用）"""
        if not self.root:
            return
        if self._service_popup is None:
            self._service_popup = ServiceListPopup(self.root, self)
        self._service_popup.show()

    def _refresh_popup_data(self):
        """静默刷新托盘右键弹窗内容：状态更新时提前刷新，右键弹出即最新"""
        popup = self._service_popup
        if popup is None:
            return
        try:
            if popup.window is not None and popup.window.winfo_exists():
                popup._refresh_data(reset_scroll=False)
        except Exception:
            pass

    def _destroy_service_popup(self):
        if self._service_popup is not None:
            self._service_popup._destroy()
            self._service_popup = None

    def _manual_refresh(self):
        if self._jenkins_monitor:
            self._jenkins_monitor.poll_now(force_discovery=True)
        if not (self._source_enabled(SOURCE_NACOS) and self.nacos_cfg.get("ip")):
            return
        self._show_progress()

        def _worker():
            try:
                services = self._fetch_services()
            except Exception as e:
                print("Manual refresh error: " + str(e))
                services = None
            if self.root and self.running:
                self.root.after(0, self._on_manual_refresh_data, services)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_manual_refresh_data(self, services):
        if not self.running:
            self._hide_progress()
            return
        self._hide_progress()
        if services is None:
            self._mark_fetch_failed()
        elif services:
            self._last_refresh_time = time.strftime("%Y-%m-%d %H:%M:%S")
            with self._lock:
                self.services = services
                new_map = {}
                for svc in services:
                    key = svc["service_name"] + ":" + svc["ip"] + ":" + str(svc["port"])
                    new_map[key] = svc
                    if svc["online"] and key not in self._last_online_time:
                        self._last_online_time[key] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.previous_services = new_map
            self._update_tray_tooltip()
            self._build_menu()
            if self._source == SOURCE_NACOS:
                self._update_window()
        local_ips = _get_local_ips()
        changed = False
        for ip in local_ips:
            if ip not in self.notes["nacos"]:
                self.notes["nacos"][ip] = "本机"
                changed = True
        if changed:
            config.save_notes(self.notes)

    def _render_status_metrics(self, pairs):
        """状态栏右侧指标：数字用标题档加粗，单位用微型档，形成明确层级"""
        import tkinter as tk
        frame = getattr(self, "_status_metric_frame", None)
        if frame is None:
            return
        C = COLORS
        for child in frame.winfo_children():
            child.destroy()
        for idx, (value, unit) in enumerate(pairs or []):
            if idx:
                tk.Label(frame, text="", bg=C["bg_main"],
                         padx=theme_mod.SPACING_SCALE[2]).pack(side=tk.LEFT)
            tk.Label(frame, text=str(value), bg=C["bg_main"], fg=C["text_primary"],
                     font=theme_mod.font("title", True)).pack(side=tk.LEFT)
            tk.Label(frame, text=" " + unit, bg=C["bg_main"], fg=C["text_secondary"],
                     font=theme_mod.font("micro")).pack(side=tk.LEFT)

    def _update_window(self):
        if not self.root:
            return
        if self._source == SOURCE_JENKINS:
            self._update_jenkins_table()
            return
        if self._view_mode == "card":
            if not self._cards_canvas:
                return
        elif not self._service_tree:
            return
        try:
            search_text = getattr(self, "_search_var", None)
            search_lower = search_text.get().strip().lower() if search_text else ""
            groups, showing = self._collect_service_groups(search_lower)
            if self._view_mode == "card":
                self._update_cards(groups, search_lower)
            else:
                self._update_table(groups)
            total = len(self.services)
            online = sum(1 for s in self.services if s["online"])
            if self._status_var:
                if search_lower and showing != total:
                    self._status_var.set("显示 " + str(showing) + "/" + str(total) + " 个服务，" + str(online) + " 个在线（过滤中）")
                else:
                    self._status_var.set("共 " + str(total) + " 个服务，" + str(online) + " 个在线")
            self._render_status_metrics([(str(online) + "/" + str(total), "在线")] if total else [])
            if hasattr(self, '_status_dot'):
                if total == 0:
                    self._status_dot.configure(fg=COLORS["text_secondary"])
                elif online == total:
                    self._status_dot.configure(fg=COLORS["online"])
                else:
                    self._status_dot.configure(fg=COLORS["warning"])
        except Exception as e:
            print("Update window error: " + str(e))

    def _ordered_service_names(self, names):
        pins = self.cfg.get("pinned_services") or []

        def sort_key(name):
            if name in pins:
                return (0, pins.index(name), name)
            return (1, 0, name)

        return sorted(names, key=sort_key)

    def _collect_service_groups(self, search_lower):
        groups = {}
        showing = 0
        for svc in self.services:
            name = svc["service_name"]
            if search_lower:
                display = self._get_display_name(svc["ip"])
                if (search_lower not in name.lower()
                        and search_lower not in svc["ip"].lower()
                        and search_lower not in display.lower()
                        and search_lower not in str(svc["port"])):
                    continue
            groups.setdefault(name, []).append(svc)
            showing += 1
        ordered = [(name, groups[name]) for name in self._ordered_service_names(list(groups))]
        return ordered, showing

    def _update_table(self, groups):
        tree = self._service_tree
        if not tree or not tree.winfo_exists():
            return
        self._hide_tooltip()
        self._hover_table_item = None
        pins = self.cfg.get("pinned_services") or []
        striped = bool(self.cfg.get("table_striped", True))
        selected = tree.selection()
        # 行键 = (服务名, 实例 IP)；同键多行时追加确定性后缀，保证 iid 唯一
        desired = []
        seen_keys = {}
        row_idx = 0
        for svc_name, instances in groups:
            pin_mark = (_ICON_GLYPHS["pin"][1] if svc_name in pins
                        else _ICON_GLYPHS["unpin"][1])
            for inst in instances:
                status = "[在线]" if inst["online"] else "[离线]"
                if inst["ip"] in self.dnd["nacos"]:
                    status = "[勿扰]" + status
                display_name = self._get_display_name(inst["ip"])
                last_key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
                last_time = self._last_online_time.get(last_key, "-")
                tag = "online" if inst["online"] else "offline"
                if striped and row_idx % 2 == 1:
                    tag = (tag, "alt")
                tag = (tag,) if isinstance(tag, str) else tuple(tag)
                key = svc_name + chr(31) + inst["ip"]
                dup = seen_keys.get(key, 0)
                seen_keys[key] = dup + 1
                iid = key if dup == 0 else key + chr(31) + "#" + str(dup)
                values = (pin_mark, _ICON_GLYPHS["info"][1], svc_name, display_name,
                          str(inst["port"]), status, last_time)
                desired.append((iid, values, tag))
                row_idx += 1
        self._diff_tree_rows(tree, desired)
        alive = set(tree.get_children())
        for iid in selected:
            if iid in alive:
                tree.selection_set(iid)

    def _diff_tree_rows(self, tree, desired):
        """按行键增量同步 Treeview：只更新变化行，移动既有行而非整表重排"""
        if not tree or not tree.winfo_exists():
            return
        existing = tree.get_children()
        existing_info = {}
        for iid in existing:
            existing_info[iid] = (tuple(tree.item(iid, "values") or ()),
                                  set(tree.item(iid, "tags") or ()))
        desired_iids = [row[0] for row in desired]
        desired_map = {row[0]: row for row in desired}
        desired_set = set(desired_iids)
        removed = [iid for iid in existing if iid not in desired_set]
        added = [iid for iid in desired_iids if iid not in existing_info]
        if removed:
            tree.delete(*removed)
        for iid in added:
            _, values, tag = desired_map[iid]
            tree.insert("", "end", iid=iid, values=values, tags=tag)
        for iid in desired_iids:
            if iid in added:
                continue
            _, values, tag = desired_map[iid]
            old_values, old_tags = existing_info.get(iid, ((), set()))
            if tuple(values) != old_values or set(tag) != old_tags:
                tree.item(iid, values=values, tags=tag)
        current = list(tree.get_children())
        for idx, iid in enumerate(desired_iids):
            if idx < len(current) and current[idx] == iid:
                continue
            tree.move(iid, "", idx)
            current.remove(iid)
            current.insert(idx, iid)

    def _poll_once(self):
        if not self.running:
            return
        if not (self._source_enabled(SOURCE_NACOS) and self.nacos_cfg.get("ip")):
            self._schedule_poll()
            return
        if getattr(self, "_poll_in_progress", False):
            self._schedule_poll()
            return
        self._poll_in_progress = True
        if self.root:
            self.root.after(0, self._show_progress)

        def _worker():
            try:
                self._refresh_login_if_needed()
                services = self._fetch_services()
            except Exception as e:
                print("Poll error: " + str(e))
                services = None
            if self.root and self.running:
                self.root.after(0, self._on_poll_data, services)

        threading.Thread(target=_worker, daemon=True).start()

    def _show_progress(self):
        if not self._progress_canvas or self._progress_active:
            return
        self._progress_active = True
        self._progress_pos = 0
        self._animate_progress()

    def _hide_progress(self):
        self._progress_active = False
        if self._progress_job:
            try:
                self.root.after_cancel(self._progress_job)
            except Exception:
                pass
            self._progress_job = None
        if self._progress_canvas:
            try:
                self._progress_canvas.delete("bar")
            except Exception:
                pass

    def _animate_progress(self):
        self._progress_job = None
        if not self._progress_active or not self._progress_canvas:
            return
        try:
            if not self._progress_canvas.winfo_exists():
                return
            width = self._progress_canvas.winfo_width()
            if width <= 1:
                width = 600
            bar_width = max(60, width // 4)
            self._progress_canvas.delete("bar")
            self._progress_canvas.create_rectangle(
                self._progress_pos, 0, self._progress_pos + bar_width, 3,
                fill=COLORS["primary"], outline="", tags="bar")
            self._progress_pos += max(6, width // 48)
            if self._progress_pos > width:
                self._progress_pos = -bar_width
        except Exception:
            return
        try:
            self._progress_job = self.root.after(30, self._animate_progress)
        except Exception:
            self._progress_job = None

    def _on_poll_data(self, services):
        if not self.running:
            self._poll_in_progress = False
            self._hide_progress()
            self._schedule_poll()
            return
        if not self._source_enabled(SOURCE_NACOS):
            self._poll_in_progress = False
            self._schedule_poll()
            return
        self._hide_progress()
        try:
            if services is None:
                self._mark_fetch_failed()
            elif services:
                self._last_refresh_time = time.strftime("%Y-%m-%d %H:%M:%S")
                with self._lock:
                    self.services = services
                changes = self._detect_changes(services)
                events = []
                for event_type, svc in changes:
                    event = self._notify_change(event_type, svc)
                    if event:
                        events.append(event)
                if events and self._notifier:
                    self._notifier.notify_batch(events)
                self._update_tray_tooltip()
                self._build_menu()
                if self._source == SOURCE_NACOS:
                    self._update_window()
                self._refresh_popup_data()
        except Exception as e:
            print("Poll UI update error: " + str(e))
        self._poll_in_progress = False
        self._schedule_poll()

    def _schedule_poll(self):
        if self.running and self.root:
            try:
                self.root.after(self.nacos_cfg.get("poll_interval", 30) * 1000,
                                self._poll_once)
            except:
                pass

    def _create_window(self):
        import tkinter as tk
        self.root = tk.Tk()
        _set_icon(self.root)
        self.root.title(APP_NAME + " " + APP_VERSION)
        self.root.geometry("800x560")
        self.root.minsize(600, 400)
        _center_on_screen(self.root)
        self._build_root_ui()
        theme_mod.set_dark_titlebar(self.root, COLORS.get("mode") == theme_mod.MODE_DARK)

    def _rebuild_root_ui(self):
        if not self.root:
            return
        self._cancel_hover_job()
        self._hide_tooltip()
        self._close_context_menu()
        for child in self.root.winfo_children():
            if child.winfo_class() == "Toplevel":
                continue
            child.destroy()
        self._build_root_ui()

    def _build_root_ui(self):
        import tkinter as tk
        from tkinter import ttk
        sp_xs, sp_sm, sp_md, sp_lg = theme_mod.SPACING_SCALE
        self.root.configure(bg=COLORS["bg_main"])
        theme_mod.apply_ttk_style(self.root, COLORS, self._table_row_height())
        main_frame = ttk.Frame(self.root, padding=0)
        main_frame.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(main_frame, bg=COLORS["header_bg"], height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        title_label = tk.Label(header, text=" " + APP_NAME,
                               bg=COLORS["header_bg"], fg=COLORS["header_fg"],
                               font=theme_mod.font("title", True),
                               padx=sp_lg)
        title_label.pack(side=tk.LEFT, fill=tk.Y)
        source_bar = tk.Frame(header, bg=COLORS["header_bg"])
        source_bar.pack(side=tk.LEFT, padx=(sp_sm, 0), pady=sp_md)
        self._source_segments = []
        for value, label in SOURCE_LABELS:
            if not self._source_enabled(value):
                continue
            self._source_segments.append((value, label))
        self._source_boxes = []
        self._source_canvas = tk.Canvas(source_bar, height=32, bg=COLORS["header_bg"],
                                        highlightthickness=0, bd=0, cursor="hand2")
        self._source_canvas.pack(side=tk.LEFT)
        self._source_canvas.bind("<Button-1>", self._on_source_canvas_click)
        self._source_info = tk.Label(header, text="", bg=COLORS["header_bg"],
                                     fg=COLORS["text_secondary"],
                                     font=theme_mod.font("secondary"),
                                     anchor=tk.W)
        self._source_info.pack(side=tk.LEFT, padx=(sp_md, 0), fill=tk.X, expand=True)
        self._update_source_buttons()
        right_frame = tk.Frame(header, bg=COLORS["header_bg"])
        right_frame.pack(side=tk.RIGHT, padx=sp_lg)
        gear_text, gear_font = _icon(self.root, "settings", _ICON_SIZE_LG)
        gear = tk.Label(right_frame,
                        text=gear_text,
                        bg=COLORS["header_bg"], fg=COLORS["header_fg"],
                        font=gear_font,
                        padx=sp_sm, pady=sp_sm, cursor="hand2")
        gear.pack()
        gear.bind("<Button-1>", lambda e: self._on_settings_click())
        gear.bind("<Enter>", lambda e, w=gear: w.configure(fg=COLORS["primary"]))
        gear.bind("<Leave>", lambda e, w=gear: w.configure(fg=COLORS["header_fg"]))
        header_sep = tk.Frame(main_frame, bg=COLORS["separator"], height=1)
        header_sep.pack(fill=tk.X)
        self._hide_progress()
        self._progress_canvas = tk.Canvas(main_frame, height=3, bg=COLORS["separator"],
                                          highlightthickness=0, bd=0)
        self._progress_canvas.pack(fill=tk.X)
        self._progress_pos = 0
        search_frame = tk.Frame(main_frame, bg=COLORS["bg_main"])
        search_frame.pack(fill=tk.X, padx=sp_lg, pady=(sp_sm, sp_xs))
        search_text, search_font = _icon(self.root, "search", _ICON_SIZE_SM)
        tk.Label(search_frame, text=search_text, bg=COLORS["bg_main"],
                fg=COLORS["text_secondary"], font=search_font).pack(side=tk.LEFT)
        if self._search_var is None:
            self._search_var = tk.StringVar()
            self._search_var.trace_add("write", lambda *a: self._update_window())
        search_entry = ttk.Entry(search_frame, textvariable=self._search_var, width=40,
                                 font=theme_mod.font("body"))
        search_entry.pack(side=tk.LEFT, padx=(sp_sm, 0))
        self._list_frame = ttk.Frame(main_frame)
        self._list_frame.pack(fill=tk.BOTH, expand=True)
        self._build_list_view()
        status_frame = tk.Frame(main_frame, bg=COLORS["bg_main"])
        status_frame.pack(fill=tk.X, padx=sp_lg, pady=(0, sp_md))
        self._status_var = tk.StringVar(value="就绪")
        self._status_dot = tk.Label(status_frame, text="●", bg=COLORS["bg_main"],
                                     fg=COLORS["text_secondary"],
                                     font=theme_mod.font("body"))
        self._status_dot.pack(side=tk.LEFT)
        self._status_label = tk.Label(status_frame, textvariable=self._status_var,
                                      bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                                      font=theme_mod.font("secondary"),
                                      anchor=tk.W)
        self._status_label.pack(side=tk.LEFT, padx=(sp_xs, 0), fill=tk.X, expand=True)
        self._status_metric_frame = tk.Frame(status_frame, bg=COLORS["bg_main"])
        self._status_metric_frame.pack(side=tk.RIGHT, padx=(sp_sm, 0))
        self._bind_shortcuts()
        self.root.bind("<MouseWheel>", self._on_cards_wheel)
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._update_window()

    def _render_source_segments(self):
        """分段药丸来源切换：轨道用次级表面，选中段用强调色"""
        import tkinter.font as tkfont
        C = COLORS
        canvas = self._source_canvas
        if not canvas:
            return
        canvas.delete("all")
        segments = self._source_segments or []
        if not segments:
            canvas.configure(width=1, height=32)
            self._source_boxes = []
            return
        font = tkfont.Font(family=theme_mod.FONT_FAMILY,
                           size=theme_mod.FONT_SIZES["body"], weight="bold")
        pad_x = theme_mod.SPACING_SCALE[2]
        gap = 2
        height = 32
        boxes = []
        widths = [font.measure(label) + pad_x * 2 for _, label in segments]
        total_width = sum(widths) + gap * (len(segments) - 1)
        radius = height // 2
        theme_mod.rounded_rect(canvas, 0, 0, total_width, height, radius,
                               fill=C["header_hover_bg"], outline="")
        x = 0
        for idx, (value, label) in enumerate(segments):
            width = widths[idx]
            active = value == self._source
            if active:
                theme_mod.rounded_rect(canvas, x + 1, 1, x + width - 1, height - 1,
                                       radius - 1, fill=C["primary"], outline="")
            fill = theme_mod.readable_text(C["primary"]) if active else C["header_fg"]
            canvas.create_text(x + width // 2, height // 2, text=label,
                               fill=fill, font=font)
            boxes.append((value, x, x + width))
            x += width + gap
        canvas.configure(width=total_width, height=height)
        self._source_boxes = boxes

    def _on_source_canvas_click(self, event):
        for value, x1, x2 in self._source_boxes:
            if x1 <= event.x <= x2:
                self._switch_source(value)
                return

    def _update_source_buttons(self):
        self._render_source_segments()
        if self._source_info:
            if self._source == SOURCE_NACOS:
                ip = self.nacos_cfg.get("ip", "")
                port = self.nacos_cfg.get("port", 8848)
                text = ("Nacos: " + str(ip) + ":" + str(port)) if ip else "Nacos: 未配置"
            else:
                text = "Jenkins: " + (self.jenkins_cfg.get("url") or "未配置")
            if not self._source_enabled(self._source):
                text += "（未启用）"
            self._source_info.configure(text=text)

    def _switch_source(self, source):
        if source not in (SOURCE_NACOS, SOURCE_JENKINS) or source == self._source:
            return
        if not self._source_enabled(source):
            return
        self._source = source
        self._update_source_buttons()
        self._cancel_hover_job()
        self._hide_tooltip()
        self._close_context_menu()
        self._show_source_container(source)
        self._update_window()

    def _show_source_container(self, source):
        """同一时刻只显示一个来源容器；另一来源整体驻留，保留滚动与选中状态"""
        if self._list_frame is None:
            return
        if source == SOURCE_JENKINS:
            if self._jenkins_container is None:
                self._build_jenkins_container()
            nacos = self._nacos_container
            if nacos is not None and nacos.winfo_ismapped():
                nacos.pack_forget()
            jenkins = self._jenkins_container
            if jenkins is not None and not jenkins.winfo_ismapped():
                jenkins.pack(fill=tk.BOTH, expand=True)
        else:
            if self._nacos_container is None:
                self._build_nacos_container()
            jenkins = self._jenkins_container
            if jenkins is not None and jenkins.winfo_ismapped():
                jenkins.pack_forget()
            nacos = self._nacos_container
            if nacos is not None and not nacos.winfo_ismapped():
                nacos.pack(fill=tk.BOTH, expand=True)

    def _build_jenkins_container(self):
        from tkinter import ttk
        container = ttk.Frame(self._list_frame)
        self._jenkins_container = container
        self._jenkins_tree = None
        self._jenkins_rows = {}
        self._build_jenkins_table(container)

    def _build_jenkins_table(self, parent=None):
        import tkinter as tk
        from tkinter import ttk
        list_frame = parent or self._list_frame
        self._jenkins_rows = {}
        columns = ("status", "project", "alias", "job", "build", "branch",
                   "start", "end", "duration")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                            selectmode="browse")
        headings = [
            ("status", "状态", 60, tk.CENTER),
            ("project", "项目", 110, tk.W),
            ("alias", "备注", 80, tk.W),
            ("job", "Job", 210, tk.W),
            ("build", "构建", 55, tk.CENTER),
            ("branch", "分支", 80, tk.W),
            ("start", "开始时间", 125, tk.W),
            ("end", "结束时间", 125, tk.W),
            ("duration", "用时", 70, tk.CENTER),
        ]
        for key, text, width, anchor in headings:
            tree.heading(key, text=text)
            tree.column(key, width=width, anchor=anchor)
        scrollbar = ThinScrollbar(self._list_frame, tree)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.tag_configure("failure", foreground=COLORS["offline"])
        tree.tag_configure("success", foreground=COLORS["online"])
        tree.tag_configure("building", foreground=COLORS["warning"])
        tree.tag_configure("muted", foreground=COLORS["text_secondary"])
        if bool(self.cfg.get("table_striped", True)):
            tree.tag_configure("stripe", background=COLORS["bg_row_alt"])
        tree.bind("<Double-1>", self._on_jenkins_double_click)
        tree.bind("<Button-3>", self._on_jenkins_context_menu)
        self._jenkins_tree = tree
        self._update_jenkins_table()

    def _update_jenkins_table(self):
        tree = self._jenkins_tree
        if not tree or not tree.winfo_exists():
            return
        try:
            search_var = getattr(self, "_search_var", None)
            search_lower = search_var.get().strip().lower() if search_var else ""
            selected = tree.selection()
            showing = 0
            striped = bool(self.cfg.get("table_striped", True))
            # 行键 = Job 全名（即 iid），按搜索过滤后的顺序做增量同步
            desired = []
            rows_map = {}
            for job in self.jenkins_jobs:
                name = job.get("name", "")
                alias = (self.notes.get("jenkins") or {}).get(name, "")
                branch = job.get("branch", "-")
                project = str(job.get("project") or "").strip()
                search_text = " ".join([name, alias, branch,
                                        project]).lower()
                if search_lower and search_lower not in search_text:
                    continue
                showing += 1
                if job.get("building"):
                    status_text = "构建中" + "." * (self._jenkins_dot_phase + 1)
                    tag = "building"
                elif job.get("success"):
                    status_text, tag = "成功", "success"
                elif job.get("failure"):
                    status_text, tag = "失败", "failure"
                else:
                    status_text, tag = "未构建", "muted"
                alias_text = alias or "-"
                if name in (self.dnd.get("jenkins") or {}):
                    alias_text = "[勿扰] " + alias_text
                number = job.get("number") or 0
                timestamp = job.get("timestamp") or 0
                duration = job.get("duration") or 0
                end_text = "-"
                duration_text = "-"
                if not job.get("building") and timestamp:
                    end_text = format_timestamp(timestamp + duration) if duration else format_timestamp(timestamp)
                    duration_text = format_duration(duration)
                tags = (tag, "stripe") if (striped and showing % 2 == 0) else (tag,)
                desired.append((name, (
                    status_text,
                    project or "-",
                    alias_text,
                    name,
                    ("#" + str(number)) if number else "-",
                    branch or "-",
                    format_timestamp(timestamp),
                    end_text,
                    duration_text,
                ), tags))
                rows_map[name] = job
            self._diff_tree_rows(tree, desired)
            self._jenkins_rows = rows_map
            alive = set(tree.get_children())
            for name in selected:
                if name in alive:
                    tree.selection_set(name)
            failures = sum(1 for job in self.jenkins_jobs if job.get("failure"))
            configured = bool(self.jenkins_cfg.get("url"))
            if self._status_var:
                if not configured:
                    text = "Jenkins 未配置，请在设置 → 通知源 → Jenkins 中填写连接"
                else:
                    text = "共 " + str(len(self.jenkins_jobs)) + " 个任务，" + str(failures) + " 个失败"
                    if search_lower and showing != len(self.jenkins_jobs):
                        text += "（显示 " + str(showing) + " 个）"
                    if self._jenkins_status.get("state") == "error":
                        text += " · 连接异常"
                    elif self._jenkins_status.get("polled_at"):
                        text += " · 更新于 " + self._jenkins_status["polled_at"][-8:]
                self._status_var.set(text)
            if configured:
                self._render_status_metrics([(str(len(self.jenkins_jobs)), "任务"),
                                             (str(failures), "失败")])
            else:
                self._render_status_metrics([])
            if hasattr(self, "_status_dot"):
                if not configured:
                    self._status_dot.configure(fg=COLORS["text_secondary"])
                elif self._jenkins_status.get("state") == "error":
                    self._status_dot.configure(fg=COLORS["warning"])
                elif failures:
                    self._status_dot.configure(fg=COLORS["offline"])
                elif self.jenkins_jobs:
                    self._status_dot.configure(fg=COLORS["online"])
                else:
                    self._status_dot.configure(fg=COLORS["text_secondary"])
            self._sync_jenkins_dots()
        except Exception as exc:
            print("Update jenkins table error: " + str(exc))

    def _sync_jenkins_dots(self):
        """有构建中任务时启动省略号动画，否则停表"""
        if not self.root or self._source != SOURCE_JENKINS:
            return
        active = any(job.get("building") for job in self.jenkins_jobs)
        if active:
            if self._jenkins_dots_job is None:
                self._jenkins_dot_phase = 0
                self._jenkins_dots_job = self.root.after(300,
                                                         self._animate_jenkins_dots)
        elif self._jenkins_dots_job is not None:
            try:
                self.root.after_cancel(self._jenkins_dots_job)
            except Exception:
                pass
            self._jenkins_dots_job = None

    def _animate_jenkins_dots(self):
        self._jenkins_dots_job = None
        if not self.root or not self.root.winfo_exists():
            return
        tree = self._jenkins_tree
        if not self.jenkins_jobs or self._source != SOURCE_JENKINS:
            return
        if not tree or not tree.winfo_exists():
            return
        if not any(job.get("building") for job in self.jenkins_jobs):
            return
        self._jenkins_dot_phase = (self._jenkins_dot_phase + 1) % 3
        dots = "." * (self._jenkins_dot_phase + 1)
        for iid, job in list(self._jenkins_rows.items()):
            if not job.get("building"):
                continue
            try:
                values = list(tree.item(iid, "values"))
                if values:
                    values[0] = "构建中" + dots
                    tree.item(iid, values=values)
            except Exception:
                pass
        self._jenkins_dots_job = self.root.after(300, self._animate_jenkins_dots)

    def _selected_jenkins_job(self):
        tree = self._jenkins_tree
        if not tree:
            return None
        selection = tree.selection()
        if not selection:
            return None
        return self._jenkins_rows.get(selection[0])

    def _on_jenkins_double_click(self, event=None):
        job = self._selected_jenkins_job()
        if job:
            self._open_jenkins_build(job)

    def _open_jenkins_build(self, job):
        url = job.get("url") or ""
        if url:
            webbrowser.open(url)

    def _on_jenkins_context_menu(self, event):
        tree = self._jenkins_tree
        if tree:
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
        job = self._selected_jenkins_job()
        if not job:
            return
        muted = job.get("name") in (self.dnd.get("jenkins") or {})
        items = [
            ("打开构建", lambda: self._open_jenkins_build(job), True),
            ("最近提交历史", lambda: self._show_commit_history(job), True),
            ("取消免打扰" if muted else "免打扰",
             lambda: self._toggle_jenkins_dnd(job.get("name")), True),
            ("管理备注...", lambda: self._show_settings(
                page=SettingsDialog.PAGE_JENKINS_NOTES), True),
            ("刷新", self._on_refresh_click, True),
        ]
        self._open_items_menu(items, event.x_root, event.y_root)

    def _find_jenkins_job(self, job_name):
        for job in self.jenkins_jobs:
            if job.get("name") == job_name:
                return job
        return {"name": job_name, "url": ""}

    def _load_commit_history(self, job_name, callback):
        """按需读取最近成功构建；带缓存，结果统一回主线程回调"""
        cached = self._commit_history_cache.get(job_name)
        if cached is not None and "loading" not in cached:
            callback(cached)
            return
        if cached is None:
            self._commit_history_cache[job_name] = {"loading": True}
        job = self._find_jenkins_job(job_name)
        cfg = self.jenkins_cfg

        def worker():
            try:
                client = JenkinsClient(cfg.get("url", ""), cfg.get("username", ""),
                                       cfg.get("password", ""),
                                       bool(cfg.get("verify_ssl", True)))
                builds = client.get_recent_success_builds(job)
                result = {"builds": builds}
            except Exception as exc:
                result = {"error": str(exc)}
            if self.root and self.running:
                self.root.after(0, lambda: self._deliver_commit_history(
                    job_name, result, callback))

        threading.Thread(target=worker, daemon=True).start()

    def _deliver_commit_history(self, job_name, result, callback):
        self._commit_history_cache[job_name] = result
        callback(result)

    def _show_commit_history(self, job):
        panel = CommitHistoryPanel(self.root, self)
        x = self.root.winfo_pointerx()
        y = self.root.winfo_pointery()
        panel.show_for_job(job, anchor=(x, y))

    def _toggle_jenkins_dnd(self, job_name):
        if not job_name:
            return
        dnd = self.dnd.setdefault("jenkins", {})
        if job_name in dnd:
            dnd.pop(job_name, None)
        else:
            dnd[job_name] = True
        config.save_dnd(self.dnd)
        self._update_window()
        self._update_tray_tooltip()

    def _restart_jenkins_monitor(self):
        if self._jenkins_monitor:
            self._jenkins_monitor.stop()
            self._jenkins_monitor = None
        if not self._source_enabled(SOURCE_JENKINS):
            return
        self._jenkins_monitor = JenkinsMonitor(
            config_provider=lambda: self.jenkins_cfg,
            notes_provider=lambda: self.notes,
            dnd_provider=lambda: self.dnd,
            on_events=self._on_jenkins_events,
            on_status=self._on_jenkins_status,
        )
        self._jenkins_monitor.start()

    def _on_jenkins_events(self, events):
        if self.root and self.running and self._notifier:
            self.root.after(0, self._notifier.notify_batch, events)

    def _on_jenkins_status(self, status):
        if self.root and self.running:
            self.root.after(0, self._apply_jenkins_status, status)

    def _apply_jenkins_status(self, status):
        self._jenkins_status = dict(status)
        self.jenkins_jobs = list(status.get("jobs") or [])
        self._commit_history_cache.clear()
        self._update_tray_tooltip()
        self._build_menu()
        if self._source == SOURCE_JENKINS:
            self._update_window()
        self._refresh_popup_data()

    def _on_notification_click(self, event):
        source = event.get("source")
        url = event.get("url") or ""
        if url:
            webbrowser.open(url)
            return
        if source in (SOURCE_NACOS, SOURCE_JENKINS):
            self._switch_source(source)
        self._show_window()

    def _toggle_view_mode(self):
        self._set_view_mode("table" if self._view_mode == "card" else "card")

    def _set_view_mode(self, mode):
        if mode not in ("table", "card") or mode == self._view_mode:
            return
        self._view_mode = mode
        self.cfg["view_mode"] = mode
        config.save_config(self.cfg)
        self._cancel_hover_job()
        self._hide_tooltip()
        self.root.after(0, self._rebuild_root_ui)

    def _table_row_height(self):
        return TABLE_ROW_HEIGHTS.get(self.cfg.get("table_row_height", "normal"), 28)

    def _card_min_width(self):
        return CARD_DENSITY_WIDTHS.get(self.cfg.get("card_density", "normal"), 360)

    def _card_name_size(self):
        return CARD_NAME_SIZES.get(self.cfg.get("card_name_size", "normal"), 10)

    def _card_fields(self):
        fields = dict(config.DEFAULT_CARD_FIELDS)
        stored = self.cfg.get("card_fields")
        if isinstance(stored, dict):
            for key in fields:
                fields[key] = bool(stored.get(key, fields[key]))
        return fields

    def _bind_shortcuts(self):
        for sequence in self._shortcut_sequences:
            try:
                self.root.unbind(sequence)
            except Exception:
                pass
        self._shortcut_sequences = []
        shortcuts = self.cfg.get("shortcuts") or {}
        bindings = [
            (_normalize_shortcut(shortcuts.get("refresh", config.DEFAULT_SHORTCUTS["refresh"])),
             self._on_refresh_click),
            (_normalize_shortcut(shortcuts.get("toggle_view", config.DEFAULT_SHORTCUTS["toggle_view"])),
             self._toggle_view_mode),
            (_normalize_shortcut(shortcuts.get("open_settings", config.DEFAULT_SHORTCUTS["open_settings"])),
             self._on_settings_click),
        ]
        for sequence, command in bindings:
            if not sequence:
                continue
            try:
                self.root.bind(sequence, self._make_shortcut_handler(command))
                self._shortcut_sequences.append(sequence)
            except Exception:
                pass

    def _make_shortcut_handler(self, command):
        def handler(event=None):
            command()
            return "break"
        return handler

    def _build_list_view(self):
        if self._nacos_container is not None and not self._nacos_container.winfo_exists():
            self._nacos_container = None
        if self._jenkins_container is not None and not self._jenkins_container.winfo_exists():
            self._jenkins_container = None
        self._show_source_container(self._source)

    def _reset_nacos_view_state(self):
        self._service_tree = None
        self._cards_canvas = None
        self._cards_frame = None
        self._cards_window = None
        self._card_states = {}
        self._card_order = []
        self._card_cols = 0
        self._cards_compact = False
        self._hover_table_item = None
        self._cards_empty = None

    def _build_nacos_container(self):
        from tkinter import ttk
        container = ttk.Frame(self._list_frame)
        self._nacos_container = container
        self._reset_nacos_view_state()
        if self._view_mode == "card":
            self._build_card_view(container)
        else:
            self._build_table_view(container)

    def _build_table_view(self, parent=None):
        import tkinter as tk
        from tkinter import ttk
        list_frame = parent or self._list_frame
        columns = ("pin", "info", "service", "instance", "port", "status", "last_online")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("pin", text="置顶")
        tree.heading("info", text="信息")
        tree.heading("service", text="服务名")
        tree.heading("instance", text="实例")
        tree.heading("port", text="端口")
        tree.heading("status", text="状态")
        tree.heading("last_online", text="最近上线时间")
        tree.column("pin", width=40, anchor=tk.CENTER, stretch=False)
        tree.column("info", width=38, anchor=tk.CENTER, stretch=False)
        tree.column("service", width=150)
        tree.column("instance", width=170)
        tree.column("port", width=50, anchor=tk.CENTER)
        tree.column("status", width=70, anchor=tk.CENTER)
        tree.column("last_online", width=150)
        tree.tag_configure("online", foreground=COLORS["online"])
        tree.tag_configure("offline", foreground=COLORS["offline"])
        tree.tag_configure("alt", background=COLORS["bg_row_alt"])
        scrollbar = ThinScrollbar(list_frame, tree)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.bind("<Button-1>", self._on_tree_click)
        tree.bind("<Button-3>", self._show_context_menu)
        tree.bind("<Double-1>", self._on_double_click)
        tree.bind("<Motion>", self._on_tree_motion)
        tree.bind("<Leave>", self._on_tree_leave)
        self._service_tree = tree

    def _build_card_view(self, parent=None):
        import tkinter as tk
        from tkinter import ttk
        list_frame = parent or self._list_frame
        canvas = tk.Canvas(list_frame, bg=COLORS["bg_main"], highlightthickness=0, bd=0,
                           yscrollincrement=20)
        scrollbar = ThinScrollbar(list_frame, canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=(4, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        inner = tk.Frame(canvas, bg=COLORS["bg_main"])
        window_id = canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", self._on_cards_resize)
        self._cards_canvas = canvas
        self._cards_window = window_id
        self._cards_frame = inner
        self._cards_empty = tk.Label(inner, text="暂无服务数据", bg=COLORS["bg_main"],
                                     fg=COLORS["text_secondary"],
                                     font=("Microsoft YaHei UI", 9))
        self._cards_empty.grid(row=0, column=0, columnspan=3, pady=24)

    def _on_cards_resize(self, event):
        if not self._cards_canvas or not self._cards_window:
            return
        try:
            self._cards_canvas.itemconfigure(self._cards_window, width=event.width)
            min_width = self._card_min_width()
            fit = max(1, event.width // min_width)
            setting = self.cfg.get("card_columns", "auto")
            if setting == "auto":
                cols = min(3, fit)
            else:
                try:
                    cols = int(setting)
                except (TypeError, ValueError):
                    cols = 1
                cols = max(1, min(3, cols))
            compact = (event.width // max(1, cols)) < 340
            changed = cols != self._card_cols or compact != self._cards_compact
            self._card_cols = cols
            self._cards_compact = compact
            if changed:
                self._layout_cards()
                self._update_window()
        except Exception:
            pass

    def _layout_cards(self):
        if not self._cards_frame:
            return
        self._hide_tooltip()
        cols = max(1, self._card_cols)
        for c in range(3):
            self._cards_frame.grid_columnconfigure(
                c, weight=1 if c < cols else 0,
                uniform="cards" if c < cols else "")
        for idx, name in enumerate(self._card_order):
            state = self._card_states.get(name)
            if state:
                state["frame"].grid(row=idx // cols, column=idx % cols,
                                    sticky="nsew", padx=6, pady=6)

    def _ensure_card(self, svc_name):
        import tkinter as tk
        state = self._card_states.get(svc_name)
        if state:
            return state
        card = tk.Frame(self._cards_frame, bg=COLORS["bg_card"],
                        highlightbackground=COLORS["separator"], highlightthickness=1)
        head = tk.Frame(card, bg=COLORS["bg_card"])
        head.pack(fill=tk.X, padx=10, pady=(8, 0))
        title = tk.Label(head, text=svc_name, bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                         font=("Microsoft YaHei UI", self._card_name_size(), "bold"), anchor=tk.W,
                         justify=tk.LEFT, wraplength=300)
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        info_text, info_font = _icon(self.root, "info", _ICON_SIZE_SM)
        pin_off_text, pin_off_font = _icon(self.root, "unpin", _ICON_SIZE_SM)
        info = tk.Label(head, text=info_text,
                        bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                        font=info_font,
                        cursor="hand2", padx=4)
        pin = tk.Label(head, text=pin_off_text,
                       bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                       font=pin_off_font,
                       cursor="hand2", padx=4)
        pin.pack(side=tk.RIGHT)
        info.pack(side=tk.RIGHT, padx=(0, 6))
        pin.bind("<Button-1>", lambda e, n=svc_name: self._toggle_pin(n))
        info.bind("<Enter>", lambda e, n=svc_name, w=info: self._schedule_service_tooltip(n, w))
        info.bind("<Leave>", lambda e: self._hide_tooltip())
        sub = tk.Label(card, text="", bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                       font=("Microsoft YaHei UI", 8), anchor=tk.W,
                       justify=tk.LEFT, wraplength=300)
        sub.pack(fill=tk.X, padx=10, pady=(0, 4))
        line = tk.Frame(card, bg=COLORS["separator"], height=1)
        line.pack(fill=tk.X, padx=10)
        rows = tk.Frame(card, bg=COLORS["bg_card"])
        rows.pack(fill=tk.X, padx=2, pady=(2, 8))
        state = {"frame": card, "pin": pin,
                 "pin_on": _icon(self.root, "pin", _ICON_SIZE_SM)[0],
                 "pin_off": pin_off_text,
                 "sub": sub, "line": line, "rows": rows,
                 "rows_map": {}, "order": [], "sub_visible": True}
        self._card_states[svc_name] = state
        for w in (card, head, title, sub, line, rows, pin, info):
            w.bind("<Button-3>", lambda e, n=svc_name: self._show_card_context_menu(e, n, None))
            self._bind_card_border_hover(w, card)
        return state

    def _create_card_row(self, state, svc_name, inst):
        import tkinter as tk
        pause_text, icon_font = _icon(self.root, "pause", _ICON_SIZE_SM)
        play_text, _ = _icon(self.root, "play", _ICON_SIZE_SM)
        row = tk.Frame(state["rows"], bg=COLORS["bg_card"], cursor="hand2")
        dot = tk.Label(row, text="●", bg=COLORS["bg_card"], font=("Microsoft YaHei UI", 8), width=2)
        dot.pack(side=tk.LEFT)
        name = tk.Label(row, text="", bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                        font=("Consolas", 9), anchor=tk.W, width=24)
        name.pack(side=tk.LEFT, fill=tk.X, expand=True)
        when = tk.Label(row, text="", bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                        font=("Microsoft YaHei UI", 8), anchor=tk.E)
        pending_font = ("Microsoft YaHei UI", 9, "bold")
        action = tk.Label(row, text="", bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                          font=icon_font, padx=4, pady=0, cursor="hand2", bd=0,
                          highlightthickness=1, highlightbackground=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=1)
        row_state = {"row": row, "dot": dot, "name": name, "when": when,
                     "action": action, "svc": inst,
                     "when_visible": False, "action_visible": False,
                     "hovered": False, "action_hovered": False,
                     "show_when": True, "icon_pause": pause_text, "icon_play": play_text,
                     "icon_font": icon_font, "pending_font": pending_font,
                     "base_bg": COLORS["bg_card"]}
        for w in (row, dot, name, when, action):
            w.bind("<Enter>", lambda e, rs=row_state: self._row_enter(rs), add="+")
            w.bind("<Leave>", lambda e, rs=row_state: self._row_leave(rs), add="+")
            self._bind_card_border_hover(w, state["frame"])
        for w in (row, dot, name, when):
            w.bind("<Button-1>", lambda e, rs=row_state: self._confirm_toggle_instance(rs["svc"]))
            w.bind("<Button-3>", lambda e, n=svc_name, rs=row_state: self._show_card_context_menu(e, n, rs["svc"]))
        action.bind("<Button-1>", lambda e, rs=row_state: self._quick_toggle_instance(rs["svc"]))
        action.bind("<Button-3>", lambda e, n=svc_name, rs=row_state: self._show_card_context_menu(e, n, rs["svc"]))
        action.bind("<Enter>", lambda e, rs=row_state: self._action_enter(rs), add="+")
        action.bind("<Leave>", lambda e, rs=row_state: self._action_leave(rs), add="+")
        return row_state

    def _sync_card(self, svc_name, instances):
        import tkinter as tk
        state = self._ensure_card(svc_name)
        pins = self.cfg.get("pinned_services") or []
        pinned = svc_name in pins
        state["pin"].configure(text=state["pin_on"] if pinned else state["pin_off"],
                               fg=COLORS["primary"] if pinned else COLORS["text_secondary"])
        total = len(instances)
        online = sum(1 for i in instances if i["online"])
        port = instances[0]["port"] if instances else "-"
        fields = self._card_fields()
        parts = []
        if fields["port"]:
            parts.append("端口 " + str(port))
        if fields["online"]:
            parts.append(str(online) + "/" + str(total) + " 在线")
        if parts:
            state["sub"].configure(text=" · ".join(parts))
            if not state["sub_visible"]:
                state["sub"].pack(fill=tk.X, padx=10, pady=(0, 4), before=state["line"])
                state["sub_visible"] = True
        elif state["sub_visible"]:
            state["sub"].pack_forget()
            state["sub_visible"] = False
        ordered = sorted(instances, key=lambda i: (not i["online"], self._get_display_name(i["ip"]).lower()))
        seen = set()
        ordered_keys = []
        for inst in ordered:
            key = inst["ip"] + ":" + str(inst["port"])
            seen.add(key)
            ordered_keys.append(key)
            row = state["rows_map"].get(key)
            if row is None:
                row = self._create_card_row(state, svc_name, inst)
                state["rows_map"][key] = row
            self._update_card_row(row, inst, fields)
        for key in list(state["rows_map"]):
            if key not in seen:
                state["rows_map"].pop(key)["row"].destroy()
        for idx, key in enumerate(ordered_keys):
            row = state["rows_map"].get(key)
            if not row:
                continue
            base = COLORS["bg_row_alt"] if idx % 2 == 1 else COLORS["bg_card"]
            row["base_bg"] = base
            if not row["hovered"]:
                self._paint_card_row(row, base)
        if ordered_keys != state["order"]:
            state["order"] = ordered_keys
            for key in ordered_keys:
                row = state["rows_map"].get(key)
                if row:
                    row["row"].pack_forget()
                    row["row"].pack(fill=tk.X, pady=1)

    def _paint_card_row(self, row, color):
        for widget in (row["row"], row["dot"], row["name"], row["when"], row["action"]):
            widget.configure(bg=color)
        if not row["action_hovered"]:
            row["action"].configure(highlightbackground=color)

    def _row_enter(self, row):
        if row["hovered"]:
            return
        row["hovered"] = True
        self._paint_card_row(row, COLORS["bg_hover"])
        self._update_row_right(row, True)

    def _row_leave(self, row):
        if self._pointer_in_widget(row["row"]):
            return
        if not row["hovered"]:
            return
        row["hovered"] = False
        self._paint_card_row(row, row.get("base_bg", COLORS["bg_card"]))
        self._update_row_right(row, False)

    def _action_enter(self, row):
        row["action_hovered"] = True
        row["action"].configure(highlightbackground=COLORS["primary"])

    def _action_leave(self, row):
        row["action_hovered"] = False
        color = COLORS["bg_hover"] if row["hovered"] else row.get("base_bg", COLORS["bg_card"])
        row["action"].configure(highlightbackground=color)

    def _row_key(self, row):
        svc = row.get("svc") or {}
        return (svc.get("service_name", "") + ":" + svc.get("ip", "")
                + ":" + str(svc.get("port", "")))

    def _ensure_pending_animation(self):
        if self._pending_dots_job is None:
            self._pending_dot_phase = 0
            self._pending_dots_job = self.root.after(300, self._animate_pending_dots)

    def _animate_pending_dots(self):
        self._pending_dots_job = None
        if not self._quick_pending or not self.root:
            return
        self._pending_dot_phase = (self._pending_dot_phase + 1) % 3
        dots = "." * (self._pending_dot_phase + 1)
        for state in list(self._card_states.values()):
            for row in list(state.get("rows_map", {}).values()):
                if self._row_key(row) in self._quick_pending:
                    try:
                        row["action"].configure(text=dots)
                    except Exception:
                        pass
        try:
            self._pending_dots_job = self.root.after(300, self._animate_pending_dots)
        except Exception:
            self._pending_dots_job = None

    def _update_row_right(self, row, hovered):
        when = row["when"]
        action = row["action"]
        pending = self._row_key(row) in self._quick_pending
        if hovered or pending:
            if row["when_visible"]:
                when.pack_forget()
                row["when_visible"] = False
            if not row["action_visible"]:
                action.place(relx=1.0, rely=0.5, anchor=tk.E, x=-8)
                row["action_visible"] = True
            if not row["action_hovered"]:
                color = COLORS["bg_hover"] if hovered else row.get("base_bg", COLORS["bg_card"])
                action.configure(highlightbackground=color)
            return
        if row["action_visible"]:
            action.place_forget()
            row["action_visible"] = False
        if row["show_when"]:
            if not row["when_visible"]:
                when.pack(side=tk.RIGHT, padx=(6, 8))
                row["when_visible"] = True
        elif row["when_visible"]:
            when.pack_forget()
            row["when_visible"] = False

    def _update_card_row(self, row, inst, fields=None):
        if fields is None:
            fields = self._card_fields()
        online = inst["online"]
        color = COLORS["online"] if online else COLORS["offline"]
        row["svc"] = inst
        row["dot"].configure(fg=color)
        display = self._get_display_name(inst["ip"]) if fields["note"] else inst["ip"]
        if fields["dnd"] and inst["ip"] in self.dnd["nacos"]:
            display = "[勿扰] " + display
        row["name"].configure(text=display, fg=color)
        row["show_when"] = fields["last_online"] and not self._cards_compact
        last_key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
        row["when"].configure(text=self._last_online_time.get(last_key, "-"))
        busy = last_key in self._quick_pending
        if busy:
            row["action"].configure(
                text="." * (self._pending_dot_phase + 1),
                fg=COLORS["primary"], font=row["pending_font"], width=3,
                cursor="arrow")
        else:
            if online:
                icon = row["icon_pause"]
                action_color = COLORS["offline"]
            else:
                icon = row["icon_play"]
                action_color = COLORS["online"]
            row["action"].configure(text=icon, fg=action_color,
                                    font=row["icon_font"], width=0,
                                    cursor="hand2")
        self._update_row_right(row, row["hovered"])

    def _bind_card_border_hover(self, widget, card):
        widget.bind("<Enter>", lambda e, c=card: self._card_border_enter(c), add="+")
        widget.bind("<Leave>", lambda e, c=card: self._card_border_leave(c), add="+")

    def _card_border_enter(self, card):
        try:
            card.configure(highlightbackground=COLORS["primary"])
        except Exception:
            pass

    def _card_border_leave(self, card):
        if self._pointer_in_widget(card):
            return
        try:
            card.configure(highlightbackground=COLORS["separator"])
        except Exception:
            pass

    def _quick_toggle_instance(self, inst):
        if not inst:
            return
        key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
        if key in self._quick_pending:
            return
        self._quick_pending.add(key)
        self._ensure_pending_animation()
        self._hide_tooltip()
        self._update_window()
        target_enabled = not inst["online"]

        def worker():
            error = None
            services = None
            try:
                if not self._ensure_login():
                    raise RuntimeError("未连接到 Nacos")
                self.client.update_instance_status(
                    inst["service_name"], inst["ip"], inst["port"],
                    enabled=target_enabled)
                services = self._fetch_services()
            except Exception as exc:
                error = str(exc)
            if self.root and self.running:
                try:
                    self.root.after(0, self._on_quick_action_done, key, services, error)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_quick_action_done(self, key, services, error):
        self._quick_pending.discard(key)
        if not self._quick_pending and self._pending_dots_job:
            try:
                self.root.after_cancel(self._pending_dots_job)
            except Exception:
                pass
            self._pending_dots_job = None
        if error:
            self._notify("快捷操作失败", error, "error")
        elif services:
            self._last_refresh_time = time.strftime("%Y-%m-%d %H:%M:%S")
            with self._lock:
                self.services = services
                new_map = {}
                for svc in services:
                    svc_key = svc["service_name"] + ":" + svc["ip"] + ":" + str(svc["port"])
                    new_map[svc_key] = svc
                    if svc["online"] and svc_key not in self._last_online_time:
                        self._last_online_time[svc_key] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.previous_services = new_map
            try:
                self._update_tray_tooltip()
                self._build_menu()
            except Exception:
                pass
        if self._source == SOURCE_NACOS:
            self._update_window()

    def _update_cards(self, groups, search_lower=""):
        if not self._cards_frame:
            return
        if self._cards_empty:
            self._cards_empty.configure(text="没有匹配的服务" if search_lower else "暂无服务数据")
        names = []
        for svc_name, instances in groups:
            names.append(svc_name)
            self._sync_card(svc_name, instances)
        for name in list(self._card_states):
            if name not in names:
                self._card_states.pop(name)["frame"].destroy()
        if self._hover_service and self._hover_service not in names:
            self._hide_tooltip()
        if names != self._card_order or not self._card_cols:
            self._card_order = names
            self._layout_cards()
        if self._cards_empty:
            if names:
                self._cards_empty.grid_remove()
            else:
                self._cards_empty.grid()

    def _tree_cell_at(self, event, column_id):
        tree = self._service_tree
        if not tree:
            return None
        item = tree.identify_row(event.y)
        if not item:
            return None
        box = tree.bbox(item, column_id)
        if not box:
            return None
        x, y, width, height = box
        if x <= event.x <= x + width and y <= event.y <= y + height:
            return item
        return None

    def _on_tree_motion(self, event):
        tree = self._service_tree
        if not tree:
            return
        item = self._tree_cell_at(event, "#2")
        if not item:
            if self._hover_table_item is not None:
                self._hover_table_item = None
                self._hide_tooltip()
            return
        if item == self._hover_table_item:
            return
        self._hover_table_item = item
        values = tree.item(item, "values")
        if len(values) < 3:
            self._hide_tooltip()
            return
        svc_name = str(values[2])
        if svc_name == self._hover_service:
            return
        self._hide_tooltip()
        self._schedule_service_tooltip(svc_name, tree)

    def _on_tree_leave(self, event=None):
        self._hover_table_item = None
        self._cancel_hover_job()
        self._hide_tooltip()

    def _pointer_in_widget(self, widget):
        try:
            x, y = self.root.winfo_pointerxy()
            return (widget.winfo_rootx() <= x <= widget.winfo_rootx() + widget.winfo_width()
                    and widget.winfo_rooty() <= y <= widget.winfo_rooty() + widget.winfo_height())
        except Exception:
            return False

    def _pointer_in_widget_bounds(self, widget):
        try:
            x = self.root.winfo_pointerx() - widget.winfo_rootx()
            y = self.root.winfo_pointery() - widget.winfo_rooty()
            return (0 <= x < widget.winfo_width()
                    and 0 <= y < widget.winfo_height())
        except Exception:
            return False

    def _foreground_is_root(self):
        """前台窗口是否为本程序主窗口，用于识别圆角透明区的沿角点击"""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            return False
        if not hwnd:
            return False
        try:
            return hwnd == self.root.winfo_id()
        except Exception:
            return False


    def _schedule_service_tooltip(self, svc_name, anchor):
        self._cancel_hover_job()
        self._hover_service = svc_name
        self._hover_job = self.root.after(
            theme_mod.TOOLTIP_DELAY_MS,
            lambda: self._show_service_tooltip(svc_name, anchor))

    def _cancel_hover_job(self):
        if self._hover_job:
            try:
                self.root.after_cancel(self._hover_job)
            except Exception:
                pass
            self._hover_job = None

    def _hide_tooltip(self):
        self._cancel_hover_job()
        if self._hover_window:
            theme_mod.stop_alpha(self._hover_window)
            try:
                self._hover_window.destroy()
            except Exception:
                pass
            self._hover_window = None
        self._hover_service = None

    def _show_service_tooltip(self, svc_name, anchor):
        self._hover_job = None
        if not self._pointer_in_widget(anchor):
            return
        try:
            if not anchor.winfo_exists():
                return
        except Exception:
            return
        instances = [s for s in self.services if s["service_name"] == svc_name]
        if not instances:
            return
        import tkinter as tk
        self._hide_tooltip()
        C = COLORS
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.withdraw()
        key = theme_mod.transparent_key(C)
        top.configure(bg=key)
        try:
            top.attributes("-transparentcolor", key)
        except tk.TclError:
            pass
        canvas = tk.Canvas(top, bg=key, highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        self._apply_float_material(top, key)
        outer = tk.Frame(canvas, bg=C["bg_card"])
        inner = tk.Frame(outer, bg=C["bg_card"])
        inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        pinned = svc_name in (self.cfg.get("pinned_services") or [])
        title_text = (_ICON_GLYPHS["pin"][1] + " " if pinned else "") + svc_name
        tk.Label(inner, text=title_text, bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 10, "bold"), anchor=tk.W,
                 justify=tk.LEFT, wraplength=420).pack(fill=tk.X)
        total = len(instances)
        online = sum(1 for i in instances if i["online"])
        ports = sorted({str(i["port"]) for i in instances})
        summary = "端口 " + "/".join(ports) + " · " + str(online) + "/" + str(total) + " 在线"
        tk.Label(inner, text=summary, bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=("Microsoft YaHei UI", 8), anchor=tk.W).pack(fill=tk.X, pady=(2, 6))
        tk.Frame(inner, bg=COLORS["separator"], height=1).pack(fill=tk.X, pady=(0, 6))
        ordered = sorted(instances,
                         key=lambda i: (not i["online"], self._get_display_name(i["ip"]).lower()))
        for inst in ordered[:12]:
            self._build_tooltip_instance(inner, inst)
        if total > 12:
            tk.Label(inner, text="还有 " + str(total - 12) + " 个实例",
                     bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                     font=("Microsoft YaHei UI", 8), anchor=tk.W).pack(fill=tk.X, pady=(4, 0))
        context = ("Nacos " + str(self.nacos_cfg.get("ip", "-")) + ":" + str(self.nacos_cfg.get("port", 8848))
                   + " · 命名空间 " + (self.nacos_cfg.get("namespace") or "默认")
                   + " · 集群 " + (self.nacos_cfg.get("cluster_name") or "-"))
        if self._last_refresh_time:
            context += " · 更新 " + self._last_refresh_time
        tk.Label(inner, text=context, bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=("Microsoft YaHei UI", 8), anchor=tk.W,
                 justify=tk.LEFT, wraplength=420).pack(fill=tk.X, pady=(4, 0))
        outer.update_idletasks()
        width = outer.winfo_reqwidth()
        height = outer.winfo_reqheight()
        radius = theme_mod.RADIUS_TOOLTIP
        total_w = width + 2 * radius
        total_h = height + 2 * radius
        canvas.configure(width=total_w, height=total_h)
        theme_mod.rounded_rect(canvas, 1, 1, total_w - 1, total_h - 1, radius,
                               fill=COLORS["bg_card"], outline=COLORS["separator"])
        canvas.create_window(radius, radius, window=outer, anchor=tk.NW,
                             width=width, height=height)
        px, py = self.root.winfo_pointerxy()
        screen_w = top.winfo_screenwidth()
        screen_h = top.winfo_screenheight()
        x = px + 18
        if x + total_w > screen_w - 8:
            x = px - total_w - 18
        y = py + 18
        if y + total_h > screen_h - 8:
            y = screen_h - total_h - 8
        try:
            top.attributes("-alpha", 0.0)
        except Exception:
            pass
        top.geometry(str(total_w) + "x" + str(total_h)
                     + "+" + str(max(4, x)) + "+" + str(max(4, y)))
        self._hover_window = top
        self._hover_service = svc_name
        top.deiconify()
        top.lift()
        theme_mod.animate_alpha(top, 1.0, theme_mod.TOOLTIP_FADE_MS)

    def _build_tooltip_instance(self, parent, inst):
        import tkinter as tk
        online = inst["online"]
        color = COLORS["online"] if online else COLORS["offline"]
        block = tk.Frame(parent, bg=COLORS["bg_card"])
        block.pack(fill=tk.X, pady=(0, 6))
        row = tk.Frame(block, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="●", bg=COLORS["bg_card"], fg=color,
                 font=("Microsoft YaHei UI", 8)).pack(side=tk.LEFT)
        ip_text = inst["ip"] + ":" + str(inst["port"])
        note = self.notes["nacos"].get(inst["ip"], "")
        if note:
            ip_text += "  " + note
        tk.Label(row, text=ip_text, bg=COLORS["bg_card"], fg=color,
                 font=("Consolas", 9), anchor=tk.W).pack(side=tk.LEFT, padx=(4, 0))
        if inst["ip"] in self.dnd["nacos"]:
            tk.Label(row, text="免打扰", bg=COLORS["bg_card"], fg=COLORS["warning"],
                     font=("Microsoft YaHei UI", 8)).pack(side=tk.RIGHT)
        details = []
        if not inst.get("enabled", True):
            details.append("已禁用")
        elif not inst.get("healthy", True):
            details.append("不健康")
        else:
            details.append("在线" if online else "离线")
        last_key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
        details.append("最近上线 " + self._last_online_time.get(last_key, "-"))
        weight = inst.get("weight")
        if weight is not None:
            details.append("权重 " + str(weight))
        cluster = inst.get("cluster_name")
        if cluster:
            details.append("集群 " + str(cluster))
        ephemeral = inst.get("ephemeral")
        if ephemeral is not None:
            details.append("临时实例" if ephemeral else "持久实例")
        tk.Label(block, text=" · ".join(details), bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"], font=("Microsoft YaHei UI", 8),
                 anchor=tk.W, justify=tk.LEFT, wraplength=420).pack(
            fill=tk.X, padx=(12, 0), pady=(2, 0))
        metadata = inst.get("metadata") or {}
        if isinstance(metadata, dict) and metadata:
            items = list(metadata.items())[:6]
            meta_text = ", ".join(str(k) + "=" + str(v) for k, v in items)
            if len(metadata) > 6:
                meta_text += ", ..."
            tk.Label(block, text="元数据 " + meta_text, bg=COLORS["bg_card"],
                     fg=COLORS["text_secondary"], font=("Microsoft YaHei UI", 8),
                     anchor=tk.W, justify=tk.LEFT, wraplength=420).pack(
                fill=tk.X, padx=(12, 0), pady=(2, 0))
        tk.Frame(block, bg=COLORS["separator"], height=1).pack(fill=tk.X, pady=(6, 0))

    def _confirm_toggle_instance(self, svc):
        if not svc:
            return
        self._hide_tooltip()
        from tkinter import messagebox
        action = "下线" if svc["online"] else "上线"
        note = self.notes["nacos"].get(svc["ip"], "")
        ip_port = svc["ip"] + ":" + str(svc["port"])
        if note:
            ip_port += " (" + note + ")"
        msg = "确定要" + action + "服务？\n\n" + svc["service_name"] + "\n" + ip_port
        if messagebox.askyesno("确认" + action, msg, parent=self.root):
            if svc["online"]:
                self._take_offline(svc)
            else:
                self._bring_online(svc)

    def _on_cards_wheel(self, event):
        if self._source != SOURCE_NACOS:
            return
        if self._view_mode != "card" or not self._cards_canvas:
            return
        canvas = self._cards_canvas
        x, y = self.root.winfo_pointerxy()
        if not (canvas.winfo_rootx() <= x <= canvas.winfo_rootx() + canvas.winfo_width()
                and canvas.winfo_rooty() <= y <= canvas.winfo_rooty() + canvas.winfo_height()):
            return
        if event.delta:
            self._hide_tooltip()
            canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

    def _ensure_context_menu_shell(self):
        if self._context_menu is not None and self._context_menu.winfo_exists():
            return
        import tkinter as tk
        C = COLORS
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.withdraw()
        self._menu_transparent_key = theme_mod.transparent_key(C)
        top.configure(bg=self._menu_transparent_key)
        try:
            top.attributes("-transparentcolor", self._menu_transparent_key)
        except tk.TclError:
            pass
        canvas = tk.Canvas(top, bg=self._menu_transparent_key,
                           highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        self._apply_float_material(top, self._menu_transparent_key)
        host = tk.Frame(canvas, bg=C["bg_card"])
        self._context_menu = top
        self._menu_canvas = canvas
        self._menu_host = host
        self._menu_host_item = canvas.create_window(0, 0, window=host, anchor=tk.NW)
        top.bind("<FocusOut>", self._on_menu_focus_out)
        top.bind("<Escape>", lambda e: self._close_context_menu())

    def _discard_context_menu(self):
        """主题切换等需要彻底销毁菜单单例时调用"""
        if self._context_menu is not None:
            try:
                self._context_menu.destroy()
            except Exception:
                pass
        self._context_menu = None
        self._menu_canvas = None
        self._menu_host = None
        self._menu_host_item = None

    def _on_menu_focus_out(self, event):
        if self._context_menu is None:
            return
        # 与弹窗一致：圆角透明角落到主窗口时收回焦点，不收起
        if (self._pointer_in_widget_bounds(self._context_menu)
                and self._foreground_is_root()):
            try:
                self._context_menu.focus_force()
            except Exception:
                pass
            return
        self._close_context_menu()

    def _close_context_menu(self):
        """隐藏菜单单例，窗口实例保留复用"""
        if self._context_menu:
            theme_mod.stop_alpha(self._context_menu)
            try:
                self._context_menu.withdraw()
            except Exception:
                pass

    def _show_card_context_menu(self, event, svc_name, svc):
        self._open_context_menu(svc_name, svc, event.x_root, event.y_root)

    def _open_context_menu(self, svc_name, svc, x_root, y_root):
        import tkinter as tk
        self._hide_tooltip()
        self._close_context_menu()
        self._menu_service = svc
        self._menu_service_name = svc_name
        pins = self.cfg.get("pinned_services") or []
        items = [
            ("上线", self._ctx_online, bool(svc and not svc["online"])),
            ("下线", self._ctx_offline, bool(svc and svc["online"])),
            None,
            ("取消置顶" if svc_name in pins else "置顶服务", self._ctx_toggle_pin, True),
            ("管理备注...", self._ctx_set_note, True),
            None,
            (("取消免打扰" if svc["ip"] in self.dnd["nacos"] else "免打扰") if svc else "免打扰",
             self._ctx_toggle_dnd, bool(svc)),
            ("刷新", self._on_refresh_click, True),
        ]
        self._open_items_menu(items, x_root, y_root)

    def _open_items_menu(self, items, x_root, y_root):
        import tkinter as tk
        self._hide_tooltip()
        self._close_context_menu()
        self._ensure_context_menu_shell()
        top = self._context_menu
        canvas = self._menu_canvas
        host = self._menu_host
        for child in host.winfo_children():
            child.destroy()
        C = COLORS
        for item in items:
            if item is None:
                tk.Frame(host, bg=C["separator"], height=1).pack(
                    fill=tk.X, padx=8, pady=4)
                continue
            text, command, enabled = item
            label = tk.Label(host, text=text, bg=C["bg_card"],
                             fg=C["text_primary"] if enabled else C["text_secondary"],
                             font=("Microsoft YaHei UI", 9), anchor=tk.W,
                             padx=18, pady=6, cursor="hand2" if enabled else "arrow")
            label.pack(fill=tk.X)
            if enabled:
                label.bind("<Enter>", lambda e, w=label: w.configure(
                    bg=COLORS["primary"], fg=COLORS["header_text"]))
                label.bind("<Leave>", lambda e, w=label: w.configure(
                    bg=COLORS["bg_card"], fg=COLORS["text_primary"]))
                label.bind("<Button-1>", lambda e, c=command: self._run_menu_command(c))
        host.update_idletasks()
        width = host.winfo_reqwidth()
        height = host.winfo_reqheight()
        radius = theme_mod.RADIUS_MENU
        total_w = width + 2 * radius
        total_h = height + 2 * radius
        canvas.configure(width=total_w, height=total_h)
        canvas.delete("all")
        theme_mod.rounded_rect(canvas, 1, 1, total_w - 1, total_h - 1, radius,
                               fill=COLORS["bg_card"], outline=COLORS["separator"])
        self._menu_host_item = canvas.create_window(
            radius, radius, window=host, anchor=tk.NW, width=width, height=height)
        screen_w = top.winfo_screenwidth()
        screen_h = top.winfo_screenheight()
        x = min(x_root, screen_w - total_w - 6)
        y = min(y_root, screen_h - total_h - 6)
        try:
            top.attributes("-alpha", 0.0)
        except Exception:
            pass
        top.geometry(str(total_w) + "x" + str(total_h)
                     + "+" + str(max(0, x)) + "+" + str(max(0, y)))
        top.deiconify()
        top.lift()
        theme_mod.stop_alpha(top)
        theme_mod.animate_alpha(top, 1.0, theme_mod.MENU_FADE_MS)
        top.focus_force()

    def _run_menu_command(self, command):
        self._close_context_menu()
        command()

    def _on_tree_click(self, event):
        item = self._tree_cell_at(event, "#1")
        if not item:
            return
        values = self._service_tree.item(item, "values")
        if len(values) < 3:
            return
        self._service_tree.selection_set(item)
        self._toggle_pin(str(values[2]))
        return "break"

    def _toggle_pin(self, svc_name):
        now = time.time()
        last = self._last_pin_click
        if last and last[0] == svc_name and now - last[1] < 0.4:
            return
        self._last_pin_click = (svc_name, now)
        pins = self.cfg.setdefault("pinned_services", [])
        if svc_name in pins:
            pins.remove(svc_name)
        else:
            pins.append(svc_name)
        config.save_config(self.cfg)
        self._update_window()

    def _on_refresh_click(self):
        if self._status_var:
            self._status_var.set("正在刷新...")
        if self.root:
            self.root.update()
        self._manual_refresh()

    def _on_settings_click(self):
        self._show_settings()

    def _on_window_close(self):
        """Minimize to tray instead of closing"""
        self.root.withdraw()

    def _show_context_menu(self, event):
        item = self._service_tree.identify_row(event.y)
        if item:
            self._service_tree.selection_set(item)
        svc = self._get_selected_service()
        if not svc:
            return
        self._open_context_menu(svc["service_name"], svc, event.x_root, event.y_root)

    def _get_selected_service(self):
        if not self._service_tree:
            return None
        selection = self._service_tree.selection()
        if not selection:
            return None
        values = self._service_tree.item(selection[0])["values"]
        if not values or len(values) < 7:
            return None
        svc_name = values[2]
        instance_text = values[3]
        port = int(values[4])
        for svc in self.services:
            if svc["service_name"] == svc_name and svc["port"] == port:
                display = self._get_display_name(svc["ip"])
                if display == instance_text or svc["ip"] == instance_text:
                    return svc
        return None

    def _ctx_online(self):
        svc = self._menu_service
        if svc and not svc["online"]:
            self._bring_online(svc)

    def _ctx_offline(self):
        svc = self._menu_service
        if svc and svc["online"]:
            self._take_offline(svc)

    def _ctx_set_note(self):
        if self._menu_service_name:
            self._show_notes()

    def _ctx_toggle_pin(self):
        if self._menu_service_name:
            self._toggle_pin(self._menu_service_name)

    def _ctx_toggle_dnd(self):
        svc = self._menu_service
        if not svc:
            return
        dnd = self.dnd.setdefault("nacos", {})
        ip = svc["ip"]
        if ip in dnd:
            dnd.pop(ip, None)
        else:
            dnd[ip] = True
        config.save_dnd(self.dnd)
        self._update_window()

    def _on_double_click(self, event):
        if self._tree_cell_at(event, "#1") or self._tree_cell_at(event, "#2"):
            return "break"
        svc = self._get_selected_service()
        if svc:
            if svc["online"]:
                self._take_offline(svc)
            else:
                self._bring_online(svc)

    def run(self):
        self.running = True
        # 把旧版 NacosTray 自启键改名为 TrayNotify，保留原有启动路径
        config.migrate_auto_start_key()
        self._create_window()
        self.tray = TrayIcon(tooltip=APP_NAME + "\n双击显示主窗口", tk_root=self.root)
        self.tray.callbacks["double_click"] = self._show_window
        self.tray.set_tooltip(APP_NAME + "\n双击显示主窗口")
        self.tray.set_popup_callback(self._show_service_list_popup)
        self.tray.start()
        self._daozai = daozai_sink.create_sink(self.cfg)
        self._notifier = notifier_mod.NotifierCenter(
            self.root,
            tray_getter=lambda: self.tray,
            palette_getter=lambda: COLORS,
            style_getter=lambda: (self.cfg.get("notify") or {}).get(
                "style", notifier_mod.STYLE_DEFAULT),
            on_click=self._on_notification_click,
            remote_emit=self._daozai.push,
            enabled_sources=self._enabled_sources_map,
        )
        nacos_ready = (self._source_enabled(SOURCE_NACOS)
                       and bool(self.nacos_cfg.get("ip")))
        jenkins_ready = (self._source_enabled(SOURCE_JENKINS)
                         and bool(self.jenkins_cfg.get("url")))
        if nacos_ready:
            self._init_client()
            self._do_login()
        self._restart_jenkins_monitor()
        if not nacos_ready and not jenkins_ready:
            self._notify("提示", "请在设置中启用并配置至少一个通知源（Nacos 或 Jenkins）",
                         "info")
        self.root.after(2000, self._manual_refresh)
        self._schedule_poll()
        self._ensure_theme_poll()
        print(APP_NAME + " started")
        if self.root:
            self.root.mainloop()
        self.quit()

    def quit(self):
        print(APP_NAME + " exiting...")
        self.running = False
        if self._jenkins_monitor:
            self._jenkins_monitor.stop()
            self._jenkins_monitor = None
        if self._daozai:
            self._daozai.configure("", False)
        if self._notifier:
            self._notifier.dismiss_all()
        if self.tray:
            self.tray.stop()
        if self.root:
            try:
                self.root.destroy()
            except:
                pass


def main():
    try:
        app = TrayNotifyApp()
        app.run()
    except Exception as e:
        tb = traceback.format_exc()
        show_error(tb)


if __name__ == "__main__":
    main()
