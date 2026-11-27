"""
daozai_sink.py - 岛仔本机通知来源推送

按岛仔 notice-provider-v1 协议发送短时通知：TCP 连 127.0.0.1，每连接一行 UTF-8 JSON。
凭据文件由岛仔设置页授权后生成：%APPDATA%\\Daozai\\plugin-notices\\<来源ID>.json
岛仔重启会更换端口与令牌，因此每条通知发送前都重新读取凭据文件。
发送在后台线程进行，失败只记日志，不影响本地气泡。
"""
import json
import queue
import socket
import threading
import time
import uuid
from pathlib import Path

MAX_TITLE = 120
MAX_MARKDOWN = 32 * 1024
TIMEOUT = 1.0
RETRY_DELAYS = (0.3, 0.6, 1.2)
SOURCE_PREFIX = {"nacos": "[Nacos] ", "jenkins": "[Jenkins] "}


def _fit(text, limit):
    """按 UTF-8 字节截断，避免超出协议长度限制"""
    text = text or ""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", "ignore")


def _load_credentials(path):
    creds = json.loads(Path(path).read_text(encoding="utf-8"))
    if creds.get("version") != 1 or creds.get("host") != "127.0.0.1":
        raise ValueError("需要 v1 本机通知凭据")
    for key in ("port", "source", "token"):
        if key not in creds:
            raise ValueError("凭据缺少字段: " + key)
    return creds


def _request(creds, method, **fields):
    body = {key: creds[key] for key in ("version", "source", "token")}
    body.update(method=method, **fields)
    frame = (json.dumps(body, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.create_connection(("127.0.0.1", int(creds["port"])), timeout=TIMEOUT) as conn:
        conn.sendall(frame)
        line = conn.makefile("rb").readline(128 * 1024)
    return json.loads(line)


def send_once(path, event):
    """发一条通知，busy 时退避重试；返回 (ok, message)"""
    prefix = SOURCE_PREFIX.get(event.get("source"), "")
    card = {
        "id": uuid.uuid4().hex,
        "title": _fit(prefix + (event.get("title") or ""), MAX_TITLE),
        "markdown": _fit(event.get("body") or "", MAX_MARKDOWN),
    }
    last = "未知错误"
    for delay in (0,) + RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            resp = _request(_load_credentials(path), "notify", **card)
        except (OSError, ValueError, KeyError) as exc:
            return False, str(exc)
        if resp.get("ok"):
            return True, ""
        last = resp.get("error") or last
        if last != "busy":
            return False, last
    return False, last


def test_connection(path):
    """用 status 方法验证凭据有效且岛仔在线，不产生通知"""
    try:
        creds = _load_credentials(path)
        resp = _request(creds, "status")
    except (OSError, ValueError, KeyError) as exc:
        return False, str(exc)
    if resp.get("ok"):
        return True, "连接成功，来源：" + str(creds.get("source"))
    return False, resp.get("error") or "未知错误"


class DaozaiSink:
    """后台队列消费者：仅在启用且有凭据路径时投递"""

    def __init__(self):
        self._path = ""
        self._enabled = False
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def configure(self, path, enabled):
        self._path = (path or "").strip()
        self._enabled = bool(enabled and self._path)

    def push(self, event):
        if self._enabled:
            self._queue.put(dict(event))

    def _run(self):
        while True:
            event = self._queue.get()
            try:
                ok, error = send_once(self._path, event)
                if not ok:
                    print("[Daozai] 通知发送失败: " + str(error))
            except Exception as exc:
                print("[Daozai] 通知异常: " + str(exc))


def create_sink(cfg):
    notify_cfg = cfg.get("notify") or {}
    sink = DaozaiSink()
    sink.configure(notify_cfg.get("daozai_credentials", ""),
                   bool(notify_cfg.get("daozai_enabled")))
    return sink
