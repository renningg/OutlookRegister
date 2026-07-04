"""
直接使用 GeekEZ 的 Chrome for Testing + 指纹扩展运行注册
"""
import sys, os, json, time, random, string, subprocess, socket
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from faker import Faker
from playwright.sync_api import sync_playwright
from utils import check_captcha_type

fake = Faker()
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SS_LOCAL = "/opt/homebrew/bin/ss-local"

PROFILES_FILE = os.path.expanduser("~/Library/Application Support/geekez-browser/BrowserProfiles/profiles.json")

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

# ============ GeekEZ 启动器 ============

def find_profile(name):
    with open(PROFILES_FILE) as f:
        profiles = json.load(f)
    for p in profiles:
        if p['name'] == name:
            return p
    # 模糊匹配
    for p in profiles:
        if name.lower() in p['name'].lower():
            return p
    return profiles[0] if profiles else None

def start_ss_proxy(server_addr, server_port, socks_port):
    """用 ss-local 启动 SOCKS5 代理"""
    config = {
        "server": server_addr, "server_port": server_port,
        "method": "chacha20-ietf-poly1305",
        "password": "091fcebd-811d-48d2-8cc1-7fd489fc29a7",
        "local_address": "127.0.0.1", "local_port": socks_port,
        "timeout": 60
    }
    temp_config = f"/tmp/ss_geekez.json"
    with open(temp_config, 'w') as f:
        json.dump(config, f)
    
    subprocess.run(['pkill', '-f', f'ss-local.*{socks_port}'], capture_output=True)
    time.sleep(0.5)
    
    proc = subprocess.Popen([SS_LOCAL, '-c', temp_config, '-b', '127.0.0.1', '-l', str(socks_port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    return proc

def launch_geekez_chrome(profile_id, socks_port, debug_port, proxy_host=None):
    ext_path = os.path.expanduser(f"~/Library/Application Support/geekez-browser/BrowserProfiles/{profile_id}/extension")
    user_data = os.path.expanduser(f"~/Library/Application Support/geekez-browser/BrowserProfiles/{profile_id}/browser_data")
    
    # 确保 user_data 存在
    os.makedirs(user_data, exist_ok=True)
    os.makedirs(f"{user_data}/Default", exist_ok=True)
    
    args = [
        CHROME,
        f'--user-data-dir={user_data}',
        f'--remote-debugging-port={debug_port}',
        '--remote-allow-origins=*',
        f'--load-extension={ext_path}',
        '--no-first-run',
        '--no-default-browser-check',
        '--window-size=1280,800',
        '--disable-blink-features=AutomationControlled',
    ]
    if socks_port and socks_port != 'no_proxy':
        args.append(f'--proxy-server=socks5://127.0.0.1:{socks_port}')
        args.append('--proxy-bypass-list=127.0.0.1,localhost')
    if proxy_host:
        args.append(f'--proxy-server={proxy_host}')
        args.append('--proxy-bypass-list=127.0.0.1,localhost')
    
    # 杀掉旧实例
    subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)
    time.sleep(1)
    
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(20):
        time.sleep(1)
        s = socket.socket()
        if s.connect_ex(('127.0.0.1', debug_port)) == 0:
            s.close()
            print(f"  [Chrome] 端口 {debug_port} 已就绪 (等待{i+1}s)")
            return proc
        s.close()
    print(f"  [Chrome] 端口 {debug_port} 超时")
    return None

# ============ 浏览伪装 ============

SITES = [
    ("Google", "https://www.google.com/search?q=weather"),
    ("YouTube", "https://www.youtube.com"),
    ("Bing", "https://www.bing.com/search?q=movies"),
    ("Wikipedia", "https://en.wikipedia.org"),
    ("Amazon", "https://www.amazon.com"),
]

def browse_as_normal_user(browser):
    context = browser.contexts[0]
    pages = [context.pages[0]]
    # 只开2个常用站，超时短
    for name, url in [("Google", "https://www.google.com"), ("Bing", "https://www.bing.com")]:
        try:
            p = context.new_page()
            pages.append(p)
            p.goto(url, timeout=8000, wait_until="commit")
        except:
            pass
    print(f"  [伪装] 已打开 {len(pages)} 个标签页")
    outlook_page = context.new_page()
    return outlook_page

def get_ws_url(debug_port):
    try:
        s = socket.create_connection(('127.0.0.1', debug_port), timeout=5)
        s.settimeout(10)
        s.sendall(f'GET /json/version HTTP/1.1\r\nHost: 127.0.0.1:{debug_port}\r\nConnection: close\r\n\r\n'.encode())
        resp = b''
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
            except socket.timeout:
                break
        s.close()
        body = resp.split(b'\r\n\r\n', 1)[-1]
        return json.loads(body).get('webSocketDebuggerUrl', '')
    except Exception as e:
        print(f"  [WS Debug] get_ws_url error: {e}")
        return None

# ============ 验证码处理 ============

def handle_longpress(page, btn_x, btn_y):
    # 用 Playwright mouse API（比 CDP 更自然）
    # 先移到按钮位置
    steps = random.randint(20, 40)
    for i in range(steps):
        t = i / steps
        x = bezier_curve(t, random.randint(100, 400), btn_x*0.3, btn_x*0.7, btn_x)
        y = bezier_curve(t, random.randint(100, 300), btn_y*0.3, btn_y*0.7, btn_y)
        page.mouse.move(x + random.uniform(-2, 2), y + random.uniform(-2, 2))
        time.sleep(random.uniform(0.015, 0.04))
    
    time.sleep(random.uniform(0.2, 0.5))
    
    # 按下
    page.mouse.down(button='left')
    print(f"    [Captcha] 按住 ({btn_x:.0f},{btn_y:.0f})...")
    
    # 长按 18-25 秒
    hold_time = random.uniform(18, 25)
    start = time.time()
    while time.time() - start < hold_time:
        elapsed = time.time() - start
        if random.random() < 0.10:
            page.mouse.move(btn_x + random.uniform(-3, 3), btn_y + random.uniform(-3, 3))
        time.sleep(random.uniform(0.3, 0.7))
    
    # 松开
    page.mouse.up(button='left')
    print(f"    [Captcha] 已松开（按住{hold_time:.0f}秒）")

def handle_push_button(page):
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
            if ct in ('unknown',) or ct != 'push_button':
                return True
        except:
            if attempt < 2:
                time.sleep(2)
    return False

def handle_captcha(page):
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
            try:
                
                # 找 #human 容器内的长按按钮
                btn_box = None
                try:
                    human = page.locator('#human')
                    box = human.bounding_box(timeout=3000)
                    if box:
                        # 按钮通常在 #human 偏下位置（上部是文字说明）
                        bx = box['x'] + box['width'] / 2
                        by = box['y'] + box['height'] * 0.65
                        btn_box = (bx, by)
                        print(f"    [Captcha] #human 按钮: ({bx:.0f},{by:.0f}) 尺寸={box['width']:.0f}x{box['height']:.0f}")
                    
                    # 更好的方式：在 #human 内找到实际可点击元素
                    human_children = page.evaluate("""() => {
                        const h = document.getElementById('human');
                        if (!h) return [];
                        const all = h.querySelectorAll('div, button, a, [role="button"]');
                        return Array.from(all).filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 30 && r.height > 30;
                        }).map(el => ({
                            tag: el.tagName,
                            text: (el.innerText || '').trim().slice(0,20),
                            rect: el.getBoundingClientRect()
                        }));
                    }""")
                    if human_children:
                        for el in human_children:
                            r = el['rect']
                            print(f"    [Captcha] #human 内元素: {el['tag']} '{el['text']}' at ({r['x']:.0f},{r['y']:.0f},{r['width']:.0f}x{r['height']:.0f})")
                            if not btn_box or el['text']:
                                bx = r['x'] + r['width'] / 2
                                by = r['y'] + r['height'] / 2
                                btn_box = (bx, by)
                except Exception as e:
                    print(f"    [Captcha] #human 查找失败: {e}")
                
                if not btn_box:
                    print("    [Captcha] 找不到按钮")
                    return False
                
                time.sleep(random.uniform(0.2, 0.5))
                
                # 使用 Playwright mouse API 长按
                handle_longpress(page, btn_box[0], btn_box[1])
                
                # 等待验证结果（45秒）
                for w in range(45):
                    time.sleep(1)
                    current_ct = check_captcha_type(page)
                    if current_ct == 'unknown':
                        print(f"    [Captcha] 验证码已消失!")
                        return True
                    title = page.title()
                    if '机器人' not in title and '个人数据' in title:
                        print(f"    [Captcha] 页面跳转: title='{title[:30]}'")
                        return True
                    if w % 15 == 0:
                        print(f"    [Captcha] 等待中 {w}s... captcha_type={current_ct}")
                
                print(f"    [Captcha] 长按超时（仍检测到验证码）")
                
                if attempt < 2:
                    print("    [Captcha] 刷新重试...")
                    page.reload()
                    time.sleep(5)
                    
            except Exception as e:
                print(f"    [Captcha] 异常: {e}")
                import traceback
                traceback.print_exc()
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

WORKING_PROXIES = [
    ("🇯🇵 日本A[BGP]", "normal.relay.jpa.sys-metric-report.com", 20437),
    ("🇯🇵 日本B[BGP]", "normal.relay.jpb.sys-metric-report.com", 43292),
    ("🇭🇰 香港[C]", "mix.relay.ss.hkc.sys-metric-report.com", 25070),
    ("🇸🇬 新加坡D[BGP]", "normal.relay.sgpd.sys-metric-report.com", 12167),
    ("🇺🇸 美国C[BGP]", "normal.relay.usc.sys-metric-report.com", 17319),
    ("🇻🇳 越南A[BGP]", "normal.relay.vna.sys-metric-report.com", 17463),
]

def register(email, password, socks_port):
    print(f"\n邮箱: {email}@outlook.com")
    print(f"密码: {password}")
    print(f"SOCKS5: 127.0.0.1:{socks_port}")
    
    debug_port = 24000 + random.randint(0, 100)
    
    # 用 test profile（有 extension + browser_data）
    profile = find_profile("test")
    if not profile:
        print("找不到 test profile")
        return False, None
    print(f"使用 profile: {profile['name']}")
    
    # 直连（无代理）
    proxy_proc = None
    socks_port = None
    proxy_url = None
    print(f"代理: 无（直连）")
    
    # 启动 GeekEZ Chrome
    chrome_proc = launch_geekez_chrome(profile['id'], socks_port, debug_port, proxy_url)
    if not chrome_proc:
        print("Chrome 启动失败")
        subprocess.run(['pkill', '-f', f'ss-local'], capture_output=True)
        return False, None
    
    # 获取 WS URL
    ws_url = get_ws_url(debug_port)
    if not ws_url:
        print("无法获取 WS URL")
        subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)
        subprocess.run(['pkill', '-f', f'ss-local'], capture_output=True)
        return False, None
    
    # 设置环境变量绕过系统代理（Proxy 会拦截 ws://127.0.0.1 连接）
    os.environ['no_proxy'] = '127.0.0.1,localhost,.local'
    
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(ws_url, timeout=60000)
        context = browser.contexts[0]
        
        # 额外加强反指纹（在 Extension content.js 之上）
        context.add_init_script("""
        // 额外反指纹加强
        // 1. 确保 webdriver = false
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        
        // 2. 覆盖 getClientRects toString（PerimeterX 检测点）
        const origRect = Element.prototype.getClientRects;
        Element.prototype.getClientRects = function() {
            const rects = origRect.apply(this, arguments);
            rects.toString = function() { return '[object DOMRectList]'; };
            return rects;
        };
        
        // 3. 覆盖 Function.prototype.toString 隐藏 native code 检测
        const origToString = Function.prototype.toString;
        Function.prototype.toString = function() {
            if (this === origToString || this.name === '') return origToString.call(this);
            return origToString.call(this);
        };
        
        // 4. Chrome runtime 对象
        if (!window.chrome) {
            window.chrome = { runtime: { id: 'fake' }, app: { isInstalled: false } };
        }
        """)
        
        # 浏览伪装
        page = browse_as_normal_user(browser)
        
        # 导航到注册页
        print("  [1] 导航到注册页...")
        page.goto("https://outlook.live.com/mail/0/?prompt=create_account",
                  timeout=30000, wait_until="networkidle")
        time.sleep(3)
        
        # 处理数据导出同意
        print(f"  [同意] URL: {page.url[:60]}")
        for _ in range(20):
            ab = page.get_by_text('同意并继续')
            if ab.count() > 0 and ab.first.is_visible():
                print("  [同意] 点击'同意并继续'...")
                ab.first.click()
                time.sleep(3)
                continue
            if page.locator('[aria-label="新建电子邮件"]').count() > 0:
                break
            time.sleep(1)
        
        # 输入邮箱
        print("  [2] 输入邮箱...")
        page.locator('[aria-label="新建电子邮件"]').fill(email)
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)
        
        # 输入密码
        print("  [3] 输入密码...")
        page.locator('[type="password"]').fill(password)
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)
        
        # 生日
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
        
        # 姓名
        print("  [5] 填写姓名...")
        page.locator('#lastNameInput').fill(fake.last_name())
        page.locator('#firstNameInput').fill(fake.first_name())
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        
        # 验证码
        print("  [6] 处理验证码...")
        time.sleep(3)
        captcha_ok = handle_captcha(page)
        
        if not captcha_ok:
            print("  ✗ 验证码处理失败")
            return False, None
        
        print("  [7] 等待注册完成...")
        for step in range(120):
            url = page.url
            title = page.title()
            
            if 'outlook.live.com/mail' in url or '收件箱' in title:
                print(f"  ✅ 注册成功！已进入收件箱!")
                return True, {'email': f"{email}@outlook.com", 'password': password}
            
            try:
                ab = page.get_by_text('同意并继续')
                if ab.count() > 0 and ab.first.is_visible():
                    print("  [同意] 点击数据导出'同意并继续'...")
                    ab.first.click(force=True)
                    time.sleep(5)
                    continue
            except:
                pass
            
            ct = check_captcha_type(page)
            if ct != 'unknown':
                print(f"  [验证码] 再次检测到 {ct}...")
                if handle_captcha(page):
                    continue
                break
            
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
        import traceback
        traceback.print_exc()
        return False, None
    finally:
        p.stop()
        subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], capture_output=True)
        subprocess.run(['pkill', '-f', f'ss-local'], capture_output=True)
        subprocess.run(['pkill', '-f', 'local_proxy.py'], capture_output=True)

# ============ 主程序 ============

def main():
    print("=" * 60)
    print("Outlook 注册自动化 (GeekEZ Chrome + 指纹扩展)")
    print("=" * 60)
    
    email = random_email()
    password = generate_password()
    
    # 使用一个固定的 SOCKS5 端口
    socks_port = 18765
    
    success, result = register(email, password, socks_port)
    
    if success:
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Results')
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, 'outlook_success.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{result['email']}:{result['password']}:geekez\n")
        print(f"\n✅ 账号已保存: {result['email']}:{result['password']}")
    else:
        print("\n✗ 注册失败")

if __name__ == "__main__":
    main()
