"""
代理轮换系统 - 从 GeekEZ 配置提取 Shadowsocks 代理并管理
"""
import json
import base64
import subprocess
import time
import os
import signal

PROFILES_PATH = "/Users/pingchuan/Library/Application Support/geekez-browser/BrowserProfiles/profiles.json"
SS_LOCAL = "/opt/homebrew/bin/ss-local"
PID_DIR = "/tmp/ss_proxies"

def decode_ss_url(ss_url):
    """解码 ss:// URL，返回 (method, password, server, port, name)"""
    # ss://base64(method:password)@server:port#name
    rest = ss_url.replace("ss://", "")
    
    # Split on @ to get encoded part and server part
    if "@" in rest:
        encoded, server_part = rest.split("@", 1)
    else:
        return None
    
    # Split server part
    if "#" in server_part:
        server_part, name = server_part.split("#", 1)
    else:
        name = "unknown"
    
    if ":" in server_part:
        server, port = server_part.rsplit(":", 1)
        port = int(port)
    else:
        return None
    
    # Decode base64 part
    try:
        # Add padding if needed
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += "=" * padding
        decoded = base64.b64decode(encoded).decode("utf-8")
    except:
        return None
    
    if ":" in decoded:
        method, password = decoded.split(":", 1)
    else:
        return None
    
    return {
        "method": method,
        "password": password,
        "server": server,
        "port": port,
        "name": name.strip()
    }

def load_shadowsocks_proxies():
    """从 GeekEZ 配置加载所有 ss:// 代理"""
    if not os.path.exists(PROFILES_PATH):
        print(f"[Error] 找不到配置文件: {PROFILES_PATH}")
        return []
    
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    
    proxies = []
    seen_servers = set()
    
    for p in profiles:
        proxy_str = p.get("proxyStr", "")
        if proxy_str and proxy_str.startswith("ss://"):
            # Strip trailing newline/whitespace
            proxy_str = proxy_str.strip()
            info = decode_ss_url(proxy_str)
            if info and info["server"] not in seen_servers:
                seen_servers.add(info["server"])
                info["profile_name"] = p.get("name", "unknown")
                proxies.append(info)
    
    return proxies

def start_ss_local(proxy_info, local_port):
    """启动一个 ss-local 实例"""
    config = {
        "server": proxy_info["server"],
        "server_port": proxy_info["port"],
        "method": proxy_info["method"],
        "password": proxy_info["password"],
        "local_address": "127.0.0.1",
        "local_port": local_port,
        "timeout": 60
    }
    
    config_path = f"/tmp/ss_config_{local_port}.json"
    with open(config_path, "w") as f:
        json.dump(config, f)
    
    pid_file = f"/tmp/ss-local-{local_port}.pid"
    
    # Kill any existing instance on this local port
    subprocess.run(["pkill", "-f", f"ss-local.*{local_port}"], capture_output=True)
    time.sleep(0.5)
    
    proc = subprocess.Popen(
        [SS_LOCAL, "-c", config_path, "-b", "127.0.0.1", "-l", str(local_port), "-f", pid_file],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    time.sleep(1)
    return proc, f"socks5://127.0.0.1:{local_port}"

def stop_all_ss_local():
    """停止所有 ss-local 实例"""
    subprocess.run(["pkill", "-f", "ss-local"], capture_output=True)

class ProxyRotator:
    """代理轮换器"""
    
    def __init__(self, start_port=1080):
        self.proxies = load_shadowsocks_proxies()
        self.start_port = start_port
        self._instances = []
        self._current = 0
        
        if not self.proxies:
            print("[Warning] 没有找到 Shadowsocks 代理，将使用系统代理")
            self.proxies = [{"name": "system_default", "profile_name": "系统代理"}]
    
    def start_proxy(self, index):
        """启动指定索引的代理"""
        stop_all_ss_local()
        time.sleep(1)
        
        if index >= len(self.proxies):
            return None
        
        proxy = self.proxies[index]
        if proxy.get("name") == "system_default":
            return {"proxy": None, "name": "系统代理", "profile_name": "系统代理"}
        
        local_port = self.start_port + index
        try:
            proc, proxy_url = start_ss_local(proxy, local_port)
            result = {
                "proxy": proxy_url,
                "name": proxy["name"],
                "profile_name": proxy["profile_name"],
                "proc": proc,
                "port": local_port,
                "server": proxy["server"]
            }
            print(f"  ✓ 代理 [{proxy['profile_name']}] → SOCKS5 {proxy_url}")
            return result
        except Exception as e:
            print(f"  ✗ 代理启动失败 [{proxy['profile_name']}]: {e}")
            return None
    
    def start_all(self):
        """启动所有代理实例（仅用于测试）"""
        stop_all_ss_local()
        results = []
        for i in range(min(len(self.proxies), 5)):  # 最多启动5个测试
            r = self.start_proxy(i)
            if r:
                results.append(r)
        self._instances = results
        return results
    
    def get_current_proxy(self):
        """获取当前代理"""
        if not self._instances:
            return None
        return self._instances[self._current].get("proxy")
    
    def get_current_name(self):
        """获取当前代理名称"""
        if not self._instances:
            return "无代理"
        return self._instances[self._current].get("profile_name", "unknown")
    
    def rotate(self):
        """切换到下一个代理"""
        if len(self._instances) <= 1:
            return self.get_current_name()
        self._current = (self._current + 1) % len(self._instances)
        return self.get_current_name()
    
    def stop_all(self):
        """停止所有代理"""
        stop_all_ss_local()

if __name__ == "__main__":
    # 测试
    rotator = ProxyRotator()
    print(f"共找到 {len(rotator.proxies)} 个 Shadowsocks 代理:")
    for p in rotator.proxies:
        print(f"  {p['profile_name']}: {p['server']}:{p['port']} [{p['method']}]")
    
    print("\n启动所有代理...")
    instances = rotator.start_all()
    if instances:
        print(f"\n当前代理: {rotator.get_current_proxy()}")
        print(f"轮换后: {rotator.rotate()}")
    
    print("\n停止所有代理...")
    rotator.stop_all()
