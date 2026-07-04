"""测试所有代理找到可用的"""
import subprocess
import time
from proxy_rotator import ProxyRotator, start_ss_local

pkill = lambda: subprocess.run(['pkill', '-f', 'ss-local'], capture_output=True)
pkill()
time.sleep(1)

rotator = ProxyRotator()
working = []

for i, proxy in enumerate(rotator.proxies):
    port = 11000 + i
    try:
        proc, url = start_ss_local(proxy, port)
        time.sleep(1.5)
        
        result = subprocess.run(
            ['curl', '--socks5-hostname', f'127.0.0.1:{port}', '-s',
             '--connect-timeout', '8', '--max-time', '12', 'https://httpbin.org/ip'],
            capture_output=True, text=True, timeout=15
        )
        ip = result.stdout.strip()
        if ip and 'origin' in ip:
            print(f"  ✓ [{proxy['profile_name']}] IP={ip}")
            working.append((proxy['profile_name'], url, ip))
        else:
            print(f"  ✗ [{proxy['profile_name']}]")
    except Exception as e:
        err = str(e)[:60]
        print(f"  ✗ [{proxy['profile_name']}] {err}")
    finally:
        subprocess.run(['pkill', '-f', f'ss-local.*{port}'], capture_output=True)
        time.sleep(0.5)

print(f"\n=== 可用代理: {len(working)} ===")
for name, url, ip in working:
    print(f"  ✓ {name}: {url} ({ip})")

# Save working proxies
with open('working_proxies.txt', 'w') as f:
    for name, url, ip in working:
        f.write(f"{name}|{url}|{ip}\n")
print(f"\n已保存到 working_proxies.txt")
