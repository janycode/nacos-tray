"""
tray_v2.py - 系统托盘模块 (Win32 API via ctypes)
使用独立隐藏消息窗口 + 独立消息线程，避免与 tkinter 主循环冲突。
"""
import ctypes
import ctypes.wintypes
import threading
import time

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
WM_COMMAND = 0x0111
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010

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
MF_GRAYED = 0x1
MF_CHECKED = 0x8

TPM_RIGHTALIGN = 0x8
TPM_LEFTBUTTON = 0x0
TPM_RETURNCMD = 0x100
TPM_NONOTIFY = 0x80

IDI_APPLICATION = 32512
WS_EX_TOOLWINDOW = 0x00000080
CW_USEDEFAULT = 0x80000000

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.CreateWindowExW.restype = ctypes.c_void_p

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong)


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


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_uint32),
        ("guidItem", GUID),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint32),
        ("wParam", ctypes.c_void_p),
        ("lParam", ctypes.c_void_p),
        ("time", ctypes.c_uint32),
        ("pt", ctypes.c_long * 2),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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


class TrayIcon:
    """System tray icon - uses dedicated hidden message window"""

    _class_name = "TrayNotifyMessageWindow"

    def __init__(self, tooltip="Tray Notify Tool", tk_root=None):
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
        self._popup_callback = None

    def set_popup_callback(self, callback):
        """设置右键弹窗回调"""
        self._popup_callback = callback

    def _get_default_icon(self):
        import os
        import sys
        icon_paths = []
        if hasattr(sys, "_MEIPASS"):
            icon_paths.append(os.path.join(sys._MEIPASS, "nacos.ico"))
        icon_paths.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "nacos.ico"))
        icon_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nacos.ico"))
        icon_paths.append(os.path.join(os.getcwd(), "nacos.ico"))
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                try:
                    hicon = user32.LoadImageW(0, icon_path, 1, 0, 0, 0x00000010)
                    if hicon:
                        return hicon
                except:
                    pass
        return user32.LoadIconW(None, IDI_APPLICATION)

    def _create_message_window(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEX()
        wc.cbSize = ctypes.sizeof(WNDCLASSEX)
        wc.style = 0
        wc.lpfnWndProc = self._wnd_proc_callback
        wc.hInstance = hinst
        wc.lpszClassName = self._class_name
        wc.hIcon = self._get_default_icon()
        wc.hIconSm = self._get_default_icon()
        class_atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not class_atom:
            return None
        hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW,
            self._class_name,
            "TrayNotifyMsg",
            0,
            CW_USEDEFAULT, CW_USEDEFAULT, 0, 0,
            None, None, hinst, None
        )
        return hwnd

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAYICON:
                if lparam == WM_RBUTTONUP:
                    self._show_context_menu()
                    return 0
                elif lparam == WM_LBUTTONDBLCLK:
                    if "double_click" in self.callbacks and self.tk_root:
                        self.tk_root.after(0, self.callbacks["double_click"])
                    return 0
            elif msg == WM_COMMAND:
                menu_id = wparam & 0xFFFF
                if menu_id in self.callbacks and self.tk_root:
                    self.tk_root.after(0, self.callbacks[menu_id])
                return 0
            elif msg == WM_DESTROY:
                return 0
        except Exception as e:
            import traceback
            traceback.print_exc()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _add_tray_icon(self):
        self._wnd_proc_callback = WNDPROC(self._wnd_proc)
        self.hwnd = self._create_message_window()
        if not self.hwnd:
            return

        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = ctypes.c_void_p(self.hwnd)
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._get_default_icon()
        nid.szTip = self._tooltip[:127]
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _run(self):
        """在独立线程中运行消息循环"""
        self._wnd_proc_callback = WNDPROC(self._wnd_proc)
        self.hwnd = self._create_message_window()
        if not self.hwnd:
            return

        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = ctypes.c_void_p(self.hwnd)
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._get_default_icon()
        nid.szTip = self._tooltip[:127]
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        self.running = True
        msg = MSG()
        while self.running:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0 or result == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _remove_tray_icon(self):
        if self.hwnd:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = ctypes.c_void_p(self.hwnd)
            nid.uID = 1
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def set_tooltip(self, text):
        self._tooltip = text
        if self.hwnd:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = ctypes.c_void_p(self.hwnd)
            nid.uID = 1
            nid.uFlags = NIF_TIP
            nid.szTip = text[:127]
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def icon_rect(self):
        """查询托盘图标的屏幕矩形，失败或图标不可见时返回 None"""
        if not self.hwnd:
            return None
        identifier = NOTIFYICONIDENTIFIER()
        identifier.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        identifier.hWnd = ctypes.c_void_p(self.hwnd)
        identifier.uID = 1
        rect = _RECT()
        try:
            if shell32.Shell_NotifyIconGetRect(ctypes.byref(identifier),
                                               ctypes.byref(rect)) != 0:
                return None
        except Exception:
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return rect.left, rect.top, rect.right, rect.bottom

    def show_balloon(self, title, message, icon_type=NIIF_INFO, timeout=5000):
        if self.hwnd:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = ctypes.c_void_p(self.hwnd)
            nid.uID = 1
            nid.uFlags = NIF_INFO
            nid.szInfoTitle = title[:63]
            nid.szInfo = message[:255]
            nid.dwInfoFlags = icon_type
            nid.uTimeout = timeout
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _show_context_menu(self):
        """右键点击触发弹窗回调（在主线程执行）"""
        if self._popup_callback and self.tk_root:
            self.tk_root.after(0, self._popup_callback)

    def _build_menu(self):
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

    def set_menu_items(self, items):
        with self._lock:
            self._menu_items = items
        if self.hwnd:
            self._build_menu()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.5)

    def stop(self):
        self.running = False
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(timeout=3)
        self._remove_tray_icon()
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
        self._wnd_proc_callback = None
        self.hwnd = None
