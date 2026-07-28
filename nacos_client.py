"""
nacos_client.py - Nacos 3.x Open API Client
"""
import urllib.request
import urllib.parse
import urllib.error
import json
import time


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[Nacos {timestamp}] {msg}")


class NacosClient:
    def __init__(self, ip, port=8848, username="nacos", password="nacos", namespace=""):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.namespace = namespace
        self.base_url = f"http://{ip}:{port}/v3"
        self.token = None
        self.token_expire_time = 0

    def is_token_valid(self):
        return self.token is not None and time.time() < self.token_expire_time

    def login(self):
        log(f"Logging in to {self.base_url}/auth/user/login")
        log(f"Username: {self.username}")
        url = f"{self.base_url}/auth/user/login"
        data = urllib.parse.urlencode({
            "username": self.username,
            "password": self.password
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read().decode("utf-8")
                log(f"Login response status: {resp.status}")
                log(f"Login response body: {resp_body}")
                result = json.loads(resp_body)
                self.token = result.get("accessToken", "")
                self.token_expire_time = time.time() + 1200
                log(f"Token obtained: {self.token[:30]}...")
                return True
        except Exception as e:
            log(f"Login failed: {e}")
            self.token = None
            self.token_expire_time = 0
            return False

    def ensure_login(self):
        if not self.is_token_valid():
            log("Token expired or missing, re-logging in...")
            return self.login()
        return True

    def _add_auth(self, req):
        if self.token:
            req.add_header("accessToken", self.token)
            req.add_header("authorization", f"Bearer {self.token}")

    def _request(self, method, path, params=None, data=None, content_type=None):
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = None
        if data is not None:
            if isinstance(data, dict):
                body = json.dumps(data).encode("utf-8")
            elif isinstance(data, str):
                body = data.encode("utf-8")
            elif isinstance(data, bytes):
                body = data
            else:
                body = str(data).encode("utf-8")

        log(f"REQUEST: {method} {url}")
        if params:
            log(f"  Params: {json.dumps(params, ensure_ascii=False)}")
        if body:
            body_str = body.decode("utf-8", errors="replace")[:500]
            log(f"  Body: {body_str}")

        req = urllib.request.Request(url, data=body, method=method)
        self._add_auth(req)
        if content_type:
            req.add_header("Content-Type", content_type)
        log(f"  Headers: accessToken={self.token[:20] if self.token else "None"}...")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8")
                log(f"RESPONSE: status={resp.status}")
                log(f"  Body: {resp_body[:1000]}")
                return json.loads(resp_body)
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except:
                pass
            log(f"HTTP Error {e.code}: {error_body[:500]}")
            if e.code in (403, 500):
                log("Re-logging in and retrying...")
                self.token = None
                if self.login():
                    return self._request(method, path, params, data, content_type)
            raise
        except Exception:
            raise

    def get_service_list(self, page_no=1, page_size=100):
        log("=== Getting service list ===")
        params = {
            "pageNo": page_no,
            "pageSize": page_size,
            "ignoreEmptyService": "true",
            "withInstances": "false",
            "serviceNameParam": "",
            "groupNameParam": ""
        }
        if self.namespace:
            params["namespaceId"] = self.namespace
        return self._request("GET", "/console/ns/service/list", params=params)

    def get_instance_list(self, service_name, group_name="DEFAULT_GROUP", cluster_name="ShenZhen"):
        log(f"=== Getting instances for {service_name} ===")
        params = {
            "serviceName": service_name,
            "groupName": group_name,
            "clusterName": cluster_name,
            "pageSize": 100,
            "pageNo": 1
        }
        if self.namespace:
            params["namespaceId"] = self.namespace
        return self._request("GET", "/console/ns/instance/list", params=params)

    def update_instance_status(self, service_name, ip, port, enabled=True,
                              cluster_name="ShenZhen", group_name="DEFAULT_GROUP",
                              ephemeral=True, weight=1, metadata=None):
        log(f"=== Updating instance status: {service_name} {ip}:{port} enabled={enabled} ===")
        params = {
            "serviceName": service_name,
            "clusterName": cluster_name,
            "groupName": group_name,
            "ip": ip,
            "port": port,
            "ephemeral": str(ephemeral).lower(),
            "weight": weight,
            "enabled": str(enabled).lower(),
        }
        if metadata:
            params["metadata"] = metadata
        if self.namespace:
            params["namespaceId"] = self.namespace
        body = urllib.parse.urlencode(params).encode("utf-8")
        return self._request("PUT", "/console/ns/instance", data=body,
                           content_type="application/x-www-form-urlencoded")

    def get_all_services_with_status(self):
        log("=== Getting all services with status ===")
        service_list_data = self.get_service_list(page_size=500)
        services = service_list_data.get("data", {}).get("pageItems", [])
        log(f"Found {len(services)} services")
        result = []
        for item in services:
            try:
                service_name = item.get("name", "")
                instance_data = self.get_instance_list(service_name)
                hosts = instance_data.get("data", {}).get("pageItems", [])
                log(f"  {service_name}: {len(hosts)} instances")
                for host in hosts:
                    result.append({
                        "service_name": item.get("name", ""),
                        "ip": host.get("ip", ""),
                        "port": host.get("port", 0),
                        "enabled": host.get("enabled", True),
                        "healthy": host.get("healthy", True),
                        "online": host.get("enabled", True) and host.get("healthy", True),
                    })
            except Exception as e:
                print(f"Get {service_name} instances failed: {e}")
        log(f"Total: {len(result)} instances")
        return result