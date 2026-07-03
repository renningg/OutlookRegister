import os
import re
import random
import string
import secrets
from datetime import datetime
from bs4 import BeautifulSoup, Comment

def random_email(length=random.randint(12,14)):

    first_char = random.choice(string.ascii_lowercase)

    other_chars = []
    for _ in range(length - 1):  
        if random.random() < 0.07:  
            other_chars.append(random.choice(string.digits))
        else: 
            other_chars.append(random.choice(string.ascii_lowercase))

    return first_char + ''.join(other_chars)

def generate_strong_password(length=random.randint(11, 15)):

    chars = string.ascii_letters + string.digits + "!@#$%^&*"

    while True:
        password = ''.join(secrets.choice(chars) for _ in range(length))

        if (any(c.islower() for c in password) 
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*" for c in password)):
            return password


_EVENT_ATTRS = {
    'onclick', 'ondblclick', 'onmousedown', 'onmouseup', 'onmouseover',
    'onmouseout', 'onmousemove', 'onmouseenter', 'onmouseleave',
    'onkeydown', 'onkeypress', 'onkeyup', 'onsubmit', 'onreset',
    'onfocus', 'onblur', 'onchange', 'oninput', 'onselect',
    'onload', 'onerror', 'onunload', 'onresize', 'onscroll',
    'onpointerdown', 'onpointerup', 'onpointermove', 'onpointerover',
    'onpointerout', 'onpointerenter', 'onpointerleave',
    'ontouchstart', 'ontouchend', 'ontouchmove', 'ontouchcancel',
    'onwheel', 'onanimationstart', 'onanimationend', 'onanimationiteration',
    'ontransitionend', 'oncut', 'oncopy', 'onpaste',
}


def sanitize_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    for tag in soup.find_all(['script', 'style', 'noscript', 'iframe',
                               'link', 'meta', 'svg', 'source', 'track']):
        tag.decompose()

    for tag in soup.find_all(True):
        for attr in list(tag.attrs.keys()):
            if attr.startswith('on') or attr in _EVENT_ATTRS:
                del tag.attrs[attr]

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    return str(soup)


def check_captcha_type(page):
    try:
        if page.locator('iframe[title="Human Iframe"]').count() > 0:
            if page.locator('[data-testid="accessibleImg"]').count() > 0:
                return 'longpress'
            if page.locator('[aria-label="可访问性挑战"]').count() > 0:
                return 'push_button'
            return 'hsprotect_unknown'

        if page.locator('iframe#enforcementFrame').count() > 0:
            return 'funcaptcha_iframe'

        if page.locator('iframe[title="验证质询"]').count() > 0:
            return 'push_button'

        title = page.title()
        if '机器人' in title:
            return 'bot_detection'
    except Exception:
        pass
    return 'unknown'


def capture_page_state(page, label="debug"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'Results', 'page_dumps')
    shot_dir = os.path.join(base, 'screenshots')
    html_dir = os.path.join(base, 'html')
    os.makedirs(shot_dir, exist_ok=True)
    os.makedirs(html_dir, exist_ok=True)

    shot_path = os.path.join(shot_dir, f'{label}_{timestamp}.png')
    html_path = os.path.join(html_dir, f'{label}_{timestamp}.html')

    try:
        page.screenshot(path=shot_path, full_page=True)
    except Exception:
        shot_path = None

    try:
        html = page.content()
        clean = sanitize_html(html)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(clean)
    except Exception:
        html_path = None

    return shot_path, html_path
