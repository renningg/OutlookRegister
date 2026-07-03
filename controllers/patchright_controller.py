import random
import time
from patchright.sync_api import sync_playwright
from .base_controller import BaseBrowserController
from utils import capture_page_state, check_captcha_type


class PatchrightController(BaseBrowserController):

    _stealth_script = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
    window.chrome = { runtime: {} };
    """

    def _apply_stealth(self, context):
        context.add_init_script(self._stealth_script)

    def launch_browser(self):
        try:
            p = sync_playwright().start() 

            proxy_settings = {
                "server": self.proxy,
                "bypass": "localhost",
            } if self.proxy else None

            b = p.chromium.launch(
                headless=False,            
                args=[
                    '--lang=zh-CN',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                ],
                proxy=proxy_settings
            )

            return p, b

        except Exception as e:
            print(f"启动浏览器失败: {e}")
            return False, False

    def handle_captcha(self, page):

        captcha_type = check_captcha_type(page)
        if captcha_type == 'longpress':
            self._handle_longpress_captcha(page)
            page.wait_for_timeout(3000)
            captcha_type = check_captcha_type(page)

        if captcha_type == 'unknown':
            return True

        if captcha_type not in ('push_button', 'funcaptcha_iframe'):
            return False

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
                    if page.get_by_text('一些异常活动').count() or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count() > 0:
                        print("[Error: Rate limit] - 正常通过验证码，但当前IP注册频率过快。")
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

    def get_thread_page(self):
        browser = self.get_thread_browser()
        context = browser.new_context()
        self._apply_stealth(context)
        return context.new_page()

    def clean_up(self, page=None, type="all_browser"):
        if type == "done_browser" and page:
            context = page.context
            context.close()

        elif type == "all_browser":
            for p, b in self.active_resources:
                try:
                    b.close()
                except Exception: pass
                try:
                    p.stop()
                except Exception: pass

    