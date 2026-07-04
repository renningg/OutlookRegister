# Outlook 注册自动化 - 执行计划

## 核心流程

```
GeekEZ Browser (指纹+代理环境)
    ↓ Playwright 连接 CDP
注册页面
    ↓ 填写邮箱
    ↓ 填写密码
    ↓ 填写生日
    ↓ 填写姓名
    ↓ 提交
PerimeterX 验证码 ("证明你不是机器人")
    ↓ CDP Input + 贝塞尔曲线绕过
"个人数据导出许可" 页面
    ↓ 点击 "同意并继续"
Outlook 邮箱页面 ← ✅ 这才是注册完成
```

## 判断注册成功的唯一标准

**页面 URL 包含 `outlook.live.com/mail` 或页面标题包含 "收件箱"**

不是看验证码是否通过，不是看"同意并继续"是否点击，而是必须真正进入邮箱页面。

## 步骤

### Step 1: 启动 GeekEZ Browser 环境

```bash
# 用户手动启动 GeekEZ Browser，选择一个环境，开启远程调试端口
# 或者直接启动 Chrome 带 --remote-debugging-port 和 --user-data-dir
```

### Step 2: Playwright 连接 CDP

```python
ws_url = 获取 /json/version 的 webSocketDebuggerUrl
browser = playwright.chromium.connect_over_cdp(ws_url)
page = browser.contexts[0].pages[0]
```

### Step 3: 注册流程

1. 导航到 `https://outlook.live.com/mail/0/?prompt=create_account`
2. 点击"同意并继续"（如果出现）
3. 输入邮箱（只输入用户名，域名选择器已有 @outlook.com）
4. 点击"下一步"
5. 输入密码
6. 点击"下一步"
7. 填写生日（年/月/日）
8. 点击"下一步"
9. 填写姓氏和名字
10. 点击"下一步"

### Step 4: 处理 PerimeterX 验证码

如果页面标题包含"机器人"：
1. 获取 `iframe[title="验证质询"]` 的位置
2. 按钮位置 = iframe 底部中间
3. CDP Input API + 贝塞尔曲线模拟长按
4. 等待验证结果
5. 失败则刷新重试（最多 3 次）

### Step 5: 处理"个人数据导出许可"

验证码通过后可能出现此页面：
- 点击"同意并继续"
- **这不是注册完成！**

### Step 6: 判断注册成功

```python
# 循环检查直到超时
for _ in range(30):  # 最多等 30 秒
    url = page.url
    title = page.title()
    if 'outlook.live.com/mail' in url or '收件箱' in title:
        # ✅ 注册成功，已进入邮箱
        return True
    if '机器人' in title:
        # 需要再处理验证码
        handle_captcha(page)
    if '一些异常活动' in title or 'rate' in title.lower():
        # IP 被限制
        return False
    time.sleep(1)

# 超时未进入邮箱 = 注册失败
return False
```

## 验证码绕过方案

- CDP `Input.dispatchMouseEvent` 产生 `isTrusted:true` 事件
- 贝塞尔曲线鼠标移动打破线性检测
- 随机延迟 + 按住时微调模拟手抖
- 详见 `docs/perimeterx_bypass.md`

## 关键文件

| 文件 | 职责 |
|------|------|
| `auto_register.py` | 完整自动化脚本 |
| `controllers/base_controller.py` | `_handle_longpress_captcha` |
| `controllers/geekez_controller.py` | CDP 连接控制器 |

## 已知问题

1. 注册流程必须进入邮箱才算成功，之前判断逻辑有误
2. 同一 session 多次触发验证码会降低通过率
3. 需要独享代理 IP 提高成功率
