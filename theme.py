# theme.py - 明暗主题：配色预设、自定义派生、系统检测、ttk 样式与标题栏
import ctypes
import re

MODE_SYSTEM = "system"
MODE_LIGHT = "light"
MODE_DARK = "dark"
MODE_OPTIONS = [(MODE_SYSTEM, "跟随系统"), (MODE_LIGHT, "亮色"), (MODE_DARK, "暗色")]

CUSTOM_ID = "custom"
CUSTOM_NAME = "自定义"
DEFAULT_PRESET = "qinglan"
DEFAULT_CUSTOM = {"light": "#F0F8FF", "dark": "#2B2B2B"}

# 状态色只区分明暗，不随预设变化
STATUS_COLORS = {
    MODE_LIGHT: {"online": "#009639", "offline": "#FF5252", "warning": "#FF9800"},
    MODE_DARK: {"online": "#4ADE80", "offline": "#FF7B72", "warning": "#FFB74D"},
}

PRESETS = {
    "qinglan": {
        "name": "青蓝",
        "light": {
            "primary": "#0096B7", "primary_dark": "#007A96", "primary_darker": "#00647A",
            "secondary": "#90E0EF", "bg_main": "#F0F8FF", "bg_card": "#FFFFFF",
            "bg_row_alt": "#F5FBFD", "text_primary": "#1A2A3A", "text_secondary": "#57707D",
            "separator": "#E0E0E0", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#0096B7", "primary_dark": "#26C9E8", "primary_darker": "#5FD8EF",
            "secondary": "#123240", "bg_main": "#0F1B24", "bg_card": "#16242F",
            "bg_row_alt": "#1B2B38", "text_primary": "#E6F4F8", "text_secondary": "#9DB4C0",
            "separator": "#243642", "header_text": "#FFFFFF",
        },
    },
    "haiLan": {
        "name": "海蓝",
        "light": {
            "primary": "#2F6FED", "primary_dark": "#2558C0", "primary_darker": "#1E4A9E",
            "secondary": "#DBEAFE", "bg_main": "#F5F7FA", "bg_card": "#FFFFFF",
            "bg_row_alt": "#FAFCFF", "text_primary": "#1F2937", "text_secondary": "#5B6472",
            "separator": "#E3E8EF", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#4C8DFF", "primary_dark": "#6BA3FF", "primary_darker": "#8BB9FF",
            "secondary": "#172A4A", "bg_main": "#0B1220", "bg_card": "#121A2B",
            "bg_row_alt": "#172136", "text_primary": "#E2E8F0", "text_secondary": "#94A3B8",
            "separator": "#1E2A42", "header_text": "#FFFFFF",
        },
    },
    "huiLu": {
        "name": "灰绿",
        "light": {
            "primary": "#16A34A", "primary_dark": "#128A3E", "primary_darker": "#0F7033",
            "secondary": "#DCFCE7", "bg_main": "#F5F6F7", "bg_card": "#FFFFFF",
            "bg_row_alt": "#FAFBFC", "text_primary": "#2B2F33", "text_secondary": "#5F6B73",
            "separator": "#E5E7EB", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#2EA043", "primary_dark": "#3FB950", "primary_darker": "#56D36B",
            "secondary": "#12351F", "bg_main": "#0D1117", "bg_card": "#161B22",
            "bg_row_alt": "#1C2128", "text_primary": "#E6EDF3", "text_secondary": "#8B949E",
            "separator": "#21262D", "header_text": "#FFFFFF",
        },
    },
    "mihuang": {
        "name": "护眼米黄",
        "light": {
            "primary": "#268BD2", "primary_dark": "#1E6FA8", "primary_darker": "#175A88",
            "secondary": "#E8E0C8", "bg_main": "#FDF6E3", "bg_card": "#FFFBF0",
            "bg_row_alt": "#F5EEDC", "text_primary": "#586E75", "text_secondary": "#5F7480",
            "separator": "#EEE8D5", "header_text": "#FDF6E3",
        },
        "dark": {
            "primary": "#268BD2", "primary_dark": "#3AA0E0", "primary_darker": "#5FB4EC",
            "secondary": "#0E4451", "bg_main": "#002B36", "bg_card": "#073642",
            "bg_row_alt": "#0B3C49", "text_primary": "#EEE8D5", "text_secondary": "#93A1A1",
            "separator": "#14404C", "header_text": "#FDF6E3",
        },
    },
    "dousha": {
        "name": "护眼豆沙绿",
        "light": {
            "primary": "#2E7D32", "primary_dark": "#246129", "primary_darker": "#1B4A20",
            "secondary": "#B7E0BC", "bg_main": "#C7EDCC", "bg_card": "#DDF3E0",
            "bg_row_alt": "#D2F0D7", "text_primary": "#1F3B28", "text_secondary": "#4A6452",
            "separator": "#ACDDB0", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#3E9B43", "primary_dark": "#4CAF50", "primary_darker": "#66BB6A",
            "secondary": "#1F3D28", "bg_main": "#10241A", "bg_card": "#17301F",
            "bg_row_alt": "#1C3826", "text_primary": "#D6F0DC", "text_secondary": "#92B39B",
            "separator": "#26462F", "header_text": "#FFFFFF",
        },
    },
    "shimo": {
        "name": "石墨灰",
        "light": {
            "primary": "#007ACC", "primary_dark": "#0062A3", "primary_darker": "#004D80",
            "secondary": "#E8F1FA", "bg_main": "#F7F7F7", "bg_card": "#FFFFFF",
            "bg_row_alt": "#F2F2F2", "text_primary": "#1F1F1F", "text_secondary": "#636363",
            "separator": "#E0E0E0", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#3794FF", "primary_dark": "#5AA7FF", "primary_darker": "#7DBAFF",
            "secondary": "#383838", "bg_main": "#2B2B2B", "bg_card": "#333333",
            "bg_row_alt": "#2F2F2F", "text_primary": "#E8E8E8", "text_secondary": "#B0B0B0",
            "separator": "#3C3C3C", "header_text": "#FFFFFF",
        },
    },
    "wuye": {
        "name": "午夜蓝紫",
        "light": {
            "primary": "#5C6BC0", "primary_dark": "#4A58A8", "primary_darker": "#3B478A",
            "secondary": "#E8EBF5", "bg_main": "#F7F8FC", "bg_card": "#FFFFFF",
            "bg_row_alt": "#F2F4FA", "text_primary": "#23263A", "text_secondary": "#5C6180",
            "separator": "#E2E5EF", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#82AAFF", "primary_dark": "#9DBCFF", "primary_darker": "#B8CEFF",
            "secondary": "#383E56", "bg_main": "#292D3E", "bg_card": "#31364A",
            "bg_row_alt": "#2D3144", "text_primary": "#E7E9F3", "text_secondary": "#A6ACCD",
            "separator": "#3A4058", "header_text": "#0F1320",
        },
    },
    "chunhei": {
        "name": "纯黑",
        "light": {
            "primary": "#0096B7", "primary_dark": "#007A96", "primary_darker": "#00647A",
            "secondary": "#CFEFF7", "bg_main": "#FAFAFA", "bg_card": "#FFFFFF",
            "bg_row_alt": "#F5F5F5", "text_primary": "#1C1C1C", "text_secondary": "#6B6B6B",
            "separator": "#E5E5E5", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#4DD0E1", "primary_dark": "#6FDDEB", "primary_darker": "#92E8F2",
            "secondary": "#10333A", "bg_main": "#000000", "bg_card": "#0B0B0B",
            "bg_row_alt": "#121212", "text_primary": "#F5F5F5", "text_secondary": "#9E9E9E",
            "separator": "#262626", "header_text": "#0B0B0B",
        },
    },
}

PRESET_ORDER = ["qinglan", "haiLan", "huiLu", "mihuang", "dousha", "shimo", "wuye", "chunhei"]

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_valid_hex(value):
    return bool(_HEX_RE.match((value or "").strip()))


def normalize_hex(value, fallback):
    text = (value or "").strip()
    if _HEX_RE.match(text):
        return "#" + text[1:].upper()
    return fallback


def _rgb(hex_color):
    return (int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16))


def _hex(rgb):
    return "#%02X%02X%02X" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def blend(base, other, ratio):
    """按比例把 other 混入 base，ratio 0 到 1"""
    a = _rgb(base)
    b = _rgb(other)
    return _hex(tuple(a[i] + (b[i] - a[i]) * ratio for i in range(3)))


def luminance(hex_color):
    """WCAG 相对亮度"""
    channels = []
    for value in _rgb(hex_color):
        c = value / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(color_a, color_b):
    """WCAG 对比度，1 到 21"""
    la = luminance(color_a)
    lb = luminance(color_b)
    high = max(la, lb)
    low = min(la, lb)
    return (high + 0.05) / (low + 0.05)


def readable_text(bg):
    """在给定背景上取黑或白文字，优先满足 4.5:1"""
    if contrast("#1A1A1A", bg) >= contrast("#FFFFFF", bg):
        return "#1A1A1A"
    return "#FFFFFF"


def ensure_contrast(color, bg, target):
    """朝黑或白微调颜色，直到对背景达到目标对比度"""
    if contrast(color, bg) >= target:
        return color
    light_bg = luminance(bg) > 0.35
    toward = "#000000" if light_bg else "#FFFFFF"
    current = color
    for step in range(1, 21):
        current = blend(color, toward, step * 0.05)
        if contrast(current, bg) >= target:
            return current
    return current


def system_uses_light():
    """读取 Windows 应用主题，失败时按亮色处理"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0, winreg.KEY_READ,
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return True


def resolve_mode(cfg):
    mode = cfg.get("theme_mode", MODE_SYSTEM)
    if mode == MODE_LIGHT:
        return MODE_LIGHT
    if mode == MODE_DARK:
        return MODE_DARK
    return MODE_LIGHT if system_uses_light() else MODE_DARK


def _custom_palette(cfg, mode):
    custom = cfg.get("theme_custom") or {}
    bg_main = normalize_hex(custom.get(mode), DEFAULT_CUSTOM[mode])
    light_bg = luminance(bg_main) > 0.35
    accent_id = cfg.get("theme_custom_accent", DEFAULT_PRESET)
    accent_source = PRESETS.get(accent_id) or PRESETS[DEFAULT_PRESET]
    primary = ensure_contrast(accent_source[mode]["primary"], bg_main, 3.0)
    text_primary = ensure_contrast("#1B1B1B" if light_bg else "#EDEDED", bg_main, 4.5)
    text_secondary = ensure_contrast(blend(text_primary, bg_main, 0.30), bg_main, 4.5)
    bg_card = blend(bg_main, "#FFFFFF", 0.06 if light_bg else 0.05)
    bg_row_alt = blend(bg_main, "#000000", 0.02) if light_bg else blend(bg_main, "#FFFFFF", 0.025)
    toward = "#000000" if light_bg else "#FFFFFF"
    return {
        "primary": primary,
        "primary_dark": blend(primary, toward, 0.15),
        "primary_darker": blend(primary, toward, 0.25),
        "secondary": blend(bg_main, primary, 0.16),
        "bg_main": bg_main,
        "bg_card": bg_card,
        "bg_row_alt": bg_row_alt,
        "text_primary": text_primary,
        "text_secondary": text_secondary,
        "separator": blend(bg_main, text_primary, 0.16),
        "header_text": readable_text(primary),
    }


def _header_tokens(palette):
    """顶部条取色：亮色用强调色填充，暗色用深色表面加强调色文字"""
    if palette["mode"] == MODE_DARK:
        header_bg = palette["bg_card"]
        header_fg = ensure_contrast(palette["primary"], header_bg, 4.5)
        header_hover = palette["secondary"]
    else:
        header_bg = palette["primary"]
        header_fg = palette["header_text"]
        header_hover = palette["primary_dark"]
    return header_bg, header_fg, header_hover


def build_palette(cfg):
    """按配置生成当前生效的语义色"""
    mode = resolve_mode(cfg)
    preset_id = cfg.get("theme_preset", DEFAULT_PRESET)
    if preset_id == CUSTOM_ID:
        palette = _custom_palette(cfg, mode)
    else:
        preset = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET]
        palette = dict(preset[mode])
    palette.update(STATUS_COLORS[mode])
    palette["mode"] = mode
    palette["preset"] = preset_id
    header_bg, header_fg, header_hover = _header_tokens(palette)
    palette["header_bg"] = header_bg
    palette["header_fg"] = header_fg
    palette["header_hover_bg"] = header_hover
    palette["selection_bg"] = blend(palette["bg_card"], palette["primary"], 0.18)
    return palette


def preset_preview(preset_id, mode):
    """取某预设某明暗下的语义色，供界面预览"""
    preset = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET]
    return preset[mode]


def apply_ttk_style(root, palette, row_height=28):
    """配置 ttk 样式：亮色用 vista 原生外观，暗色用 clam 重绘"""
    from tkinter import ttk
    style = ttk.Style(root)
    dark = palette["mode"] == MODE_DARK
    bg = palette["bg_main"]
    card = palette["bg_card"]
    text = palette["text_primary"]
    text_sub = palette["text_secondary"]
    sub = palette["secondary"]
    sep = palette["separator"]
    primary = palette["primary"]
    header_text = palette["header_text"]
    font = ("Microsoft YaHei UI", 9)

    if not dark and "vista" in style.theme_names():
        style.theme_use("vista")

    if dark and "clam" in style.theme_names():
        style.theme_use("clam")
        style.configure(".", background=bg, foreground=text, fieldbackground=card)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("TLabelframe", background=bg, bordercolor=sep, lightcolor=bg, darkcolor=bg)
        style.configure("TLabelframe.Label", background=bg, foreground=text)
        style.configure("TButton", background=sub, foreground=text, bordercolor=sep,
                        lightcolor=sub, darkcolor=sub, focuscolor=sub, padding=(10, 4))
        style.map("TButton",
                  background=[("active", primary), ("pressed", palette["primary_dark"])],
                  foreground=[("active", header_text), ("pressed", header_text)])
        style.configure("TEntry", fieldbackground=card, foreground=text, insertcolor=text,
                        bordercolor=sep, lightcolor=card, darkcolor=card)
        style.configure("TCheckbutton", background=bg, foreground=text)
        style.map("TCheckbutton", background=[("active", bg)])
        style.configure("TCombobox", fieldbackground=card, background=sub, foreground=text,
                        arrowcolor=text, bordercolor=sep)
        style.map("TCombobox",
                  fieldbackground=[("readonly", card)],
                  foreground=[("readonly", text)])
        style.configure("Vertical.TScrollbar", background=blend(bg, text, 0.25), troughcolor=bg,
                        bordercolor=bg, arrowcolor=text_sub,
                        lightcolor=blend(bg, text, 0.25), darkcolor=blend(bg, text, 0.25), gripcount=0)
        style.configure("Horizontal.TScrollbar", background=blend(bg, text, 0.25), troughcolor=bg,
                        bordercolor=bg, arrowcolor=text_sub,
                        lightcolor=blend(bg, text, 0.25), darkcolor=blend(bg, text, 0.25), gripcount=0)
        style.configure("TNotebook", background=bg, bordercolor=sep,
                        lightcolor=bg, darkcolor=bg)
        style.configure("TNotebook.Tab", background=sub, foreground=text, padding=(14, 5),
                        lightcolor=sub, darkcolor=sub)
        style.map("TNotebook.Tab",
                  background=[("selected", card)],
                  foreground=[("selected", text)],
                  lightcolor=[("selected", card)],
                  darkcolor=[("selected", card)])
        style.configure("TProgressbar", background=primary, troughcolor=card, bordercolor=sep)
        style.configure("TSeparator", background=sep)
        root.option_add("*TCombobox*Listbox.background", card)
        root.option_add("*TCombobox*Listbox.foreground", text)
        root.option_add("*TCombobox*Listbox.selectBackground", primary)
        root.option_add("*TCombobox*Listbox.selectForeground", header_text)

    style.configure("Treeview", background=card, fieldbackground=card, foreground=text,
                    font=font, rowheight=row_height, bordercolor=sep, lightcolor=card, darkcolor=card)
    style.configure("Treeview.Heading", background=sub, foreground=text,
                    font=("Microsoft YaHei UI", 9, "bold"), relief="flat", bordercolor=sep,
                    lightcolor=sub, darkcolor=sub)
    style.map("Treeview",
              background=[("selected", palette["selection_bg"])],
              foreground=[])


def set_dark_titlebar(window, dark):
    """DWM 暗色标题栏，系统不支持时静默失败"""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                return True
    except Exception:
        pass
    return False
