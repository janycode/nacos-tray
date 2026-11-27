"""
notifier.py - 通知中心与自绘气泡

四种气泡样式：
- default   Windows 系统通知（沿用托盘 NIF_INFO）
- card      右下角圆角卡片浮窗
- gradient  强调色渐变卡片
- minimal   极简横幅

所有自绘样式只使用当前主题的语义色，不提供独立配色。
"""
import ctypes
import time
import tkinter as tk
import tkinter.font as tkfont

import theme as theme_mod

STYLE_DEFAULT = "default"
STYLE_CARD = "card"
STYLE_GRADIENT = "gradient"
STYLE_MINIMAL = "minimal"

STYLE_OPTIONS = [
    (STYLE_DEFAULT, "默认通知"),
    (STYLE_CARD, "卡片浮窗"),
    (STYLE_GRADIENT, "强调渐变"),
    (STYLE_MINIMAL, "极简横幅"),
]

NIIF_INFO = 0x1
NIIF_WARNING = 0x2
NIIF_ERROR = 0x3

_TRANSPARENT_KEY = "#010203"
_CARD_WIDTH = 364
_MINIMAL_WIDTH = 324
_GAP = 10
_MARGIN = 12
_TAIL_W = 22
_TAIL_H = 14
_TAIL_OVERLAP = 2
_DURATION_MS = theme_mod.BUBBLE_DURATION_MS
_MAX_BODY_LINES = 14
_FADE_STEP = theme_mod.ANIMATE_STEP_MS / float(theme_mod.BUBBLE_FADE_MS)


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def work_area(root):
    """主屏工作区（已扣除任务栏），失败时退回屏幕尺寸"""
    try:
        rect = _RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            if rect.right > rect.left and rect.bottom > rect.top:
                return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 48


_MONITOR_DEFAULTTONEAREST = 2


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_uint32),
    ]


ctypes.windll.user32.MonitorFromRect.restype = ctypes.c_void_p
ctypes.windll.user32.MonitorFromRect.argtypes = [ctypes.POINTER(_RECT), ctypes.c_uint32]


def monitor_work_rect(rect):
    """返回矩形所在显示器的工作区，失败返回 None"""
    try:
        area = _RECT(rect[0], rect[1], rect[2], rect[3])
        monitor = ctypes.windll.user32.MonitorFromRect(
            ctypes.byref(area), _MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return None
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        work = info.rcWork
        return work.left, work.top, work.right, work.bottom
    except Exception:
        return None


def _gradient_round_rect(canvas, x1, y1, x2, y2, radius, color_top, color_bottom):
    height = max(int(y2 - y1), 1)
    band = 2
    y = y1
    while y < y2:
        ratio = (y - y1) / height
        color = theme_mod.blend(color_top, color_bottom, ratio)
        inset = 0
        if y < y1 + radius:
            dy = radius - (y - y1)
            inset = radius - (radius * radius - dy * dy) ** 0.5
        elif y > y2 - radius:
            dy = y - (y2 - radius)
            inset = radius - (radius * radius - dy * dy) ** 0.5
        canvas.create_rectangle(
            x1 + inset, y, x2 - inset, min(y + band, y2),
            fill=color, outline=color)
        y += band


def _truncate_lines(text, max_lines):
    lines = (text or "").split("\n")
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines]) + "\n…"


def _font(size, bold=False):
    # 不缓存：Tk 根销毁后旧 Font 会失效，气泡渲染频率低，直接创建即可
    return tkfont.Font(family=theme_mod.FONT_FAMILY, size=size,
                       weight="bold" if bold else "normal")


def _wrap_text(font, text, max_width):
    """按像素宽度手工折行（Canvas 文本不自动折行）"""
    lines = []
    current = ""
    for char in text:
        if not current or font.measure(current + char) <= max_width:
            current += char
        else:
            lines.append(current)
            current = char
    lines.append(current)
    return lines


_KEY_LABELS = ("项目", "构建", "状态", "服务", "实例",
               "开始", "结束", "用时", "分支", "环境")
_HOT_KEYS = ("项目", "构建", "状态", "分支", "环境")


def _split_field(text):
    if "：" in text:
        head, rest = text.split("：", 1)
        if head in _KEY_LABELS:
            return head + "：", rest
    return None, None


def _draw_body(canvas, body, x, y, width, normal_font, key_font, value_font,
               hot_font, normal_fill, key_fill, value_fill, hot_fill):
    """渲染正文；已知字段的标签弱化、值加粗着色（项目/构建/状态/分支/环境为强调色）。

    canvas 传 None 时只计算高度。
    """
    bottom = y
    normal_step = normal_font.metrics("linespace")
    value_step = value_font.metrics("linespace")
    hot_step = hot_font.metrics("linespace")
    for raw in (body or "").split("\n"):
        text = raw.rstrip()
        if not text:
            bottom += normal_step
            continue
        label, value = _split_field(text)
        if label is None:
            for line in _wrap_text(normal_font, text, width):
                if canvas is not None:
                    canvas.create_text(x, bottom, text=line, anchor="nw",
                                       font=normal_font, fill=normal_fill)
                bottom += normal_step
            continue
        if canvas is not None:
            canvas.create_text(x, bottom, text=label, anchor="nw",
                               font=key_font, fill=key_fill)
        cursor = x + key_font.measure(label)
        avail = max(width - key_font.measure(label), 20)
        hot = label[:-1] in _HOT_KEYS
        fill = hot_fill if hot else value_fill
        font = hot_font if hot else value_font
        step = hot_step if hot else value_step
        first = True
        for line in _wrap_text(font, value, avail):
            if canvas is not None:
                if first:
                    canvas.create_text(cursor, bottom, text=line, anchor="nw",
                                       font=font, fill=fill)
                else:
                    canvas.create_text(x, bottom, text=line, anchor="nw",
                                       font=font, fill=fill)
            first = False
            bottom += step
    return bottom


def _level_color(palette, level):
    return {
        "success": palette.get("online", "#009639"),
        "error": palette.get("offline", "#FF5252"),
        "warning": palette.get("warning", "#FF9800"),
        "info": palette.get("primary", "#0096B7"),
    }.get(level or "info", palette.get("primary", "#0096B7"))


def _level_glyph(level):
    # 用微软雅黑自带字形（√ / ×），避免图标字体缺失时出现空白方框
    return {
        "success": "√",
        "error": "×",
        "warning": "!",
        "info": "i",
    }.get(level or "info", "i")


def _source_label(source):
    return {"nacos": "Nacos", "jenkins": "Jenkins"}.get(source or "", "")


class BubbleWindow:
    def __init__(self, manager, event, style, palette, duration_ms=_DURATION_MS,
                 tail_tip=None):
        self.manager = manager
        self.event = event
        self.style = style
        self.palette = palette
        self.duration_ms = duration_ms
        self.width = _MINIMAL_WIDTH if style == STYLE_MINIMAL else _CARD_WIDTH
        self.tail_tip = tail_tip
        self._paused = False
        self._closed = False
        self._destroyed = False
        self._timer = None
        self._fade_job = None

        self.window = tk.Toplevel(manager.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=_TRANSPARENT_KEY)
        self._transparent = True
        try:
            self.window.attributes("-transparentcolor", _TRANSPARENT_KEY)
        except tk.TclError:
            self._transparent = False
            self.window.configure(bg=palette["bg_main"])
        self.canvas = tk.Canvas(self.window, bg=(
            _TRANSPARENT_KEY if self._transparent else palette["bg_main"]),
            highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        if style == STYLE_GRADIENT:
            self.height = self._render_gradient()
        elif style == STYLE_MINIMAL:
            self.height = self._render_minimal()
        else:
            self.height = self._render_card()

        self.window.geometry(f"{self.width}x{self.height}")
        self._target_alpha = 0.94 if style == STYLE_MINIMAL else 1.0
        self.window.attributes("-alpha", 0.0)
        self._fade_in()
        self._schedule_close()

        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

    def set_tail(self, tip_x):
        """设置尾尖在气泡内的 x 偏移；None 表示不绘制尾巴，随后重绘"""
        if tip_x is not None:
            margin = _TAIL_W // 2 + 4
            tip_x = max(margin, min(tip_x, self.width - margin))
        if tip_x == self.tail_tip:
            return
        self.tail_tip = tip_x
        if self.style == STYLE_GRADIENT:
            self._render_gradient()
        elif self.style == STYLE_MINIMAL:
            self._render_minimal()
        else:
            self._render_card()
        self.window.geometry(f"{self.width}x{self.height}")

    def _draw_tail(self, canvas, base_y, fill, outline):
        tip_x = self.tail_tip
        left = tip_x - _TAIL_W // 2
        right = tip_x + _TAIL_W // 2
        tip_y = base_y + _TAIL_H - _TAIL_OVERLAP
        canvas.create_polygon([left, base_y, tip_x, tip_y, right, base_y],
                              smooth=True, splinesteps=24,
                              fill=fill, outline=outline)

    # ---------- 渲染 ----------

    def _render_card(self):
        palette = self.palette
        canvas = self.canvas
        accent = _level_color(palette, self.event.get("level"))
        padding = 14
        title = self.event.get("title", "")
        body = _truncate_lines(self.event.get("body", ""), _MAX_BODY_LINES)
        icon_cx, icon_cy, icon_r = 32, 32, 13
        title_x = 54
        title_font = _font(theme_mod.FONT_SIZES["body"], True)
        normal_font = _font(theme_mod.FONT_SIZES["secondary"])
        key_font = _font(theme_mod.FONT_SIZES["micro"])
        value_font = _font(theme_mod.FONT_SIZES["secondary"], True)
        hot_font = _font(theme_mod.FONT_SIZES["body"], True)
        body_y = 46
        body_bottom = _draw_body(
            None, body, padding, body_y, self.width - padding * 2,
            normal_font, key_font, value_font, hot_font,
            palette["text_secondary"], palette["text_secondary"],
            palette["text_primary"], accent)
        height = max(body_bottom + 14, 104)
        extra = _TAIL_H - _TAIL_OVERLAP if self.tail_tip is not None else 0
        self.height = height + extra
        canvas.configure(width=self.width, height=self.height)
        canvas.delete("all")
        theme_mod.rounded_rect(canvas, 1, 1, self.width - 1, height - 1,
                               theme_mod.RADIUS_BUBBLE,
                               fill=palette["bg_card"], outline=palette["separator"])
        canvas.create_rectangle(3, 14, 6, height - 14, fill=accent, outline=accent)
        canvas.create_oval(icon_cx - icon_r, icon_cy - icon_r,
                           icon_cx + icon_r, icon_cy + icon_r,
                           fill=accent, outline=accent)
        canvas.create_text(icon_cx, icon_cy, text=_level_glyph(self.event.get("level")),
                           fill=theme_mod.readable_text(accent),
                           font=_font(theme_mod.ICON_SIZE_TIERS[0], True))
        canvas.create_text(title_x, 16, text=title, anchor="nw",
                           fill=accent, font=title_font,
                           width=self.width - title_x - 14)
        source = _source_label(self.event.get("source"))
        if source:
            canvas.create_text(self.width - padding, 20, text=source, anchor="ne",
                               fill=palette["text_secondary"],
                               font=_font(theme_mod.FONT_SIZES["micro"]))
        _draw_body(canvas, body, padding, body_y, self.width - padding * 2,
                   normal_font, key_font, value_font, hot_font,
                   palette["text_secondary"], palette["text_secondary"],
                   palette["text_primary"], accent)
        if extra:
            self._draw_tail(canvas, height - _TAIL_OVERLAP,
                            palette["bg_card"], palette["separator"])
        return height

    def _render_gradient(self):
        palette = self.palette
        canvas = self.canvas
        padding = 16
        top = palette["primary"]
        text_color = theme_mod.readable_text(top)
        toward = "#FFFFFF" if text_color == "#1A1A1A" else "#000000"
        bottom = theme_mod.blend(top, toward, 0.22)
        title = self.event.get("title", "")
        body = _truncate_lines(self.event.get("body", ""), _MAX_BODY_LINES)
        normal_font = _font(theme_mod.FONT_SIZES["secondary"])
        key_font = _font(theme_mod.FONT_SIZES["micro"])
        value_font = _font(theme_mod.FONT_SIZES["secondary"], True)
        hot_font = _font(theme_mod.FONT_SIZES["body"], True)
        key_fill = theme_mod.blend(text_color, top, 0.45)
        body_y = 46
        body_bottom = _draw_body(
            None, body, padding, body_y, self.width - padding * 2,
            normal_font, key_font, value_font, hot_font,
            text_color, key_fill, text_color, text_color)
        height = max(body_bottom + 16, 100)
        extra = _TAIL_H - _TAIL_OVERLAP if self.tail_tip is not None else 0
        self.height = height + extra
        canvas.configure(width=self.width, height=self.height)
        canvas.delete("all")
        _gradient_round_rect(canvas, 1, 1, self.width - 1, height - 1,
                             theme_mod.RADIUS_BUBBLE, top, bottom)
        canvas.create_oval(padding - 2, 18, padding + 10, 30,
                           fill=text_color, outline=text_color)
        canvas.create_text(padding + 18, 15, text=title, anchor="nw",
                           fill=text_color,
                           font=_font(theme_mod.FONT_SIZES["body"], True),
                           width=self.width - padding * 2 - 18)
        source = _source_label(self.event.get("source"))
        if source:
            canvas.create_text(self.width - padding, 17, text=source, anchor="ne",
                               fill=text_color, font=_font(theme_mod.FONT_SIZES["micro"]))
        _draw_body(canvas, body, padding, body_y, self.width - padding * 2,
                   normal_font, key_font, value_font, hot_font,
                   text_color, key_fill, text_color, text_color)
        canvas.create_line(padding, height - 8, self.width - padding, height - 8,
                           fill=theme_mod.blend(text_color, top, 0.55), width=1)
        if extra:
            self._draw_tail(canvas, height - _TAIL_OVERLAP, bottom,
                            palette["separator"])
        return height

    def _render_minimal(self):
        palette = self.palette
        canvas = self.canvas
        padding = 14
        height = 58
        extra = _TAIL_H - _TAIL_OVERLAP if self.tail_tip is not None else 0
        self.height = height + extra
        canvas.configure(width=self.width, height=self.height)
        theme_mod.rounded_rect(canvas, 1, 1, self.width - 1, height - 1,
                               theme_mod.RADIUS_BUBBLE,
                               fill=palette["bg_card"], outline=palette["separator"])
        accent = _level_color(palette, self.event.get("level"))
        canvas.create_oval(padding, height // 2 - 5, padding + 10, height // 2 + 5,
                           fill=accent, outline=accent)
        title = self.event.get("title", "")
        canvas.create_text(padding + 20, 12, text=title, anchor="nw",
                           fill=palette["text_primary"],
                           font=_font(theme_mod.FONT_SIZES["body"], True),
                           width=self.width - padding * 2 - 20)
        body = (self.event.get("body", "") or "").split("\n")[0]
        font = _font(theme_mod.FONT_SIZES["secondary"], True)
        max_width = self.width - padding * 2 - 20
        if font.measure(body) > max_width:
            while body and font.measure(body + "…") > max_width:
                body = body[:-1]
            body += "…"
        canvas.create_text(padding + 20, 30, text=body, anchor="nw",
                           fill=accent, font=font)
        if extra:
            self._draw_tail(canvas, height - _TAIL_OVERLAP,
                            palette["bg_card"], palette["separator"])
        return height

    # ---------- 交互 ----------

    def move(self, x, y):
        try:
            self.window.geometry(f"+{int(x)}+{int(y)}")
        except Exception:
            pass

    def _schedule_close(self):
        if self._closed:
            return
        self._timer = self.window.after(self.duration_ms, self.close)

    def _on_enter(self, event=None):
        if self._closed:
            return
        self._paused = True
        if self._timer:
            try:
                self.window.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None

    def _on_leave(self, event=None):
        if self._closed:
            return
        self._paused = False
        self._schedule_close()

    def _on_click(self, event=None):
        if self._closed:
            return
        event_data = dict(self.event)
        self.close()
        self.manager.handle_click(event_data)

    def _fade_in(self):
        if self._closed:
            return
        try:
            alpha = float(self.window.attributes("-alpha"))
        except Exception:
            alpha = 0.0
        alpha = min(alpha + _FADE_STEP, self._target_alpha)
        try:
            self.window.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha < self._target_alpha:
            self._fade_job = self.window.after(theme_mod.ANIMATE_STEP_MS, self._fade_in)

    def _fade_out(self, then_destroy=True):
        if self._destroyed:
            return
        try:
            alpha = float(self.window.attributes("-alpha"))
        except Exception:
            alpha = 0.0
        alpha = max(alpha - _FADE_STEP, 0.0)
        try:
            self.window.attributes("-alpha", alpha)
        except Exception:
            alpha = 0.0
        if alpha > 0:
            self._fade_job = self.window.after(
                theme_mod.ANIMATE_STEP_MS, lambda: self._fade_out(then_destroy))
        elif then_destroy:
            self._destroy()

    def close(self, immediate=False):
        if self._closed:
            return
        self._closed = True
        if self._timer:
            try:
                self.window.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        if self._fade_job:
            try:
                self.window.after_cancel(self._fade_job)
            except Exception:
                pass
            self._fade_job = None
        if immediate:
            self._destroy()
            return
        self._fade_out()

    def _destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        manager = self.manager
        if self in manager._active:
            manager._active.remove(self)
        try:
            self.window.destroy()
        except Exception:
            pass
        try:
            manager._relayout()
            manager._drain()
        except Exception as exc:
            print("Bubble cleanup failed: " + str(exc))


class NotifierCenter:
    def __init__(self, root, tray_getter, palette_getter, style_getter, on_click,
                 remote_emit=None, enabled_sources=None):
        self.root = root
        self._tray_getter = tray_getter
        self._palette_getter = palette_getter
        self._style_getter = style_getter
        self._on_click = on_click
        self._remote_emit = remote_emit
        self._enabled_sources_getter = enabled_sources
        self._active = []
        self._queue = []

    def _source_enabled(self, source):
        getter = self._enabled_sources_getter
        if getter is None:
            return True
        try:
            enabled = getter()
            if not enabled:
                return False
            return bool(enabled.get(source))
        except Exception:
            return True

    def notify(self, title, body, level="info", url="", source=""):
        self.notify_batch([{
            "title": title,
            "body": body,
            "level": level,
            "url": url,
            "source": source,
            "time": time.time(),
        }])

    def notify_batch(self, events):
        events = [event for event in (events or []) if event]
        if not events:
            return
        events = [e for e in events if self._source_enabled(e.get("source"))]
        if not events:
            return
        if self._remote_emit is not None:
            for event in events:
                try:
                    self._remote_emit(event)
                except Exception as exc:
                    print("Remote emit failed: " + str(exc))
        if self._style_getter() == STYLE_DEFAULT:
            for event in events:
                self._send_native(event)
            return
        if len(events) > 3:
            events = [self._summarize(events)]
        self._queue.extend(events)
        self._drain()

    def _summarize(self, events):
        first = events[0]
        source = first.get("source", "")
        count = len(events)
        if source == "jenkins":
            title = str(count) + " 个构建状态变化"
        elif source == "nacos":
            title = str(count) + " 个服务状态变化"
        else:
            title = str(count) + " 个状态变化"
        lines = []
        for event in events[:3]:
            body_line = (event.get("body") or "").split("\n")[0]
            lines.append("• " + event.get("title", "") + "  " + body_line)
        if count > 3:
            lines.append("等 " + str(count - 3) + " 条")
        level = "info"
        order = {"info": 0, "success": 1, "warning": 2, "error": 3}
        for event in events:
            if order.get(event.get("level", "info"), 0) > order.get(level, 0):
                level = event.get("level")
        return {
            "title": title,
            "body": "\n".join(lines),
            "level": level,
            "url": "",
            "source": source,
            "summary": True,
            "time": time.time(),
        }

    def _drain(self):
        while self._queue and len(self._active) < 3:
            event = self._queue.pop(0)
            self._show(event)

    def _show(self, event):
        palette = dict(self._palette_getter())
        style = self._style_getter()
        if style == STYLE_DEFAULT:
            self._send_native(event)
            return
        try:
            bubble = BubbleWindow(self, event, style, palette)
        except Exception as exc:
            print("Create bubble failed: " + str(exc))
            self._send_native(event)
            return
        self._active.insert(0, bubble)
        self._relayout()

    def _relayout(self):
        if not self.root:
            return
        try:
            work = work_area(self.root)
        except Exception:
            return
        anchor_x = None
        bounds = work
        tray = self._tray_getter()
        icon_rect = None
        if tray is not None and hasattr(tray, "icon_rect"):
            try:
                icon_rect = tray.icon_rect()
            except Exception:
                icon_rect = None
        base_bottom = work[3] - _MARGIN
        if icon_rect:
            anchor_x = (icon_rect[0] + icon_rect[2]) // 2
            bounds = monitor_work_rect(icon_rect) or work
            # 尖角尖端贴住任务栏上沿：去掉气泡与任务栏之间的间隔
            base_bottom = bounds[3]
        tail_owner = self._active[0] if (anchor_x is not None and self._active) else None
        y = base_bottom
        for bubble in self._active:
            if anchor_x is None:
                x = bounds[2] - bubble.width - _MARGIN
            else:
                x = anchor_x - bubble.width // 2
                x = max(bounds[0] + _MARGIN,
                         min(x, bounds[2] - bubble.width - _MARGIN))
            if bubble is tail_owner:
                bubble.set_tail(anchor_x - x)
            else:
                bubble.set_tail(None)
            y -= bubble.height
            bubble.move(x, max(bounds[1] + _MARGIN, y))
            y -= _GAP

    def bubble_closed(self, bubble):
        if bubble in self._active:
            self._active.remove(bubble)
        self._relayout()
        self._drain()

    def handle_click(self, event):
        try:
            self._on_click(event)
        except Exception as exc:
            print("Notification click failed: " + str(exc))

    def dismiss_all(self):
        self._queue = []
        for bubble in list(self._active):
            bubble.close(immediate=True)
        self._active = []
        self._relayout()

    def _send_native(self, event):
        tray = self._tray_getter()
        if not tray:
            return
        icon = {
            "success": NIIF_INFO,
            "info": NIIF_INFO,
            "warning": NIIF_WARNING,
            "error": NIIF_ERROR,
        }.get(event.get("level", "info"), NIIF_INFO)
        body = event.get("body", "") or ""
        if len(body) > 255:
            cut = body[:252]
            if "\n" in cut:
                cut = cut.rsplit("\n", 1)[0]
            body = cut + "\n..."
        try:
            tray.show_balloon(event.get("title", ""), body, icon)
        except Exception as exc:
            print("Native balloon failed: " + str(exc))
