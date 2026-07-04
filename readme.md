# OutlookRegister

Outlook 邮箱注册自动化工具。使用 **GeekEZ 指纹扩展** + **正式版 Chrome** 伪装浏览器环境，自动化填写注册表单，绕过 Microsoft 验证。

## 架构

```
OutlookRegister/
├── run_geekez.py          # 主脚本 — GeekEZ 指纹扩展 + Chrome + 注册全流程
├── run_register.py        # 备用脚本 — 纯 Playwright（无指纹扩展）
├── local_proxy.py         # asyncio 本地代理 — 转发到住宅代理（gate.decodo.com）
├── proxy_rotator.py       # 代理轮换器 — 从 GeekEZ profiles.json 提取 SS 代理
├── utils.py               # check_captcha_type(), random_email(), generate_password()
├── working_proxies.txt    # 已验证可用的代理列表
├── requirements.txt       # Python 依赖
├── controllers/           # 控制器模块（旧版）
├── docs/                  # 文档
└── Results/               # 成功注册的账号保存位置
```

## 环境要求

- **macOS**（需要 GeekEZ Browser 或 Chrome）
- **Python 3.10+**
- **Node.js 18+**（proxy_rotator 需要 ss-local）

## 安装

```bash
pip install -r requirements.txt
brew install shadowsocks-libev   # 提供 ss-local 命令
```

选择一种浏览器：

### 方式 A：正式版 Chrome（推荐当前方式）

```bash
# 直接使用 /Applications/Google Chrome.app
# run_geekez.py 中 CHROME 已默认指向此路径
```

### 方式 B：Chrome for Testing（需 GeekEZ Browser）

```bash
# GeekEZ 内置的 Chrome for Testing
# 路径：/Applications/GeekEZ Browser.app/Contents/Resources/puppeteer/chrome/...
# 修改 run_geekez.py 中 CHROME 变量
```

## 使用

### 主脚本（推荐）

```bash
python run_geekez.py
```

流程：
1. 启动正式版 Chrome + GeekEZ 指纹扩展
2. 打开 3 个标签页模拟正常浏览（Google、Bing）
3. 导航到 Outlook 注册页
4. 自动通过"个人数据导出许可"同意
5. 填写邮箱 → 密码 → 生日 → 姓名
6. 处理 PerimeterX 验证码（当前被阻断，见下方说明）
7. 注册成功 → 保存到 Results/outlook_success.txt

### 备用脚本（纯 Playwright，无指纹扩展）

```bash
python run_register.py
```

### 代理转发（住宅代理）

```bash
python local_proxy.py [端口]
# 默认 18888，转发到 gate.decodo.com:10001
```

### 测试代理连通性

```bash
python proxy_rotator.py    # 列出所有 SS 代理
python test_proxies.py     # 测试哪个代理可访问 Outlook
```

## 指纹伪装

使用 GeekEZ 浏览器指纹扩展（已配置在 `test` profile 中）：

| 特征 | 真实值 | 伪装值 |
|------|--------|--------|
| User-Agent | Chrome/147 | Chrome/129.0.0.0 |
| 语言 | zh-CN | en-US, en |
| 屏幕 | 1512x982 | 1920x1080 |
| 硬件并发 | 12 | 8 |
| 内存 | 32GB | 8GB |
| WebGL 厂商 | Apple | ATI Technologies Inc. |
| WebGL 渲染器 | Apple GPU | AMD Radeon Pro 5500M |
| navigator.webdriver | true | false |
| 插件数 | 0 | 5 |
| Canvas | 真实指纹 | 带噪声 |
| Audio | 真实指纹 | 带噪声 |
| UserAgentData | Chrome 147, arm64 | Chrome 129, x86, macOS 14 |

扩展位于：`~/Library/Application Support/geekez-browser/BrowserProfiles/cd4d406d-22e1-4c7a-919d-024ed5707f89/extension/`

如需修改指纹参数，编辑 `content.js` 第 4 行的 `fp` 对象。

## 验证码问题（核心难点）

当前被 **PerimeterX** 阻断，具体表现为：

1. **类型**: `longpress` — 长按按钮验证（非点击/滑动）
2. **位置**: 按钮在 `div#human` 容器中，iframe 被偏移到 `x=-9586` 不可见
3. **检测**: PerimeterX 检测到 CDP 注入的鼠标事件，服务端拒绝通过
4. **重试**: `page.reload()` 后 `#human` 不再出现

### 已知失败的尝试

| 尝试 | 结果 |
|------|------|
| Playwright mouse API + Bezier 曲线 | 按住 24s 后服务端拒绝 |
| Chrome for Testing → 正式版 Chrome | 无改善 |
| 完整指纹伪装（WebGL/UA/Canvas） | PerimeterX 不依赖简单指纹 |
| 更换代理（SS/直连/住宅代理） | 所有 IP 都走到人机验证 |
| SS-local 代理 → xray 代理 | 无改善 |
| 直连中国 IP | 同样走到验证码 |

### 推荐的解决方向

**Capsolver API**（需充值激活）：

```python
# Capsolver 已注册，API Key: CAP-97BBAEA99A5B1E9E2E7DCE1D2029BE66C4F3CD67DAD6CA8416FDC90AED1FA109
# 但账户未充值，返回 Code 41（ERROR_KEY_DENIED_ACCESS）
# 充值后使用 createTask 创建 AntiPerimiterX 任务
```

### PerimeterX 关键信息

- App ID: `PXzC5j78di`
- iframe: `https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di`
- 验证 `div#human` 尺寸: 360x336（在 1280x800 窗口下位置 x=452, y=212）
- 触发阶段：完成姓名填写后点击"下一步"

## 代理配置

### 已验证可用的 SS 代理

| 地区 | 服务器 | 端口 |
|------|--------|------|
| 🇯🇵 日本A | normal.relay.jpa.sys-metric-report.com | 20437 |
| 🇯🇵 日本B | normal.relay.jpb.sys-metric-report.com | 43292 |
| 🇭🇰 香港C | mix.relay.ss.hkc.sys-metric-report.com | 25070 |
| 🇸🇬 新加坡D | normal.relay.sgpd.sys-metric-report.com | 12167 |
| 🇺🇸 美国C | normal.relay.usc.sys-metric-report.com | 17319 |
| 🇻🇳 越南A | normal.relay.vna.sys-metric-report.com | 17463 |

完整列表见 `working_proxies.txt`。

### 住宅代理

```yaml
地址: gate.decodo.com:10001
用户: sp2senzuf2
密码: vto~iJQ30kEa6Ghvm5
用途: 通过 local_proxy.py 转发到 HTTP 代理
状态: 巴西 IP，被 Microsoft 返回 ERR_EMPTY_RESPONSE，不可用
```

### Microsoft IP 限制

- 所有 SS 代理（HK/TW/JP/SG/US/VN）都走到 PerimeterX 验证码
- 巴西住宅代理被直接拦截
- 直连中国 IP 同样触发验证码
- **根本问题不在 IP，在验证码**

## 关键文件说明

| 文件 | 说明 |
|------|------|
| `run_geekez.py` | **主入口** — 启动 Chrome + 指纹扩展 + 注册流程 |
| `utils.py` | `check_captcha_type()` 检测验证码类型（longpress/push_button/funcaptcha/unknown） |
| `proxy_rotator.py` | 从 GeekEZ profiles.json 解析 SS 代理并启动 ss-local |
| `local_proxy.py` | asyncio HTTP 代理，转发到 gate.decodo.com 住宅代理 |
| `config.json` | 旧版配置（并发数、OAuth2 等） |
| `main.py` | 旧版入口（多线程并发） |
| `auto_register.py` | 旧版自动化 |

## git 历史

```bash
d5bf93e feat: add proxy rotation, stealth browsing, and multi-tab fingerprint spoofing
```

## 交接清单

- [ ] Capsolver 充值（https://capsolver.com）后集成 `createTask` + `AntiPerimiterX`
- [ ] 或尝试 2captcha 替代
- [ ] 或使用 pyautogui 生成真实 OS 鼠标事件长按验证码
