"""
GeekEZ Browser 连接控制器
通过远程调试端口连接到已启动的 Chrome
"""
import json
import time
import random
import threading
import urllib.request
import socket
from playwright.sync_api import sync_playwright
from .base_controller import BaseBrowserController
from utils import capture_page_state, check_captcha_type


class GeekEzController(BaseBrowserController):
    """
    通过 CDP 连接到 GeekEZ Browser 启动的 Chrome
    """

    def __init__(self, debug_port=9222):
        super().__init__()
        self.debug_port = debug_port
        self._playwright = None
        self._browser = None
        self._connected = False
        self._lock = threading.Lock()
        self._ws_url = None

    def launch_browser(self):
        """
        验证端口可用并获取 WebSocket URL
        """
        try:
            print(f"[Info] 正在连接 GeekEZ Browser (端口: {self.debug_port})...")

            # 检查端口
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', self.debug_port))
            sock.close()

            if result != 0:
                print(f"[Error] 无法连接到端口 {self.debug_port}")
                return False, False

            # 获取 WebSocket URL
            with urllib.request.urlopen(f"http://127.0.0.1:{self.debug_port}/json/version", timeout=5) as response:
                version_info = json.loads(response.read())
                self._ws_url = version_info.get('webSocketDebuggerUrl', '')
                if not self._ws_url:
                    print("[Error] 无法获取 WebSocket URL")
                    return False, False
                print(f"[Info] WebSocket URL: {self._ws_url}")

            # 启动 Playwright（仅用于后续连接）
            p = sync_playwright().start()
            self._playwright = p
            self._connected = True

            print(f"[Success] 已准备好连接 GeekEZ Browser")
            # 返回 p 和一个占位符，实际连接在 get_thread_page 中进行
            return p, True

        except Exception as e:
            print(f"[Error] 连接 GeekEZ Browser 失败: {e}")
            return False, False

    def get_thread_browser(self):
        """
        获取浏览器实例 - 延迟连接到 CDP
        """
        if not self._connected or not self._ws_url:
            return False

        # 如果已经有浏览器实例，直接返回
        if hasattr(self.thread_local, "browser") and self.thread_local.browser:
            return self.thread_local.browser

        try:
            # 延迟连接到 CDP
            print(f"[Info] 正在建立 CDP 连接...")
            browser = self._playwright.chromium.connect_over_cdp(self._ws_url, timeout=30000)
            self._browser = browser
            self.thread_local.browser = browser

            with self.cleanup_lock:
                self.active_resources.append((self._playwright, browser))

            print(f"[Success] CDP 连接成功")
            return browser

        except Exception as e:
            print(f"[Error] CDP 连接失败: {e}")
            return False

    def get_thread_page(self):
        """
        获取浏览器页面
        """
        browser = self.get_thread_browser()
        if not browser:
            return None

        try:
            # 获取已有的上下文和页面
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                pages = context.pages
                if pages:
                    return pages[0]

            # 尝试创建新页面
            try:
                context = browser.new_context()
                return context.new_page()
            except Exception:
                # CDP 连接限制
                all_pages = []
                for ctx in contexts:
                    all_pages.extend(ctx.pages)
                if all_pages:
                    return all_pages[0]
                return None

        except Exception as e:
            print(f"[Error] 获取页面失败: {e}")
            return None

    def handle_captcha(self, page):
        """
        处理验证码
        """
        captcha_type = check_captcha_type(page)

        if captcha_type == 'unknown':
            return True

        if captcha_type == 'longpress':
            print("[Info] 检测到长按验证，正在处理...")
            result = self._handle_longpress_captcha(page)
            page.wait_for_timeout(3000)
            captcha_type = check_captcha_type(page)
            if captcha_type == 'unknown':
                return True

        if captcha_type == 'push_button':
            try:
                iframe1 = page.frame_locator('iframe[title="验证质询"]')
                iframe2 = iframe1.frame_locator('iframe[style*="display: block"]')

                for _ in range(self.max_captcha_retries + 1):
                    page.wait_for_timeout(200)
                    try:
                        loc = iframe2.locator('[aria-label="可访问性挑战"]')
                        box = loc.bounding_box()
                        if not box:
                            return True
                        x = box['x'] + box['width'] / 2 + random.randint(-10, 10)
                        y = box['y'] + box['height'] / 2 + random.randint(-10, 10)
                        page.mouse.click(x, y)

                        loc2 = iframe2.locator('[aria-label="再次按下"]')
                        box2 = loc2.bounding_box()
                        x = box2['x'] + box2['width'] / 2 + random.randint(-20, 20)
                        y = box2['y'] + box2['height'] / 2 + random.randint(-13, 13)
                        page.mouse.click(x, y)
                    except:
                        return False

                    try:
                        page.locator('.draw').wait_for(state="detached")
                        try:
                            page.locator('[role="status"][aria-label="正在加载..."]').wait_for(timeout=5000)
                            page.wait_for_timeout(8000)
                            if page.get_by_text('一些异常活动').count() or page.get_by_text('此站点正在维护').count() > 0:
                                print("[Error: Rate limit] - IP 注册频率过快。")
                                capture_page_state(page, "captcha_rate_limited")
                                return False
                            elif iframe2.locator('[aria-label="可访问性挑战"]').count() > 0:
                                continue
                            break
                        except:
                            if page.get_by_text('取消').count() > 0:
                                break
                            iframe1.get_by_text("请再试一次").wait_for(timeout=15000)
                            continue
                    except:
                        if page.get_by_text('取消').count() > 0:
                            break
                        return False
                else:
                    return False
                return True
            except Exception as e:
                print(f"[Error] 处理 push_button 验证码失败: {e}")
                return False

        if captcha_type == 'funcaptcha_iframe':
            print("[Error: FunCaptcha] - FunCaptcha 验证码，需要第三方服务。")
            capture_page_state(page, "funcaptcha")
            return False

        return False

    def clean_up(self, page=None, type="all_browser"):
        """
        清理资源
        """
        if type == "done_browser" and page:
            try:
                context = page.context
                context.close()
            except:
                pass

        elif type == "all_browser":
            with self._lock:
                if self._browser:
                    try:
                        self._browser.close()
                    except:
                        try:
                            self._browser.disconnect()
                        except:
                            pass
                    self._browser = None

                if self._playwright:
                    try:
                        self._playwright.stop()
                    except:
                        pass
                    self._playwright = None

                self._connected = False

    def _handle_longpress_captcha(self, page):
        """
        处理 PerimeterX 长按验证码
        使用 CDP Input API 和贝塞尔曲线模拟真人操作
        """
        try:
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
                btn = page.locator('#human > div:first-child')
                btn.wait_for(state='visible', timeout=10000)
                box = btn.bounding_box()
                if not box:
                    return False
                btn_x = box['x'] + box['width'] / 2
                btn_y = box['y'] + box['height'] / 2
            else:
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

            print("  [Captcha] 按住中...")

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

            print("  [Captcha] 松开，等待验证结果...")
            time.sleep(5)

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


def connect_to_geekez(port=9222):
    controller = GeekEzController(debug_port=port)
    p, b = controller.launch_browser()
    if p:
        return controller
    return None
