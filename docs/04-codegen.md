# 04 浏览器自动化与 Codegen

本章解决整个系统里"人工介入最少但不可省略"的一环：把人手动操作浏览器一遍的过程，转成 03 章讲的 `record.spec.js`——一段可以被程序反复、稳定重放的自动化脚本。

## 4.1 Playwright Codegen 的工作原理

`npx playwright codegen <url>` 会启动一个真实的 Chromium 实例，并注入一段监听脚本，捕获你在页面上的每一次点击、输入、选择、导航，实时生成对应的 Playwright API 调用代码，显示在旁边的 "Playwright Inspector" 窗口里。它本质上是一个"操作 → 代码"的实时翻译器，翻译规则大致是：

- 点击一个按钮 → `await page.getByRole('button', { name: '导出' }).click();`
- 输入文本 → `await page.getByLabel('用户名').fill('demo');`
- 下拉选择 → `await page.getByLabel('格式').selectOption('excel');`
- 页面跳转 → 自动插入 `await page.waitForURL(...)` 或什么都不插（取决于是否是 SPA 内部路由）

选择器优先级上，Playwright codegen 会尽量选择"面向用户可见语义"的定位方式（role、label、text），而不是脆弱的 CSS class/xpath——这一点非常重要，直接决定了脚本在下次 UI 微调后还能不能跑，4.4 节会展开讲。

## 4.2 录制会话的标准操作流程

```bash
# 启动 codegen，指定输出文件、初始视口，直接对着目标系统录
npx playwright codegen \
  --target javascript \
  --viewport-size=1440,900 \
  --output=feature-07-export-report/nav-draft.spec.js \
  https://staging.example.com/login
```

操作建议（这次会话产出的是**整个功能点从头到尾的一份完整草稿**，不是切成一小段一小段分别录）：

1. **一次会话走完整个功能点的操作路径**：登录 → 打开报表页 → 选时间范围/维度 → 点导出 → 选 Excel → 确认。中间不要关闭 codegen 窗口再重开，保持一条连续的操作序列，因为最终 `record.spec.js` 也是一份连续脚本，不是拼接起来的分段文件。
2. 如果登录这类前置操作在多个功能点之间完全一致，可以把这部分单独抽成一个共享函数（见 4.5 节），但仍然是在**同一次 codegen 会话里**先走一遍，产出草稿之后再手动把登录部分替换成对共享函数的调用，而不是提前单独录一份登录专用脚本。
3. 录制过程中动作要"干净"：不要有多余的误点、悬停、来回切换标签页，这些都会被原样录进脚本，之后要手动清理（4.3 节）。

这次会话产出的 `nav-draft.spec.js` 只是一份**选择器草稿**，下一步是把里面的选择器整理进正式的 `record.spec.js`——这一步通常交给 AI 完成（17 章会给出具体方法），人工负责最后审阅操作顺序是否符合真实业务语义。

## 4.3 清洗生成的脚本

Codegen 生成的原始代码是"能跑但不干净"的，直接拿去录制正式视频通常有三类问题需要处理：

**问题一：多余的等待/断言**。Codegen 有时会插入一些调试用的 `expect()` 断言或不必要的 `waitForTimeout`，这些要么直接删掉，要么替换成基于真实页面状态的显式等待（比如等某个文案出现），写法见下面的清洗示例。

**问题二：硬编码的绝对时间等待**，比如 `await page.waitForTimeout(1500)`。这类等待在真实网络环境下可能不够（页面卡顿导致按钮还没出现就点了）也可能过多（白白拉长录制时间且不受配音节奏控制）。应该统一替换成基于状态的等待：

```typescript
// 清洗前（codegen 原始产出）
await page.click('#export-btn');
await page.waitForTimeout(1500);
await page.click('text=Excel');

// 清洗后
await page.getByRole('button', { name: '导出' }).click();
await page.getByText('Excel').waitFor({ state: 'visible' });
await page.getByText('Excel').click();
```

**问题三：脆弱选择器**。如果 codegen 因为页面缺少语义化标签（没有 `aria-label`、按钮用 `<div onclick>` 实现）而退化生成了 `page.locator('.css-3xk2j9')` 这种基于自动生成 class 的选择器，要么推动前端加上语义化属性（长期最优解），要么在清洗脚本时替换为更稳定的替代定位方式，比如相对文本、相对父容器结构。这一步做得好坏，直接决定这套流水线在产品持续迭代下的"保质期"。

清洗后的 `record.spec.js` 是一份连续脚本，各个业务动作之间该停留多久，由写脚本的人凭观感直接决定（想让观众多看一眼某个界面，就多留一个 `waitForTimeout`），不依赖任何外部配置驱动：

```javascript
// feature-07-export-report/record.spec.js（清洗后的片段）
await page.getByRole("link", { name: "报表" }).click();
await page.waitForURL("**/reports");
await page.getByLabel("时间范围").click();
await page.getByText("最近30天").click();
await page.getByLabel("数据维度").selectOption("按渠道");
await page.waitForTimeout(1500); // 留给观众看清页面筛选结果，纯粹凭观感决定的停留

await page.getByRole("button", { name: "导出报表" }).click();
await page.getByText("Excel").waitFor({ state: "visible" });
await page.getByText("Excel").click();
```

## 4.4 选择器稳定性策略

功能演示视频要长期维护，最大的隐性成本是"UI 一改脚本就断"。几条硬性原则：

1. **优先级：`getByRole` > `getByLabel` > `getByText` > `data-testid` > CSS 选择器**。前三种基于用户可感知的语义，UI 视觉改版（换个颜色、挪个位置）通常不影响它们；`data-testid` 需要研发配合埋点但非常稳定；纯 CSS 选择器/xpath 是最后手段。
2. **如果条件允许，推动研发团队给关键交互元素加 `data-testid`**。这是一次性投入，换来的是自动化脚本对视觉改版免疫。这一点值得写进团队的前端开发规范里，而不是每次录制前才发现选择器全挂了。
3. **避免基于绝对位置/索引的选择器**（如 `nth-child(3)`），列表顺序一旦变化就会点错行。
4. **对每个清洗后的脚本片段，建立一个轻量"冒烟测试"**（见 4.6 节），在正式录制前先跑一遍，快速发现选择器失效，而不是等到合成阶段才发现某一步的视频是空的。

## 4.5 可复用片段库

像"登录""关闭引导弹窗""切换到某个工作区"这类几乎每个功能点视频都要用到的前置操作，应该沉淀成一个共享函数，供各个 `record.spec.js` 直接 `require`：

```javascript
// common/login.js
async function login(page, username, password) {
  await page.goto(process.env.ADMIN_URL);
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL("**/dashboard");
}
module.exports = { login };
```

```javascript
// feature-07-export-report/record.spec.js
const { login } = require("../common/login");

test("导出报表", async ({ page }) => {
  await login(page, process.env.DEMO_USERNAME, process.env.DEMO_PASSWORD);
  // ... 后续操作
});
```

## 4.6 录制前先跑一遍冒烟检查

正式录制（05 章）会同时启动屏幕录制和浏览器自动化，一旦 `record.spec.js` 里的选择器失效，浪费的不只是重新调试的时间，还有一段已经录废的视频。稳妥的做法是在真正触发录制之前，先用 headless 模式把整个脚本跑一遍：

```bash
npx playwright test record.spec.js --headed=false
```

跑通再进入 05 章的正式录制流程；跑不通就先按 17 章讲的方法把报错交给 AI 处理，不要带着还会报错的脚本去做真正的录制。

## 4.7 codegen 层的产物边界

到本章结束，一个功能点目录下应该有：

- 一份清洗过的 `record.spec.js`（03 章已经展示过完整例子）
- 如果有跨功能点复用的前置操作（登录等），额外一个 `common/` 目录下的共享函数

这份脚本只包含操作逻辑本身，**该等多久、什么时候截图、什么时候说话，都直接写在脚本里，不依赖任何外部配置驱动**——03 章已经解释过为什么这三份文件（`record.spec.js`/`timeline.json`/`meta.json`）要保持这样的职责边界。

下一章讲这份脚本如何和屏幕录制同步执行，产出一条完整的原始录像。
