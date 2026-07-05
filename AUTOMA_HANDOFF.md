# Outlook 注册 Automa 工作流 - 交接文档

## 当前状态

Automa 工作流已创建在 `/Users/pingchuan/Desktop/outlook-signup.automa.json`，注册流程的前半段（填写表单）已完成，**验证码阶段卡住**。

## 已完成的部分

表单填写流程全部通过 Automa 原生节点实现：
- `trigger` → `javascript-code`(生成账号) → `new-tab`(打开注册页)
- `event-click`(#nextButton) → `forms`(填邮箱) → `event-click`(下一步)
- `forms`(填密码) → `event-click`(下一步)
- `javascript-code`(生成生日) → `forms`(填年份) → `event-click`(月份下拉) → `event-click`(选月份) → `event-click`(日期下拉) → `event-click`(选日期) → `event-click`(下一步)
- `javascript-code`(生成姓名) → `forms`(填姓氏) → `forms`(填名字) → `event-click`(下一步)

变量传递：`automaSetVariable` 存储，`{{variables.xxx}}` 在 forms 节点引用。

## 卡在哪一步

**第 6 步（姓名提交后）→ 弹出验证码页 → `n_captcha_js` 节点失败**

Automa 工作流走到 `n_captcha_js`（javascript-code 节点）时，JS 代码执行 `document.querySelector('[aria-label="可访问性挑战"]')` 返回 `null`，因为该按钮在跨域 iframe 内部，主页面 JS 无法访问。

### 验证码页面长这样
```
<div id="human">
  <img>                         ← 机器人图标
  <span>长按该按钮。</span>
  <iframe title="验证质询"       ← 跨域 iframe (hsprotect.net)
    内部包含:
      [aria-label="可访问性挑战"]  ← 需要点击这个 (iframe内)
      [aria-label="再次按下"]     ← 自动长按后出现 (iframe内)
  </iframe>
</div>
```

### 需要解决的问题
`[aria-label="可访问性挑战"]` 和 `[aria-label="再次按下"]` 都在 iframe **内部**，Automa 的 `javascript-code` 节点无法访问跨域 iframe 的 DOM。

### 可能的解决方向
1. 测试 Automa 是否支持 frame selector（某些版本的 `event-click` 有 `frameSelector` 参数）
2. 用 `javascript-code` 节点通过坐标 + `elementFromPoint` 或 `postMessage` 与 iframe 交互
3. 混合方案：Automa 处理表单填写，验证码部分暂停后用外部脚本（Playwright/CDP）处理，再恢复 Automa

### 已验证的选择器
| 元素 | 选择器 | 来源 |
|------|--------|------|
| 同意按钮 | `#nextButton` | 主页面 |
| 邮箱输入 | `input[aria-label='新建电子邮件']` | 主页面 |
| 密码输入 | `input[type='password']` | 主页面 |
| 年份 | `input[name='BirthYear']` | 主页面 |
| 月份下拉 | `#BirthMonthDropdown` | 主页面 |
| 日期下拉 | `#BirthDayDropdown` | 主页面 |
| 姓氏 | `#lastNameInput` | 主页面 |
| 名字 | `#firstNameInput` | 主页面 |
| 提交按钮 | `button[data-testid='primaryButton']` | 主页面 |
| 验证码 iframe | `iframe[title='验证质询']` | 主页面 |
| 可访问性挑战 | `[aria-label="可访问性挑战"]` | **iframe 内部** |
| 再次按下 | `[aria-label="再次按下"]` | **iframe 内部** |
| 错误提示 | `[role="alert"]` | 主页面 |

## 注册成功判断

进入邮箱页面才算成功：
- URL 包含 `outlook.live.com/mail`
- 或页面标题包含"收件箱"/"Inbox"

仅通过验证码 + 点击"同意并继续" ≠ 成功（之前因此产生了不存在的账号）。

## 域名跳转

- Step 1（数据导出页）：`outlook.live.com`
- Step 2-6（表单+验证码）：`signup.live.com`
- localStorage 跨域不通，用 `automaSetVariable` 解决

## 文件位置

- Automa 工作流：`/Users/pingchuan/Desktop/outlook-signup.automa.json`
- Automa 安装：`/Users/pingchuan/Desktop/chrome_exten/automa/`（build 目录可直接加载为 Chrome 扩展）
- 参考工作流：`/Users/pingchuan/Desktop/chatgpt-signup.automa.json`
