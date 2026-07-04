import os
import time
import json
import random
import threading
from faker import Faker
from abc import ABC, abstractmethod
from utils import capture_page_state, check_captcha_type

class BaseBrowserController(ABC):
    """
    所有浏览器通用的接口和共享逻辑
    """

    def __init__(self):
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.wait_time = data['bot_protection_wait'] * 1000
        self.max_captcha_retries = data['max_captcha_retries']
        self.enable_oauth2 = data["oauth2"]['enable_oauth2']
        self.proxy = data['proxy']
        self.email_suffix = data['email_suffix']

        self.thread_local = threading.local()
        self.cleanup_lock = threading.Lock()
        self.active_resources = []  # 记录资源以便关闭

        self.results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Results')
        os.makedirs(self.results_dir, exist_ok=True)


    @abstractmethod
    def launch_browser(self):
        """
        获取浏览器实例,返回playwright_instance, browser_instance
        """
        pass

    @abstractmethod
    def handle_captcha(self, page):
        """
        验证码处理流程
        """
        pass

    @abstractmethod 
    def clean_up(self, page=None, type = "all_browser"):
        """
        清理自己创建的内容
        一个是单进程结束后关闭进程，另一个是程序结束后清除所有内容
        """
        pass

    @abstractmethod
    def get_thread_page(self):
        """
        返回页面
        """


    def get_thread_browser(self):
        """
        通用逻辑:获取不同进程的浏览器
        """

        if not hasattr(self.thread_local,"browser"):

            p, b  = self.launch_browser()
            if not p:
                return False

            self.thread_local.playwright = p
            self.thread_local.browser = b

            with self.cleanup_lock:
                self.active_resources.append((p, b))

        return self.thread_local.browser

    def outlook_register(self, page, email, password):
        """
        通用逻辑:注册邮箱
        """

        fake = Faker()

        lastname = fake.last_name()
        firstname = fake.first_name()
        year = str(random.randint(1960, 2005))
        month = str(random.randint(1, 12))
        day = str(random.randint(1, 28))

        try:
            page.goto("https://outlook.live.com/mail/0/?prompt=create_account", timeout=20000, wait_until="domcontentloaded")
            page.get_by_text('同意并继续').wait_for(timeout=30000)
            start_time = time.time()
            page.wait_for_timeout(0.1 * self.wait_time)
            page.get_by_text('同意并继续').click(timeout=30000)
        except:
            print("[Error: IP] - IP质量不佳，无法进入注册界面。")
            capture_page_state(page, "ip_quality")
            return False

        try:
            if self.email_suffix == "@hotmail.com":
                page.get_by_text("@outlook.com").click(timeout=10000)
                page.locator(f'[role="option"]:text-is("@hotmail.com")').click()

            page.locator('[aria-label="新建电子邮件"]').type(email, delay=0.015 * self.wait_time, timeout=15000)
            page.wait_for_timeout(0.03 * self.wait_time)
            page.locator('[data-testid="primaryButton"]').click(timeout=5000)
            page.wait_for_timeout(0.05 * self.wait_time)
            page.locator('[type="password"]').type(password, delay=0.01 * self.wait_time, timeout=15000)
            page.wait_for_timeout(0.05 * self.wait_time)
            page.locator('[data-testid="primaryButton"]').click(timeout=5000)

            page.wait_for_timeout(0.06 * self.wait_time)
            page.locator('[name="BirthYear"]').fill(year, timeout=10000)

            page.locator('[name="BirthMonth"]').click()
            page.wait_for_timeout(0.04 * self.wait_time)
            page.locator(f'[role="option"]:text-is("{month}月")').click()
            page.wait_for_timeout(0.06 * self.wait_time)
            page.locator('[name="BirthDay"]').click()
            page.wait_for_timeout(0.05 * self.wait_time)
            page.locator(f'[role="option"]:text-is("{day}日")').click()
            page.wait_for_timeout(0.03 * self.wait_time)
            page.locator('[data-testid="primaryButton"]').click(timeout=5000)

            page.wait_for_timeout(0.06 * self.wait_time)
            page.locator('#lastNameInput').type(lastname, delay=0.008 * self.wait_time, timeout=15000)
            page.wait_for_timeout(0.04 * self.wait_time)
            page.locator('#firstNameInput').fill(firstname, timeout=10000)

            if time.time() - start_time < self.wait_time / 1000:
                page.wait_for_timeout(self.wait_time - (time.time() - start_time) * 1000)

            page.locator('[data-testid="primaryButton"]').click(timeout=5000)
            page.locator('span > [href="https://go.microsoft.com/fwlink/?LinkID=521839"]').wait_for(state='detached', timeout=22000)
            page.wait_for_timeout(400)

            if page.get_by_text('一些异常活动').count() or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count() > 0:
                print("[Error: IP or browser] - 当前IP注册频率过快。检查IP与是否为指纹浏览器并关闭了无头模式。")
                capture_page_state(page, "rate_limited")
                return False

            captcha_type = check_captcha_type(page)
            if captcha_type == 'funcaptcha_iframe':
                print("[Error: FunCaptcha] - 验证码类型错误，非按压验证码。")
                capture_page_state(page, "funcaptcha")
                return False

            if captcha_type == 'longpress':
                print("[Info] - 检测到长按验证，正在处理...")
                self._handle_longpress_captcha(page)

            captcha_result = self.handle_captcha(page)
            if not captcha_result:
                raise TimeoutError

        except Exception:
            print("[Error: IP] - 加载超时或因触发机器人检测导致按压次数达到最大仍未通过。")
            capture_page_state(page, "timeout_or_bot")
            return False

        filename = os.path.join(self.results_dir, 'logged_email.txt' if self.enable_oauth2 else 'unlogged_email.txt')
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{email}{self.email_suffix}: {password}\n")
        print(f'[Success: Email Registration] - {email}{self.email_suffix}: {password}')

        if not self.enable_oauth2:
            return True

    def _handle_longpress_captcha(self, page):
        """
        处理 PerimeterX 长按验证码
        使用 CDP Input API 和贝塞尔曲线模拟真人操作
        """
        try:
            import random as rnd

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
                # 回退到原来的逻辑
                btn = page.locator('#human > div:first-child')
                btn.wait_for(state='visible', timeout=10000)
                box = btn.bounding_box()
                if not box:
                    return False
                btn_x = box['x'] + box['width'] / 2
                btn_y = box['y'] + box['height'] / 2
            else:
                # 按钮在 iframe 底部中间
                btn_x = iframe_info['x'] + iframe_info['width'] / 2
                btn_y = iframe_info['y'] + iframe_info['height'] - 30

            print(f"  [Captcha] 按钮位置: x={btn_x:.0f}, y={btn_y:.0f}")

            # 使用 CDP session
            cdp = page.context.new_cdp_session(page)

            # 贝塞尔曲线函数
            def bezier_curve(t, p0, p1, p2, p3):
                u = 1 - t
                return u**3 * p0 + 3*u**2*t * p1 + 3*u*t**2 * p2 + t**3 * p3

            # 1. 从随机位置开始移动
            start_x = rnd.randint(100, 400)
            start_y = rnd.randint(100, 300)

            # 2. 生成贝塞尔曲线控制点
            cp1_x = start_x + (btn_x - start_x) * 0.3 + rnd.uniform(-50, 50)
            cp1_y = start_y + (btn_y - start_y) * 0.3 + rnd.uniform(-50, 50)
            cp2_x = start_x + (btn_x - start_x) * 0.7 + rnd.uniform(-50, 50)
            cp2_y = start_y + (btn_y - start_y) * 0.7 + rnd.uniform(-50, 50)

            # 3. 沿贝塞尔曲线移动鼠标
            steps = rnd.randint(20, 40)
            for i in range(steps):
                t = i / steps
                x = bezier_curve(t, start_x, cp1_x, cp2_x, btn_x)
                y = bezier_curve(t, start_y, cp1_y, cp2_y, btn_y)

                # 添加微小的随机抖动
                x += rnd.uniform(-2, 2)
                y += rnd.uniform(-2, 2)

                cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": x,
                    "y": y,
                    "button": "none",
                    "clickCount": 0,
                    "pointerType": "mouse"
                })

                time.sleep(rnd.uniform(0.01, 0.05))

            time.sleep(rnd.uniform(0.1, 0.3))

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

            print("  [Captcha] 按住中...")

            # 5. 保持按住，偶尔微调位置
            hold_time = rnd.uniform(10, 15)
            start_time = time.time()

            while time.time() - start_time < hold_time:
                # 偶尔移动鼠标（模拟手抖）
                if rnd.random() < 0.2:
                    jitter_x = btn_x + rnd.uniform(-3, 3)
                    jitter_y = btn_y + rnd.uniform(-3, 3)
                    cdp.send("Input.dispatchMouseEvent", {
                        "type": "mouseMoved",
                        "x": jitter_x,
                        "y": jitter_y,
                        "button": "left",
                        "clickCount": 0,
                        "buttons": 1,
                        "pointerType": "mouse"
                    })

                time.sleep(rnd.uniform(0.3, 0.7))

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

            print("  [Captcha] 松开，等待验证结果...")
            time.sleep(5)

            # 检查是否通过
            title = page.title()
            if '机器人' not in title:
                print("  [Captcha] 验证通过!")
                cdp.detach()
                return True

            cdp.detach()
            return False

        except Exception as e:
            print(f"[Debug] 长按异常: {e}")
            return False