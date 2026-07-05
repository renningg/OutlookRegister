#!/usr/bin/env python3
"""
Outlook 注册自动化 — GeekEZ 指纹环境 + CDP 精确定位 + pyautogui

用法:
  python register.py profiles                    # 列出所有 profile
  python register.py launch --profile test       # 自动启动并注册
  python register.py connect --port 24000        # 连接已运行的 GeekEZ
"""
import sys, os, json, time, random, string, subprocess, socket, argparse, math, struct, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from faker import Faker
from playwright.sync_api import sync_playwright
import pyautogui

pyautogui.PAUSE = 0.01
pyautogui.FAILSAFE = True

fake = Faker()

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GEEKEZ_DIR = os.path.expanduser(
    "~/Library/Application Support/geekez-browser/BrowserProfiles"
)
PROFILES_FILE = os.path.join(GEEKEZ_DIR, "profiles.json")

# ──────────────── 工具函数 ────────────────

def random_email(length=None):
    length = length or random.randint(12, 14)
    first = random.choice(string.ascii_lowercase)
    rest = [
        random.choice(string.digits) if random.random() < 0.07
        else random.choice(string.ascii_lowercase)
        for _ in range(length - 1)
    ]
    return first + "".join(rest)


def generate_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pw = "".join(random.choice(chars) for _ in range(random.randint(11, 15)))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%^&*" for c in pw)
        ):
            return pw


def check_captcha_type(page):
    try:
        if page.locator('iframe[title="Human Iframe"]').count() > 0:
            if page.locator('[data-testid="accessibleImg"]').count() > 0:
                return "longpress"
            if page.locator('[aria-label="可访问性挑战"]').count() > 0:
                return "push_button"
            return "hsprotect_unknown"
        if page.locator("iframe#enforcementFrame").count() > 0:
            return "funcaptcha_iframe"
        if page.locator('iframe[title="验证质询"]').count() > 0:
            return "push_button"
        title = page.title()
        if "机器人" in title:
            return "bot_detection"
    except Exception:
        pass
    return "unknown"

# ──────────────── CDP 直接操作 (绕过 Playwright iframe 限制) ────────────────

class CDPClient:
    """直接通过 WebSocket 与 Chrome CDP 通信"""

    def __init__(self, ws_url):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=10)
        self._id = 0
        self._responses = {}

    def send(self, method, params=None):
        self._id += 1
        msg = {"id": self._id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        # 等待对应 id 的响应
        deadline = time.time() + 10
        while time.time() < deadline:
            self.ws.settimeout(2)
            try:
                data = json.loads(self.ws.recv())
                if data.get("id") == self._id:
                    return data.get("result", {})
            except Exception:
                continue
        return {}

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def get_ws_url(debug_port):
    import urllib.request
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{debug_port}/json/version", timeout=5
        ) as resp:
            data = json.loads(resp.read())
            return data.get("webSocketDebuggerUrl", "")
    except Exception as e:
        print(f"  获取 WS URL 失败: {e}")
        return None


def find_circle_screen_coords(debug_port):
    """
    用 CDP 直接找到 circle 元素的屏幕坐标。
    流程:
      1. Page.getFrameTree → 找到包含 circle 的 frame
      2. DOM.getDocument → 获取该 frame 的 DOM
      3. DOM.querySelector("circle") → 找到 circle 节点
      4. DOM.getBoxModel → 获取绝对坐标
    返回 (screen_x, screen_y) 或 None
    """
    ws_url = get_ws_url(debug_port)
    if not ws_url:
        return None

    cdp = None
    try:
        cdp = CDPClient(ws_url)

        # 获取 frame 树
        tree = cdp.send("Page.getFrameTree")
        frame_tree = tree.get("frameTree", {})

        # 递归找所有 frame
        def collect_frames(node, result=None):
            if result is None:
                result = []
            frame = node.get("frame", {})
            result.append(frame)
            for child in node.get("childFrames", []):
                collect_frames(child, result)
            return result

        all_frames = collect_frames(frame_tree)
        print(f"    CDP: 找到 {len(all_frames)} 个 frame")

        # 启用 DOM
        cdp.send("DOM.enable")

        # 在每个 frame 中查找 circle
        for frame in all_frames:
            frame_id = frame.get("id", "")
            frame_url = frame.get("url", "")[:60]

            try:
                # 获取该 frame 的文档节点
                doc = cdp.send("DOM.getDocument", {"depth": 0, "pierce": True})
                root_node_id = doc.get("root", {}).get("nodeId", 0)
                if not root_node_id:
                    continue

                # 在整个文档中搜索 circle (DOM 会穿透 iframe)
                result = cdp.send("DOM.querySelector", {
                    "nodeId": root_node_id,
                    "selector": "circle"
                })
                node_id = result.get("nodeId", 0)
                if not node_id:
                    continue

                # 获取 box model (屏幕绝对坐标)
                box = cdp.send("DOM.getBoxModel", {"nodeId": node_id})
                content = box.get("model", {}).get("content", [])
                if len(content) >= 8:
                    # content 是 [x1,y1, x2,y2, x3,y3, x4,y4] 四个角
                    x = (content[0] + content[2] + content[4] + content[6]) / 4
                    y = (content[1] + content[3] + content[5] + content[7]) / 4
                    print(f"    CDP: circle 屏幕坐标 = ({x:.0f}, {y:.0f})")
                    return (x, y)
            except Exception as e:
                continue

        print("    CDP: 未找到 circle")
        return None

    finally:
        if cdp:
            cdp.close()


def find_circle_abs_pos(page):
    """
    在所有 Playwright frames 中找 circle，逐层累加 iframe 偏移得到绝对坐标。
    返回 (abs_x, abs_y) 或 None
    """
    for fr in page.frames:
        try:
            local = fr.evaluate("""() => {
                const c = document.querySelector('circle');
                if (!c) return null;
                const r = c.getBoundingClientRect();
                return {x: r.x + r.width/2, y: r.y + r.height/2};
            }""")
            if not local:
                continue

            print(f"    circle 在 frame '{fr.url[:40]}' local=({local['x']:.0f},{local['y']:.0f})")

            # 逐层向上找 iframe 偏移
            abs_x, abs_y = local['x'], local['y']
            cur = fr
            while cur.parent_frame:
                parent = cur.parent_frame
                # 在父 frame 中找包含当前 frame 的 iframe 元素位置
                iframe_pos = parent.evaluate("""() => {
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        const r = iframe.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) return {x: r.x, y: r.y};
                    }
                    return null;
                }""")
                if iframe_pos:
                    abs_x += iframe_pos['x']
                    abs_y += iframe_pos['y']
                    print(f"    +parent iframe offset ({iframe_pos['x']:.0f},{iframe_pos['y']:.0f})")
                cur = parent

            # 最后加主页面的 scroll 偏移
            scroll = page.evaluate("() => ({x: window.scrollX, y: window.scrollY})")
            abs_x += scroll['x']
            abs_y += scroll['y']

            print(f"    绝对坐标: ({abs_x:.0f},{abs_y:.0f})")
            return (abs_x, abs_y)
        except Exception as e:
            continue
    return None


def click_at(page, debug_port, x, y):
    """用 CDP Input 在 (x,y) 执行点击"""
    ws_url = get_ws_url(debug_port)
    if not ws_url:
        return False
    cdp = CDPClient(ws_url)
    try:
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
            "button": "none", "pointerType": "mouse"
        })
        time.sleep(random.uniform(0.05, 0.15))
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1, "buttons": 1, "pointerType": "mouse"
        })
        time.sleep(random.uniform(0.05, 0.15))
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1, "buttons": 0, "pointerType": "mouse"
        })
        return True
    finally:
        cdp.close()


# ──────────────── pyautogui 鼠标模拟 ────────────────

def _bezier(t, p0, p1, p2, p3):
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


def human_move_to(screen_x, screen_y):
    cx, cy = pyautogui.position()
    dist = math.hypot(screen_x - cx, screen_y - cy)
    steps = max(int(dist / 8), 25)
    steps = min(steps, 60)
    cp1x = cx + (screen_x - cx) * 0.3 + random.uniform(-40, 40)
    cp1y = cy + (screen_y - cy) * 0.3 + random.uniform(-40, 40)
    cp2x = cx + (screen_x - cx) * 0.7 + random.uniform(-40, 40)
    cp2y = cy + (screen_y - cy) * 0.7 + random.uniform(-40, 40)
    for i in range(steps + 1):
        t = i / steps
        x = _bezier(t, cx, cp1x, cp2x, screen_x) + random.uniform(-1.5, 1.5)
        y = _bezier(t, cy, cp1y, cp2y, screen_y) + random.uniform(-1.5, 1.5)
        pyautogui.moveTo(x, y, _pause=False)
        time.sleep(random.uniform(0.005, 0.025))


def pyautogui_longpress(screen_x, screen_y, hold_min=12, hold_max=20):
    human_move_to(screen_x, screen_y)
    time.sleep(random.uniform(0.15, 0.4))
    pyautogui.mouseDown(button="left")
    hold_time = random.uniform(hold_min, hold_max)
    print(f"    pyautogui 长按中... ({hold_time:.1f}s)")
    start = time.time()
    while time.time() - start < hold_time:
        if random.random() < 0.12:
            jx = screen_x + random.uniform(-4, 4)
            jy = screen_y + random.uniform(-4, 4)
            pyautogui.moveTo(jx, jy, duration=random.uniform(0.05, 0.15), _pause=False)
        time.sleep(random.uniform(0.25, 0.6))
    pyautogui.mouseUp(button="left")
    print("    pyautogui 已松开")


def pyautogui_click(screen_x, screen_y):
    human_move_to(screen_x, screen_y)
    time.sleep(random.uniform(0.08, 0.2))
    pyautogui.click(screen_x, screen_y)

# ──────────────── 验证码处理 ────────────────

def handle_captcha(page, debug_port):
    ct = "unknown"
    for _ in range(20):
        ct = check_captcha_type(page)
        if ct != "unknown":
            break
        time.sleep(1)
    else:
        print("    未检测到验证码")
        return True

    print(f"    验证码类型: {ct}")
    if ct == "funcaptcha_iframe":
        print("    FunCaptcha 需要第三方服务，跳过")
        return False

    for attempt in range(3):
        print(f"    尝试 {attempt+1}/3 (type={ct})")
        time.sleep(3)

        try:
            # 找 circle 绝对坐标
            coords = find_circle_abs_pos(page)
            if not coords:
                print("    找不到 circle")
                if attempt < 2:
                    page.reload()
                    time.sleep(5)
                    ct = check_captcha_type(page)
                continue

            cx, cy = coords
            # 用 CDP Input 点击 circle
            click_at(page, debug_port, cx, cy)
            print("    已点击 circle")

            # 等待 "再次按下"
            time.sleep(2)
            for fr in page.frames:
                try:
                    retry_pos = fr.evaluate("""() => {
                        const els = document.querySelectorAll('*');
                        for (const el of els) {
                            if (el.innerText && el.innerText.trim() === '再次按下' && el.offsetParent !== null) {
                                const r = el.getBoundingClientRect();
                                return {x: r.x + r.width/2, y: r.y + r.height/2};
                            }
                        }
                        return null;
                    }""")
                    if retry_pos:
                        # 用同样的逐层累加方法
                        rx, ry = retry_pos['x'], retry_pos['y']
                        cur = fr
                        while cur.parent_frame:
                            parent = cur.parent_frame
                            iframe_pos = parent.evaluate("""() => {
                                const iframes = document.querySelectorAll('iframe');
                                for (const iframe of iframes) {
                                    const r = iframe.getBoundingClientRect();
                                    if (r.width > 0 && r.height > 0) return {x: r.x, y: r.y};
                                }
                                return null;
                            }""")
                            if iframe_pos:
                                rx += iframe_pos['x']
                                ry += iframe_pos['y']
                            cur = parent
                        scroll = page.evaluate("() => ({x: window.scrollX, y: window.scrollY})")
                        rx += scroll['x']
                        ry += scroll['y']
                        print(f"    点击 '再次按下' ({rx:.0f},{ry:.0f})")
                        click_at(page, debug_port, rx, ry)
                        break
                except Exception:
                    continue

            # 等待验证结果
            for w in range(30):
                time.sleep(1)
                current = check_captcha_type(page)
                if current == "unknown":
                    print("    验证通过!")
                    return True
                title = page.title()
                if "机器人" not in title and "outlook.live.com/mail" in page.url:
                    print(f"    页面跳转: {title[:30]}")
                    return True
                if w % 10 == 0 and w > 0:
                    print(f"    等待 {w}s... type={current}")

        except Exception as e:
            print(f"    异常: {e}")
            import traceback
            traceback.print_exc()

        if attempt < 2:
            page.reload()
            time.sleep(5)
            ct = check_captcha_type(page)

    return False

# ──────────────── GeekEZ Profile 管理 ────────────────

def list_profiles():
    with open(PROFILES_FILE) as f:
        profiles = json.load(f)
    print(f"\n{'名称':35s} | {'扩展':^4s} | {'Xray SOCKS':^15s}")
    print("-" * 70)
    for p in profiles:
        cid = p["id"]
        ext_path = os.path.join(GEEKEZ_DIR, cid, "extension")
        cfg_path = os.path.join(GEEKEZ_DIR, cid, "config.json")
        has_ext = os.path.exists(ext_path) and os.listdir(ext_path)
        xray_port = "?"
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
            inbounds = cfg.get("inbounds", [])
            if inbounds:
                xray_port = str(inbounds[0].get("port", "?"))
        print(f"  {p['name']:33s} | {'Y' if has_ext else 'N':^4s} | {'127.0.0.1:'+xray_port:^15s}")
    print()


def find_profile(name):
    with open(PROFILES_FILE) as f:
        profiles = json.load(f)
    for p in profiles:
        if p["name"] == name:
            return p
    for p in profiles:
        if name.lower() in p["name"].lower():
            return p
    return profiles[0] if profiles else None

# ──────────────── Chrome 启动 ────────────────

def launch_chrome(profile_id, debug_port):
    ext_path = os.path.join(GEEKEZ_DIR, profile_id, "extension")
    user_data = os.path.join(GEEKEZ_DIR, profile_id, "browser_data")
    os.makedirs(user_data, exist_ok=True)
    os.makedirs(os.path.join(user_data, "Default"), exist_ok=True)

    args = [
        CHROME,
        f"--user-data-dir={user_data}",
        f"--remote-debugging-port={debug_port}",
        "--remote-allow-origins=*",
        "--no-first-run", "--no-default-browser-check",
        "--window-size=1280,800",
        "--disable-blink-features=AutomationControlled",
    ]
    if os.path.exists(ext_path):
        args.append(f"--load-extension={ext_path}")

    subprocess.run(["pkill", "-f", f"remote-debugging-port={debug_port}"], capture_output=True)
    time.sleep(1)

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(20):
        time.sleep(1)
        s = socket.socket()
        if s.connect_ex(("127.0.0.1", debug_port)) == 0:
            s.close()
            print(f"  Chrome 已就绪 (端口 {debug_port}, {i+1}s)")
            return proc
        s.close()
    print(f"  Chrome 启动超时")
    return None

# ──────────────── 注册流程 ────────────────

def register_one(email, password, ws_url, debug_port):
    print(f"\n{'='*50}")
    print(f"  邮箱: {email}@outlook.com")
    print(f"  密码: {password}")
    print(f"{'='*50}")

    os.environ["no_proxy"] = "127.0.0.1,localhost,.local"

    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(ws_url, timeout=60000)
        context = browser.contexts[0]
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        # 浏览伪装
        for url in ["https://www.google.com", "https://www.bing.com"]:
            try:
                pg = context.new_page()
                pg.goto(url, timeout=8000, wait_until="commit")
            except Exception:
                pass

        page = context.new_page()

        # Step 1
        print("  [1/7] 导航到注册页...")
        page.goto("https://outlook.live.com/mail/0/?prompt=create_account",
                  timeout=30000, wait_until="networkidle")
        time.sleep(3)

        for _ in range(20):
            btn = page.get_by_text("同意并继续")
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                time.sleep(3)
                continue
            if page.locator('[aria-label="新建电子邮件"]').count() > 0:
                break
            time.sleep(1)

        # Step 2-5: 表单填写
        print("  [2/7] 输入邮箱...")
        page.locator('[aria-label="新建电子邮件"]').fill(email)
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)

        print("  [3/7] 输入密码...")
        page.locator('[type="password"]').fill(password)
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)

        print("  [4/7] 填写生日...")
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

        print("  [5/7] 填写姓名...")
        page.locator("#lastNameInput").fill(fake.last_name())
        page.locator("#firstNameInput").fill(fake.first_name())
        time.sleep(0.5)
        page.locator('[data-testid="primaryButton"]').click()
        time.sleep(3)

        # Step 6: 验证码
        print("  [6/7] 处理验证码...")
        if not handle_captcha(page, debug_port):
            print("  验证码处理失败")
            return False

        # Step 7: 等待完成
        print("  [7/7] 等待注册完成...")
        for step in range(120):
            url = page.url
            title = page.title()
            if "outlook.live.com/mail" in url or "收件箱" in title or "Inbox" in title:
                print("  注册成功!")
                return True
            try:
                btn = page.get_by_text("同意并继续")
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(force=True)
                    time.sleep(5)
                    continue
            except Exception:
                pass
            ct = check_captcha_type(page)
            if ct != "unknown":
                print(f"  再次出现验证码: {ct}")
                if handle_captcha(page, debug_port):
                    continue
                break
            if "一些异常活动" in page.content():
                print("  IP 被限制")
                break
            if step % 20 == 0:
                print(f"  等待中 {step}s...")
            time.sleep(1)
        else:
            print("  注册超时")
        return False

    except Exception as e:
        print(f"  异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        p.stop()

# ──────────────── 命令 ────────────────

def cmd_profiles(args):
    list_profiles()

def cmd_connect(args):
    print(f"\n连接 GeekEZ Browser (端口 {args.port})...")
    ws_url = get_ws_url(args.port)
    if not ws_url:
        print(f"无法连接到端口 {args.port}")
        return
    print(f"已连接: {ws_url}")

    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Results")
    os.makedirs(results_dir, exist_ok=True)

    for i in range(args.count):
        if i > 0:
            time.sleep(random.uniform(3, 8))
        email = random_email()
        password = generate_password()
        ok = register_one(email, password, ws_url, args.port)
        if ok:
            with open(os.path.join(results_dir, "outlook_success.txt"), "a") as f:
                f.write(f"{email}@outlook.com:{password}:geekez\n")
            print(f"  已保存: {email}@outlook.com:{password}")

def cmd_launch(args):
    profile = find_profile(args.profile)
    if not profile:
        print(f"找不到 profile: {args.profile}")
        return

    print(f"\nProfile: {profile['name']}")

    proxy_proc, socks_port = None, None
    print(f"  代理: 直连")

    chrome_proc = launch_chrome(profile["id"], args.port)
    if not chrome_proc:
        return

    ws_url = get_ws_url(args.port)
    if not ws_url:
        print("无法获取 WS URL")
        chrome_proc.kill()
        return

    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Results")
    os.makedirs(results_dir, exist_ok=True)

    try:
        for i in range(args.count):
            if i > 0:
                time.sleep(random.uniform(3, 8))
            email = random_email()
            password = generate_password()
            ok = register_one(email, password, ws_url, args.port)
            if ok:
                with open(os.path.join(results_dir, "outlook_success.txt"), "a") as f:
                    f.write(f"{email}@outlook.com:{password}:geekez+cdp\n")
                print(f"  已保存: {email}@outlook.com:{password}")
    finally:
        if not args.keep:
            print("\n清理资源...")
            chrome_proc.kill()
        else:
            print("\n浏览器保持打开 (--keep)")

# ──────────────── 主程序 ────────────────

def main():
    parser = argparse.ArgumentParser(description="Outlook 注册 (GeekEZ + CDP + pyautogui)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("profiles", help="列出所有 GeekEZ profile")

    p_connect = sub.add_parser("connect", help="连接已运行的 GeekEZ Browser")
    p_connect.add_argument("--port", type=int, default=9222)
    p_connect.add_argument("--count", type=int, default=1)

    p_launch = sub.add_parser("launch", help="自动启动 Chrome + GeekEZ 环境")
    p_launch.add_argument("--profile", default="test")
    p_launch.add_argument("--port", type=int, default=9222)
    p_launch.add_argument("--count", type=int, default=1)
    p_launch.add_argument("--keep", action="store_true")

    args = parser.parse_args()

    if args.command == "profiles":
        cmd_profiles(args)
    elif args.command == "connect":
        cmd_connect(args)
    elif args.command == "launch":
        cmd_launch(args)
    else:
        parser.print_help()
        print("\n示例:")
        print("  python register.py profiles")
        print("  python register.py launch --profile test")
        print("  python register.py connect --port 24000")

if __name__ == "__main__":
    main()
