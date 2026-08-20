# DocRAG · 前端

可本地部署、带**精准页码溯源**的文档问答（RAG）应用前端。基于 Spec 与 Design System 实现，暗色为默认主题、附完整浅色主题。

## 技术栈

| 关注点 | 选型 |
| --- | --- |
| 框架 | React 19 + Vite 8 + TypeScript 5.6（strict） |
| 样式 | Tailwind CSS 4（`@tailwindcss/vite`，设计 Token 经 `@theme inline` 映射） |
| 服务端状态 | @tanstack/react-query v5 |
| 客户端状态 | zustand v5（主题 + 跨组件 PDF 导航联动） |
| 路由 | react-router-dom v6 |
| 组件原语 | Radix UI（Dialog / Tooltip）+ lucide-react（**全部图标**，无 emoji） |
| PDF 渲染 | pdfjs-dist v6（worker 经 `?url` 引入 + `Promise.withResolvers` polyfill） |
| 流式问答 | 原生 `fetch` + `ReadableStream` 手动解析 SSE（delta / citation / done / error） |

## 目录结构

```
frontend/
├── index.html                 # 入口，<html data-theme="dark">
├── package.json
├── vite.config.ts            # react + tailwindcss 插件，/api 代理到 :8000
├── tsconfig*.json
├── eslint.config.js          # ESLint 9 flat config
├── src/
│   ├── main.tsx              # QueryClient + RouterProvider + 主题引导
│   ├── App.tsx               # createBrowserRouter，AppShell 包裹 4 条路由
│   ├── pages/                # Home / Documents / Chat / Evaluation
│   ├── components/
│   │   ├── ui/               # Button / Card / Input / Badge / Spinner / Tooltip / Dialog / EmptyState / Switch
│   │   ├── layout/           # AppShell / Sidebar / Header / MobileNav / ThemeToggle / nav
│   │   └── common/           # UploadDropzone / DocTable / Stepper / CitationChip / MessageBubble
│   │                        # BackendSelector / SystemStatus / RecentDocs / RecentChats / PDFPreview
│   ├── hooks/                # useDocuments / useSystem
│   ├── api/                  # client / documents / health / chat / evaluation
│   ├── lib/                  # theme / format / pdf / citation / cn / status / stores / recentQueries
│   ├── types/               # api / chat
│   └── styles/              # tokens.css（唯一色彩真相源）+ globals.css
```

## 页面

- **概览 `/`**：上传区 + 系统状态（文档 / 分块 / 解析中 / 向量库 / Embedding）+ 最近文档 + 最近问答。
- **文档库 `/documents`**：文档表格（加载 / 空 / 错误三态）、搜索、5 阶段处理进度、删除确认；点击行跳转 `/chat?doc={id}`。
- **问答 `/chat`**：三栏工作区（文档面板 | 对话 | PDF 预览）。顶部双后端 + Rerank 开关；SSE 增量渲染回答与 `[n]` 引用角标；点击角标 → PDF 跳页并高亮 bbox（含反向联动）。支持 `?q=`（预填提问）与 `?doc=`（预选文档）。
- **评测看板 `/evaluation`**：运行评测集，展示引用准确率 / 召回@K / 命中率 / MRR 与逐条明细。

## 设计约束（P0 红线，已通过正则扫描保证）

1. **禁止 emoji 作功能图标**——所有图标来自 `lucide-react`（16 / 20 / 24px，`currentColor`）。
2. **禁止紫色→粉色渐变**与任何其他 AI 模板配色。
3. **禁止硬编码颜色**——组件只引用 `var(--token)`（由 `tokens.css` 提供，`#fff`/`#000` 例外）。
4. **禁止 AI 模板味文案**——使用具体中文文案，无 "Lorem ipsum" / "Welcome to"。

## 设计 Token

- 暗色默认：`--bg #0b0d10`、`--accent #3e63dd`、`--citation #f5b544`（签名琥珀，与 accent 冷暖对比）。
- 浅色主题经 `<html data-theme="light">` 翻转整套变量，组件零改动。
- 语义色：`--success` / `--warn` / `--danger`。
- 动效尊重 `prefers-reduced-motion`（全局兜底）。

## 脚本

```bash
npm install        # 安装依赖
npm run dev        # 开发服务器（默认 5173，/api 代理到 http://localhost:8000）
npm run build      # tsc --noEmit && vite build
npm run preview    # 预览构建产物
npm run lint       # ESLint
```

## 与后端的契约（端点前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/documents` | 上传 PDF（multipart），触发解析流水线 |
| GET | `/documents` | 文档列表 |
| GET | `/documents/{id}` | 文档详情 + 分块预览 |
| GET | `/documents/{id}/file` | PDF 二进制（供 pdfjs 加载完整文档以定位页码 / bbox） |
| DELETE | `/documents/{id}` | 删除文档 |
| POST | `/chat` | SSE 问答（delta / citation / done / error） |
| GET | `/health` | 健康与模型状态 |
| GET | `/config/backends` | LLM / Rerank / Embedding 后端状态 |
| POST | `/evaluation/run` | 运行评测集 |

> PDF 原文统一使用整文档端点 `/file`：pdfjs 需要完整 PDF 对象才能定位页码与 bbox 高亮，前端、后端与 Spec 均以此为唯一契约。
