# PerimeterX 验证码绕过方案

## 问题背景

Microsoft Outlook 注册流程使用 PerimeterX (hsprotect) 长按验证码，传统的 Playwright/Patchright 自动化无法通过。

## 解决方案

使用 **CDP (Chrome DevTools Protocol) Input API** + **贝塞尔曲线鼠标移动** 模拟真人操作。

### 关键技术点

1. **CDP Input API** - 产生 `isTrusted: true` 的事件
2. **贝塞尔曲线移动** - 模拟真人鼠标轨迹
3. **随机延迟** - 打破固定的时间模式
4. **按住时微调** - 模拟手抖

### 成功的代码实现

```python
# 贝塞尔曲线函数
def bezier_curve(t, p0, p1, p2, p3):
    u = 1 - t
    return u**3 * p0 + 3*u**2*t * p1 + 3*u*t**2 * p2 + t**3 * p3

# 1. 从随机位置开始
start_x = random.randint(100, 400)
start_y = random.randint(100, 300)

# 2. 生成控制点
cp1_x = start_x + (btn_x - start_x) * 0.3 + random.uniform(-50, 50)
cp1_y = start_y + (btn_y - start_y) * 0.3 + random.uniform(-50, 50)
cp2_x = start_x + (btn_x - start_x) * 0.7 + random.uniform(-50, 50)
cp2_y = start_y + (btn_y - start_y) * 0.7 + random.uniform(-50, 50)

# 3. 沿曲线移动
steps = random.randint(20, 40)
for i in range(steps):
    t = i / steps
    x = bezier_curve(t, start_x, cp1_x, cp2_x, btn_x)
    y = bezier_curve(t, start_y, cp1_y, cp2_y, btn_y)
    # 添加抖动
    x += random.uniform(-2, 2)
    y += random.uniform(-2, 2)
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": x, "y": y,
        "button": "none",
        "pointerType": "mouse"
    })
    time.sleep(random.uniform(0.01, 0.05))

# 4. 按下
cdp.send("Input.dispatchMouseEvent", {
    "type": "mousePressed",
    "x": btn_x, "y": btn_y,
    "button": "left",
    "clickCount": 1,
    "buttons": 1,
    "pointerType": "mouse"
})

# 5. 保持按住，偶尔微调
hold_time = random.uniform(10, 15)
start_time = time.time()
while time.time() - start_time < hold_time:
    if random.random() < 0.2:  # 20% 概率微调
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": btn_x + random.uniform(-3, 3),
            "y": btn_y + random.uniform(-3, 3),
            "button": "left",
            "buttons": 1,
            "pointerType": "mouse"
        })
    time.sleep(random.uniform(0.3, 0.7))

# 6. 松开
cdp.send("Input.dispatchMouseEvent", {
    "type": "mouseReleased",
    "x": btn_x, "y": btn_y,
    "button": "left",
    "clickCount": 1,
    "buttons": 0,
    "pointerType": "mouse"
})
```

## 已更新的文件

1. `controllers/base_controller.py` - 基础控制器的 `_handle_longpress_captcha` 方法
2. `controllers/geekez_controller.py` - GeekEZ 控制器的 `_handle_longpress_captcha` 方法

## 测试结果

- ✅ 成功通过 PerimeterX 长按验证码
- ✅ 页面跳转到下一步（创建账户页面）
- ✅ 可以继续完整的注册流程

## 注意事项

1. **CDP 连接** - 需要通过远程调试端口连接到浏览器
2. **iframe 位置** - 按钮位置在 PerimeterX iframe 底部中间
3. **随机性** - 每次操作都有随机延迟和位置偏移
4. **IP 质量** - 仍然建议使用独享 IP 以提高成功率

## 与其他方案的比较

| 方案 | 优点 | 缺点 |
|------|------|------|
| CDP + 贝塞尔曲线 (当前方案) | 无需第三方服务，可本地运行 | 需要 CDP 连接 |
| capsolver.com | 专业服务，成功率高 | 需要付费 |
| undetected-chromedriver | 绕过 WebDriver 检测 | 需要额外配置 |
| 真实用户手动操作 | 100% 成功率 | 不可自动化 |
