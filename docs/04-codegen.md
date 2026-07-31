# 04 浏览器自动化与 Codegen

本章解决整个系统里"人工介入最少但不可省略"的一环：把人手动操作浏览器一遍的过程，转成可以被程序反复、稳定重放的自动化脚本，并且让脚本片段能对应到 03 章 Feature Spec 里的 `codegen_ref`。

## 4.1 Playwright Codegen 的工作原理

`npx playwright codegen <url>` 会启动一个真实的 Chromium 实例，并注入一段监听脚本，捕获你在页面上的每一次点击、输入、选择、导航，实时生成对应的 Playwright API 调用代码，显示在旁边的 "Playwright Inspector" 窗口里。它本质上是一个"操作 → 代码"的实时翻译器，翻译规则大致是：

- 点击一个按钮 → `await page.getByRole('button', { name: '导出' }).click();`
- 输入文本 → `await page.getByLabel('用户名').fill('demo');`
- 下拉选择 → `await page.getByLabel('格式').selectOption('excel');`
- 页面跳转 → 自动插入 `await page.waitForURL(...)` 或什么都不插（取决于是否是 SPA 内部路由）

选择器优先级上，Playwright codegen 会尽量选择"面向用户可见语义"的定位方式（role、label、text），而不是脆弱的 CSS class/xpath——这一点非常重要，直接决定了脚本在下次 UI 微调后还能不能跑，4.4 节会展开讲。

## 4.2 录制会话的标准操作流程

```bash
# 启动 codegen，指定输出文件、初始视口、设备场景
npx playwright codegen \
  --target javascript \
  --viewport-size=1440,900 \
  --output=src/codegen/raw/open-report-page.raw.ts \
  https://staging.example.com/login
```

操作建议（对照 03 章 Spec 里的 `steps`，一个 `codegen_ref` 对应一次独立的 codegen 会话，不要把整个功能点从头到尾录成一条脚本）：

1. **登录单独录一次**，产出 `login.raw.ts`，因为几乎每个功能点视频都要先登录，这段可以被多个 Feature 复用（见 4.5 节的"可复用片段库"）。
2. **每个 Spec 里的 `action` 步骤单独录一次会话**，只做该步骤范围内的操作，操作完成后就关闭 codegen 窗口。例如 `codegen_ref: open-report-page` 对应的会话，只做"打开报表页 → 选时间范围 → 选维度"这几个动作，不要连着把导出也一起录了。
3. 录制过程中动作要"干净"：不要有多余的误点、悬停、来回切换标签页，这些都会被原样录进脚本，之后要手动清理（4.3 节）。

这样录出来一堆 `*.raw.ts` 片段，文件名直接对应 Spec 里的 `codegen_ref` 值，是编排器自动关联脚本片段与 Spec 步骤的依据。

## 4.3 清洗生成的脚本

Codegen 生成的原始代码是"能跑但不干净"的，直接拿去录制正式视频通常有三类问题需要处理：

**问题一：多余的等待/断言**。Codegen 有时会插入一些调试用的 `expect()` 断言或不必要的 `waitForTimeout`，这些要么删掉，要么替换成 03 章 Spec 里显式声明的 `pace.wait_for`。

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

清洗脚本的标准结构（每个片段包裹成一个具名的异步函数，供编排器调用）：

```typescript
// src/codegen/steps/open-report-page.ts
import { Page } from "playwright";

export async function openReportPage(page: Page): Promise<void> {
  await page.getByRole("link", { name: "报表" }).click();
  await page.waitForURL("**/reports");
  await page.getByLabel("时间范围").click();
  await page.getByText("最近30天").click();
  await page.getByLabel("数据维度").selectOption("按渠道");
  // 停留由编排器根据 Spec 的 pace 配置统一控制，脚本本身不硬编码等待
}
```

## 4.4 选择器稳定性策略

功能演示视频要长期维护，最大的隐性成本是"UI 一改脚本就断"。几条硬性原则：

1. **优先级：`getByRole` > `getByLabel` > `getByText` > `data-testid` > CSS 选择器**。前三种基于用户可感知的语义，UI 视觉改版（换个颜色、挪个位置）通常不影响它们；`data-testid` 需要研发配合埋点但非常稳定；纯 CSS 选择器/xpath 是最后手段。
2. **如果条件允许，推动研发团队给关键交互元素加 `data-testid`**。这是一次性投入，换来的是自动化脚本对视觉改版免疫。这一点值得写进团队的前端开发规范里，而不是每次录制前才发现选择器全挂了。
3. **避免基于绝对位置/索引的选择器**（如 `nth-child(3)`），列表顺序一旦变化就会点错行。
4. **对每个清洗后的脚本片段，建立一个轻量"冒烟测试"**（见 4.6 节），在正式录制前先跑一遍，快速发现选择器失效，而不是等到合成阶段才发现某一步的视频是空的。

## 4.5 可复用片段库

像"登录""关闭引导弹窗""切换到某个工作区"这类几乎每个功能点视频都要用到的前置操作，应该沉淀成公共片段，避免每个 Feature Spec 都重新录一遍：

```typescript
// src/codegen/steps/common/login.ts
import { Page } from "playwright";

export async function login(page: Page, username: string, password: string): Promise<void> {
  await page.goto(process.env.TARGET_BASE_URL!);
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL("**/dashboard");
}
```

在编排器里，任何 Feature Spec 只要 `target.account` 字段存在，就自动在所有 `action` 步骤之前插入一次 `login()` 调用，Spec 本身不需要显式声明"第一步是登录"。

## 4.6 片段的冒烟测试

每个清洗后的片段，建议用 Playwright Test 写一个最小化的可运行验证，在正式合成录制之前先确认脚本本身是健康的：

```typescript
// src/codegen/steps/__smoke__/open-report-page.smoke.ts
import { chromium } from "playwright";
import { login } from "../common/login";
import { openReportPage } from "../open-report-page";

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, process.env.DEMO_USERNAME!, process.env.DEMO_PASSWORD!);
  await openReportPage(page);
  console.log("✅ open-report-page 冒烟测试通过");
  await browser.close();
})();
```

可以在编排器启动录制前，自动遍历 Spec 里所有 `codegen_ref` 对应的片段，逐一跑一遍 headless 冒烟测试，任何一个失败就提前中止，而不是带着录制录屏一起失败后再排查（这是 09 章编排器实现里 `preflightCheck` 函数要做的事情）。

## 4.7 codegen 层的产物边界

到本章结束，`src/codegen/steps/` 目录下应该积累了：

- 若干个公共片段（login 等）
- 每个 Feature Spec 的 `codegen_ref` 对应的具名异步函数
- 对应的冒烟测试

这些片段是"纯操作逻辑"，**不包含任何录制、等待节奏、配音相关代码**——节奏控制、录制启停都由 05 章的 Record 层和 09 章的编排器负责，职责边界要分清楚，否则片段没法在"冒烟测试"和"正式录制"两种场景下复用。

下一章讲这些操作脚本如何和屏幕/浏览器录制结合，产出分段视频文件。
