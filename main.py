"""
main.py - Nacos Tray Main Application
"""
import sys
import os
import time
import threading
import json
import traceback
import ctypes
import ctypes.wintypes
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import theme as theme_mod
from nacos_client import NacosClient

APP_VERSION = "v1.7"

try:
    from tray_v2 import TrayIcon, NIIF_INFO, NIIF_WARNING, NIIF_ERROR
except ImportError:
    from tray import TrayIcon, NIIF_INFO, NIIF_WARNING, NIIF_ERROR


def show_error(msg):
    try:
        ctypes.windll.user32.MessageBoxW(0, str(msg), "Nacos Tray Error", 0x10)
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
    window.geometry("+" + str(x) + "+" + str(y))


def _center_on_screen(window):
    window.update_idletasks()
    w = window.winfo_width()
    h = window.winfo_height()
    x = (window.winfo_screenwidth() - w) // 2
    y = (window.winfo_screenheight() - h) // 2
    window.geometry(f"+{x}+{y}")


# ==================== 按钮图标 ====================
# 使用 Windows 自带的 Segoe MDL2 Assets 字形，缺失时回退为纯文字
_ICON_FONT = "Segoe MDL2 Assets"
_ICON_GLYPHS = {
    "settings": "\uE713",
}
_ICON_FONT_CACHE = []


def _icon_font_available(widget):
    if not _ICON_FONT_CACHE:
        try:
            import tkinter.font as tkfont
            _ICON_FONT_CACHE.append(_ICON_FONT in tkfont.families(widget))
        except Exception:
            _ICON_FONT_CACHE.append(False)
    return _ICON_FONT_CACHE[0]


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
    ("v1.7", "NacosTray_v1.7.exe", [
        "卡片服务名字号可在外观设置中调整，支持小/标准/大/特大",
        "悬浮详情同时支持表格与卡片，靠近屏幕右侧时自动翻到左侧",
        "设置中的勾选框统一显示为 √",
        "移除行为页的立即刷新，刷新仍可使用快捷键与托盘入口",
        "关于页增加作者邮箱",
        "配色预设改为紧凑三列，减少外观页滚动",
        "托盘右键弹窗按钮改为纯文字并移除关闭按钮",
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


class SettingsDialog:
    PAGE_CONNECTION = 0
    PAGE_BEHAVIOR = 1
    PAGE_APPEARANCE = 2
    PAGE_SHORTCUTS = 3
    PAGE_NOTES = 4
    PAGE_ABOUT = 5
    PAGE_TITLES = ["连接", "行为", "外观", "快捷键", "备注", "关于"]

    def __init__(self, parent, cfg, on_save=None, app=None, geometry=None, page=None):
        self.cfg = dict(cfg)
        self.base_cfg = dict(cfg)
        self.on_save = on_save
        self.app = app
        self.result = False
        self._page_index = page if page is not None else self.PAGE_CONNECTION
        if self._page_index not in range(len(self.PAGE_TITLES)):
            self._page_index = self.PAGE_CONNECTION
        self._scroll_pos = 0.0
        self._appearance_canvas = None
        self._about_canvas = None
        self._notes_tree = None
        self._capture_action = None
        self._shortcut_widgets = {}
        self._preview_job = None
        self.notes = self.app.notes if self.app else config.load_notes()
        self.available_ips = None
        import tkinter as tk
        self._mode_var = tk.StringVar(value=self.base_cfg.get("theme_mode", theme_mod.MODE_SYSTEM))
        self._preset_var = tk.StringVar(value=self.base_cfg.get("theme_preset", theme_mod.DEFAULT_PRESET))
        custom = self.base_cfg.get("theme_custom") or {}
        self._custom_light_var = tk.StringVar(value=custom.get("light", theme_mod.DEFAULT_CUSTOM["light"]))
        self._custom_dark_var = tk.StringVar(value=custom.get("dark", theme_mod.DEFAULT_CUSTOM["dark"]))
        self._custom_accent = self.base_cfg.get("theme_custom_accent", theme_mod.DEFAULT_PRESET)
        if self._custom_accent == theme_mod.CUSTOM_ID:
            self._custom_accent = theme_mod.DEFAULT_PRESET
        self.ip_var = tk.StringVar(value=self.base_cfg.get("ip", ""))
        self.port_var = tk.StringVar(value=str(self.base_cfg.get("port", 8848)))
        self.namespace_var = tk.StringVar(value=self.base_cfg.get("namespace", ""))
        self.cluster_name_var = tk.StringVar(value=self.base_cfg.get("cluster_name", "ShenZhen"))
        self.username_var = tk.StringVar(value=self.base_cfg.get("username", "nacos"))
        self.password_var = tk.StringVar(value=self.base_cfg.get("password", ""))
        self.auto_start_var = tk.BooleanVar(value=config.is_auto_start())
        self.login_interval_var = tk.StringVar(value=str(self.base_cfg.get("login_interval", 1800)))
        self.poll_interval_var = tk.StringVar(value=str(self.base_cfg.get("poll_interval", 30)))
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
        shortcuts = self.base_cfg.get("shortcuts") or {}
        self._shortcut_vars = {}
        for action, default in config.DEFAULT_SHORTCUTS.items():
            value = shortcuts.get(action, default)
            if not isinstance(value, str):
                value = default
            self._shortcut_vars[action] = tk.StringVar(value=value)
        self._shortcut_status_var = tk.StringVar(value="")
        self.window = tk.Toplevel(parent)
        self.window.title("设置")
        if geometry:
            self.window.geometry(geometry)
        else:
            self.window.geometry("660x700")
            _center_on_parent(self.window, parent)
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()
        _set_icon(self.window)
        self._build()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        if self.app:
            self.app._register_dialog("settings", self.window, dialog=self)

    def _build(self):
        import tkinter as tk
        from tkinter import ttk
        for child in self.window.winfo_children():
            child.destroy()
        self._shortcut_widgets = {}
        self._appearance_canvas = None
        self._about_canvas = None
        self._notes_tree = None
        self.window.configure(bg=COLORS["bg_main"])
        header = tk.Frame(self.window, bg=COLORS["header_bg"], height=46)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=" 设置", bg=COLORS["header_bg"],
                fg=COLORS["header_fg"],
                font=("Microsoft YaHei UI", 11, "bold"),
                anchor=tk.W, padx=16).pack(side=tk.LEFT, fill=tk.Y)
        body = tk.Frame(self.window, bg=COLORS["bg_main"])
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))
        sidebar = tk.Frame(body, bg=COLORS["bg_card"], width=140,
                           highlightthickness=1, highlightbackground=COLORS["separator"])
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        self._nav_labels = []
        for index, title in enumerate(self.PAGE_TITLES):
            label = tk.Label(sidebar, text=title, anchor=tk.W, padx=14, pady=9, cursor="hand2")
            label.pack(fill=tk.X)
            label.bind("<Button-1>", lambda e, i=index: self._select_page(i))
            self._nav_labels.append(label)
        content = tk.Frame(body, bg=COLORS["bg_main"])
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        self._pages = [
            self._build_connection_page(content),
            self._build_behavior_page(content),
            self._build_appearance_page(content),
            self._build_shortcuts_page(content),
            self._build_notes_page(content),
            self._build_about_page(content),
        ]
        btn_frame = ttk.Frame(self.window, padding=(12, 0, 12, 12))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="测试连接", command=self._test_connection).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btn_frame, text="取消", command=self._cancel).pack(side=tk.RIGHT)
        self.window.bind("<KeyPress>", self._on_shortcut_key)
        self.window.bind("<MouseWheel>", self._on_settings_wheel)
        self._select_page(self._page_index)
        if self.app:
            theme_mod.set_dark_titlebar(self.window, COLORS.get("mode") == theme_mod.MODE_DARK)

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
        for i, label in enumerate(self._nav_labels):
            active = i == index
            label.configure(
                bg=COLORS["secondary"] if active else COLORS["bg_card"],
                fg=COLORS["text_primary"],
                font=("Microsoft YaHei UI", 11 if active else 9,
                      "bold" if active else "normal"))
        for i, page in enumerate(self._pages):
            if i == index:
                page.pack(fill=tk.BOTH, expand=True)
            else:
                page.pack_forget()
        if index == self.PAGE_NOTES and self._notes_tree:
            self._notes_refresh()
        if index == self.PAGE_APPEARANCE and self._appearance_canvas:
            self.window.update_idletasks()
            if self._scroll_pos > 0:
                self._appearance_canvas.yview_moveto(self._scroll_pos)

    def _build_connection_page(self, parent):
        from tkinter import ttk
        page = ttk.Frame(parent, padding=4)
        self._build_connection(page)
        return page

    def _build_behavior_page(self, parent):
        from tkinter import ttk
        page = ttk.Frame(parent, padding=4)
        self._build_behavior(page)
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

        self._section(inner, "主题模式")
        mode_bar = tk.Frame(inner, bg=COLORS["bg_card"], highlightthickness=1,
                            highlightbackground=COLORS["separator"])
        mode_bar.pack(fill=tk.X, pady=(2, 8))
        for value, label in theme_mod.MODE_OPTIONS:
            active = self._mode_var.get() == value
            btn = tk.Label(mode_bar, text=label,
                           bg=COLORS["primary"] if active else COLORS["bg_card"],
                           fg=COLORS["header_text"] if active else COLORS["text_primary"],
                           font=("Microsoft YaHei UI", 9, "bold" if active else ""),
                           padx=10, pady=6, cursor="hand2")
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
            btn.bind("<Button-1>", lambda e, v=value: self._set_mode(v))
        self._section(inner, "配色预设")
        grid = tk.Frame(inner, bg=COLORS["bg_main"])
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=1)
        entries = [(pid, theme_mod.PRESETS[pid]["name"]) for pid in theme_mod.PRESET_ORDER]
        entries.append((theme_mod.CUSTOM_ID, theme_mod.CUSTOM_NAME))
        for index, (preset_id, name) in enumerate(entries):
            light, dark = self._preview_colors(preset_id)
            card = self._make_card(grid, preset_id, name, light, dark)
            card.grid(row=index // 3, column=index % 3, padx=3, pady=3, sticky="nsew")
        self._custom_area = tk.Frame(inner, bg=COLORS["bg_main"])
        self._custom_area.pack(fill=tk.X)
        self._build_custom_inputs()

        self._section(inner, "视图")
        tk.Label(inner, text="视图模式", bg=COLORS["bg_main"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        self._segmented(inner, [("table", "表格"), ("card", "卡片")], self._view_mode_var)

        self._section(inner, "卡片")
        tk.Label(inner, text="每行列数", bg=COLORS["bg_main"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        self._segmented(inner, [("auto", "自动"), ("1", "1"), ("2", "2"), ("3", "3")],
                        self._card_columns_var)
        tk.Label(inner, text="密度", bg=COLORS["bg_main"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        self._segmented(inner, [("compact", "紧凑"), ("normal", "标准"), ("comfortable", "宽松")],
                        self._card_density_var)
        tk.Label(inner, text="服务名字号", bg=COLORS["bg_main"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        self._segmented(inner, [("small", "小"), ("normal", "标准"), ("large", "大"), ("xlarge", "特大")],
                        self._card_name_size_var)
        tk.Label(inner, text="显示字段", bg=COLORS["bg_main"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(4, 2))
        fields_wrap = tk.Frame(inner, bg=COLORS["bg_main"])
        fields_wrap.pack(fill=tk.X, pady=(0, 6))
        for field, label in CARD_FIELD_LABELS:
            self._check_button(fields_wrap, label,
                               self._card_field_vars[field]).pack(side=tk.LEFT, padx=(0, 12))

        self._section(inner, "表格")
        tk.Label(inner, text="行高", bg=COLORS["bg_main"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        self._segmented(inner, [("compact", "紧凑"), ("normal", "标准"), ("comfortable", "宽松")],
                        self._table_row_height_var)
        self._check_button(inner, "斑马纹", self._table_striped_var).pack(anchor=tk.W)

        foot = ttk.Frame(inner)
        foot.pack(fill=tk.X, pady=(10, 6))
        ttk.Button(foot, text="恢复默认", command=self._restore_default).pack(side=tk.LEFT)
        self.window.update_idletasks()
        if self._scroll_pos > 0:
            canvas.yview_moveto(self._scroll_pos)
        return page

    def _section(self, parent, text):
        import tkinter as tk
        tk.Label(parent, text=text, bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=("Microsoft YaHei UI", 9, "bold")).pack(anchor=tk.W, pady=(8, 2))

    def _segmented(self, parent, options, var):
        import tkinter as tk
        bar = tk.Frame(parent, bg=COLORS["bg_card"], highlightthickness=1,
                       highlightbackground=COLORS["separator"])
        bar.pack(fill=tk.X, pady=(2, 8))
        labels = []

        def refresh():
            for value, label in labels:
                active = var.get() == value
                label.configure(
                    bg=COLORS["primary"] if active else COLORS["bg_card"],
                    fg=COLORS["header_text"] if active else COLORS["text_primary"],
                    font=("Microsoft YaHei UI", 9, "bold" if active else "normal"))

        def choose(value):
            var.set(value)
            refresh()

        for value, title in options:
            label = tk.Label(bar, text=title, padx=10, pady=5, cursor="hand2")
            label.pack(side=tk.LEFT, expand=True, fill=tk.X)
            label.bind("<Button-1>", lambda e, v=value: choose(v))
            labels.append((value, label))
        refresh()
        return bar

    def _check_button(self, parent, text, var):
        import tkinter as tk
        frame = tk.Frame(parent, bg=COLORS["bg_main"], cursor="hand2")
        box = tk.Label(frame, text="√" if var.get() else "", width=2,
                       bg=COLORS["bg_card"], fg=COLORS["primary"],
                       font=("Microsoft YaHei UI", 10, "bold"),
                       relief=tk.SOLID, bd=1, anchor=tk.CENTER)
        box.pack(side=tk.LEFT)
        label = tk.Label(frame, text=text, bg=COLORS["bg_main"],
                         fg=COLORS["text_primary"], font=("Microsoft YaHei UI", 9))
        label.pack(side=tk.LEFT, padx=(6, 0))

        def toggle(event=None):
            var.set(not var.get())
            box.configure(text="√" if var.get() else "")

        for widget in (frame, box, label):
            widget.bind("<Button-1>", toggle)
        return frame

    def _build_shortcuts_page(self, parent):
        import tkinter as tk
        from tkinter import ttk
        page = ttk.Frame(parent, padding=4)
        ttk.Label(page, text="快捷键只在主窗口获得焦点时生效；清空表示禁用。",
                  foreground=COLORS["text_secondary"]).pack(anchor=tk.W, pady=(0, 8))
        group = ttk.LabelFrame(page, text="按键绑定", padding=10)
        group.pack(fill=tk.X)
        for action, label in SHORTCUT_LABELS.items():
            row = ttk.Frame(group)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=label).pack(side=tk.LEFT)
            btn = ttk.Button(row, width=18,
                             text=self._shortcut_display(self._shortcut_vars[action].get()),
                             command=lambda a=action: self._begin_capture(a))
            btn.pack(side=tk.RIGHT)
            self._shortcut_widgets[action] = btn
        ttk.Label(group, textvariable=self._shortcut_status_var,
                  foreground=COLORS["warning"]).pack(anchor=tk.W, pady=(6, 0))
        ttk.Button(group, text="恢复默认", command=self._reset_shortcuts).pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(page, text="提示：字母、数字和符号需要配合 Ctrl / Alt / Shift；F1-F12 可单独使用。",
                  foreground=COLORS["text_secondary"], wraplength=420).pack(anchor=tk.W, pady=(10, 0))
        return page

    def _build_notes_page(self, parent):
        import tkinter as tk
        from tkinter import ttk
        page = ttk.Frame(parent, padding=4)
        toolbar = tk.Frame(page, bg=COLORS["bg_main"])
        toolbar.pack(fill=tk.X, pady=(0, 8))
        for text, cmd in [("新增", self._notes_add),
                          ("编辑", self._notes_edit),
                          ("删除", self._notes_delete)]:
            btn = tk.Label(toolbar, text=text, bg=COLORS["secondary"],
                           fg=COLORS["text_primary"],
                           font=("Microsoft YaHei UI", 9),
                           padx=12, pady=4, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, 6))
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=COLORS["primary"]))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=COLORS["secondary"]))
        tree_wrap = ttk.Frame(page)
        tree_wrap.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(tree_wrap, columns=("ip", "note"), show="headings",
                            selectmode="browse")
        tree.heading("ip", text="IP 地址")
        tree.heading("note", text="备注名")
        tree.column("ip", width=220)
        tree.column("note", width=260)
        scrollbar = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.bind("<Double-1>", self._notes_edit)
        self._notes_tree = tree
        tk.Label(page, text="备注修改会立即保存，无需点击下方保存按钮",
                 bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor=tk.W, pady=(6, 0))
        self._notes_refresh()
        return page

    def _build_about_page(self, parent):
        import tkinter as tk
        from tkinter import ttk
        page = ttk.Frame(parent, padding=4)
        basic = ttk.Frame(page)
        basic.pack(fill=tk.X)
        for i, (label, value) in enumerate([
            ("应用名称", "Nacos Tray"),
            ("当前版本", APP_VERSION),
            ("兼容", "Nacos v3.2.1+（v3.x）"),
            ("作者", "JiangYuan"),
            ("邮箱", "yuan62387@qq.com"),
        ]):
            ttk.Label(basic, text=label + "：",
                      font=("Microsoft YaHei UI", 9),
                      foreground=COLORS["text_secondary"]).grid(row=i, column=0, sticky=tk.E,
                                                               pady=1, padx=(0, 6))
            ttk.Label(basic, text=value,
                      font=("Microsoft YaHei UI", 9, "bold" if label == "应用名称" else ""),
                      foreground=COLORS["text_primary"]).grid(row=i, column=1, sticky=tk.W, pady=1)
        ttk.Separator(page, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 4))
        ttk.Label(page, text="更新记录", font=("Microsoft YaHei UI", 9, "bold"),
                  foreground=COLORS["text_secondary"]).pack(anchor=tk.W)
        container = tk.Frame(page, bg=COLORS["bg_main"])
        container.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
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
                     font=("Microsoft YaHei UI", 9, "bold"), anchor=tk.W,
                     justify=tk.LEFT, wraplength=440).pack(fill=tk.X, pady=(6, 2))
            for item in items:
                tk.Label(inner, text="• " + item, bg=COLORS["bg_main"],
                         fg=COLORS["text_secondary"],
                         font=("Microsoft YaHei UI", 9), anchor=tk.W,
                         justify=tk.LEFT, wraplength=440).pack(
                    fill=tk.X, padx=(14, 0))
        return page

    def _build_connection(self, page):
        from tkinter import ttk
        import tkinter as tk
        conn_group = ttk.LabelFrame(page, text="Nacos 连接设置", padding=10)
        conn_group.pack(fill=tk.X)
        ttk.Label(conn_group, text="IP:").grid(row=0, column=0, sticky=tk.W, pady=3)
        ttk.Entry(conn_group, textvariable=self.ip_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="端口:").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Entry(conn_group, textvariable=self.port_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="命名空间:").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Entry(conn_group, textvariable=self.namespace_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="集群名:").grid(row=3, column=0, sticky=tk.W, pady=3)
        ttk.Entry(conn_group, textvariable=self.cluster_name_var, width=30).grid(row=3, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="用户名:").grid(row=4, column=0, sticky=tk.W, pady=3)
        ttk.Entry(conn_group, textvariable=self.username_var, width=30).grid(row=4, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="密码:").grid(row=5, column=0, sticky=tk.W, pady=3)
        ttk.Entry(conn_group, textvariable=self.password_var, width=30, show="*").grid(row=5, column=1, sticky=tk.W, pady=3)
        ttk.Label(page, text="保存后立即重新登录并刷新服务列表",
                  foreground=COLORS["text_secondary"]).pack(anchor=tk.W, pady=(8, 0))

    def _build_behavior(self, page):
        from tkinter import ttk
        import tkinter as tk
        behavior_group = ttk.LabelFrame(page, text="行为设置", padding=10)
        behavior_group.pack(fill=tk.X)
        self._check_button(behavior_group, "开机自动启动",
                           self.auto_start_var).pack(anchor=tk.W, pady=3)
        rf1 = ttk.Frame(behavior_group)
        rf1.pack(fill=tk.X, pady=3)
        ttk.Label(rf1, text="登录刷新间隔(秒):").pack(side=tk.LEFT)
        ttk.Entry(rf1, textvariable=self.login_interval_var, width=10).pack(side=tk.LEFT, padx=10)
        rf2 = ttk.Frame(behavior_group)
        rf2.pack(fill=tk.X, pady=3)
        ttk.Label(rf2, text="状态轮询(秒):").pack(side=tk.LEFT)
        ttk.Entry(rf2, textvariable=self.poll_interval_var, width=10).pack(side=tk.LEFT, padx=10)

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

    def _draw_preview(self, canvas, light, dark):
        width, height, gap = 120, 28, 4
        half = (width - gap) // 2

        def draw_block(x0, palette):
            x1 = x0 + half
            canvas.create_rectangle(x0, 0, x1, height,
                                    fill=palette["bg_card"], outline=palette["separator"])
            canvas.create_rectangle(x0, 0, x1, 6,
                                    fill=palette["primary"], outline=palette["primary"])
            canvas.create_rectangle(x0 + 4, 10, x1 - 8, 13,
                                    fill=palette["text_primary"], outline=palette["text_primary"])
            canvas.create_rectangle(x0 + 4, 16, x1 - 4, 19,
                                    fill=palette["text_secondary"], outline=palette["text_secondary"])
            canvas.create_rectangle(x0 + 4, 22, x1 - 12, 25,
                                    fill=palette["secondary"], outline=palette["secondary"])

        draw_block(0, light)
        draw_block(half + gap, dark)

    def _make_card(self, parent, preset_id, name, light, dark):
        import tkinter as tk
        selected = self._preset_var.get() == preset_id
        card = tk.Frame(parent, bg=COLORS["bg_card"],
                        highlightthickness=2 if selected else 1,
                        highlightbackground=COLORS["primary"] if selected else COLORS["separator"],
                        cursor="hand2")
        preview = tk.Canvas(card, width=120, height=28, bg=COLORS["bg_card"], highlightthickness=0)
        preview.pack(padx=4, pady=(4, 1))
        self._draw_preview(preview, light, dark)
        row = tk.Frame(card, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, padx=4, pady=(0, 4))
        tk.Label(row, text=name, bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                 font=("Microsoft YaHei UI", 8, "bold" if selected else "")).pack(side=tk.LEFT)
        if selected:
            tk.Label(row, text="使用中", bg=COLORS["bg_card"], fg=COLORS["primary"],
                     font=("Microsoft YaHei UI", 7)).pack(side=tk.RIGHT)
        for widget in (card, preview, row):
            widget.bind("<Button-1>", lambda e, p=preset_id: self._select_preset(p))
        for widget in row.winfo_children():
            widget.bind("<Button-1>", lambda e, p=preset_id: self._select_preset(p))
        for item in preview.find_all():
            preview.tag_bind(item, "<Button-1>", lambda e, p=preset_id: self._select_preset(p))
        return card

    def _build_custom_inputs(self):
        import tkinter as tk
        from tkinter import ttk
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
                     font=("Microsoft YaHei UI", 8)).pack(anchor=tk.W, pady=(2, 0))
            return
        for label, var in (("亮色背景", self._custom_light_var), ("暗色背景", self._custom_dark_var)):
            row = ttk.Frame(self._custom_area)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label + ":").pack(side=tk.LEFT)
            entry = ttk.Entry(row, textvariable=var, width=12)
            entry.pack(side=tk.LEFT, padx=8)
            swatch = tk.Canvas(row, width=28, height=18, highlightthickness=1,
                               highlightbackground=COLORS["separator"], bg=COLORS["bg_card"])
            swatch.pack(side=tk.LEFT)
            trace_id = var.trace_add("write", lambda *a, c=swatch, v=var: self._refresh_swatch(c, v))
            self._swatch_traces.append((var, trace_id))
            self._refresh_swatch(swatch, var)
            entry.bind("<FocusOut>", lambda e: self._preview_theme())
            entry.bind("<Return>", lambda e: self._preview_theme())
        self._custom_hint = tk.Label(self._custom_area, text="格式 #RRGGBB，例如 #2B2B2B",
                                     bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                                     font=("Microsoft YaHei UI", 8))
        self._custom_hint.pack(anchor=tk.W, pady=(2, 0))

    def _refresh_swatch(self, canvas, var):
        try:
            if not canvas.winfo_exists():
                return
        except Exception:
            return
        value = var.get().strip()
        color = theme_mod.normalize_hex(value, COLORS["bg_card"])
        canvas.configure(bg=color)
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

    def _notes_refresh(self):
        if not self._notes_tree:
            return
        self._notes_tree.delete(*self._notes_tree.get_children())
        for ip, note in sorted(self.notes.items()):
            self._notes_tree.insert("", "end", values=(ip, note))

    def _notes_save(self):
        config.save_notes(self.notes)
        if self.app:
            self.app._update_window()

    def _notes_add(self):
        import tkinter as tk
        from tkinter import ttk
        if self.available_ips is None:
            self.available_ips = self.app._get_all_ips() if self.app else []
        dialog = tk.Toplevel(self.window)
        dialog.title("添加备注")
        dialog.geometry("360x200")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        _set_icon(dialog)
        _center_on_parent(dialog, self.window)
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="IP 地址:").pack(anchor=tk.W)
        ip_var = tk.StringVar()
        combo = ttk.Combobox(frame, textvariable=ip_var, values=self.available_ips, width=35)
        combo.pack(fill=tk.X, pady=(2, 8))
        combo.focus_set()
        ttk.Label(frame, text="备注名:").pack(anchor=tk.W)
        note_var = tk.StringVar()
        ttk.Entry(frame, textvariable=note_var, width=35).pack(fill=tk.X, pady=(2, 8))
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))

        def on_ok():
            ip = ip_var.get().strip()
            note = note_var.get().strip()
            if not ip:
                return
            if note:
                self.notes[ip] = note
                self._notes_save()
                self._notes_refresh()
            dialog.destroy()

        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)

    def _notes_edit(self, event=None):
        if not self._notes_tree:
            return
        selection = self._notes_tree.selection()
        if not selection:
            return
        ip = str(self._notes_tree.item(selection[0])["values"][0])
        from tkinter import simpledialog
        new_note = simpledialog.askstring("编辑备注", "修改 " + ip + " 的备注名:",
                                          initialvalue=self.notes.get(ip, ""), parent=self.window)
        if new_note is not None:
            if new_note.strip():
                self.notes[ip] = new_note.strip()
            else:
                self.notes.pop(ip, None)
            self._notes_save()
            self._notes_refresh()

    def _notes_delete(self):
        if not self._notes_tree:
            return
        selection = self._notes_tree.selection()
        if not selection:
            return
        ip = str(self._notes_tree.item(selection[0])["values"][0])
        from tkinter import messagebox
        if messagebox.askyesno("确认删除", "确定删除 " + ip + " 的备注吗？", parent=self.window):
            self.notes.pop(ip, None)
            self._notes_save()
            self._notes_refresh()

    def _set_mode(self, value):
        if self._mode_var.get() == value:
            return
        self._mode_var.set(value)
        self._preview_theme()

    def _select_preset(self, preset_id):
        previous = self._preset_var.get()
        if preset_id == theme_mod.CUSTOM_ID and previous != theme_mod.CUSTOM_ID:
            self._custom_accent = previous
        self._preset_var.set(preset_id)
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
        self._view_mode_var.set("table")
        self._card_columns_var.set("auto")
        self._card_density_var.set("normal")
        self._card_name_size_var.set("normal")
        for var in self._card_field_vars.values():
            var.set(True)
        self._table_row_height_var.set("normal")
        self._table_striped_var.set(True)
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

    def _test_connection(self):
        from tkinter import messagebox
        try:
            client = NacosClient(ip=self.ip_var.get().strip(), port=int(self.port_var.get().strip()),
                username=self.username_var.get().strip(), password=self.password_var.get().strip(),
                namespace=self.namespace_var.get().strip(),
                cluster_name=self.cluster_name_var.get().strip() or "ShenZhen")
            if client.login():
                messagebox.showinfo("成功", "连接成功！", parent=self.window)
            else:
                messagebox.showerror("失败", "登录失败，请检查配置", parent=self.window)
        except Exception as e:
            messagebox.showerror("错误", "连接异常: " + str(e), parent=self.window)

    def _save(self):
        from tkinter import messagebox
        if not self._theme_valid():
            messagebox.showerror("错误", "自定义颜色格式应为 #RRGGBB，例如 #2B2B2B", parent=self.window)
            return
        try:
            new_cfg = dict(self.base_cfg)
            new_cfg.update({
                "ip": self.ip_var.get().strip(), "port": int(self.port_var.get().strip()),
                "username": self.username_var.get().strip(), "password": self.password_var.get(),
                "namespace": self.namespace_var.get().strip(),
                "cluster_name": self.cluster_name_var.get().strip() or "ShenZhen",
                "auto_start": self.auto_start_var.get(),
                "login_interval": int(self.login_interval_var.get().strip()),
                "poll_interval": int(self.poll_interval_var.get().strip()),
            })
        except ValueError as e:
            messagebox.showerror("错误", "输入格式错误: " + str(e), parent=self.window)
            return
        new_cfg.update(self._theme_values())
        shortcut_values = [var.get() for var in self._shortcut_vars.values() if var.get()]
        if len(shortcut_values) != len(set(shortcut_values)):
            messagebox.showerror("错误", "快捷键不能重复，请先修改冲突项", parent=self.window)
            return
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
            "shortcuts": {action: var.get() for action, var in self._shortcut_vars.items()},
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


class ServiceListPopup:
    """右键服务列表弹窗，按服务名分组、IP 带颜色、透明度 60%、点击确认上下线"""

    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.window = None
        self._build()

    def _build(self):
        import tkinter as tk
        C = COLORS
        services = self.app.services
        self.window = tk.Toplevel(self.parent)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        outer = tk.Frame(self.window, bg=C["bg_card"], relief=tk.SOLID, borderwidth=1,
                         highlightbackground=C["separator"], highlightthickness=1)
        outer.pack()
        ip = self.app.cfg.get("ip", "?")
        port = self.app.cfg.get("port", 8848)
        header = tk.Frame(outer, bg=C["header_bg"], height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        left_frame = tk.Frame(header, bg=C["header_bg"])
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=12)
        tk.Label(left_frame, text=f"Nacos: {ip}:{port}", bg=C["header_bg"],
                fg=C["header_fg"], font=("Microsoft YaHei UI", 9, "bold"),
                anchor=tk.W).pack(fill=tk.Y, expand=True)
        right_frame = tk.Frame(header, bg=C["header_bg"])
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=12)
        total = len(services)
        online = sum(1 for s in services if s["online"])
        tk.Label(right_frame, text=f"{online}/{total} 在线", bg=C["header_bg"],
                fg=C["header_fg"], font=("Microsoft YaHei UI", 9),
                anchor=tk.E).pack(fill=tk.Y, expand=True)
        list_frame = tk.Frame(outer, bg=C["bg_card"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        if not services:
            tk.Label(list_frame, text="暂无服务数据", bg=C["bg_card"],
                    font=("Microsoft YaHei UI", 9), fg=C["text_secondary"]).pack(pady=16)
        else:
            svc_groups = {}
            for svc in services:
                name = svc["service_name"]
                if name not in svc_groups:
                    svc_groups[name] = []
                svc_groups[name].append(svc)
            for svc_name in self.app._ordered_service_names(list(svc_groups)):
                instances = svc_groups[svc_name]
                online_count = sum(1 for i in instances if i["online"])
                total_count = len(instances)
                port = instances[0]["port"]
                svc_frame = tk.Frame(list_frame, bg=C["secondary"], padx=8, pady=3)
                svc_frame.pack(fill=tk.X, pady=(4, 2))
                tk.Label(svc_frame,
                        text=f"{svc_name} ({online_count}/{total_count} 在线) 端口: {port}",
                        bg=C["secondary"], fg=C["text_primary"],
                        font=("Microsoft YaHei UI", 9, "bold"),
                        anchor=tk.W).pack(fill=tk.X)
                for inst in instances:
                    display = self.app._get_display_name(inst["ip"])
                    status = "●" if inst["online"] else "○"
                    tag = "online" if inst["online"] else "offline"
                    lbl = tk.Label(list_frame,
                                  text=f"  {status} {display}",
                                  bg=C["bg_card"], fg=C[tag],
                                  font=("Consolas", 9), anchor=tk.W,
                                  cursor="hand2", padx=8)
                    lbl.pack(fill=tk.X)
                    lbl.bind("<Button-1>", lambda e, s=inst: self._on_service_click(s))
                    lbl.bind("<Enter>", lambda e, l=lbl: l.configure(bg=C["secondary"]))
                    lbl.bind("<Leave>", lambda e, l=lbl: l.configure(bg=C["bg_card"]))
        btn_frame = tk.Frame(outer, bg=C["header_bg"])
        btn_frame.pack(fill=tk.X)
        btns = [
            ("还原窗口", self._on_restore),
            ("设置", self._on_settings),
            ("刷新", self._on_refresh),
            ("退出", self._on_quit),
        ]
        for label, cmd in btns:
            btn = tk.Label(btn_frame, text=label, bg=C["header_bg"],
                           fg=C["header_fg"], font=("Microsoft YaHei UI", 9),
                           padx=8, pady=6, cursor="hand2")
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=C["header_hover_bg"]))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=C["header_bg"]))
        self.window.update_idletasks()
        w = self.window.winfo_reqwidth()
        h = self.window.winfo_reqheight()
        screen_w = self.parent.winfo_screenwidth()
        screen_h = self.parent.winfo_screenheight()
        px = self.parent.winfo_pointerx()
        py = self.parent.winfo_pointery()
        x = px - w // 2
        if x < 0:
            x = 0
        if x + w > screen_w:
            x = screen_w - w
        y = py - h - 8
        if y < 0:
            y = py + 20
        if y + h > screen_h:
            y = screen_h - h - 5
        self.window.geometry(f"+{x}+{y}")
        self.window.bind("<FocusOut>", self._on_focus_out)
        self.window.focus_force()

    def _on_service_click(self, service):
        """点击 IP 行，弹出上线/下线确认"""
        action = "下线" if service["online"] else "上线"
        note = self.app.notes.get(service["ip"], "")
        ip_port = f"{service['ip']}:{service['port']}"
        if note:
            ip_port += f" ({note})"
        msg = f"确定要{action}服务？\n\n{service['service_name']}\n{ip_port}"
        import tkinter.messagebox
        self.window.attributes('-topmost', False)
        if tkinter.messagebox.askyesno("确认" + action, msg, parent=self.parent):
            self._destroy()
            if service["online"]:
                self.app._take_offline(service)
            else:
                self.app._bring_online(service)
        self.window.attributes('-topmost', True)

    def _on_restore(self):
        self._destroy()
        self.app._show_window()

    def _on_settings(self):
        self._destroy()
        self.app._show_settings()

    def _on_refresh(self):
        self._destroy()
        self.app._manual_refresh()

    def _on_quit(self):
        self._destroy()
        self.app.quit()

    def _on_focus_out(self, event):
        self._destroy()

    def _destroy(self):
        if self.window:
            self.window.destroy()
            self.window = None


class NacosTrayApp:
    def __init__(self):
        self.cfg = config.load_config()
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
        self._notified = set()
        self._last_online_time = {}
        self._search_var = None
        self._list_frame = None
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
        self._system_light = theme_mod.system_uses_light()
        COLORS.clear()
        COLORS.update(theme_mod.build_palette(self.cfg))

    def _register_dialog(self, key, window, reopen=None, dialog=None):
        self._dialogs[key] = {"window": window, "reopen": reopen, "dialog": dialog}

    def _unregister_dialog(self, key, window=None):
        entry = self._dialogs.get(key)
        if entry and (window is None or entry.get("window") is window):
            self._dialogs.pop(key, None)

    def _apply_theme(self, cfg=None):
        """立即切换主题：更新语义色后重建主窗口与已打开的子窗口"""
        target = cfg if cfg is not None else self.cfg
        COLORS.clear()
        COLORS.update(theme_mod.build_palette(target))
        dark = COLORS.get("mode") == theme_mod.MODE_DARK
        if self.root:
            self._rebuild_root_ui()
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
        if not self.cfg.get("ip"):
            return False
        self.client = NacosClient(ip=self.cfg["ip"], port=self.cfg.get("port", 8848),
            username=self.cfg.get("username", "nacos"), password=self.cfg.get("password", "nacos"),
            namespace=self.cfg.get("namespace", ""),
            cluster_name=self.cfg.get("cluster_name", "ShenZhen"))
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
        interval = self.cfg.get("login_interval", 1800)
        if time.time() - self._last_login_time >= interval:
            self._do_login()

    def _fetch_services(self):
        if not self._ensure_login():
            return []
        try:
            return self.client.get_all_services_with_status()
        except Exception as e:
            print("Fetch failed: " + str(e))
            if self.client:
                self.client.token = None
            return []

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
        note = self.notes.get(ip, "")
        if note:
            return ip + "(" + note + ")"
        return ip

    def _notify_change(self, event_type, service):
        if service["ip"] in self.dnd:
            return
        svc_name = service["service_name"]
        ip = service["ip"]
        note = self.notes.get(ip, "")
        port = str(service["port"])
        line = svc_name + "[" + port + "] " + ip + ("(" + note + ")" if note else "")
        if event_type == "up":
            title = "服务上线"
            msg = line
            icon = NIIF_INFO
        elif event_type == "offline":
            title = "注意"
            msg = "服务被手动下线！" + chr(10) + line
            icon = NIIF_WARNING
        else:
            title = "服务下线"
            msg = line
            icon = NIIF_ERROR
        self.tray.show_balloon(title, msg, icon)

    def _update_tray_tooltip(self):
        total = len(self.services)
        online = sum(1 for s in self.services if s["online"])
        offline = total - online
        ip = self.cfg.get("ip", "未配置")
        port = self.cfg.get("port", 8848)
        tooltip = "Nacos Tray" + chr(10)
        tooltip += "服务: " + str(total) + " | 在线: " + str(online) + " | 离线: " + str(offline) + chr(10)
        tooltip += "Nacos: " + ip + ":" + str(port)
        self.tray.set_tooltip(tooltip)

    def _build_menu(self):
        items = []
        items.append({"text": "Nacos: " + self.cfg.get("ip", "未配置"), "enabled": False})
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
                    if inst["ip"] in self.dnd:
                        status = "🔇" + status
                    display_name = self._get_display_name(inst["ip"])
                    text = "  " + status + " " + display_name + ":" + str(inst["port"])
                    if inst["online"]:
                        items.append({"text": text, "callback": lambda s=inst: self._take_offline(s)})
                    else:
                        items.append({"text": text, "callback": lambda s=inst: self._bring_online(s)})
                online_count = sum(1 for i in instances if i["online"])
                total_count = len(instances)
                items.append({"text": "  -> " + svc_name + " (" + str(online_count) + "/" + str(total_count) + " 在线)", "enabled": False})
        items.append(None)
        items.append({"text": "还原窗口", "callback": self._show_window})
        items.append({"text": "设置...", "callback": self._show_settings})
        items.append(None)
        items.append({"text": "立即刷新", "callback": self._manual_refresh})
        items.append({"text": "退出", "callback": self.quit})
        self.tray.set_menu_items(items)

    def _take_offline(self, service):
        if not self._ensure_login():
            self.tray.show_balloon("错误", "未连接到 Nacos", NIIF_ERROR)
            return
        try:
            self.client.update_instance_status(service["service_name"], service["ip"], service["port"], enabled=False)
            self.tray.show_balloon("成功", "已下线: " + service["service_name"], NIIF_INFO)
            time.sleep(1)
            self._manual_refresh()
        except Exception as e:
            self.tray.show_balloon("失败", "下线失败: " + str(e), NIIF_ERROR)

    def _bring_online(self, service):
        if not self._ensure_login():
            self.tray.show_balloon("错误", "未连接到 Nacos", NIIF_ERROR)
            return
        try:
            self.client.update_instance_status(service["service_name"], service["ip"], service["port"], enabled=True)
            self.tray.show_balloon("成功", "已上线: " + service["service_name"], NIIF_INFO)
            time.sleep(1)
            self._manual_refresh()
        except Exception as e:
            self.tray.show_balloon("失败", "上线失败: " + str(e), NIIF_ERROR)

    def _show_settings(self, geometry=None, page=None):
        if not self.root:
            return
        entry = self._dialogs.get("settings")
        if entry and entry.get("window") and entry["window"].winfo_exists():
            if page is not None and entry.get("dialog"):
                entry["dialog"]._select_page(page)
            entry["window"].lift()
            entry["window"].focus_force()
            return

        def on_save(new_cfg):
            self.cfg = new_cfg
            self._view_mode = new_cfg.get("view_mode", "table")
            if self._view_mode not in ("table", "card"):
                self._view_mode = "table"
            self._apply_theme()
            self._init_client()
            self._do_login()
            self._manual_refresh()
            self._ensure_theme_poll()

        SettingsDialog(self.root, self.cfg, on_save=on_save, app=self,
                       geometry=geometry, page=page)

    def _get_all_ips(self):
        ips = set()
        for svc in self.services:
            ips.add(svc["ip"])
        return sorted(ips)

    def _show_notes(self, geometry=None):
        self._show_settings(page=SettingsDialog.PAGE_NOTES)

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
        """显示服务列表弹窗"""
        if not self.root:
            return
        ServiceListPopup(self.root, self)

    def _manual_refresh(self):
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
        if services:
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
            self._update_window()
        local_ips = _get_local_ips()
        changed = False
        for ip in local_ips:
            if ip not in self.notes:
                self.notes[ip] = "本机"
                changed = True
        if changed:
            config.save_notes(self.notes)

    def _update_window(self):
        if not self.root:
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
        self._hide_tooltip()
        self._hover_table_item = None
        tree.delete(*tree.get_children())
        pins = self.cfg.get("pinned_services") or []
        striped = bool(self.cfg.get("table_striped", True))
        row_idx = 0
        for svc_name, instances in groups:
            pin_mark = "★" if svc_name in pins else "☆"
            for inst in instances:
                status = "[在线]" if inst["online"] else "[离线]"
                if inst["ip"] in self.dnd:
                    status = "🔇" + status
                display_name = self._get_display_name(inst["ip"])
                last_key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
                last_time = self._last_online_time.get(last_key, "-")
                tag = "online" if inst["online"] else "offline"
                if striped and row_idx % 2 == 1:
                    tag = (tag, "alt")
                tree.insert("", "end",
                            values=(pin_mark, svc_name, display_name, str(inst["port"]), status, last_time),
                            tags=tag)
                row_idx += 1

    def _poll_once(self):
        if not self.running:
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
        import tkinter as tk
        if hasattr(self, "_progress_bar") and self._progress_bar:
            self._progress_bar.pack(fill=tk.X, padx=16, pady=(2, 0), before=self._progress_before)
            self._progress_bar.start(10)

    def _hide_progress(self):
        if hasattr(self, "_progress_bar") and self._progress_bar:
            self._progress_bar.stop()
            self._progress_bar.pack_forget()

    def _on_poll_data(self, services):
        if not self.running:
            self._poll_in_progress = False
            self._hide_progress()
            self._schedule_poll()
            return
        self._hide_progress()
        try:
            if services:
                self._last_refresh_time = time.strftime("%Y-%m-%d %H:%M:%S")
                with self._lock:
                    self.services = services
                changes = self._detect_changes(services)
                for event_type, svc in changes:
                    self._notify_change(event_type, svc)
                self._update_tray_tooltip()
                self._build_menu()
                self._update_window()
        except Exception as e:
            print("Poll UI update error: " + str(e))
        self._poll_in_progress = False
        self._schedule_poll()

    def _schedule_poll(self):
        if self.running and self.root:
            try:
                self.root.after(self.cfg.get("poll_interval", 30) * 1000, self._poll_once)
            except:
                pass

    def _create_window(self):
        import tkinter as tk
        self.root = tk.Tk()
        _set_icon(self.root)
        self.root.title("Nacos Tray - 服务状态监控与通知 " + APP_VERSION)
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
        if self._context_menu:
            try:
                self._context_menu.destroy()
            except Exception:
                pass
            self._context_menu = None
        for child in self.root.winfo_children():
            if child.winfo_class() == "Toplevel":
                continue
            child.destroy()
        self._build_root_ui()

    def _build_root_ui(self):
        import tkinter as tk
        from tkinter import ttk
        self.root.configure(bg=COLORS["bg_main"])
        theme_mod.apply_ttk_style(self.root, COLORS, self._table_row_height())
        main_frame = ttk.Frame(self.root, padding=0)
        main_frame.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(main_frame, bg=COLORS["header_bg"], height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        ip_text = self.cfg.get("ip", "未配置")
        port_text = str(self.cfg.get("port", 8848))
        title_label = tk.Label(header, text=f" Nacos: {ip_text}:{port_text}",
                               bg=COLORS["header_bg"], fg=COLORS["header_fg"],
                               font=("Microsoft YaHei UI", 12, "bold"),
                               padx=16)
        title_label.pack(side=tk.LEFT, fill=tk.Y)
        right_frame = tk.Frame(header, bg=COLORS["header_bg"])
        right_frame.pack(side=tk.RIGHT, padx=14)
        use_icon = _icon_font_available(self.root)
        gear = tk.Label(right_frame,
                        text=_ICON_GLYPHS["settings"] if use_icon else "设置",
                        bg=COLORS["header_bg"], fg=COLORS["header_fg"],
                        font=(_ICON_FONT, 15) if use_icon else ("Microsoft YaHei UI", 9),
                        padx=10, pady=6, cursor="hand2")
        gear.pack()
        gear.bind("<Button-1>", lambda e: self._on_settings_click())
        gear.bind("<Enter>", lambda e, w=gear: w.configure(bg=COLORS["header_hover_bg"]))
        gear.bind("<Leave>", lambda e, w=gear: w.configure(bg=COLORS["header_bg"]))
        tk.Frame(main_frame, bg=COLORS["separator"], height=1).pack(fill=tk.X)
        self._progress_bar = ttk.Progressbar(main_frame, mode="indeterminate")
        self._progress_before = search_frame = tk.Frame(main_frame, bg=COLORS["bg_main"])
        search_frame.pack(fill=tk.X, padx=16, pady=(6, 4))
        tk.Label(search_frame, text="🔍", bg=COLORS["bg_main"],
                fg=COLORS["text_secondary"],
                font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT)
        if self._search_var is None:
            self._search_var = tk.StringVar()
            self._search_var.trace_add("write", lambda *a: self._update_window())
        search_entry = ttk.Entry(search_frame, textvariable=self._search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=(4, 0))
        self._list_frame = ttk.Frame(main_frame)
        self._list_frame.pack(fill=tk.BOTH, expand=True)
        self._build_list_view()
        status_frame = tk.Frame(main_frame, bg=COLORS["bg_main"])
        status_frame.pack(fill=tk.X, padx=16, pady=(0, 10))
        self._status_var = tk.StringVar(value="就绪")
        self._status_dot = tk.Label(status_frame, text="●", bg=COLORS["bg_main"],
                                     fg=COLORS["text_secondary"],
                                     font=("Microsoft YaHei UI", 10))
        self._status_dot.pack(side=tk.LEFT)
        self._status_label = tk.Label(status_frame, textvariable=self._status_var,
                                      bg=COLORS["bg_main"], fg=COLORS["text_secondary"],
                                      font=("Microsoft YaHei UI", 9),
                                      anchor=tk.W)
        self._status_label.pack(side=tk.LEFT, padx=(4, 0))
        self._build_context_menu()
        self._bind_shortcuts()
        self.root.bind("<MouseWheel>", self._on_cards_wheel)
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._update_window()

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
            (shortcuts.get("refresh", "F5"), self._on_refresh_click),
            (shortcuts.get("toggle_view", "Control-Tab"), self._toggle_view_mode),
            (shortcuts.get("open_settings", "Control-comma"), self._on_settings_click),
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
        if self._view_mode == "card":
            self._build_card_view()
        else:
            self._build_table_view()

    def _build_table_view(self):
        import tkinter as tk
        from tkinter import ttk
        list_frame = self._list_frame
        columns = ("pin", "service", "instance", "port", "status", "last_online")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("pin", text="置顶")
        tree.heading("service", text="服务名")
        tree.heading("instance", text="实例")
        tree.heading("port", text="端口")
        tree.heading("status", text="状态")
        tree.heading("last_online", text="最近上线时间")
        tree.column("pin", width=46, anchor=tk.CENTER, stretch=False)
        tree.column("service", width=170)
        tree.column("instance", width=190)
        tree.column("port", width=55, anchor=tk.CENTER)
        tree.column("status", width=75, anchor=tk.CENTER)
        tree.column("last_online", width=165)
        tree.tag_configure("online", foreground=COLORS["online"])
        tree.tag_configure("offline", foreground=COLORS["offline"])
        tree.tag_configure("alt", background=COLORS["bg_row_alt"])
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.bind("<Button-1>", self._on_tree_click)
        tree.bind("<Button-3>", self._show_context_menu)
        tree.bind("<Double-1>", self._on_double_click)
        tree.bind("<Motion>", self._on_tree_motion)
        tree.bind("<Leave>", self._on_tree_leave)
        self._service_tree = tree

    def _build_card_view(self):
        import tkinter as tk
        from tkinter import ttk
        list_frame = self._list_frame
        canvas = tk.Canvas(list_frame, bg=COLORS["bg_main"], highlightthickness=0, bd=0,
                           yscrollincrement=20)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
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
                    cols = 3
                cols = max(1, min(3, min(cols, fit)))
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
        star = tk.Label(head, text="☆", bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                        font=("Microsoft YaHei UI", 11), cursor="hand2", padx=4)
        star.pack(side=tk.RIGHT)
        star.bind("<Button-1>", lambda e, n=svc_name: self._toggle_pin(n))
        sub = tk.Label(card, text="", bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                       font=("Microsoft YaHei UI", 8), anchor=tk.W,
                       justify=tk.LEFT, wraplength=300)
        sub.pack(fill=tk.X, padx=10, pady=(0, 4))
        line = tk.Frame(card, bg=COLORS["separator"], height=1)
        line.pack(fill=tk.X, padx=10)
        rows = tk.Frame(card, bg=COLORS["bg_card"])
        rows.pack(fill=tk.X, padx=2, pady=(2, 8))
        state = {"frame": card, "star": star, "sub": sub, "line": line, "rows": rows,
                 "rows_map": {}, "order": [], "sub_visible": True}
        self._card_states[svc_name] = state
        for w in (card, head, title, sub, line, rows, star):
            w.bind("<Button-3>", lambda e, n=svc_name: self._show_card_context_menu(e, n, None))
            self._bind_card_hover(w, svc_name, card)
        return state

    def _create_card_row(self, state, svc_name, inst):
        import tkinter as tk
        row = tk.Frame(state["rows"], bg=COLORS["bg_card"], cursor="hand2")
        dot = tk.Label(row, text="●", bg=COLORS["bg_card"], font=("Microsoft YaHei UI", 8), width=2)
        dot.pack(side=tk.LEFT)
        name = tk.Label(row, text="", bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                        font=("Consolas", 9), anchor=tk.W, width=24)
        name.pack(side=tk.LEFT, fill=tk.X, expand=True)
        when = tk.Label(row, text="", bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                        font=("Microsoft YaHei UI", 8), anchor=tk.E)
        when.pack(side=tk.RIGHT, padx=(6, 8))
        row.pack(fill=tk.X, pady=1)
        row_state = {"row": row, "dot": dot, "name": name, "when": when, "svc": inst,
                     "when_visible": True}
        for w in (row, dot, name, when):
            w.bind("<Button-1>", lambda e, rs=row_state: self._confirm_toggle_instance(rs["svc"]))
            w.bind("<Button-3>", lambda e, n=svc_name, rs=row_state: self._show_card_context_menu(e, n, rs["svc"]))
            self._bind_card_hover(w, svc_name, state["frame"])
        return row_state

    def _sync_card(self, svc_name, instances):
        import tkinter as tk
        state = self._ensure_card(svc_name)
        pins = self.cfg.get("pinned_services") or []
        pinned = svc_name in pins
        state["star"].configure(text="★" if pinned else "☆",
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
        if ordered_keys != state["order"]:
            state["order"] = ordered_keys
            for key in ordered_keys:
                row = state["rows_map"].get(key)
                if row:
                    row["row"].pack_forget()
                    row["row"].pack(fill=tk.X, pady=1)

    def _update_card_row(self, row, inst, fields=None):
        import tkinter as tk
        if fields is None:
            fields = self._card_fields()
        online = inst["online"]
        color = COLORS["online"] if online else COLORS["offline"]
        row["svc"] = inst
        row["dot"].configure(fg=color)
        display = self._get_display_name(inst["ip"]) if fields["note"] else inst["ip"]
        if fields["dnd"] and inst["ip"] in self.dnd:
            display = "[勿扰] " + display
        row["name"].configure(text=display, fg=color)
        show_when = fields["last_online"] and not self._cards_compact
        if show_when:
            last_key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
            row["when"].configure(text=self._last_online_time.get(last_key, "-"))
            if not row["when_visible"]:
                row["when"].pack(side=tk.RIGHT, padx=(6, 8))
                row["when_visible"] = True
        elif row["when_visible"]:
            row["when"].pack_forget()
            row["when_visible"] = False

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

    def _on_tree_motion(self, event):
        tree = self._service_tree
        if not tree:
            return
        item = tree.identify_row(event.y)
        if item == self._hover_table_item:
            return
        self._hover_table_item = item
        if not item:
            self._cancel_hover_job()
            self._hide_tooltip()
            return
        values = tree.item(item, "values")
        if len(values) < 2:
            self._cancel_hover_job()
            self._hide_tooltip()
            return
        svc_name = str(values[1])
        if svc_name == self._hover_service:
            return
        self._hide_tooltip()
        self._schedule_service_tooltip(svc_name, tree)

    def _on_tree_leave(self, event=None):
        self._hover_table_item = None
        self._cancel_hover_job()
        self._hide_tooltip()

    def _bind_card_hover(self, widget, svc_name, anchor):
        widget.bind("<Enter>",
                    lambda e, n=svc_name, a=anchor: self._schedule_service_tooltip(n, a),
                    add="+")
        widget.bind("<Leave>", lambda e, a=anchor: self._leave_hover(a), add="+")

    def _pointer_in_widget(self, widget):
        try:
            x, y = self.root.winfo_pointerxy()
            return (widget.winfo_rootx() <= x <= widget.winfo_rootx() + widget.winfo_width()
                    and widget.winfo_rooty() <= y <= widget.winfo_rooty() + widget.winfo_height())
        except Exception:
            return False

    def _schedule_service_tooltip(self, svc_name, anchor):
        self._cancel_hover_job()
        self._hover_service = svc_name
        self._hover_job = self.root.after(400, lambda: self._show_service_tooltip(svc_name, anchor))

    def _leave_hover(self, anchor):
        if self._pointer_in_widget(anchor):
            return
        self._cancel_hover_job()
        self._hide_tooltip()

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
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=COLORS["separator"])
        outer = tk.Frame(top, bg=COLORS["bg_card"])
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        inner = tk.Frame(outer, bg=COLORS["bg_card"])
        inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        pinned = svc_name in (self.cfg.get("pinned_services") or [])
        title_text = ("★ " if pinned else "") + svc_name
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
        tk.Frame(inner, bg=COLORS["separator"], height=1).pack(fill=tk.X, pady=(6, 4))
        context = ("Nacos " + str(self.cfg.get("ip", "-")) + ":" + str(self.cfg.get("port", 8848))
                   + " · 命名空间 " + (self.cfg.get("namespace") or "默认")
                   + " · 集群 " + (self.cfg.get("cluster_name") or "-"))
        if self._last_refresh_time:
            context += " · 更新 " + self._last_refresh_time
        tk.Label(inner, text=context, bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=("Microsoft YaHei UI", 8), anchor=tk.W,
                 justify=tk.LEFT, wraplength=420).pack(fill=tk.X)
        top.update_idletasks()
        width = top.winfo_reqwidth()
        height = top.winfo_reqheight()
        px, py = self.root.winfo_pointerxy()
        screen_w = top.winfo_screenwidth()
        screen_h = top.winfo_screenheight()
        x = px + 18
        if x + width > screen_w - 8:
            x = px - width - 18
        y = py + 18
        if y + height > screen_h - 8:
            y = screen_h - height - 8
        top.geometry("+" + str(max(4, x)) + "+" + str(max(4, y)))
        self._hover_window = top
        self._hover_service = svc_name

    def _build_tooltip_instance(self, parent, inst):
        import tkinter as tk
        online = inst["online"]
        color = COLORS["online"] if online else COLORS["offline"]
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=(0, 3))
        tk.Label(row, text="●", bg=COLORS["bg_card"], fg=color,
                 font=("Microsoft YaHei UI", 8)).pack(side=tk.LEFT)
        ip_text = inst["ip"] + ":" + str(inst["port"])
        note = self.notes.get(inst["ip"], "")
        if note:
            ip_text += "  " + note
        tk.Label(row, text=ip_text, bg=COLORS["bg_card"], fg=color,
                 font=("Consolas", 9), anchor=tk.W).pack(side=tk.LEFT, padx=(4, 0))
        if inst["ip"] in self.dnd:
            tk.Label(row, text="免打扰", bg=COLORS["bg_card"], fg=COLORS["warning"],
                     font=("Microsoft YaHei UI", 8)).pack(side=tk.RIGHT)
        states = []
        if not inst.get("enabled", True):
            states.append("已禁用")
        elif not inst.get("healthy", True):
            states.append("不健康")
        else:
            states.append("在线" if online else "离线")
        last_key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
        states.append("最近上线 " + self._last_online_time.get(last_key, "-"))
        weight = inst.get("weight")
        if weight is not None:
            states.append("权重 " + str(weight))
        cluster = inst.get("cluster_name")
        if cluster:
            states.append("集群 " + str(cluster))
        ephemeral = inst.get("ephemeral")
        if ephemeral is not None:
            states.append("临时实例" if ephemeral else "持久实例")
        metadata = inst.get("metadata") or {}
        if isinstance(metadata, dict) and metadata:
            items = list(metadata.items())[:6]
            meta_text = ", ".join(str(k) + "=" + str(v) for k, v in items)
            if len(metadata) > 6:
                meta_text += ", ..."
            states.append("元数据 " + meta_text)
        tk.Label(parent, text=" · ".join(states), bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"], font=("Microsoft YaHei UI", 8),
                 anchor=tk.W, justify=tk.LEFT, wraplength=420).pack(
            fill=tk.X, padx=(12, 0), pady=(0, 4))

    def _confirm_toggle_instance(self, svc):
        if not svc:
            return
        self._hide_tooltip()
        from tkinter import messagebox
        action = "下线" if svc["online"] else "上线"
        note = self.notes.get(svc["ip"], "")
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

    def _build_context_menu(self):
        import tkinter as tk
        self._context_menu = tk.Menu(self.root, tearoff=0)
        self._context_menu.add_command(label="上线", command=self._ctx_online)
        self._context_menu.add_command(label="下线", command=self._ctx_offline)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="置顶服务", command=self._ctx_toggle_pin)
        self._context_menu.add_command(label="管理备注...", command=self._ctx_set_note)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="免打扰", command=self._ctx_toggle_dnd)
        self._context_menu.add_command(label="刷新", command=self._on_refresh_click)

    def _prepare_context_menu(self, svc_name, svc):
        import tkinter as tk
        self._menu_service = svc
        self._menu_service_name = svc_name
        pins = self.cfg.get("pinned_services") or []
        self._context_menu.entryconfigure(3, label="取消置顶" if svc_name in pins else "置顶服务")
        state = tk.NORMAL if svc else tk.DISABLED
        self._context_menu.entryconfigure(0, state=state)
        self._context_menu.entryconfigure(1, state=state)
        if svc:
            label = "取消免打扰" if svc["ip"] in self.dnd else "免打扰"
            self._context_menu.entryconfigure(6, label=label, state=tk.NORMAL)
        else:
            self._context_menu.entryconfigure(6, label="免打扰", state=tk.DISABLED)

    def _show_card_context_menu(self, event, svc_name, svc):
        if not self._context_menu:
            return
        self._prepare_context_menu(svc_name, svc)
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    def _on_tree_click(self, event):
        tree = self._service_tree
        if not tree:
            return
        if tree.identify_region(event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#1":
            return
        item = tree.identify_row(event.y)
        if not item:
            return
        values = tree.item(item, "values")
        if len(values) < 2:
            return
        tree.selection_set(item)
        self._toggle_pin(str(values[1]))
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
        svc = self._get_selected_service()
        if not svc:
            return
        self._prepare_context_menu(svc["service_name"], svc)
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    def _get_selected_service(self):
        if not self._service_tree:
            return None
        selection = self._service_tree.selection()
        if not selection:
            return None
        values = self._service_tree.item(selection[0])["values"]
        if not values or len(values) < 5:
            return None
        svc_name = values[1]
        instance_text = values[2]
        port = int(values[3])
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
        ip = svc["ip"]
        if ip in self.dnd:
            del self.dnd[ip]
        else:
            self.dnd[ip] = True
        config.save_dnd(self.dnd)
        self._update_window()

    def _on_double_click(self, event):
        if self._service_tree.identify_column(event.x) == "#1":
            return "break"
        svc = self._get_selected_service()
        if svc:
            if svc["online"]:
                self._take_offline(svc)
            else:
                self._bring_online(svc)

    def run(self):
        self.running = True
        self._create_window()
        self.tray = TrayIcon(tooltip="Nacos Tray - 服务监控\n双击显示主窗口", tk_root=self.root)
        self.tray.callbacks["double_click"] = self._show_window
        self.tray.set_tooltip("Nacos Tray - 服务监控\n双击显示主窗口")
        self.tray.set_popup_callback(self._show_service_list_popup)
        self.tray.start()
        if self.cfg.get("ip"):
            self._init_client()
            self._do_login()
        else:
            self.tray.set_tooltip("Nacos Tray - 请配置")
            self.tray.show_balloon("提示", "请在设置中配置 Nacos 连接", NIIF_INFO)
        self.root.after(2000, self._manual_refresh)
        self._schedule_poll()
        self._ensure_theme_poll()
        print("Nacos Tray started")
        if self.root:
            self.root.mainloop()
        self.quit()

    def quit(self):
        print("Nacos Tray exiting...")
        self.running = False
        self.tray.stop()
        if self.root:
            try:
                self.root.destroy()
            except:
                pass


def main():
    try:
        app = NacosTrayApp()
        app.run()
    except Exception as e:
        tb = traceback.format_exc()
        show_error(tb)


if __name__ == "__main__":
    main()