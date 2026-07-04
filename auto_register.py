"""
Outlook 注册自动化脚本
支持：新 session、验证码重试、自动切换代理
"""
import json
import time
import random
import string
import subprocess
import os
import urllib.request
from faker import Faker

fake = Faker()

# ============ 工具函数 ============

def random_email():
    length = random.randint(12, 14)
    first_char = random.choice(string.ascii_lowercase)
    other_chars = []
    for _ in range(length - 1):
        if random.random() < 0.07:
            other_chars.append(random.choice(string.digits))
        else:
            other_chars.append(random.choice(string.ascii_lowercase))
    return first_char + ''.join(other_chars)

def generate_password():
    length = random.randint(11, 15)
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(random.choice(chars) for _ in range(length))
        if (any(c.islower() for c in password) 
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*" for c in password)):
            return password

def bezier_curve(t, p0, p1, p2, p3):
    """三次贝塞尔曲线"""
    u = 1 - t
    return u**3 * p0 + 3*u**2*t * p1 + 3*u*t**2 * p2 + t**3 * p3

# ============ Chrome 启动 ============

def start_chrome(user_data_dir, debug_port):
    """启动 Chrome 实例"""
    # 先关闭旧的 Chrome
    subprocess.run(['pkill', '-f', f'remote-debugging-port={debug_port}'], 
                   capture_output=True)
    time.sleep(2)
    
    chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    
    launch_args = [
        chrome_path,
        f'--user-data-dir={user_data_dir}',
        f'--remote-debugging-port={debug_port}',
        '--remote-allow-origins=*',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1280,800',
    ]
    
    print(f"  启动 Chrome...")
    proc = subprocess.Popen(launch_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 等待端口就绪
    import socket
    for _ in range(10):
        time.sleep(1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', debug_port))
        sock.close()
        if result == 0:
            print(f"  ✓ Chrome 已启动，端口 {debug_port} 就绪")
            return proc
    
    print(f"  ✗ Chrome 启动超时")
    return None

def get_ws_url(debug_port):
    """获取 WebSocket URL"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/version", timeout=5) as response:
            version_info = json.loads(response.read())
            return version_info.get('webSocketDebuggerUrl', '')
    except:
        return None

# ============ 验证码处理 ============

def handle_captcha(page, max_retries=3):
    """
    处理 PerimeterX 长按验证码
    返回: True=通过, False=失败
    """
    from playwright.sync_api import sync_playwright
    
    for attempt in range(max_retries):
        print(f"    [Captcha] 尝试 {attempt + 1}/{max_retries}")
        
        # 检查是否需要验证码
        title = page.title()
        if '机器人' not in title:
            print(f"    [Captcha] 无需验证码")
            return True
        
        # 获取验证质询 iframe 的位置
        iframe_info = page.evaluate("""
        () => {
            const iframes = document.querySelectorAll('iframe');
            for (const iframe of iframes) {
                if (iframe.title === '验证质询') {
                    const rect = iframe.getBoundingClientRect();
                    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                }
            }
            return null;
        }
        """)
        
        if not iframe_info:
            print(f"    [Captcha] 未找到验证质询 iframe")
            # 尝试回退到原来的逻辑
            try:
                btn = page.locator('#human > div:first-child')
                btn.wait_for(state='visible', timeout=5000)
                box = btn.bounding_box()
                if box:
                    btn_x = box['x'] + box['width'] / 2
                    btn_y = box['y'] + box['height'] / 2
                else:
                    page.reload()
                    time.sleep(3)
                    continue
            except:
                page.reload()
                time.sleep(3)
                continue
        else:
            btn_x = iframe_info['x'] + iframe_info['width'] / 2
            btn_y = iframe_info['y'] + iframe_info['height'] - 30
        
        print(f"    [Captcha] 按钮位置: x={btn_x:.0f}, y={btn_y:.0f}")
        
        # 使用 CDP session
        cdp = page.context.new_cdp_session(page)
        
        try:
            # 1. 从随机位置开始移动
            start_x = random.randint(100, 400)
            start_y = random.randint(100, 300)
            
            # 2. 生成贝塞尔曲线控制点
            cp1_x = start_x + (btn_x - start_x) * 0.3 + random.uniform(-50, 50)
            cp1_y = start_y + (btn_y - start_y) * 0.3 + random.uniform(-50, 50)
            cp2_x = start_x + (btn_x - start_x) * 0.7 + random.uniform(-50, 50)
            cp2_y = start_y + (btn_y - start_y) * 0.7 + random.uniform(-50, 50)
            
            # 3. 沿贝塞尔曲线移动鼠标
            steps = random.randint(20, 40)
            for i in range(steps):
                t = i / steps
                x = bezier_curve(t, start_x, cp1_x, cp2_x, btn_x)
                y = bezier_curve(t, start_y, cp1_y, cp2_y, btn_y)
                x += random.uniform(-2, 2)
                y += random.uniform(-2, 2)
                
                cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": x,
                    "y": y,
                    "button": "none",
                    "clickCount": 0,
                    "pointerType": "mouse"
                })
                time.sleep(random.uniform(0.01, 0.05))
            
            time.sleep(random.uniform(0.1, 0.3))
            
            # 4. 按下鼠标
            cdp.send("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": btn_x,
                "y": btn_y,
                "button": "left",
                "clickCount": 1,
                "buttons": 1,
                "pointerType": "mouse"
            })
            
            # 5. 保持按住，偶尔微调位置
            hold_time = random.uniform(10, 15)
            start_time = time.time()
            
            while time.time() - start_time < hold_time:
                if random.random() < 0.2:
                    jitter_x = btn_x + random.uniform(-3, 3)
                    jitter_y = btn_y + random.uniform(-3, 3)
                    cdp.send("Input.dispatchMouseEvent", {
                        "type": "mouseMoved",
                        "x": jitter_x,
                        "y": jitter_y,
                        "button": "left",
                        "clickCount": 0,
                        "buttons": 1,
                        "pointerType": "mouse"
                    })
                time.sleep(random.uniform(0.3, 0.7))
            
            # 6. 松开鼠标
            cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": btn_x,
                "y": btn_y,
                "button": "left",
                "clickCount": 1,
                "buttons": 0,
                "pointerType": "mouse"
            })
            
            print(f"    [Captcha] 等待验证结果...")
            time.sleep(5)
            
            # 检查结果
            title = page.title()
            if '机器人' not in title:
                print(f"    [Captcha] 验证通过!")
                cdp.detach()
                return True
            
            print(f"    [Captcha] 验证失败，重试...")
            cdp.detach()
            
            # 刷新页面重试
            if attempt < max_retries - 1:
                page.reload()
                time.sleep(3)
                
        except Exception as e:
            print(f"    [Captcha] 异常: {e}")
            try:
                cdp.detach()
            except:
                pass
    
    return False

# ============ 注册流程 ============

def register_outlook(page, email, password):
    """
    执行 Outlook 注册流程
    返回: (success, email, password)
    """
    print(f"  邮箱: {email}@outlook.com")
    print(f"  密码: {password}")
    
    try:
        # 1. 导航到注册页面
        print("  [1/6] 导航到注册页面...")
        page.goto("https://outlook.live.com/mail/0/?prompt=create_account", 
                  timeout=30000, wait_until="domcontentloaded")
        time.sleep(3)
        
        # 处理"同意并继续"
        try:
            agree_btn = page.get_by_text('同意并继续')
            if agree_btn.count() > 0:
                print("  [2/6] 点击'同意并继续'...")
                agree_btn.click()
                time.sleep(3)
        except:
            pass
        
        # 2. 输入邮箱
        print("  [3/6] 输入邮箱...")
        email_input = page.locator('[aria-label="新建电子邮件"]')
        if email_input.count() > 0:
            email_input.fill(email)
            time.sleep(0.5)
        
        # 点击下一步
        next_btn = page.locator('[data-testid="primaryButton"]')
        if next_btn.count() > 0:
            next_btn.click()
            time.sleep(3)
        
        # 3. 输入密码
        print("  [4/6] 输入密码...")
        password_input = page.locator('[type="password"]')
        if password_input.count() > 0:
            password_input.fill(password)
            time.sleep(0.5)
        
        next_btn = page.locator('[data-testid="primaryButton"]')
        if next_btn.count() > 0:
            next_btn.click()
            time.sleep(3)
        
        # 4. 填写生日
        print("  [5/6] 填写生日...")
        year = str(random.randint(1985, 2000))
        month = str(random.randint(1, 12))
        day = str(random.randint(1, 28))
        
        year_input = page.locator('[name="BirthYear"]')
        if year_input.count() > 0:
            year_input.fill(year)
            time.sleep(0.3)
        
        month_select = page.locator('[name="BirthMonth"]')
        if month_select.count() > 0:
            month_select.click()
            time.sleep(0.3)
            page.locator(f'[role="option"]:text-is("{month}月")').click()
            time.sleep(0.3)
        
        day_select = page.locator('[name="BirthDay"]')
        if day_select.count() > 0:
            day_select.click()
            time.sleep(0.3)
            page.locator(f'[role="option"]:text-is("{day}日")').click()
            time.sleep(0.3)
        
        next_btn = page.locator('[data-testid="primaryButton"]')
        if next_btn.count() > 0:
            next_btn.click()
            time.sleep(3)
        
        # 5. 填写姓名
        print("  [6/6] 填写姓名...")
        lastname = fake.last_name()
        firstname = fake.first_name()
        
        lastname_input = page.locator('#lastNameInput')
        if lastname_input.count() > 0:
            lastname_input.fill(lastname)
            time.sleep(0.3)
        
        firstname_input = page.locator('#firstNameInput')
        if firstname_input.count() > 0:
            firstname_input.fill(firstname)
            time.sleep(0.3)
        
        next_btn = page.locator('[data-testid="primaryButton"]')
        if next_btn.count() > 0:
            next_btn.click()
            time.sleep(5)
        
        # 6. 处理验证码
        print("  [验证码] 处理中...")
        captcha_result = handle_captcha(page, max_retries=3)
        
        if captcha_result:
            # 处理"同意并继续"
            try:
                agree_btn = page.get_by_text('同意并继续')
                if agree_btn.count() > 0:
                    agree_btn.click()
                    time.sleep(3)
            except:
                pass
            
            # 检查是否注册成功
            title = page.title()
            url = page.url
            if 'login.live.com' in url or 'outlook.live.com' in url:
                print(f"  ✓ 注册成功!")
                return True, email, password
        
        print(f"  ✗ 注册失败")
        return False, email, password
        
    except Exception as e:
        print(f"  ✗ 注册异常: {e}")
        return False, email, password

# ============ 主程序 ============

def main():
    """主函数"""
    # 加载代理列表
    with open('/Users/pingchuan/Library/Application Support/geekez-browser/BrowserProfiles/profiles.json', 'r') as f:
        profiles = json.load(f)
    
    # 提取代理
    proxies = []
    for p in profiles:
        proxy_str = p.get('proxyStr', '')
        if proxy_str and proxy_str.startswith('ss://'):
            proxies.append({
                'name': p.get('name', ''),
                'proxy': proxy_str
            })
    
    print(f"共找到 {len(proxies)} 个代理")
    
    # 结果记录
    results = []
    success_count = 0
    fail_count = 0
    
    # 配置
    debug_port = 24000
    max_attempts = 10  # 尝试次数
    
    from playwright.sync_api import sync_playwright
    
    for attempt in range(max_attempts):
        print(f"\n{'='*60}")
        print(f"尝试 {attempt + 1}/{max_attempts}")
        print(f"{'='*60}")
        
        # 选择代理（轮询）
        proxy_info = proxies[attempt % len(proxies)]
        print(f"代理: {proxy_info['name']}")
        
        # 生成随机账号
        email = random_email()
        password = generate_password()
        
        # 创建临时用户数据目录
        user_data_dir = f"/tmp/chrome_outlook_{attempt}_{int(time.time())}"
        os.makedirs(user_data_dir, exist_ok=True)
        
        # 启动 Chrome
        proc = start_chrome(user_data_dir, debug_port)
        if not proc:
            print("  Chrome 启动失败，跳过")
            fail_count += 1
            continue
        
        # 等待 Chrome 完全启动
        time.sleep(3)
        
        # 连接到 Chrome
        ws_url = get_ws_url(debug_port)
        if not ws_url:
            print("  无法获取 WebSocket URL，跳过")
            fail_count += 1
            continue
        
        p = sync_playwright().start()
        try:
            browser = p.chromium.connect_over_cdp(ws_url, timeout=30000)
            contexts = browser.contexts
            
            if contexts and contexts[0].pages:
                page = contexts[0].pages[0]
                
                # 执行注册
                success, email, password = register_outlook(page, email, password)
                
                if success:
                    success_count += 1
                    results.append({
                        'email': f"{email}@outlook.com",
                        'password': password,
                        'proxy': proxy_info['name'],
                        'status': 'success'
                    })
                    
                    # 保存成功结果
                    with open('Results/outlook_success.txt', 'a', encoding='utf-8') as f:
                        f.write(f"{email}@outlook.com:{password}\n")
                else:
                    fail_count += 1
                    results.append({
                        'email': f"{email}@outlook.com",
                        'password': password,
                        'proxy': proxy_info['name'],
                        'status': 'failed'
                    })
            
            browser.close()
        except Exception as e:
            print(f"  连接失败: {e}")
            fail_count += 1
        finally:
            p.stop()
        
        # 清理
        try:
            proc.terminate()
        except:
            pass
        
        # 等待一段时间再尝试下一个
        time.sleep(2)
    
    # 打印结果汇总
    print(f"\n{'='*60}")
    print(f"结果汇总")
    print(f"{'='*60}")
    print(f"总尝试: {max_attempts}")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"成功率: {success_count/max_attempts*100:.1f}%")
    
    print(f"\n成功账号:")
    for r in results:
        if r['status'] == 'success':
            print(f"  {r['email']}:{r['password']} (代理: {r['proxy']})")

if __name__ == "__main__":
    main()
