# GeekEZ Browser 集成使用指南

## 概述

本方案通过远程调试端口将 OutlookRegister 脚本连接到 GeekEZ Browser，利用其深度指纹伪装能力来绕过 PerimeterX 验证码检测。

## 优势

1. **无需修改 GeekEZ Browser 代码** - 只需开启远程调试端口
2. **完整的指纹伪装** - 使用 GeekEZ 的 WebDriver 隐藏、Canvas 噪声、WebGL 伪装等
3. **独立的浏览器配置文件** - 每个环境有独立的 cookies、历史记录
4. **代理支持** - GeekEZ 内置 Xray 代理支持

## 使用步骤

### 步骤 1：配置 GeekEZ Browser

1. **启动 GeekEZ Browser**
2. **开启远程调试端口**：
   - 进入设置
   - 找到「远程调试端口」或「Remote Debugging Port」选项
   - 开启并记录端口号（默认可能是 9222）

3. **创建/选择环境**：
   - 创建一个新的 Profile 或选择已有的
   - 配置代理（建议使用独享 IP）
   - 设置指纹参数

4. **启动环境**：
   - 点击启动按钮
   - 等待浏览器窗口打开
   - **记下该环境分配的调试端口号**（通常在环境详情或启动日志中显示）

### 步骤 2：修改 OutlookRegister 配置

编辑 `config.json`：

```json
{
    "choose_browser": "geekez",
    "geekez_debug_port": 9222,  // GeekEZ 分配的调试端口
    "email_suffix": "@hotmail.com",
    "proxy": "",  // 留空，使用 GeekEZ 内部代理
    "bot_protection_wait": 11,
    "max_captcha_retries": 2,
    "concurrent_flows": 1,
    "max_tasks": 1,
    "oauth2": {
        "enable_oauth2": false
    }
}
```

### 步骤 3：修改 main.py

在 `main.py` 中添加对 GeekEZ 的支持：

```python
from controllers.geekez_controller import GeekEzController

# 在 __main__ 部分修改
if __name__ == "__main__":
    with open('config.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    os.makedirs("Results", exist_ok=True)

    max_tasks = data["max_tasks"]
    concurrent_flows = data["concurrent_flows"]

    if data["choose_browser"] == "patchright":
        selected_controller = PatchrightController()
    elif data["choose_browser"] == "playwright":
        selected_controller = PlaywrightController()
    elif data["choose_browser"] == "geekez":
        # 连接到 GeekEZ Browser
        geekez_port = data.get("geekez_debug_port", 9222)
        selected_controller = GeekEzController(debug_port=geekez_port)
    else:
        print("不支持的浏览器类型")
```

### 步骤 4：运行脚本

```bash
# 1. 先启动 GeekEZ Browser 并开启环境
# 2. 确认调试端口号
# 3. 运行注册脚本
python main.py
```

## 注意事项

### 调试端口问题

- **每个环境有独立的端口**：GeekEZ 会为每个环境分配不同的调试端口
- **端口号在启动后确定**：启动环境后才能看到实际的端口号
- **端口冲突**：确保配置的端口与 GeekEZ 分配的一致

### 如何查看 GeekEZ 的调试端口

方法 1：查看 GeekEZ 的 UI 界面
- 环境详情页面通常会显示调试端口

方法 2：查看日志
- 启动环境时，控制台会输出类似信息：
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  REMOTE DEBUGGING ENABLED
📡 Port: 24000
🔗 Connect: chrome://inspect or ws://localhost:24000
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

方法 3：使用命令行检查
```bash
# macOS/Linux
lsof -i :24000

# 或者使用 netstat
netstat -an | grep 24000
```

### 指纹伪装效果

GeekEZ 已通过以下检测：
- ✅ Browserscan
- ✅ Pixelscan
- ✅ Cloudflare 机器人检测

使用 GeekEZ 环境可以：
- 隐藏 WebDriver 指纹
- 添加 Canvas 噪声
- 伪装 WebGL 信息
- 修改 UserAgent
- 阻止 WebRTC IP 泄露

### 代理配置

**推荐使用 GeekEZ 内部代理**：
- 在 GeekEZ 中配置代理
- `config.json` 中 `proxy` 留空
- 这样可以利用 GeekEZ 的 Xray 代理引擎

**如果需要外部代理**：
- 在 `config.json` 中配置 `proxy` 字段
- 格式：`socks5://127.0.0.1:1082`

## 故障排除

### 无法连接到 GeekEZ Browser

```
[Error] 无法连接到端口 9222，请确保 GeekEZ Browser 已启动并开启了远程调试
```

**解决方案**：
1. 确认 GeekEZ Browser 已启动
2. 确认环境已启动
3. 确认远程调试端口已开启
4. 检查端口号是否正确

### 验证码仍然出现

即使使用 GeekEZ，PerimeterX 仍然可能检测到自动化。这是因为：
1. 按压时间/模式可能不符合真人行为
2. IP 质量问题
3. PerimeterX 的 ML 模型仍在进化

**建议**：
- 使用独享 IP（不是共享代理）
- 适当增加 `bot_protection_wait` 的值
- 手动在浏览器中完成几次验证，让 cookies 积累

### 脚本找不到页面

```
[Error] 获取页面失败
```

**解决方案**：
1. 确保 GeekEZ 环境已经打开了至少一个页面
2. 手动在 GeekEZ 中访问任意网站
3. 重新运行脚本

## 高级用法

### 多环境并发

如果需要同时使用多个 GeekEZ 环境：

1. 在 GeekEZ 中创建多个环境
2. 为每个环境分配不同的调试端口
3. 运行多个 OutlookRegister 实例，每个连接不同的端口

### 自动化启动 GeekEZ 环境

可以使用 GeekEZ 的 REST API 来自动化环境启动：

```bash
# 启动环境
curl "http://localhost:12345/api/open/环境名称或ID?stream=true"

# 查看环境列表
curl "http://localhost:12345/api/profiles"
```

## 相关文件

- `controllers/geekez_controller.py` - GeekEZ 连接控制器
- `config.json` - 配置文件
- `main.py` - 主入口

## 技术细节

GeekEZ Browser 使用以下技术进行指纹伪装：

1. **puppeteer-extra-plugin-stealth** - 隐藏自动化痕迹
2. **自定义指纹注入脚本** - 在页面加载前注入指纹数据
3. **WebDriver 属性覆盖** - 删除 `navigator.webdriver` 等特征
4. **Canvas/WebGL 噪声** - 添加微小随机噪声
5. **WebRTC 阻断** - 防止本地 IP 泄露
6. **Xray 代理引擎** - 支持多种代理协议

这些技术的组合使得浏览器指纹看起来更像真人用户，从而提高通过 PerimeterX 验证的概率。
