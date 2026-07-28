"""
tray.py - 系统托盘模块 (Win32 API via ctypes)
纯标准库实现，支持:
- 托盘图标
- 右键菜单
- 气泡通知
- 悬浮提示文字
"""
import ctypes
import ctypes.wintypes
import threading
import time
import os
import sys

# Windows 常量
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
WM_COMMAND = 0x0111
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010

WS_OVERLAPPEDWINDOW = 0x00CF0000
CW_USEDEFAULT = 0x80000000

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2

NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10

NIIF_INFO = 0x1
NIIF_WARNING = 0x2
NIIF_ERROR = 0x3

MF_STRING = 0x0
MF_SEPARATOR = 0x800
MF_POPUP = 0x10
MF_GRAYED = 0x1
MF_ENABLED = 0x0
MF_CHECKED = 0x8

TPM_RIGHTALIGN = 0x8
TPM_LEFTBUTTON = 0x0
TPM_RETURNCMD = 0x100
TPM_NONOTIFY = 0x80
TPM_RIGHTBUTTON = 0x2

IDI_APPLICATION = 32512

WS_EX_TOOLWINDOW = 0x00000080

IMAGE_ICON = 1

# 加载 Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32

# 定义 WNDPROC 回调类型 (64-bit safe)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong)


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_uint32),
        ("uFlags", ctypes.c_uint32),
        ("uCallbackMessage", ctypes.c_uint32),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.c_uint32),
        ("dwStateMask", ctypes.c_uint32),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeout", ctypes.c_uint32),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.c_uint32),
    ]


class WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("style", ctypes.c_uint32),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint32),
        ("wParam", ctypes.c_void_p),
        ("lParam", ctypes.c_void_p),
        ("time", ctypes.c_uint32),
        ("pt", POINT),
    ]


class TrayIcon:
    """系统托盘图标"""

    _class_name = "NacosTrayIconWindow"

    def __init__(self, tooltip="Nacos Tray", tk_root=None):
        self.tooltip = tooltip
        self.tk_root = tk_root
        self.hwnd = None
        self.hmenu = None
        self.callbacks = {}
        self.running = False
        self._thread = None
        self._menu_items = []
        self._next_id = 1000
        self._tooltip = tooltip
        self._lock = threading.Lock()
        self._wnd_proc_callback = None

    def _get_default_icon(self):
        """获取默认应用图标"""
        return user32.LoadIconW(None, IDI_APPLICATION)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """窗口过程"""
        try:
            if msg == WM_TRAYICON:
                if lparam == WM_RBUTTONUP:
                    self._show_context_menu()
                elif lparam == WM_LBUTTONDBLCLK:
                    if "double_click" in self.callbacks and self.tk_root:
                        self.tk_root.after(0, self.callbacks["double_click"])
            elif msg == WM_COMMAND:
                cmd_id = wparam & 0xFFFF
                if cmd_id in self.callbacks and self.tk_root:
                    self.tk_root.after(0, self.callbacks[cmd_id])
            elif msg == WM_DESTROY:
                self._remove_tray_icon()
                user32.PostQuitMessage(0)
        except Exception:
            pass
        return 0

    def _show_context_menu(self):
        """显示右键菜单"""
        if not self.hmenu:
            return

        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)

        user32.TrackPopupMenu(
            self.hmenu,
            TPM_RIGHTALIGN | TPM_LEFTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON,
            point.x, point.y, 0, self.hwnd, None
        )

    def _build_menu(self):
        """构建右键菜单"""
        if self.hmenu:
            user32.DestroyMenu(self.hmenu)

        self.hmenu = user32.CreatePopupMenu()
        _dc = self.callbacks.get("double_click")
        self.callbacks = {}
        if _dc:
            self.callbacks["double_click"] = _dc
        self._next_id = 1000

        for item in self._menu_items:
            if item is None:
                user32.AppendMenuW(self.hmenu, MF_SEPARATOR, 0, None)
            elif isinstance(item, dict):
                menu_id = self._next_id
                self._next_id += 1
                flags = MF_STRING
                if item.get("enabled", True) is False:
                    flags |= MF_GRAYED
                if item.get("checked"):
                    flags |= MF_CHECKED
                user32.AppendMenuW(self.hmenu, flags, menu_id, item["text"])
                if "callback" in item and item["callback"]:
                    self.callbacks[menu_id] = item["callback"]

    def _add_tray_icon(self):
        """添加托盘图标"""
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._get_default_icon()
        nid.szTip = self._tooltip[:127]
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _remove_tray_icon(self):
        """移除托盘图标"""
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def set_tooltip(self, text):
        """设置悬浮提示"""
        self._tooltip = text
        if self.hwnd:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_TIP
            nid.szTip = text[:127]
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def show_balloon(self, title, message, icon_type=NIIF_INFO, timeout=5000):
        """显示气泡通知"""
        if self.hwnd:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_INFO
            nid.szInfoTitle = title[:63]
            nid.szInfo = message[:255]
            nid.dwInfoFlags = icon_type
            nid.uTimeout = timeout
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def set_menu_items(self, items):
        """设置菜单项"""
        with self._lock:
            self._menu_items = items
        if self.hwnd:
            self._build_menu()

    def _run(self):
        """运行消息循环"""
        # 注册窗口类
        wndclass = WNDCLASSEX()
        wndclass.cbSize = ctypes.sizeof(WNDCLASSEX)
        wndclass.style = 0
        self._wnd_proc_callback = WNDPROC(self._wnd_proc)
        wndclass.lpfnWndProc = self._wnd_proc_callback
        wndclass.hInstance = kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = self._class_name
        wndclass.hIcon = self._get_default_icon()
        wndclass.hIconSm = self._get_default_icon()

        class_atom = user32.RegisterClassExW(ctypes.byref(wndclass))
        if not class_atom:
            return

        # 创建隐藏窗口
        self.hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW,
            self._class_name,
            "Nacos Tray",
            0,
            CW_USEDEFAULT, CW_USEDEFAULT, 0, 0,
            None, None, kernel32.GetModuleHandleW(None), None
        )

        if not self.hwnd:
            return

        # 构建菜单
        self._build_menu()

        # 添加托盘图标
        self._add_tray_icon()

        self.running = True

        # 消息循环
        msg = MSG()
        while self.running:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0 or result == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def start(self):
        """启动托盘（在新线程中）"""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.5)

    def stop(self):
        """停止托盘"""
        self.running = False
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(timeout=3)
