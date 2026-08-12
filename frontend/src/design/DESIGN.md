# 文档 RAG Web 应用 · 设计系统（DESIGN.md）

> 设计寄存器：**Product Register（产品型）**。工具型应用，设计服务产品本身。
> 设计语言：克制暗色（dark-first）+ 完整 light 第二主题；单一精炼靛蓝强调 + 琥珀签名高亮色。
> 技术栈（架构师锁定）：React 19 + Vite 8 + TypeScript 5.6 + Tailwind CSS 4 + Radix UI + lucide-react@^1.24。
> 图标系统（P0 锁定）：唯一 SVG 库 **Lucide**（lucide-react），尺寸 16/20/24px，统一 `currentColor`，**全项目禁止 emoji 作功能图标**。

---

## 1. Visual Theme & Atmosphere

- **基调关键词**：精密、克制、可信、溯源、信息密度适中。
- **氛围描述**：近黑画布上内容如星光浮现——层级完全靠"表面抬升 + 半透明白色发丝边框"承载，而非阴影或颜色。单一精炼靛蓝 `#3E63DD` 仅用于动作强调（每屏 ≤2 处）；琥珀 `#F5B544` 是本产品的**签名色**，专用于 PDF 页码引用高亮与引用溯源，与冷色 accent 形成冷暖对比，直接服务"带页码溯源"核心诉求。
- **明暗双主题**：dark 默认，light 为完整第二主题。PDF 预览始终暗色 chrome（白底文档在暗色框架中更跳、更护眼）。切换通过 `<html data-theme="light">` 翻转整套 CSS 变量，组件零改动。
- **绝对禁令（P0）**：禁止紫色→粉色渐变；禁止 emoji 功能图标；禁止硬编码颜色（一律走 Token，仅 `#ffffff`/`#000000` 例外且深色也不用纯黑）；禁止模板味文案与千篇一律 Hero。

---

## 2. Color Palette & Roles

### Dark（默认，`<html>` 无属性或 `data-theme="dark"`）

| Token | 值 | 角色 |
|---|---|---|
| `--bg` | `#0B0D10` | 画布（近黑、冷调，绝不用 `#000000`） |
| `--surface` | `#131619` | 面板/卡片 |
| `--surface-2` | `#1A1D21` | 抬升表面（hover/弹层底） |
| `--surface-3` | `#21252B` | 更高抬升（弹出/选中） |
| `--fg` | `#ECEEF1` | 主文本（柔白，非纯白） |
| `--muted` | `#9BA1A8` | 次级文本 |
| `--meta` | `#6B7178` | 三级/元数据 |
| `--border` | `rgba(255,255,255,0.08)` | 发丝边框 |
| `--border-soft` | `rgba(255,255,255,0.05)` | 内部弱分隔 |
| `--accent` | `#3E63DD` | 动作强调（单一色，偏蓝，区别于 `#6366f1`） |
| `--accent-on` | `#FFFFFF` | accent 背景上的前景 |
| `--accent-hover` | `color-mix(in srgb, var(--accent) 88%, #000)` | 悬停 |
| `--accent-active` | `color-mix(in srgb, var(--accent) 80%, #000)` | 按下 |
| `--focus-ring` | `0 0 0 3px rgba(62,99,221,0.40)` | 焦点环 |
| `--success` | `#3FB950` | 仅状态（成功/已索引） |
| `--warn` | `#E8833A` | 仅警告（橙，区别于 citation） |
| `--danger` | `#F85149` | 仅错误 |
| `--citation` | `#F5B544` | 琥珀签名色（引用文字/图标，暗底 AA 通过） |
| `--citation-bg` | `rgba(245,181,68,0.14)` | 引用 chip 背景 |
| `--citation-fill` | `rgba(245,181,68,0.28)` | PDF 高亮填充（bbox 升级用） |
| `--citation-ring` | `rgba(245,181,68,0.45)` | 引用焦点/选中环 |

### Light（第二主题，`<html data-theme="light">`）

| Token | 值 | 备注 |
|---|---|---|
| `--bg` | `#F9FAFB` | 画布 |
| `--surface` | `#FFFFFF` | 面板 |
| `--surface-2` | `#F3F4F6` | 抬升 |
| `--surface-3` | `#E9EBEE` | 更高抬升 |
| `--fg` | `#111827` | 主文本 |
| `--muted` | `#5B6470` | 次级 |
| `--meta` | `#9CA3AF` | 三级 |
| `--border` | `rgba(0,0,0,0.08)` | 发丝边框（暗色半透明） |
| `--border-soft` | `rgba(0,0,0,0.05)` | 弱分隔 |
| `--accent` | `#3E63DD` | 同暗色 |
| `--success` | `#16A34A` | AA 安全 |
| `--warn` | `#B45309` | 深橙，白底 AA 安全 |
| `--danger` | `#DC2626` | 错误 |
| `--citation` | `#9A6A0E` | 深琥珀，白底 AA 安全（文字/图标） |
| `--citation-bg` | `rgba(245,181,68,0.22)` | chip 背景 |
| `--citation-fill` | `rgba(245,181,68,0.30)` | PDF 高亮填充 |
| `--citation-ring` | `rgba(154,106,14,0.35)` | 引用环 |

**强调色使用纪律**：`--accent` 每屏可见使用 ≤2 处（主按钮 + 一个关键状态）。`--citation` 可在多处出现（每个引用角标），但仅作为"溯源"语义，不用于普通按钮。

---

## 3. Typography Rules

- **字体栈**
  - `--font-display` / `--font-body`：`"Inter", "Noto Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
  - `--font-mono`：`"JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, monospace`
- **OpenType 特性**：全局 `font-feature-settings: "cv01","ss03"`（几何感字形特性）。
- **字重三级**：`400`（读）/ `510`（强调、导航，签名字重）/ `590`（标题、CTA）。禁止正文用 510 以外字重堆砌。
- **字号 8 级**（基准 14px = `--text-sm`）：
  - `--text-xs` 12px · `--text-sm` 14px · `--text-base` 16px · `--text-md` 18px · `--text-lg` 20px · `--text-xl` 24px · `--text-2xl` 32px · `--text-3xl` 40px
- **行高**：`--leading-tight` 1.15（大标题）· `--leading-snug` 1.3（小标题）· `--leading-body` 1.5（正文）· `--leading-relaxed` 1.65（长文）
- **字距**：
  - 标题 ≥32px：`-0.01em ~ -0.02em`
  - 正文：0
  - **ALL CAPS 标签（如状态徽章）：强制 `0.06em`**
- **中文**：统一 Noto Sans SC，密集 UI 可读性最佳；**不引入衬线体**（Product Register 禁止 dashboard 衬线）。
- **等宽用途**：PDF 页码、分块 ID、token 计数、代码块、时间戳、技术元数据——呼应"溯源/工程精密"气质。

---

## 4. Component Stylings

### 4.1 Button
- **变体**：`primary`（accent 底 + accent-on 字）/ `secondary`（surface-2 底 + fg 字 + 1px border）/ `ghost`（透明 + muted 字，hover surface-2）/ `outline`（透明 + 1px border-accent + accent 字）/ `danger`（danger 底 + #fff 字）。
- **尺寸**：`sm` h24 px8 · `md` h32 px12（默认）· `lg` h40 px16 · `icon` 40×40 方形（内含 20px 图标）。
- **圆角**：`--radius-sm`(6px)。**状态全覆盖**：default / hover（底色微调）/ active（`scale(0.97)`）/ focus-visible（`--focus-ring`）/ disabled（`opacity .45` + 禁指针）/ loading（旋转图标 lucide `LoaderCircle` + 禁用交互）。
- 主按钮图标用 20px，文字与图标间距 `--space-2`。

### 4.2 Card
- 背景 `--surface`，`1px solid var(--border)`，`--radius-md`(12px)，内边距 `--space-5`(20px)。**无默认阴影**（暗色靠边框分层）。
- hover：边框过渡到 `var(--border)` 略亮或 `accent` 极淡（非左边框强调，禁侧条纹）。
- 选中态：边框 `var(--accent)` + 极淡 accent 背景 tint。

### 4.3 Input / Textarea
- 背景 `--surface`，`1px solid var(--border)`，`--radius-sm`，内边距 10px 12px，fg 字。
- focus：`border-color: var(--accent)` + `box-shadow: var(--focus-ring)`。
- 错误：`border-color: var(--danger)`，下方 helper 文字用 `--danger`，文案具体（如"嵌入后端未连接"）。
- 必填项用 `*` 而非仅靠占位符；占位符用 `--meta`。

### 4.4 引用角标 Citation `[n]`（F6 灵魂功能）
- 渲染为真实 `<button class="cite">`，inline，上标感：`font-mono`、`11px`、`--citation` 文字色、`--citation-bg` 背景、`1px solid var(--citation)`、`--radius-sm`、padding `0 4px`、与正文基线对齐。
- **hover**：背景加深 + `title`/Radix Tooltip 显示「文档名 · p.12」。
- **click**：跳 PDF 到该页并高亮（降级=整页高亮；升级=bbox 矩形）。跳转后 PDF 面板 `aria-live` 播报「已跳转至第 12 页，已高亮段落」。
- **focus-visible**：`--focus-ring`。
- **反向联动**：PDF 内高亮块被 hover/focus 时，对话中对应角标浮现 `--accent` 环。
- **引用溯源列表**：回答下方或右栏列出 `[1] 文档名 · p.12 · 片段摘要`，每条可点击跳转。

### 4.5 Stepper（确定性 5 阶段步骤条）
- 阶段：**上传 → 解析(Docling) → 分块 → 嵌入 → 索引**。
- 节点四态：`pending`（灰圈）/ `active`（lucide `LoaderCircle` 旋转 + accent）/ `done`（lucide `Check` + success）/ `error`（lucide `X` + danger + 原因 + 重试按钮）。
- **绝不显示 Docling 无法提供的假百分比**；连接器按完成度着色。
- 错误原因文案具体：加密 PDF →「文档已加密，无法解析」；Ollama 未启动 →「Embedding 后端未连接（Ollama 未启动）」；向量库未连接 →「向量库未连接」。

### 4.6 PDF 预览面板（降级 → 升级兼容）
- 暗色 chrome：面板背景 `--surface-2`，PDF 页面白底居中渲染（pdfjs）。
- **降级（当前）**：点击引用 → 翻到目标页（`--motion-base` 淡入）+ **整页高亮**（页面顶部 accent 条 + 极淡 `--citation-fill` 叠加 + 一次性脉冲 `scale 1.0→1.04` 220ms ease-out 后回落常驻）。
- **升级（bbox 到位后）**：在目标页按 `bbox` 坐标叠加琥珀矩形（`fill var(--citation-fill)` + `1.5px solid var(--citation)`），其余同降级。
- **数据结构（唯一坐标契约）**：`citation = { index:number, docId, docName, page:number /*必带*/, bbox?:{left,top,right,bottom} /*可选，归一化 0–1*/, snippet?:string }`。前端按 `left/top` 定位，并以 `(right-left)/(bottom-top)` 映射画布尺寸；`if (citation.bbox) 矩形高亮 else 整页高亮`。
- `prefers-reduced-motion`：去掉脉冲，直接常驻高亮。

---

## 5. Layout Principles

- **栅格**：12 / 8 / 4 列（桌面 / 平板 / 手机）；沟槽桌面 24px、平板 16px、手机 12px。
- **容器**：`--container-max` 1200px，居中，两侧 gutter `--space-6`。
- **节区节奏**：desktop 80px / tablet 48px / phone 32px。
- **全局导航**：左侧细导航栏（图标 24px + 文字，lucide），含：文档库 · 问答 · 评测看板 · 设置。
- **问答页三栏工作区**（核心布局）：
  - 左：知识库/文档面板（可折叠为图标轨，含拖拽上传区 + 文档列表）
  - 中：对话区（消息流 + 底部输入）
  - 右：PDF 原文预览（页码标记 + 高亮）
- **首页/概览**：无营销 Hero，首屏即真实内容（拖拽上传区 + 最近文档 + 最近问答 + 系统状态）。

---

## 6. Depth & Elevation

- **Dark 模式**：层级靠 `--surface`→`--surface-2`→`--surface-3` 亮度递进 + 发丝边框，**不靠阴影**。仅命令面板/弹层用多层柔和阴影（含 inset），如 `0 0 40px rgba(0,0,0,0.45)`。
- **Light 模式**：卡片可用柔和阴影 `0 1px 2px rgba(0,0,0,0.04), 0 4px 8px rgba(0,0,0,0.06)`。
- **禁止**：幽灵卡片（1px 边框 + blur≥16px 阴影同元素）；卡片圆角 ≥24px（上限 12–16px）；侧条纹边框（>1px 彩色左边框）。

---

## 7. Do's and Don'ts

- 通过 · 单一 accent `#3E63DD` + 中性灰 + 琥珀签名色；层级靠表面抬升与发丝边框。
- 通过 · 所有颜色走 Token；图标全 Lucide 16/20/24px；文案具体（"上传并解析""查看第 12 页出处"）。
- 通过 · 焦点环、键盘可达、对比度 ≥4.5:1、支持 `prefers-reduced-motion`。
- 禁止 · 紫色→粉色渐变（P0）；emoji 功能图标（P0）；硬编码颜色（P0）；模板味占位文案（P0）。
- 禁止 · Tailwind 默认 `#6366f1`（改用 `#3E63DD`）；圆角卡片+彩色左边框；虚构指标；渐变文字；每节小型大写标签/编号 section 营销语法；过度圆角/幽灵卡片。

---

## 8. Responsive Behavior

- **断点**：`sm` 640px · `md` 1024px · `lg` 1280px。
- **导航**：桌面左侧 Sidebar；移动端底部 TabBar（≤5 项，图标 24px + 文字 10px）+ 抽屉。
- **触摸目标**：移动端 ≥44×44px；桌面 ≥32×32px；可点元素间距 ≥8px。
- **三栏 → 移动端**：文档面板收为顶部抽屉；对话为主；PDF 预览为全屏弹层（底部「原文」入口唤起）。
- **安全区**：底部 `env(safe-area-inset-bottom)`（如需 PWA/小程序化）。

---

## 9. Agent Prompt Guide（给前端 Agent 的实现提示）

1. **Token 优先**：所有颜色/间距/圆角/阴影引用 `var(--token)` 或 Tailwind 4 `@theme` 生成的工具类；组件内禁止裸 hex（除 `#fff`/`#000`）。
2. **图标**：`import { Upload, FileText, Check, X, LoaderCircle, ... } from 'lucide-react'`；统一 `size={16|20|24}`、`strokeWidth={2}`、`color="currentColor"`。禁 emoji。
3. **主题切换**：读取 `<html data-theme>`，组件不写死颜色；提供主题切换按钮（lucide `Sun`/`Moon`）。
4. **引用角标**：用 `<button>` + Radix `Tooltip`；跳转调用 PDF 预览的 `goToPage(page, bbox?)`；降级先整页高亮，bbox 到位自动升级。
5. **步骤条**：阶段状态机驱动，错误态必带具体原因 + 重试回调；禁用假百分比。
6. **可访问性**：引用 chip、`Stepper` 节点、按钮均 `focus-visible` 环；PDF 跳转 `aria-live="polite"` 播报；对话框用 Radix `Dialog`。
7. **动效**：时长 150–300ms，`--ease-standard`；全局尊重 `prefers-reduced-motion`（用 Tailwind `motion-reduce:` 或 CSS 媒体查询关闭脉冲/过渡）。
8. **PDF 数据结构**：严格按 §4.6 的 `citation` 契约（page 必带、bbox 可选且始终为归一化 `left/top/right/bottom`），组件渲染兼容无 bbox 的整页降级。
