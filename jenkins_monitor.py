"""
jenkins_monitor.py - Jenkins 构建轮询与事件生成

职责：
- 独立线程按配置间隔轮询 Jenkins，失败不影响 Nacos 通知源
- 首次观察或过滤规则变化后的新 Job 只静默建立基线
- 只在构建开始、构建结束时产生通知事件
- 按 commit id 去重，只展示新提交
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from jenkins_client import (
    JenkinsClient,
    format_commit_line,
    format_duration,
    format_timestamp,
    log,
    new_commits,
)

_POLL_WORKERS = 6
_DISCOVERY_TTL = 300
_SHOWN_COMMITS_LIMIT = 200


def filter_jobs(jobs, include, exclude):
    """按完整 Job 路径做不区分大小写的包含/排除匹配，排除优先"""
    includes = [s.strip().lower() for s in (include or "").split(",") if s.strip()]
    excludes = [s.strip().lower() for s in (exclude or "").split(",") if s.strip()]
    result = []
    for job in jobs:
        name = job["name"].lower()
        if includes and not any(key in name for key in includes):
            continue
        if any(key in name for key in excludes):
            continue
        result.append(job)
    return result


class JenkinsMonitor:
    def __init__(self, config_provider, notes_provider, dnd_provider,
                 on_events, on_status, client_factory=JenkinsClient):
        self._config_provider = config_provider
        self._notes_provider = notes_provider
        self._dnd_provider = dnd_provider
        self._on_events = on_events
        self._on_status = on_status
        self._client_factory = client_factory

        self._state = config.load_jenkins_state()
        self._thread = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._force_discovery = True
        self._jobs_cache = []
        self._jobs_cache_at = 0.0
        self._jobs_cache_filters = None
        self._snapshot = []
        self._in_error = False
        self._unconfigured_emitted = False
        self._last_filtered_names = set()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="JenkinsMonitor")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._wake_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None

    def poll_now(self, force_discovery=False):
        if force_discovery:
            self._force_discovery = True
        self._wake_event.set()

    def _loop(self):
        while not self._stop_event.is_set():
            cfg = dict(self._config_provider() or {})
            interval = self._interval(cfg)
            if not self._configured(cfg):
                if not self._unconfigured_emitted:
                    self._unconfigured_emitted = True
                    self._emit_status({
                        "state": "unconfigured",
                        "configured": False,
                        "error": "",
                        "jobs": self._snapshot,
                        "last_success": self._state.get("last_success", ""),
                        "last_error": self._state.get("last_error", ""),
                    })
                self._wake_event.wait(5)
                self._wake_event.clear()
                continue
            self._unconfigured_emitted = False
            try:
                self._poll_once(cfg)
            except Exception as exc:
                self._handle_error(exc)
            self._wake_event.wait(interval)
            self._wake_event.clear()

    @staticmethod
    def _interval(cfg):
        try:
            value = int(cfg.get("poll_interval", 30))
        except Exception:
            value = 30
        return max(10, min(value, 3600))

    @staticmethod
    def _configured(cfg):
        if not bool((cfg or {}).get("enabled", True)):
            return False
        return bool(cfg.get("url") and cfg.get("username") and cfg.get("password"))

    def _poll_once(self, cfg):
        started_at = time.time()
        client = self._client_factory(
            cfg.get("url", ""), cfg.get("username", ""), cfg.get("password", ""),
            bool(cfg.get("verify_ssl", True)))
        filters_key = (cfg.get("include", ""), cfg.get("exclude", ""))
        need_discovery = (
            self._force_discovery
            or not self._jobs_cache
            or filters_key != self._jobs_cache_filters
            or started_at - self._jobs_cache_at > _DISCOVERY_TTL
        )
        if need_discovery:
            self._jobs_cache = client.discover_jobs()
            self._jobs_cache_at = started_at
            self._jobs_cache_filters = filters_key
            self._force_discovery = False
            self._prune_deleted_jobs({job["name"] for job in self._jobs_cache})
        jobs = filter_jobs(self._jobs_cache, cfg.get("include", ""), cfg.get("exclude", ""))
        current_names = {job["name"] for job in jobs}
        if self._last_filtered_names:
            jobs_state = self._state.setdefault("jobs", {})
            for name in current_names - self._last_filtered_names:
                job_state = jobs_state.get(name)
                if isinstance(job_state, dict):
                    job_state["initialized"] = False
        self._last_filtered_names = current_names
        log(f"Polling {len(jobs)} filtered jobs")

        results = []
        job_errors = []
        if jobs:
            with ThreadPoolExecutor(max_workers=min(_POLL_WORKERS, len(jobs))) as executor:
                futures = {executor.submit(client.get_last_build, job): job for job in jobs}
                for future in as_completed(futures):
                    job = futures[future]
                    try:
                        results.append((job, future.result()))
                    except Exception as exc:
                        job_errors.append(str(exc))
                        results.append((job, None))
        if job_errors and len(job_errors) == len(jobs):
            raise RuntimeError(job_errors[0])

        notes = self._notes_provider() or {}
        aliases = dict(notes.get("jenkins") or {})
        dnd = self._dnd_provider() or {}
        muted = dict(dnd.get("jenkins") or {})

        events = []
        snapshot = []
        jobs_state = self._state.setdefault("jobs", {})
        for job, info in results:
            name = job["name"]
            job_state = jobs_state.setdefault(name, {})
            alias = aliases.get(name, "")
            is_muted = name in muted
            if info is None:
                snapshot.append(self._empty_snapshot(job, job_state, is_muted))
                continue
            self._apply_job_state(job_state, info, cfg, name, alias, is_muted, events)
            snapshot.append(self._build_snapshot(job, job_state, info, is_muted))

        self._state["last_success"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._state["last_error"] = ""
        config.save_jenkins_state(self._state)
        self._snapshot = self._sort_snapshot(snapshot)

        if self._in_error:
            self._in_error = False
            events.insert(0, {
                "source": "jenkins",
                "level": "info",
                "title": "Jenkins 连接恢复",
                "body": "已恢复与 " + cfg.get("url", "") + " 的连接",
                "url": "",
                "key": "jenkins:connection:recovered",
                "time": time.time(),
            })
        if events:
            self._on_events(events)
        self._emit_status({
            "state": "ok",
            "configured": True,
            "error": "",
            "jobs": self._snapshot,
            "last_success": self._state["last_success"],
            "last_error": "",
            "polled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    def _apply_job_state(self, job_state, info, cfg, name, alias, muted, events):
        number = info["number"]
        building = info["building"]
        result = info["result"] or ""
        initialized = bool(job_state.get("initialized"))
        if not initialized:
            job_state["initialized"] = True
            if building:
                # 首次观察到正在构建：不补发开始通知，但构建结束时正常通知
                job_state["last_number"] = number
                job_state["notified_build"] = max(number - 1, 0)
                job_state["shown_commits"] = []
            else:
                job_state["last_number"] = number
                job_state["notified_build"] = number
                job_state["shown_commits"] = self._commit_ids(info.get("commits"))
            job_state["last_result"] = "BUILDING" if building else result
            job_state["last_start"] = info.get("timestamp", 0)
            job_state["last_duration"] = info.get("duration", 0)
            job_state["last_url"] = info.get("url", "")
            job_state["last_branch"] = info.get("branch", "-")
            job_state["last_project"] = info.get("project", "")
            job_state["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return

        previous_notified = int(job_state.get("notified_build", 0))
        if building:
            if number > int(job_state.get("last_number", 0)):
                job_state["last_number"] = number
                job_state["last_start"] = info.get("timestamp", 0)
                job_state["last_result"] = "BUILDING"
                if cfg.get("notify_start", True) and not muted:
                    events.append(self._build_start_event(
                        name, alias, number, info))
            return

        if number > previous_notified:
            commits = info.get("commits") or []
            shown = job_state.get("shown_commits") or []
            display, fresh_count = new_commits(commits, shown)
            success = result == "SUCCESS"
            enabled = cfg.get("notify_success", True) if success else cfg.get("notify_failure", True)
            if enabled and not muted:
                events.append(self._build_end_event(
                    name, alias, number, info, display, fresh_count, success))
            job_state["shown_commits"] = self._merge_shown(shown, commits)
            job_state["notified_build"] = number
        job_state["last_number"] = max(number, int(job_state.get("last_number", 0)))
        job_state["last_result"] = result
        job_state["last_start"] = info.get("timestamp", 0)
        job_state["last_duration"] = info.get("duration", 0)
        job_state["last_url"] = info.get("url", "")
        job_state["last_branch"] = info.get("branch", "-")
        job_state["last_project"] = info.get("project", "")
        job_state["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _commit_ids(commits):
        return [c["id"] for c in (commits or []) if c.get("id")]

    def _merge_shown(self, shown, commits):
        merged = list(shown or [])
        existing = set(merged)
        for commit_id in self._commit_ids(commits):
            if commit_id not in existing:
                merged.append(commit_id)
                existing.add(commit_id)
        return merged[-_SHOWN_COMMITS_LIMIT:]

    @staticmethod
    def _job_label(name, alias):
        """标题用的项目名：优先备注，其次 Job 路径最后一段（与完整路径区分）"""
        alias = (alias or "").strip()
        if alias:
            return alias
        name = str(name or "").strip()
        return name.rsplit("/", 1)[-1] if "/" in name else name

    @staticmethod
    def _project_label(name, alias, build_project=""):
        """正文展示的项目名：优先构建参数 PROJECT，其次备注，最后 Job 路径"""
        value = (build_project or "").strip()
        if value:
            return value
        alias = (alias or "").strip()
        if alias and alias != name:
            return alias + "（" + name + "）"
        return name

    def _event_lines(self, name, alias, number, info):
        branch = info.get("branch", "-")
        env = self._environment(name, branch)
        project = self._project_label(name, alias, info.get("project", ""))
        lines = [
            "项目：" + project,
            "构建：#" + str(number),
        ]
        if branch and branch != "-":
            lines.append("分支：" + branch)
        if env != "-":
            lines.append("环境：" + env)
        return lines

    @staticmethod
    def _environment(job_name, branch):
        """分支优先推断环境：main/master 对应生产，test 对应测试；其余按 Job 路径与分支推断"""
        text = str(branch or "-").strip().lower()
        if text.startswith("main") or text.startswith("master"):
            return "生产"
        if text.startswith("test"):
            return "测试"
        lowered = (job_name or "").lower()
        segments = [s for s in lowered.split("/") if s]
        last = segments[-1] if segments else ""
        for key, label in (("prod", "生产"), ("production", "生产"),
                           ("online", "生产"), ("release", "预发"),
                           ("pre", "预发"), ("staging", "预发"),
                           ("test", "测试"), ("dev", "开发")):
            if key in segments or key in last:
                return label
        if text.startswith("release") or text.startswith("hotfix"):
            return "预发"
        if text.startswith("dev") or text.startswith("feature") \
                or text.startswith("bugfix"):
            return "开发"
        return "-"

    def _event_title(self, name, alias, info, action):
        """标题格式：项目名 环境 动作，如 om test 构建成功"""
        project = (str(info.get("project") or "").strip()
                   or self._job_label(name, alias))
        env = self._environment(name, info.get("branch", "-"))
        parts = [project]
        if env != "-":
            parts.append(env)
        parts.append(action)
        return " ".join(parts)

    def _build_start_event(self, name, alias, number, info):
        start = format_timestamp(info.get("timestamp", 0))
        lines = self._event_lines(name, alias, number, info)
        lines.append("开始：" + start)
        return {
            "source": "jenkins",
            "level": "info",
            "title": self._event_title(name, alias, info, "构建开始"),
            "body": "\n".join(lines),
            "url": info.get("url", ""),
            "key": "jenkins:" + name + "#" + str(number) + ":start",
            "time": time.time(),
        }

    def _build_end_event(self, name, alias, number, info, display, fresh_count, success):
        start_ts = info.get("timestamp", 0)
        duration = info.get("duration", 0)
        end_ts = (start_ts + duration) if (start_ts and duration) else start_ts
        branch = info.get("branch", "-")
        env = self._environment(name, branch)
        lines = self._event_lines(name, alias, number, info)
        lines.append(
            "开始：" + format_timestamp(start_ts) + " · 结束：" + format_timestamp(end_ts))
        lines.append("用时：" + format_duration(duration))
        if display:
            lines.append("新提交：")
            for commit in display:
                lines.append(format_commit_line(commit))
            if fresh_count > len(display):
                lines.append("等 " + str(fresh_count) + " 条")
        return {
            "source": "jenkins",
            "level": "success" if success else "error",
            "title": self._event_title(
                name, alias, info, "构建成功" if success else "构建失败"),
            "body": "\n".join(lines),
            "url": info.get("url", ""),
            "key": "jenkins:" + name + "#" + str(number) + ":end",
            "time": time.time(),
        }

    def _build_snapshot(self, job, job_state, info, muted):
        building = info.get("building")
        result = info.get("result") or ""
        return {
            "name": job["name"],
            "number": info.get("number", 0),
            "building": building,
            "result": result,
            "success": (not building) and result == "SUCCESS",
            "failure": (not building) and bool(result) and result != "SUCCESS",
            "timestamp": info.get("timestamp", 0),
            "duration": info.get("duration", 0),
            "url": info.get("url") or job["url"],
            "branch": info.get("branch", "-"),
            "project": info.get("project", "") or job_state.get("last_project", ""),
            "muted": muted,
            "updated": job_state.get("updated", ""),
        }

    @staticmethod
    def _empty_snapshot(job, job_state, muted):
        return {
            "name": job["name"],
            "number": int(job_state.get("last_number", 0) or 0),
            "building": False,
            "result": str(job_state.get("last_result", "") or ""),
            "success": False,
            "failure": False,
            "timestamp": int(job_state.get("last_start", 0) or 0),
            "duration": int(job_state.get("last_duration", 0) or 0),
            "url": job_state.get("last_url") or job["url"],
            "branch": job_state.get("last_branch", "-"),
            "project": job_state.get("last_project", ""),
            "muted": muted,
            "updated": job_state.get("updated", ""),
        }

    @staticmethod
    def _sort_snapshot(snapshot):
        """按最近构建时间倒序；从未构建的（时间为 0）排最后"""
        return sorted(snapshot,
                      key=lambda item: (-int(item.get("timestamp") or 0),
                                        item.get("name") or ""))

    def _prune_deleted_jobs(self, existing_names):
        jobs_state = self._state.get("jobs") or {}
        removed = [name for name in jobs_state if name not in existing_names]
        for name in removed:
            jobs_state.pop(name, None)
        if removed:
            log(f"Pruned {len(removed)} deleted jobs from state")

    def _handle_error(self, exc):
        message = str(exc)
        previous = self._state.get("last_error", "")
        self._state["last_error"] = message
        if not self._in_error or previous != message:
            config.save_jenkins_state(self._state)
        self._emit_status({
            "state": "error",
            "configured": True,
            "error": message,
            "jobs": self._snapshot,
            "last_success": self._state.get("last_success", ""),
            "last_error": message,
        })
        if not self._in_error:
            self._in_error = True
            self._on_events([{
                "source": "jenkins",
                "level": "warning",
                "title": "Jenkins 连接失败",
                "body": message,
                "url": "",
                "key": "jenkins:connection:error",
                "time": time.time(),
            }])

    def _emit_status(self, status):
        try:
            self._on_status(status)
        except Exception as exc:
            log(f"Status callback failed: {exc}")
