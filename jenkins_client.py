"""
jenkins_client.py - Jenkins REST API 客户端（纯标准库）

复用 help-memory-system 中 JenkinsMonitorService 的请求路径、错误语义与提交筛选规则：
- Basic Auth（用户名 + 密码）逐次请求
- 递归展开文件夹 / 多分支，只监控叶子 Job
- 从构建参数提取分支，格式化用时与时间
"""
import base64
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

_LOG_ENABLED = True
_TIMEOUT = 10
_MAX_DEPTH = 6
_MAX_JOBS = 2000
_COMMIT_LIMIT = 5
_COMMIT_MESSAGE_MAX = 80
_RECENT_SCAN = 30
_RECENT_SUCCESS_LIMIT = 3

_VALID_COMMIT_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]*\))?!?:",
    re.IGNORECASE,
)
_MERGE_COMMIT_RE = re.compile(r"^merged?\b", re.IGNORECASE)


def log(msg):
    if not _LOG_ENABLED:
        return
    print(f"[Jenkins {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def set_log_enabled(enabled):
    global _LOG_ENABLED
    _LOG_ENABLED = enabled


class JenkinsError(Exception):
    pass


def normalize_base_url(url):
    """去掉首尾空白、/login 子路径与尾部斜杠，缺少协议时补 http://"""
    text = (url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    login_idx = text.find("/login")
    if login_idx > 0:
        text = text[:login_idx]
    while text.endswith("/"):
        text = text[:-1]
    return text


def format_duration(millis):
    if not millis or millis <= 0:
        return "-"
    seconds = int(millis) // 1000
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分 {seconds % 60} 秒"
    return f"{seconds // 3600} 时 {seconds % 3600 // 60} 分"


def format_timestamp(timestamp_ms):
    if not timestamp_ms or timestamp_ms <= 0:
        return "-"
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def resolve_param(node, *names):
    """按名称优先级从构建参数中提取首个非空字符串值"""
    wanted = [n.upper() for n in names]
    candidates = []
    for action in node.get("actions") or []:
        params = action.get("parameters") if isinstance(action, dict) else None
        if not isinstance(params, list):
            continue
        for param in params:
            if not isinstance(param, dict):
                continue
            name = str(param.get("name") or "")
            value = param.get("value")
            if isinstance(value, str) and value.strip():
                candidates.append((name.upper(), value.strip()))
    for name in wanted:
        for param_name, value in candidates:
            if param_name == name:
                return value
    return ""


def resolve_branch(node):
    """从构建参数的 BRANCH_NAME 或包含 BRANCH 的参数提取分支"""
    branch = resolve_param(node, "BRANCH_NAME", "BRANCH")
    if branch:
        return branch
    for action in node.get("actions") or []:
        params = action.get("parameters") if isinstance(action, dict) else None
        if not isinstance(params, list):
            continue
        for param in params:
            if not isinstance(param, dict):
                continue
            name = str(param.get("name") or "")
            if "BRANCH" in name.upper():
                value = param.get("value")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return "-"


def _is_container(class_name):
    text = class_name or ""
    if "MatrixProject" in text:
        return False
    return ("Folder" in text) or ("MultiBranch" in text)


def select_display_commits(commits, limit=_COMMIT_LIMIT):
    """最新两条无条件保留，其余只保留约定式前缀且排除 merge"""
    if not commits:
        return []
    display = list(commits[:2])
    for commit in commits[2:]:
        if len(display) >= limit:
            break
        message = commit.get("msg") or ""
        if _MERGE_COMMIT_RE.match(message):
            continue
        if _VALID_COMMIT_RE.match(message):
            display.append(commit)
    return display[:limit]


def new_commits(commits, shown_ids, limit=_COMMIT_LIMIT):
    """过滤已通知提交后，按规则挑选展示用提交；返回 (展示列表, 新提交总数)"""
    if not commits:
        return [], 0
    shown = set(shown_ids or ())
    fresh = [c for c in commits if c.get("id") and c["id"] not in shown]
    if not fresh:
        return [], 0
    return select_display_commits(fresh, limit), len(fresh)


def format_commit_line(commit):
    message = " ".join((commit.get("msg") or "").split())
    if len(message) > _COMMIT_MESSAGE_MAX:
        message = message[:_COMMIT_MESSAGE_MAX] + "…"
    author = commit.get("author") or ""
    line = f"「{commit.get('id', '')[:7]}」 {message}"
    if author:
        line += f" <{author}>"
    return line


class JenkinsClient:
    def __init__(self, url, username="", password="", verify_ssl=True):
        self.base_url = normalize_base_url(url)
        self.username = username or ""
        self.password = password or ""
        self.verify_ssl = bool(verify_ssl)

    def _auth_header(self):
        raw = f"{self.username}:{self.password}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _get_json(self, url, timeout=_TIMEOUT):
        if not url:
            raise JenkinsError("缺少 Jenkins 地址")
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", self._auth_header())
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "TrayNotifyTool/2.0")
        context = None
        if url.lower().startswith("https") and not self.verify_ssl:
            context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise JenkinsError(
                    f"Jenkins 认证失败（HTTP {exc.code}），请检查账号密码是否正确"
                ) from exc
            if exc.code == 404:
                raise JenkinsError(
                    "Jenkins 路径不存在（HTTP 404），请检查地址或 Job 名称"
                ) from exc
            raise JenkinsError(f"Jenkins 返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise JenkinsError(f"无法连接 Jenkins：{exc.reason}") from exc
        except Exception as exc:
            raise JenkinsError(f"Jenkins 请求失败：{exc}") from exc
        try:
            return json.loads(body)
        except Exception as exc:
            raise JenkinsError("Jenkins 返回的不是 JSON，请检查地址是否指向 Jenkins") from exc

    def _jobs_url(self, container_url):
        tree = "jobs[name,url,color,_class]"
        return container_url + "/api/json?" + urllib.parse.urlencode({"tree": tree})

    def discover_jobs(self):
        """递归展开容器，返回叶子 Job 列表；达到上限时记录截断警告"""
        jobs = []
        self._walk(self.base_url, "", 0, jobs, set())
        if len(jobs) >= _MAX_JOBS:
            log("Job count reached the %d limit; discovery is truncated" % _MAX_JOBS)
        else:
            log(f"Discovered {len(jobs)} jobs")
        return jobs

    def _walk(self, container_url, prefix, depth, out, seen):
        if depth > _MAX_DEPTH or len(out) >= _MAX_JOBS:
            return
        if container_url in seen:
            return
        seen.add(container_url)
        data = self._get_json(self._jobs_url(container_url))
        for node in data.get("jobs") or []:
            if not isinstance(node, dict):
                continue
            name = str(node.get("name") or "").strip()
            if not name:
                continue
            full_name = f"{prefix}/{name}" if prefix else name
            job_url = str(node.get("url") or "").rstrip("/")
            if job_url.startswith("/"):
                job_url = self.base_url + job_url
            class_name = str(node.get("_class") or "")
            if _is_container(class_name) and job_url:
                self._walk(job_url, full_name, depth + 1, out, seen)
                continue
            if not job_url:
                continue
            out.append({
                "name": full_name,
                "url": job_url,
                "color": str(node.get("color") or ""),
                "class": class_name,
            })
            if len(out) >= _MAX_JOBS:
                return

    def get_last_build(self, job):
        tree = (
            "number,building,result,timestamp,duration,url,"
            "actions[parameters[name,value]],"
            "changeSet[items[id,commitId,msg,author[fullName],timestamp]]"
        )
        query = urllib.parse.urlencode({"tree": tree})
        url = job["url"] + "/lastBuild/api/json?" + query
        try:
            node = self._get_json(url)
        except JenkinsError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        return self._parse_build(node)

    def _parse_build(self, node):
        if not isinstance(node, dict):
            return None
        commits = []
        for item in ((node.get("changeSet") or {}).get("items") or []):
            if not isinstance(item, dict):
                continue
            commit_id = item.get("commitId") or item.get("id") or ""
            if not commit_id:
                continue
            author = item.get("author") or {}
            if isinstance(author, dict):
                author = author.get("fullName") or author.get("absoluteUrl") or ""
            commits.append({
                "id": str(commit_id),
                "msg": str(item.get("msg") or "").strip(),
                "author": str(author or ""),
                "timestamp": item.get("timestamp") or 0,
            })
        return {
            "number": int(node.get("number") or 0),
            "building": bool(node.get("building")),
            "result": str(node.get("result") or ""),
            "timestamp": int(node.get("timestamp") or 0),
            "duration": int(node.get("duration") or 0),
            "url": str(node.get("url") or ""),
            "branch": resolve_branch(node),
            "project": resolve_param(node, "PROJECT", "PROJECT_NAME"),
            "commits": commits,
        }

    def get_recent_success_builds(self, job, limit=_RECENT_SUCCESS_LIMIT):
        """按需读取该 Job 最近若干次构建，返回最近 limit 个成功构建（含提交）"""
        tree = (
            "builds[number,result,timestamp,duration,url,"
            "actions[parameters[name,value]],"
            "changeSet[items[id,commitId,msg,author[fullName],timestamp]]]"
            "{0," + str(_RECENT_SCAN) + "}"
        )
        query = urllib.parse.urlencode({"tree": tree})
        node = self._get_json(job["url"] + "/api/json?" + query)
        builds = []
        for item in (node or {}).get("builds") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("result") or "") != "SUCCESS":
                continue
            parsed = self._parse_build(item)
            if parsed:
                builds.append(parsed)
            if len(builds) >= max(1, int(limit)):
                break
        return builds

    def test_connection(self):
        """验证认证并返回可见 Job 数量与样例名称"""
        if not self.base_url:
            raise JenkinsError("请填写 Jenkins 地址")
        if not self.username or not self.password:
            raise JenkinsError("请填写 Jenkins 账号和密码")
        jobs = self.discover_jobs()
        names = [job["name"] for job in jobs]
        return {
            "count": len(names),
            "names": names[:20],
            "truncated": len(names) > 20,
        }
