# theme.py - 明暗主题：配色预设、自定义派生、系统检测、ttk 样式与标题栏
import ctypes
import re
import sys
import time

MODE_SYSTEM = "system"
MODE_LIGHT = "light"
MODE_DARK = "dark"
MODE_OPTIONS = [(MODE_SYSTEM, "跟随系统"), (MODE_LIGHT, "亮色"), (MODE_DARK, "暗色")]

CUSTOM_ID = "custom"
CUSTOM_NAME = "自定义"
DEFAULT_PRESET = "daozai"

# 外观骨架标度：圆角、间距、字号与图标尺寸档位（所有配色预设共用）
RADIUS_CONTROL = 8
RADIUS_CARD = 12
RADIUS_MENU = 12
RADIUS_FLOAT = 16
RADIUS_TOOLTIP = 10
RADIUS_BUBBLE = 12
SPACING_SCALE = (4, 8, 12, 16)
FONT_FAMILY = "Microsoft YaHei UI"
FONT_SIZES = {"metric": 20, "title": 12, "body": 10, "secondary": 9, "micro": 8}
ICON_SIZE_TIERS = (11, 13, 16)

# 入场过渡参数（毫秒）
ANIMATE_STEP_MS = 16
MENU_FADE_MS = 120
POPUP_FADE_MS = 140
TOOLTIP_DELAY_MS = 200
TOOLTIP_FADE_MS = 100
BUBBLE_FADE_MS = 150
BUBBLE_DURATION_MS = 11000
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
    "daozai": {
        "name": "岛仔风",
        "light": {
            "primary": "#D63A3F", "primary_dark": "#BC3035", "primary_darker": "#9E282C",
            "secondary": "#EFE6D8", "bg_main": "#F7F2E9", "bg_card": "#FFFDF7",
            "bg_row_alt": "#F0E9DC", "text_primary": "#22201E", "text_secondary": "#6E6960",
            "separator": "#E6DCCC", "header_text": "#FFFFFF",
        },
        "dark": {
            "primary": "#E5484D", "primary_dark": "#C93E43", "primary_darker": "#A93337",
            "secondary": "#23272D", "bg_main": "#0B0D10", "bg_card": "#15181D",
            "bg_row_alt": "#191D23", "text_primary": "#EDEFF2", "text_secondary": "#98A1AB",
            "separator": "#25292F", "header_text": "#FFFFFF",
        },
    },
}

PRESET_ORDER = ["daozai", "qinglan", "haiLan", "huiLu", "mihuang", "dousha", "shimo", "wuye", "chunhei"]

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
    """顶部条取色：以表面色为底，文字用主文字色，强调色只用于选中项与动作"""
    header_bg = palette["bg_card"]
    header_fg = ensure_contrast(palette["text_primary"], header_bg, 4.5)
    header_hover = palette["secondary"]
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
    palette["bg_hover"] = blend(palette["bg_card"], palette["primary"], 0.10)
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
    base_font = font("secondary")

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
                    font=base_font, rowheight=row_height, bordercolor=sep, lightcolor=card, darkcolor=card)
    heading_bg = palette["bg_row_alt"]
    style.configure("Treeview.Heading", background=heading_bg, foreground=text,
                    font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"), relief="flat",
                    bordercolor=sep, lightcolor=heading_bg, darkcolor=heading_bg)
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


# ---------- 外观骨架公共能力 ----------

_TRANSPARENT_BASE = "#010203"


def transparent_key(palette=None):
    """浮层抠色专用色：避开调色板里的表面色，主题切换不产生杂边"""
    base = _TRANSPARENT_BASE
    if not palette:
        return base
    used = set()
    for value in palette.values():
        if isinstance(value, str) and value.startswith("#"):
            used.add(value.upper())
    if base not in used:
        return base
    red = 1
    while red < 256:
        candidate = "#%02X0203" % red
        if candidate not in used:
            return candidate
        red += 1
    return base


def ease_out_cubic(ratio):
    """0 到 1 的 ease-out cubic 缓动"""
    ratio = max(0.0, min(1.0, ratio))
    return 1 - (1 - ratio) ** 3


def animate_alpha(window, target, duration_ms, step_ms=None, on_frame=None):
    """把窗口透明度补间到目标值；时长为 0 或系统要求减少动画时直接落值。

    on_frame 可选，每帧回传已缓动的进度（0 到 1），供调用方同步做位移等效果。
    """
    if duration_ms <= 0 or system_reduces_motion():
        try:
            window.attributes("-alpha", float(target))
        except Exception:
            pass
        if on_frame is not None:
            try:
                on_frame(1.0)
            except Exception:
                pass
        return
    step_ms = step_ms or ANIMATE_STEP_MS
    try:
        start = float(window.attributes("-alpha"))
    except Exception:
        start = 0.0
    begun = time.time()

    def _step():
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return
        elapsed = (time.time() - begun) * 1000.0
        ratio = min(elapsed / float(duration_ms), 1.0)
        eased = ease_out_cubic(ratio)
        value = start + (float(target) - start) * eased
        try:
            window.attributes("-alpha", value)
        except Exception:
            return
        if on_frame is not None:
            try:
                on_frame(eased)
            except Exception:
                pass
        if ratio < 1.0:
            try:
                window._alpha_anim_job = window.after(step_ms, _step)
            except Exception:
                pass
        else:
            try:
                window._alpha_anim_job = None
            except Exception:
                pass

    _step()


def stop_alpha(window):
    """取消进行中的透明度补间，避免多次入场互相踩踏"""
    job = getattr(window, "_alpha_anim_job", None)
    if job is None:
        return
    try:
        window.after_cancel(job)
    except Exception:
        pass
    try:
        window._alpha_anim_job = None
    except Exception:
        pass


def rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """在 Canvas 上绘制圆角矩形，供各浮层复用"""
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def font(size_key, bold=False):
    """按字号档位生成字体元组；size_key 传整数时按原值使用"""
    size = FONT_SIZES.get(size_key, size_key)
    return (FONT_FAMILY, size, "bold" if bold else "normal")


def system_reduces_motion():
    """读取系统「减少动画」设置，失败按不减少处理"""
    try:
        value = ctypes.c_int()
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0):
            return not bool(value.value)
    except Exception:
        pass
    return False


def windows_build():
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


def is_win11_or_newer():
    return windows_build() >= 22000


_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMSBT_MICA = 2
_DWMSBT_ACRYLIC = 3


def set_frosted_glass(window, enabled=True, acrylic=False):
    """Windows 11 浮层毛玻璃背板；不支持或调用失败时静默返回 False"""
    if not enabled or not is_win11_or_newer():
        return False
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        value = ctypes.c_int(_DWMSBT_ACRYLIC if acrylic else _DWMSBT_MICA)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(value), ctypes.sizeof(value)
        )
        return result == 0
    except Exception:
        return False
