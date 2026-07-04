"""
Outlook 注册自动化 - 完整版
- 自动轮换代理
- 完整注册流程 + 验证码处理
- 严格判断注册成功（进入收件箱）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import random
import string
import subprocess
import socket
import urllib.request
import json
from faker import Faker
from playwright.sync_api import sync_playwright
from utils import check_captcha_type

fake = Faker()

# ============ 工具函数 ============

def random_email():
    length = random.randint(12, 14)
    first_char = random.choice(string.ascii_lowercase)
    others = [random.choice(string.digits) if random.random() < 0.07 else random.choice(string.ascii_lowercase) for _ in range(length - 1)]
    return first_char + ''.join(others)

def generate_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pw = ''.join(random.choice(chars) for _ in range(random.randint(11, 15)))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*" for c in pw)):
            return pw

def bezier_curve(t, p0, p1, p2, p3):
    u = 1 - t
    return u**3 * p0 + 3*u**2*t * p1 + 3*u*t**2 * p2 + t**3 * p3

# ============ Chrome 启动 ============

def start_chrome(user_data_dir, debug_port, proxy=None):
    subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)
    time.sleep(1)
    chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    args = [
        chrome_path, f'--user-data-dir={user_data_dir}',
        f'--remote-debugging-port={debug_port}', '--remote-allow-origins=*',
        '--no-first-run', '--no-default-browser-check',
        '--disable-blink-features=AutomationControlled', '--window-size=1280,800',
    ]
    if proxy:
        args.append(f'--proxy-server={proxy}')
        args.append('--proxy-bypass-list=127.0.0.1,localhost')
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(15):
        time.sleep(1)
        s = socket.socket()
        if s.connect_ex(('127.0.0.1', debug_port)) == 0:
            s.close()
            return proc
        s.close()
    return None

def get_ws_url(debug_port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/version", timeout=5) as r:
            return json.loads(r.read()).get('webSocketDebuggerUrl', '')
    except:
        return None

# ============ 验证码处理 ============

def handle_longpress(page, cdp, btn_x, btn_y):
    start_x = random.randint(100, 400)
    start_y = random.randint(100, 300)
    cp1_x = start_x + (btn_x - start_x) * 0.3 + random.uniform(-50, 50)
    cp1_y = start_y + (btn_y - start_y) * 0.3 + random.uniform(-50, 50)
    cp2_x = start_x + (btn_x - start_x) * 0.7 + random.uniform(-50, 50)
    cp2_y = start_y + (btn_y - start_y) * 0.7 + random.uniform(-50, 50)
    
    steps = random.randint(20, 40)
    for i in range(steps):
        t = i / steps
        x = bezier_curve(t, start_x, cp1_x, cp2_x, btn_x) + random.uniform(-2, 2)
        y = bezier_curve(t, start_y, cp1_y, cp2_y, btn_y) + random.uniform(-2, 2)
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
            "button": "none", "clickCount": 0, "pointerType": "mouse"
        })
        time.sleep(random.uniform(0.01, 0.05))
    
    time.sleep(random.uniform(0.1, 0.3))
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": btn_x, "y": btn_y,
        "button": "left", "clickCount": 1, "buttons": 1, "pointerType": "mouse"
    })
    
    hold_time = random.uniform(12, 18)
    start = time.time()
    while time.time() - start < hold_time:
        if random.random() < 0.15:
            jx = btn_x + random.uniform(-4, 4)
            jy = btn_y + random.uniform(-4, 4)
            cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": jx, "y": jy,
                "button": "left", "clickCount": 0, "buttons": 1, "pointerType": "mouse"
            })
        time.sleep(random.uniform(0.3, 0.8))
    
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": btn_x, "y": btn_y,
        "button": "left", "clickCount": 1, "buttons": 0, "pointerType": "mouse"
    })
    print("    [Captcha] 已松开，等待结果...")
    time.sleep(5)

def handle_push_button(page):
    """处理 push_button 类型验证码"""
    for attempt in range(3):
        try:
            ifr1 = page.frame_locator('iframe[title="验证质询"]')
            ifr2 = ifr1.frame_locator('iframe[style*="display: block"]')
            
            loc = ifr2.locator('[aria-label="可访问性挑战"]')
            box = loc.bounding_box()
            if not box:
                return True
            
            x = box['x'] + box['width'] / 2 + random.randint(-10, 10)
            y = box['y'] + box['height'] / 2 + random.randint(-10, 10)
            page.mouse.click(x, y)
            
            loc2 = ifr2.locator('[aria-label="再次按下"]')
            box2 = loc2.bounding_box()
            if box2:
                x2 = box2['x'] + box2['width'] / 2 + random.randint(-20, 20)
                y2 = box2['y'] + box2['height'] / 2 + random.randint(-13, 13)
                page.mouse.click(x2, y2)
            
            time.sleep(3)
            ct = check_captcha_type(page)
            if ct in ('unknown',):
                return True
            if ct != 'push_button':
                return True
        except:
            if attempt < 2:
                time.sleep(2)
    return False

def handle_captcha(page):
    """自动检测并处理验证码，最多尝试 3 次"""
    # 等待验证码出现
    for _ in range(20):
        ct = check_captcha_type(page)
        if ct != 'unknown':
            break
        time.sleep(1)
    else:
        print("    [Captcha] 未检测到验证码")
        return True
    
    ct = check_captcha_type(page)
    print(f"    [Captcha] 类型: {ct}")
    
    if ct == 'funcaptcha_iframe':
        print("    [Captcha] FunCaptcha 无法自动处理")
        return False
    
    for attempt in range(3):
        if ct == 'longpress':
            print(f"    [Captcha] longpress 尝试 {attempt+1}/3")
            cdp = page.context.new_cdp_session(page)
            try:
                iframe_info = page.evaluate("""
                () => {
                    const ifs = document.querySelectorAll('iframe');
                    for (const f of ifs) {
                        if (f.title === '验证质询') {
                            const r = f.getBoundingClientRect();
                            return { x: r.x, y: r.y, width: r.width, height: r.height };
                        }
                    }
                    return null;
                }
                """)
                if iframe_info:
                    bx = iframe_info['x'] + iframe_info['width'] / 2
                    by = iframe_info['y'] + iframe_info['height'] - 30
                else:
                    btn = page.locator('#human > div:first-child')
                    btn.wait_for(state='visible', timeout=5000)
                    box = btn.bounding_box()
                    if not box:
                        cdp.detach()
                        return False
                    bx = box['x'] + box['width'] / 2
                    by = box['y'] + box['height'] / 2
                
                print(f"    [Captcha] 按钮: x={bx:.0f}, y={by:.0f}")
                handle_longpress(page, cdp, bx, by)
                
                if '机器人' not in page.title():
                    print("    [Captcha] 长按通过!")
                    cdp.detach()
                    return True
                
                cdp.detach()
                if attempt < 2:
                    print("    [Captcha] 重试...")
                    page.reload()
                    time.sleep(3)
            except Exception as e:
                print(f"    [Captcha] 异常: {e}")
                try: cdp.detach()
                except: pass
                return False
        
        elif ct == 'push_button':
            if handle_push_button(page):
                print("    [Captcha] push_button 通过!")
                return True
            if attempt < 2:
                print("    [Captcha] push_button 重试...")
                page.reload()
                time.sleep(3)
    
    return False

# ============ 注册流程 ============

# ============ 伪造浏览记录 ============

SITES = [
    ("Google", "https://www.google.com/search?q=weather+forecast+today"),
    ("YouTube", "https://www.youtube.com"),
    ("Bing", "https://www.bing.com/search?q=new+movies+2026"),
    ("Wikipedia", "https://en.wikipedia.org/wiki/Main_Page"),
    ("Amazon", "https://www.amazon.com"),
    ("Reddit", "https://www.reddit.com"),
    ("Twitter", "https://x.com"),
    ("BBC", "https://www.bbc.com/news"),
]

def browse_as_normal_user(browser):
    """打开多个标签页模拟正常用户，不关闭，然后开新tab去注册"""
    context = browser.contexts[0]
    main_page = context.pages[0]
    
    # 第一个标签访问 YouTube 并挂机
    random.shuffle(SITES)
    
    print("  [伪装] 打开多标签页模拟正常用户...")
    pages = [main_page]
    
    for i, (name, url) in enumerate(SITES[:random.randint(3, 5)]):
        try:
            if i == 0:
                p = main_page
            else:
                p = context.new_page()
            pages.append(p)
            
            print(f"  [伪装] 打开 {name}...")
            p.goto(url, timeout=15000, wait_until="domcontentloaded")
            
            # 每个页面做一点交互
            if random.random() < 0.6:
                p.evaluate(f"window.scrollBy(0, {random.randint(100, 400)})")
            if random.random() < 0.3 and name == "YouTube":
                # 点一个视频预览
                try:
                    p.locator("a#video-title-link").first.click(timeout=3000)
                    time.sleep(2)
                except:
                    pass
            
            time.sleep(random.uniform(1, 3))
        except:
            pass
    
    print(f"  [伪装] 已打开 {len(pages)} 个标签页，准备 Outlook 注册")
    
    # 开一个新标签页去 Outlook
    outlook_page = context.new_page()
    return outlook_page

def register(email, password, proxy=None):
    print(f"\n邮箱: {email}@outlook.com")
    print(f"密码: {password}")
    if proxy:
        print(f"代理: {proxy}")
    
    debug_port = 24000 + random.randint(0, 100)
    user_data_dir = f"/tmp/chrome_reg_{int(time.time())}_{random.randint(1000,9999)}"
    os.makedirs(user_data_dir, exist_ok=True)
    
    proc = start_chrome(user_data_dir, debug_port, proxy)
    if not proc:
        return False, None
    
    ws_url = get_ws_url(debug_port)
    if not ws_url:
        subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)
        return False, None
    
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(ws_url, timeout=30000)
        context = browser.contexts[0]
        
        # 注入反检测脚本（每个新页面自动运行）
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', {
            get: () => { const a = [{name:'Chrome PDF Plugin'},{name:'Chrome PDF Viewer'},{name:'Native Client'}]; a.item=i=>a[i]; a.namedItem=n=>a.find(p=>p.name===n); a.refresh=()=>{}; return a; }
        });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        """)
        
        # 先伪造浏览记录（打开多标签页，不关闭）
        page = browse_as_normal_user(browser)
        
        # 1. 导航（等待网络空闲确保重定向完成）
        print("  [1] 导航到注册页...")
        page.goto("https://outlook.live.com/mail/0/?prompt=create_account",
                  timeout=30000, wait_until="networkidle")
        time.sleep(3)
        
        # 2. 处理数据导出同意弹窗
        print(f"  [同意] 检测到页面: {page.url[:60]}")
        for _ in range(20):
            ab = page.get_by_text('同意并继续')
            if ab.count() > 0 and ab.first.is_visible():
                print("  [同意] 点击'同意并继续'...")
                ab.first.click()
                time.sleep(3)
                continue
            # 检查是否已经到注册表单
            if page.locator('[aria-label="新建电子邮件"]').count() > 0 or 'signup' not in page.url:
                break
            time.sleep(1)
        
        # 3. 输入邮箱
        print("  [2] 输入邮箱...")
        page.locator('[aria-label="新建电子邮件"]').fill(email)
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)
        
        # 4. 输入密码
        print("  [3] 输入密码...")
        page.locator('[type="password"]').fill(password)
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)
        
        # 5. 生日
        print("  [4] 填写生日...")
        year = str(random.randint(1985, 2000))
        month = str(random.randint(1, 12))
        day = str(random.randint(1, 28))
        page.locator('[name="BirthYear"]').fill(year)
        page.locator('[name="BirthMonth"]').click()
        time.sleep(0.3)
        page.locator(f'[role="option"]:text-is("{month}月")').click()
        page.locator('[name="BirthDay"]').click()
        time.sleep(0.3)
        page.locator(f'[role="option"]:text-is("{day}日")').click()
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)
        
        # 6. 姓名
        print("  [5] 填写姓名...")
        page.locator('#lastNameInput').fill(fake.last_name())
        page.locator('#firstNameInput').fill(fake.first_name())
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        
        # 7. 处理验证码
        print("  [6] 处理验证码...")
        time.sleep(3)
        captcha_ok = handle_captcha(page)
        
        if not captcha_ok:
            print("  ✗ 验证码处理失败")
            return False, None
        
        print("  [7] 等待注册完成...")
        
        # 8. 等待注册结果（最多 120 秒）
        for step in range(120):
            url = page.url
            title = page.title()
            
            # 成功：进入收件箱
            if 'outlook.live.com/mail' in url or '收件箱' in title:
                print(f"  ✅ 注册成功！已进入收件箱!")
                return True, {'email': f"{email}@outlook.com", 'password': password, 'proxy': proxy}
            
            # 处理数据导出同意按钮
            try:
                ab = page.get_by_text('同意并继续')
                if ab.count() > 0 and ab.first.is_visible():
                    print("  [同意] 点击数据导出'同意并继续'...")
                    ab.first.click(force=True)
                    time.sleep(5)
                    continue
            except:
                pass
            
            # 检测验证码
            ct = check_captcha_type(page)
            if ct != 'unknown':
                print(f"  [验证码] 再次检测到 {ct}...")
                if handle_captcha(page):
                    continue
                break
            
            # 检测错误/限制
            if '一些异常活动' in page.content():
                print("  ✗ IP 被限制")
                break
            
            if step % 20 == 0:
                print(f"  [等待] 第 {step} 秒... url={url[:60]}")
            
            time.sleep(1)
        else:
            print(f"  ✗ 注册超时, 最后 URL: {page.url[:80]}")
        
        return False, None
        
    except Exception as e:
        print(f"  ✗ 异常: {e}")
        return False, None
    finally:
        p.stop()
        subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)

# ============ 主程序 ============

def main():
    from proxy_rotator import ProxyRotator
    
    print("=" * 60)
    print("Outlook 注册自动化 (带代理轮换)")
    print("=" * 60)
    
    # 加载工作代理
    print("\n[初始化] 加载工作代理...")
    working = []
    if os.path.exists('working_proxies.txt'):
        with open('working_proxies.txt', 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    working.append({'name': parts[0], 'url': parts[1]})
    
    if not working:
        print("[Warning] 无法加载代理列表，使用系统代理")
        working = [{'name': '系统代理', 'url': None}]
    else:
        print(f"共 {len(working)} 个可用代理:")
        for w in working:
            print(f"  {w['name']}: {w['url']}")
    
    print("\n[开始注册] 轮换代理尝试，直到注册成功\n")
    
    for attempt, proxy_info in enumerate(working):
        print(f"\n{'='*60}")
        print(f"尝试 {attempt + 1}/{len(working)}")
        print(f"{'='*60}")
        
        proxy_name = proxy_info['name']
        proxy_url = None
        
        # 启动代理（动态端口分配）
        if proxy_name != '系统代理':
            rotator = ProxyRotator()
            for p in rotator.proxies:
                if p['profile_name'] == proxy_name:
                    port = 11000 + attempt
                    from proxy_rotator import start_ss_local
                    try:
                        _, proxy_url = start_ss_local(p, port)
                        print(f"当前代理: {proxy_name} → SOCKS5 127.0.0.1:{port}")
                        time.sleep(2)
                    except Exception as e:
                        print(f"代理启动失败: {e}")
                    break
        else:
            print(f"当前代理: 系统代理")
        
        email = random_email()
        password = generate_password()
        
        success, result = register(email, password, proxy_url)
        
        # 停止所有代理
        subprocess.run(['pkill', '-f', 'ss-local'], capture_output=True)
        time.sleep(1)
        
        if success:
            # 保存结果
            results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Results')
            os.makedirs(results_dir, exist_ok=True)
            with open(os.path.join(results_dir, 'outlook_success.txt'), 'a', encoding='utf-8') as f:
                f.write(f"{result['email']}:{result['password']}:{proxy_name}\n")
            print(f"\n✅ 账号已保存: {result['email']}:{result['password']} (代理: {proxy_name})")
            break
        
        print("\n等待 3 秒后尝试下一个代理...")
        time.sleep(3)
    
    print("\n[完成]")

if __name__ == "__main__":
    main()
