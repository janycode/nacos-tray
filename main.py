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
from nacos_client import NacosClient

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
    ww = window.winfo_reqwidth()
    wh = window.winfo_reqheight()
    x = px + (pw - ww) // 2
    y = py + (ph - wh) // 2
    window.geometry("+" + str(x) + "+" + str(y))


def _center_on_screen(window):
    window.update_idletasks()
    w = window.winfo_reqwidth()
    h = window.winfo_reqheight()
    x = (window.winfo_screenwidth() - w) // 2
    y = (window.winfo_screenheight() - h) // 2
    window.geometry(f"+{x}+{y}")


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
COLORS = {
    "primary": "#00B4D8",        # 主色调青蓝
    "primary_dark": "#0096B7",   # 主色深色（悬停）
    "primary_darker": "#007A96", # 主色更深（按下）
    "secondary": "#90E0EF",      # 次要色浅青
    "bg_main": "#F0F8FF",       # 主背景色
    "bg_card": "#FFFFFF",       # 卡片背景
    "bg_row_alt": "#F5FBFD",    # 交替行背景
    "online": "#009639",         # 在线绿（加深）
    "offline": "#FF5252",        # 离线红
    "warning": "#FF9800",        # 警告橙
    "text_primary": "#1A2A3A",   # 主文字
    "text_secondary": "#607D8B", # 次要文字
    "separator": "#E0E0E0",      # 分割线
    "header_text": "#FFFFFF",   # 标题栏文字
}


class SettingsDialog:
    def __init__(self, parent, cfg, on_save=None):
        self.cfg = cfg
        self.on_save = on_save
        self.result = False
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.window = tk.Toplevel(parent)
        self.window.title("设置")
        self.window.geometry("440x480")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()
        _set_icon(self.window)
        _center_on_screen(self.window)
        header = tk.Frame(self.window, bg=COLORS["primary"], height=46)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=" 设置", bg=COLORS["primary"],
                fg=COLORS["header_text"],
                font=("Microsoft YaHei UI", 11, "bold"),
                anchor=tk.W, padx=16).pack(side=tk.LEFT, fill=tk.Y)
        frame = ttk.Frame(self.window, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        conn_group = ttk.LabelFrame(frame, text="Nacos 连接设置", padding=10)
        conn_group.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(conn_group, text="IP:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.ip_var = tk.StringVar(value=cfg.get("ip", ""))
        ttk.Entry(conn_group, textvariable=self.ip_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="端口:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.port_var = tk.StringVar(value=str(cfg.get("port", 8848)))
        ttk.Entry(conn_group, textvariable=self.port_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="命名空间:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.namespace_var = tk.StringVar(value=cfg.get("namespace", ""))
        ttk.Entry(conn_group, textvariable=self.namespace_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="用户名:").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.username_var = tk.StringVar(value=cfg.get("username", "nacos"))
        ttk.Entry(conn_group, textvariable=self.username_var, width=30).grid(row=3, column=1, sticky=tk.W, pady=3)
        ttk.Label(conn_group, text="密码:").grid(row=4, column=0, sticky=tk.W, pady=3)
        self.password_var = tk.StringVar(value=cfg.get("password", ""))
        ttk.Entry(conn_group, textvariable=self.password_var, width=30, show="*").grid(row=4, column=1, sticky=tk.W, pady=3)
        behavior_group = ttk.LabelFrame(frame, text="行为设置", padding=10)
        behavior_group.pack(fill=tk.X, pady=(0, 10))
        self.auto_start_var = tk.BooleanVar(value=config.is_auto_start())
        ttk.Checkbutton(behavior_group, text="开机自动启动", variable=self.auto_start_var).pack(anchor=tk.W, pady=3)
        rf1 = ttk.Frame(behavior_group)
        rf1.pack(fill=tk.X, pady=3)
        ttk.Label(rf1, text="登录刷新间隔(秒):").pack(side=tk.LEFT)
        self.login_interval_var = tk.StringVar(value=str(cfg.get("login_interval", 1800)))
        ttk.Entry(rf1, textvariable=self.login_interval_var, width=10).pack(side=tk.LEFT, padx=10)
        rf2 = ttk.Frame(behavior_group)
        rf2.pack(fill=tk.X, pady=3)
        ttk.Label(rf2, text="状态轮询(秒):").pack(side=tk.LEFT)
        self.poll_interval_var = tk.StringVar(value=str(cfg.get("poll_interval", 30)))
        ttk.Entry(rf2, textvariable=self.poll_interval_var, width=10).pack(side=tk.LEFT, padx=10)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="测试连接", command=self._test_connection).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="取消", command=self.window.destroy).pack(side=tk.RIGHT)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

    def _test_connection(self):
        from tkinter import messagebox
        try:
            client = NacosClient(ip=self.ip_var.get().strip(), port=int(self.port_var.get().strip()),
                username=self.username_var.get().strip(), password=self.password_var.get().strip(),
                namespace=self.namespace_var.get().strip())
            if client.login():
                messagebox.showinfo("成功", "连接成功！", parent=self.window)
            else:
                messagebox.showerror("失败", "登录失败，请检查配置", parent=self.window)
        except Exception as e:
            messagebox.showerror("错误", "连接异常: " + str(e), parent=self.window)

    def _save(self):
        from tkinter import messagebox
        try:
            new_cfg = {"ip": self.ip_var.get().strip(), "port": int(self.port_var.get().strip()),
                "username": self.username_var.get().strip(), "password": self.password_var.get(),
                "namespace": self.namespace_var.get().strip(), "auto_start": self.auto_start_var.get(),
                "login_interval": int(self.login_interval_var.get().strip()),
                "poll_interval": int(self.poll_interval_var.get().strip())}
        except ValueError as e:
            messagebox.showerror("错误", "输入格式错误: " + str(e), parent=self.window)
            return
        config.save_config(new_cfg)
        config.set_auto_start(new_cfg["auto_start"])
        if self.on_save:
            self.on_save(new_cfg)
        messagebox.showinfo("成功", "配置已保存！", parent=self.window)
        self.result = True
        self.window.destroy()


class NotesManageDialog:
    def __init__(self, parent, notes, available_ips=None, on_save=None):
        self.notes = notes
        self.available_ips = available_ips or []
        self.on_save = on_save
        import tkinter as tk
        from tkinter import ttk, simpledialog, messagebox
        self.window = tk.Toplevel(parent)
        self.window.title("IP 备注管理")
        self.window.geometry("520x500")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()
        _set_icon(self.window)
        _center_on_screen(self.window)
        header = tk.Frame(self.window, bg=COLORS["primary"], height=46)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=" IP 备注管理", bg=COLORS["primary"],
                fg=COLORS["header_text"],
                font=("Microsoft YaHei UI", 11, "bold"),
                anchor=tk.W, padx=16).pack(side=tk.LEFT, fill=tk.Y)
        main_frame = ttk.Frame(self.window, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 8))
        for text, cmd in [("新增", self._add),
                          ("编辑", self._edit_selected),
                          ("删除", self._delete_selected)]:
            btn = tk.Label(btn_frame, text=text, bg=COLORS["secondary"],
                          fg=COLORS["text_primary"],
                          font=("Microsoft YaHei UI", 9),
                          padx=12, pady=4, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, 6))
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=COLORS["primary"]))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=COLORS["secondary"]))
        close_btn = tk.Label(btn_frame, text="关闭", bg=COLORS["primary"],
                            fg=COLORS["header_text"],
                            font=("Microsoft YaHei UI", 9),
                            padx=12, pady=4, cursor="hand2")
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self._close())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(bg=COLORS["primary_dark"]))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(bg=COLORS["primary"]))
        columns = ("ip", "note")
        self.tree = ttk.Treeview(main_frame, columns=columns, show="headings", selectmode="browse", height=12)
        self.tree.heading("ip", text="IP 地址")
        self.tree.heading("note", text="备注名")
        self.tree.column("ip", width=200)
        self.tree.column("note", width=250)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", self._edit_selected)
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for ip, note in sorted(self.notes.items()):
            self.tree.insert("", "end", values=(ip, note))

    def _add(self):
        import tkinter as tk
        from tkinter import ttk
        dialog = tk.Toplevel(self.window)
        dialog.title("添加备注")
        dialog.geometry("360x200")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        _set_icon(dialog)
        _center_on_screen(dialog)
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="IP 地址:").pack(anchor=tk.W)
        ip_var = tk.StringVar()
        combo = ttk.Combobox(frame, textvariable=ip_var, values=self.available_ips, width=35)
        combo.pack(fill=tk.X, pady=(2, 8))
        combo.focus_set()
        ttk.Label(frame, text="备注名:").pack(anchor=tk.W)
        note_var = tk.StringVar()
        note_entry = ttk.Entry(frame, textvariable=note_var, width=35)
        note_entry.pack(fill=tk.X, pady=(2, 8))
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        def on_ok():
            ip = ip_var.get().strip()
            note = note_var.get().strip()
            if not ip:
                return
            if note:
                self.notes[ip] = note
                self._save()
                self._refresh()
            dialog.destroy()
        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)

    def _edit_selected(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0])["values"]
        ip = values[0]
        from tkinter import simpledialog
        new_note = simpledialog.askstring("编辑备注", "修改 " + ip + " 的备注名:",
                                          initialvalue=self.notes.get(ip, ""), parent=self.window)
        if new_note is not None:
            if new_note.strip():
                self.notes[ip] = new_note.strip()
            else:
                self.notes.pop(ip, None)
            self._save()
            self._refresh()

    def _delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0])["values"]
        ip = values[0]
        from tkinter import messagebox
        if messagebox.askyesno("确认删除", "确定删除 " + ip + " 的备注吗？", parent=self.window):
            self.notes.pop(ip, None)
            self._save()
            self._refresh()

    def _save(self):
        import config as cfg_mod
        cfg_mod.save_notes(self.notes)
        if self.on_save:
            self.on_save()

    def _close(self):
        self.window.destroy()


class AboutDialog:
    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk
        self.window = tk.Toplevel(parent)
        self.window.title("关于")
        self.window.geometry("320x260")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()
        _set_icon(self.window)
        _center_on_screen(self.window)
        header = tk.Frame(self.window, bg=COLORS["primary"], height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=" 关于 Nacos Tray", bg=COLORS["primary"],
                fg=COLORS["header_text"],
                font=("Microsoft YaHei UI", 11, "bold"),
                anchor=tk.W, padx=16).pack(side=tk.LEFT, fill=tk.Y)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        rows = [
            ("应用名称", "Nacos Tray"),
            ("版本", "v1.0"),
            ("兼容", "Nacos v3.2.1+（v3.x）"),
            ("功能", "1. 服务监控与上下线管理\n2. 状态变化气泡通知\n3. 系统托盘与 IP 备注"),
            ("作者", "JiangYuan"),
        ]
        for i, (label, value) in enumerate(rows):
            tk.Label(frame, text=label + "：", anchor=tk.NE if label == "功能" else tk.E,
                    font=("Microsoft YaHei UI", 9),
                    fg=COLORS["text_secondary"]).grid(row=i, column=0, sticky=tk.NE if label == "功能" else tk.E, pady=1, padx=(0, 6))
            tk.Label(frame, text=value, anchor=tk.NW,
                    font=("Microsoft YaHei UI", 9, "bold" if label == "应用名称" else ""),
                    fg=COLORS["text_primary"],
                    justify=tk.LEFT if label == "功能" else tk.CENTER).grid(row=i, column=1, sticky=tk.NW, pady=1)



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
        header = tk.Frame(outer, bg=C["primary"], height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        left_frame = tk.Frame(header, bg=C["primary"])
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=12)
        tk.Label(left_frame, text=f"Nacos: {ip}:{port}", bg=C["primary"],
                fg=C["header_text"], font=("Microsoft YaHei UI", 9, "bold"),
                anchor=tk.W).pack(fill=tk.Y, expand=True)
        right_frame = tk.Frame(header, bg=C["primary"])
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=12)
        total = len(services)
        online = sum(1 for s in services if s["online"])
        tk.Label(right_frame, text=f"{online}/{total} 在线", bg=C["primary"],
                fg=C["header_text"], font=("Microsoft YaHei UI", 9),
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
            for svc_name, instances in sorted(svc_groups.items()):
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
        btn_frame = tk.Frame(outer, bg=C["primary"])
        btn_frame.pack(fill=tk.X)
        btns = [
            ("还原窗口", self._on_restore),
            ("设置", self._on_settings),
            ("刷新", self._on_refresh),
            ("关闭", self._on_close),
            ("退出", self._on_quit),
        ]
        for label, cmd in btns:
            btn = tk.Label(btn_frame, text=label, bg=C["primary"],
                          fg=C["header_text"],
                          font=("Microsoft YaHei UI", 9),
                          padx=8, pady=6, cursor="hand2")
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=C["primary_dark"]))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=C["primary"]))
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

    def _on_close(self):
        self._destroy()

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
        self.client = None
        self.services = []
        self.previous_services = {}
        self.notes = config.load_notes()
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

    def _init_client(self):
        if not self.cfg.get("ip"):
            return False
        self.client = NacosClient(ip=self.cfg["ip"], port=self.cfg.get("port", 8848),
            username=self.cfg.get("username", "nacos"), password=self.cfg.get("password", "nacos"),
            namespace=self.cfg.get("namespace", ""))
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

    def _show_settings(self):
        if not self.root:
            return
        def on_save(new_cfg):
            self.cfg = new_cfg
            self._init_client()
            self._do_login()
            self._manual_refresh()
        SettingsDialog(self.root, self.cfg, on_save=on_save)

    def _show_about(self):
        if not self.root:
            return
        AboutDialog(self.root)

    def _get_all_ips(self):
        ips = set()
        for svc in self.services:
            ips.add(svc["ip"])
        return sorted(ips)

    def _show_notes(self):
        if not self.root:
            return
        def on_save():
            config.save_notes(self.notes)
        NotesManageDialog(self.root, self.notes, available_ips=self._get_all_ips(), on_save=on_save)

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
        services = self._fetch_services()
        if services:
            with self._lock:
                self.services = services
            for svc in services:
                if svc["online"]:
                    key = svc["service_name"] + ":" + svc["ip"] + ":" + str(svc["port"])
                    if key not in self._last_online_time:
                        self._last_online_time[key] = time.strftime("%Y-%m-%d %H:%M:%S")
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
        if not self.root or not self._service_tree:
            return
        try:
            self._service_tree.delete(*self._service_tree.get_children())
            service_groups = {}
            for svc in self.services:
                name = svc["service_name"]
                if name not in service_groups:
                    service_groups[name] = []
                service_groups[name].append(svc)
            row_idx = 0
            for svc_name, instances in sorted(service_groups.items()):
                for inst in instances:
                    status = "[在线]" if inst["online"] else "[离线]"
                    display_name = self._get_display_name(inst["ip"])
                    last_key = inst["service_name"] + ":" + inst["ip"] + ":" + str(inst["port"])
                    last_time = self._last_online_time.get(last_key, "-")
                    tag = "online" if inst["online"] else "offline"
                    if row_idx % 2 == 1:
                        tag = (tag, "alt")
                    self._service_tree.insert("", "end", values=(svc_name, display_name, str(inst["port"]), status, last_time), tags=tag)
                    row_idx += 1
            total = len(self.services)
            online = sum(1 for s in self.services if s["online"])
            if self._status_var:
                self._status_var.set("共 " + str(total) + " 个服务，" + str(online) + " 个在线")
            if hasattr(self, '_status_dot'):
                if total == 0:
                    self._status_dot.configure(fg=COLORS["text_secondary"])
                elif online == total:
                    self._status_dot.configure(fg=COLORS["online"])
                else:
                    self._status_dot.configure(fg=COLORS["warning"])
        except:
            pass

    def _poll_once(self):
        if not self.running:
            return
        try:
            self._refresh_login_if_needed()
            services = self._fetch_services()
            if services and self.running:
                with self._lock:
                    self.services = services
                changes = self._detect_changes(services)
                for event_type, svc in changes:
                    self._notify_change(event_type, svc)
                if not self.running:
                    return
                self._update_tray_tooltip()
                self._build_menu()
                self._update_window()
        except Exception as e:
            print("Poll error: " + str(e))
        self._schedule_poll()

    def _schedule_poll(self):
        if self.running and self.root:
            try:
                self.root.after(self.cfg.get("poll_interval", 30) * 1000, self._poll_once)
            except:
                pass

    def _create_window(self):
        import tkinter as tk
        from tkinter import ttk
        self.root = tk.Tk()
        _set_icon(self.root)
        self.root.title("Nacos Tray - 服务状态监控与通知 （By JiangYuan v1.0）")
        self.root.geometry("800x560")
        self.root.minsize(600, 400)
        self.root.configure(bg=COLORS["bg_main"])
        _center_on_screen(self.root)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", background=COLORS["bg_card"],
                        fieldbackground=COLORS["bg_card"],
                        foreground=COLORS["text_primary"],
                        font=("Microsoft YaHei UI", 9), rowheight=28)
        style.configure("Treeview.Heading", background=COLORS["secondary"],
                        foreground=COLORS["text_primary"],
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLORS["secondary"])],
                    foreground=[("selected", COLORS["text_primary"])])
        main_frame = ttk.Frame(self.root, padding=0)
        main_frame.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(main_frame, bg=COLORS["primary"], height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        ip_text = self.cfg.get("ip", "未配置")
        port_text = str(self.cfg.get("port", 8848))
        title_label = tk.Label(header, text=f" Nacos: {ip_text}:{port_text}",
                               bg=COLORS["primary"], fg=COLORS["header_text"],
                               font=("Microsoft YaHei UI", 12, "bold"),
                               padx=16)
        title_label.pack(side=tk.LEFT, fill=tk.Y)
        btn_frame = tk.Frame(header, bg=COLORS["primary"])
        btn_frame.pack(side=tk.RIGHT, padx=12)
        for text, cmd in [("刷新", self._on_refresh_click),
                          ("IP备注管理", self._show_notes),
                          ("设置", self._on_settings_click),
                          ("关于", self._show_about)]:
            btn = tk.Label(btn_frame, text=text, bg=COLORS["primary"],
                          fg=COLORS["header_text"],
                          font=("Microsoft YaHei UI", 9),
                          padx=10, pady=4, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=4)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=COLORS["primary_dark"]))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=COLORS["primary"]))
            btn.bind("<Button-1>", lambda e, c=cmd: c())
        tk.Frame(main_frame, bg=COLORS["separator"], height=1).pack(fill=tk.X)
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("service", "instance", "port", "status", "last_online")
        self._service_tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self._service_tree.heading("service", text="服务名")
        self._service_tree.heading("instance", text="实例")
        self._service_tree.heading("port", text="端口")
        self._service_tree.heading("status", text="状态")
        self._service_tree.heading("last_online", text="最近上线时间")
        self._service_tree.column("service", width=180)
        self._service_tree.column("instance", width=200)
        self._service_tree.column("port", width=60)
        self._service_tree.column("status", width=80)
        self._service_tree.column("last_online", width=170)
        self._service_tree.tag_configure("online", foreground=COLORS["online"])
        self._service_tree.tag_configure("offline", foreground=COLORS["offline"])
        self._service_tree.tag_configure("alt", background=COLORS["bg_row_alt"])
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._service_tree.yview)
        self._service_tree.configure(yscrollcommand=scrollbar.set)
        self._service_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        status_frame = tk.Frame(main_frame)
        status_frame.pack(fill=tk.X, padx=16, pady=(0, 10))
        self._status_var = tk.StringVar(value="就绪")
        self._status_dot = tk.Label(status_frame, text="●",
                                     fg=COLORS["text_secondary"],
                                     font=("Microsoft YaHei UI", 10))
        self._status_dot.pack(side=tk.LEFT)
        self._status_label = tk.Label(status_frame, textvariable=self._status_var,
                                      fg=COLORS["text_secondary"],
                                      font=("Microsoft YaHei UI", 9),
                                      anchor=tk.W)
        self._status_label.pack(side=tk.LEFT, padx=(4, 0))
        self._context_menu = tk.Menu(self.root, tearoff=0)
        self._context_menu.add_command(label="上线", command=self._ctx_online)
        self._context_menu.add_command(label="下线", command=self._ctx_offline)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="管理备注...", command=self._ctx_set_note)
        self._context_menu.add_command(label="刷新", command=self._on_refresh_click)
        self._service_tree.bind("<Button-3>", self._show_context_menu)
        self._service_tree.bind("<Double-1>", self._on_double_click)
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
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
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    def _get_selected_service(self):
        selection = self._service_tree.selection()
        if not selection:
            return None
        values = self._service_tree.item(selection[0])["values"]
        if not values or len(values) < 4:
            return None
        svc_name = values[0]
        instance_text = values[1]
        port = int(values[2])
        for svc in self.services:
            if svc["service_name"] == svc_name and svc["port"] == port:
                display = self._get_display_name(svc["ip"])
                if display == instance_text or svc["ip"] == instance_text:
                    return svc
        return None

    def _ctx_online(self):
        svc = self._get_selected_service()
        if svc and not svc["online"]:
            self._bring_online(svc)

    def _ctx_offline(self):
        svc = self._get_selected_service()
        if svc and svc["online"]:
            self._take_offline(svc)

    def _ctx_set_note(self):
        svc = self._get_selected_service()
        if svc:
            self._show_notes()

    def _on_double_click(self, event):
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