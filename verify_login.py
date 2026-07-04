"""
验证 Outlook 账号是否真正注册成功
尝试登录并检查是否进入 inbox
"""
import time
import subprocess
import urllib.request
import json
import socket
import os
from playwright.sync_api import sync_playwright

EMAIL = "lwbvpivszjhfcw@outlook.com"
PASSWORD = "yjtZDqK*HC70s"

def start_chrome():
    user_data_dir = "/tmp/chrome_verify_outlook"
    debug_port = 25000
    subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)
    time.sleep(1)
    chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    launch_args = [
        chrome_path, f'--user-data-dir={user_data_dir}',
        f'--remote-debugging-port={debug_port}',
        '--remote-allow-origins=*', '--no-first-run',
        '--no-default-browser-check', '--disable-blink-features=AutomationControlled',
    ]
    subprocess.Popen(launch_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(15):
        time.sleep(1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', debug_port))
        sock.close()
        if result == 0:
            return debug_port
    return None

def get_ws_url(debug_port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/version", timeout=5) as r:
            return json.loads(r.read()).get('webSocketDebuggerUrl', '')
    except:
        return None

print("=" * 60)
print(f"验证账号: {EMAIL}")
print("=" * 60)

debug_port = start_chrome()
if not debug_port:
    print("✗ Chrome 启动失败")
    exit(1)

ws_url = get_ws_url(debug_port)
if not ws_url:
    print("✗ 获取 WebSocket URL 失败")
    exit(1)

p = sync_playwright().start()
try:
    browser = p.chromium.connect_over_cdp(ws_url, timeout=30000)
    page = browser.contexts[0].pages[0]

    # 1. 直接导航到登录页
    print("[1/5] 导航到登录页...")
    page.goto("https://login.live.com/", timeout=30000, wait_until="domcontentloaded")
    time.sleep(3)

    page.screenshot(path="/tmp/outlook_verify_01_login_page.png")
    print(f"  当前 URL: {page.url}")

    # 2. 输入邮箱
    print("[2/5] 输入邮箱...")
    try:
        # 等待邮箱输入框出现
        email_input = page.locator('input[type="email"]')
        email_input.wait_for(timeout=10000)
        email_input.fill(EMAIL)
        print(f"  已输入邮箱: {EMAIL}")
        time.sleep(1)
        # 点击下一步
        next_btn = page.locator('input[type="submit"], button[type="submit"]').first
        next_btn.wait_for(timeout=5000)
        next_btn.click()
        print("  已点击下一步")
        time.sleep(3)
    except Exception as e:
        print(f"  邮箱输入异常: {e}")
        page.screenshot(path="/tmp/outlook_verify_02_email_fail.png")

    # 3. 输入密码
    print("[3/5] 输入密码...")
    try:
        page.screenshot(path="/tmp/outlook_verify_03_before_pw.png")
        # 等待密码输入框出现，role textbox with name containing password
        pw_input = page.locator('input[type="password"], input[name="passwd"]').first
        pw_input.wait_for(timeout=15000)
        pw_input.fill(PASSWORD)
        print(f"  已输入密码")
        time.sleep(1)
        # 点击登录
        signin_btn = page.locator('input[type="submit"], button[type="submit"]').first
        signin_btn.wait_for(timeout=5000)
        signin_btn.click()
        print("  已点击登录")
        time.sleep(5)
    except Exception as e:
        print(f"  密码输入异常: {e}")
        page.screenshot(path="/tmp/outlook_verify_04_pw_fail.png")

    # 处理"保持登录"弹窗
    try:
        no_btn = page.locator('input[type="button"][value="否"], button:has-text("否"), #declineButton')
        if no_btn.count() > 0:
            no_btn.click()
            print("  已点击'否'（不保持登录）")
            time.sleep(3)
    except:
        pass

    # 处理"已登录"页面跳转
    try:
        page.wait_for_url("**/outlook.live.com/mail/**", timeout=15000)
    except:
        pass

    # 4. 检查结果
    print("[5/5] 检查登录结果...")
    time.sleep(3)

    page.screenshot(path="/tmp/outlook_verify_05_result.png")
    current_url = page.url
    current_title = page.title()

    print(f"\n当前 URL: {current_url}")
    print(f"页面标题: {current_title}")

    if 'outlook.live.com/mail' in current_url or '收件箱' in current_title:
        print(f"\n✅ 登录成功！账号 {EMAIL} 已验证通过，已进入收件箱！")
    elif 'login.live.com' in current_url:
        print(f"\n❌ 登录失败 - 仍停留在登录页，可能密码错误或被限制")
    elif 'account.live.com' in current_url:
        print(f"\n❌ 登录失败 - 账号可能需要额外验证")
    elif '机器人' in current_title:
        print(f"\n⚠️ 触发验证码，需要人工处理")
    else:
        print(f"\n⚠️ 未知状态，请查看打开的浏览器窗口")
        print(f"截图已保存: /tmp/outlook_verify_05_result.png")

    input("\n按 Enter 键关闭浏览器...")

finally:
    p.stop()
    subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)
