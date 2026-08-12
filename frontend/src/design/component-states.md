# 组件状态矩阵（9 态）

> 每个核心组件须覆盖 9 态：`Default / Hover / Focus / Active / Disabled / Loading / Error / Empty / Success`。
> 规则：所有颜色走 Token；图标全 lucide-react（16/20/24px）；文案具体无模板味；键盘可达 + `focus-visible` 环；`prefers-reduced-motion` 兜底。
> 标注「—」表示该组件不适用此态。

---

## 1. Button（按钮）

| 态 | 视觉 | 文案/交互 |
|---|---|---|
| Default | primary: accent 底 + accent-on 字；secondary: surface-2 底 + fg 字 + 1px border；ghost: 透明 + muted 字；outline: 透明 + 1px border-accent + accent 字 | 具体动词，如「上传并解析」「查看第 12 页出处」 |
| Hover | 底色 → accent-hover（primary）/ surface-3（secondary/ghost）；outline → 极淡 accent 底 | 光标 pointer |
| Focus | `box-shadow: var(--focus-ring)` | Tab 可达 |
| Active | `transform: scale(0.97)` | 按下反馈 |
| Disabled | `opacity .45`，禁指针 | 原因 tooltip（如「请先上传文档」） |
| Loading | 内含 `LoaderCircle` 旋转（20px），禁用交互 | 按钮文字保留或「处理中…」 |
| Error | — | 仅 danger 变体用于删除/危险操作 |
| Empty | — | — |
| Success | — | 操作后由 toast/inline 反馈 |

尺寸：sm h24 / md h32（默认）/ lg h40 / icon 40×40。圆角 `--radius-sm`。

---

## 2. Input / Textarea（输入）

| 态 | 视觉 |
|---|---|
| Default | surface 底 + 1px border + fg 字，placeholder 用 meta |
| Hover | border 略亮 |
| Focus | `border-color: accent` + `box-shadow: var(--focus-ring)` |
| Active | 同 Focus |
| Disabled | opacity .45，禁指针 |
| Loading | —（长任务用独立状态区，不锁输入） |
| Error | `border-color: danger` + 下方 helper 文字 danger，文案具体：「嵌入后端未连接（Ollama 未启动）」 |
| Empty | 占位符提示具体操作，如「输入问题，例如：本文档第三章的主要结论是什么？」 |
| Success | — |

必填用 `*` 标注，不仅靠占位符。

---

## 3. 文档列表行（Document Row）

| 态 | 视觉 | 文案/交互 |
|---|---|---|
| Default | surface 卡片行，左 `FileText`(20px) + 文件名(fg) + 类型/页数(meta) + 状态徽章 + 操作菜单(ghost icon) | 点击选中 → 右侧详情抽屉 |
| Hover | 行背景 → surface-2；操作菜单图标显形 | — |
| Focus | 行 `focus-ring` | 键盘可达 |
| Active | 选中：左 2px accent 边 + surface-3 底 | — |
| Disabled | — | — |
| Loading | 行内嵌入 5 阶段 Stepper（见 §7），进行中阶段 `LoaderCircle` 旋转 | 阶段名 + 状态 |
| Error | 状态徽章 danger + 原因文字（如「文档已加密，无法解析」）+ `重试` 按钮(ghost/danger) | 可重试/移除 |
| Empty | 见 §8 空状态（列表级） | — |
| Success | 状态徽章 success「已索引」+ 分块数(meta) | — |

状态徽章：success=「已索引」(绿)；active=「解析中」(accent)；error=「失败」(红)；pending=「排队」(meta)。

---

## 4. 上传拖拽区（Upload Dropzone）

| 态 | 视觉 | 文案 |
|---|---|---|
| Default | 虚线 1px border + `Upload`(24px) + 文字 | 「拖入 PDF 开始构建知识库，或点击选择文件」 |
| Hover | border → accent | — |
| Focus | `focus-ring`（区域可聚焦） | — |
| Active | dragover：border accent + 极淡 accent 底 | 「松开以上传」 |
| Disabled | opacity .45 | 「知识库初始化中，暂不可上传」 |
| Loading | 拖入后转文档行 Loading（Stepper） | — |
| Error | border danger + `AlertCircle` + 原因 | 「文档已加密，无法解析」/「仅支持 PDF 格式」 |
| Empty | 即 Default（首屏引导） | 同上 |
| Success | 短暂 toast「已加入解析队列」→ 转文档行 Loading | — |

支持格式提示：PDF（Docling 解析）；大小上限标注具体值（如 ≤ 200MB）。

---

## 5. PDF 预览面板（PDF Preview · F6）

| 态 | 视觉 | 交互 |
|---|---|---|
| Default | 面板 surface-2 底，白底 PDF 页居中（pdfjs），顶部页码导航 + 缩放 | — |
| Hover | 页面 hover 轻微亮度 | — |
| Focus | 面板 `focus-ring`（跳转后焦点移入） | 键盘翻页 |
| Active | — | — |
| Disabled | 空文档时面板占位（见 Empty） | — |
| Loading | 页面渲染 spinner（`LoaderCircle` 居中） | — |
| Error | `AlertTriangle` + 原因 | 「PDF 渲染失败」+ 重试 |
| Empty | 居中 `FileText`(24px) + 「暂无文档，请先在左侧上传」+ 上传入口 | — |
| Success(Highlight) | **引用高亮**：跳转目标页（200ms 淡入）+ 降级=整页高亮（顶部 accent 条 + 极淡 citation-fill 叠加 + 一次性脉冲 220ms）；升级=bbox 琥珀矩形(`fill citation-fill` + `1.5px citation`)。常驻柔和高亮 | 点击引用角标触发；`aria-live` 播报「已跳转至第 N 页，已高亮段落」 |

数据结构：`citation = { index, docId, docName, page /*必带*/, bbox? /*可选*/, snippet? }`。渲染：`if (bbox) 矩形 else 整页`。

---

## 6. 引用角标（Citation `[n]`）

| 态 | 视觉 |
|---|---|
| Default | inline `<button>`：font-mono 11px + citation 字 + citation-bg 底 + 1px citation 边框 + radius-sm |
| Hover | 背景加深 + Radix Tooltip「文档名 · p.12」 |
| Focus | `focus-ring` |
| Active | `scale(0.97)` |
| Disabled | — |
| Loading | — |
| Error | — |
| Empty | 回答无引用时不渲染 |
| Success(Linked) | 对应 PDF 高亮块被 hover/focus 时，本角标浮现 accent 环（反向联动） |

点击 → 调 PDF 面板 `goToPage(page, bbox?)`。

---

## 7. Stepper（5 阶段确定性步骤条）

阶段：**上传 → 解析(Docling) → 分块 → 嵌入 → 索引**。

| 节点态 | 视觉 | 文案 |
|---|---|---|
| pending | 灰圈(meta) | — |
| active | `LoaderCircle` 旋转 + accent 环 | 阶段名（如「嵌入中」） |
| done | `Check` + success | — |
| error | `X` + danger + 原因 + `重试` 按钮 | 「文档已加密，无法解析」/「Ollama 未启动」/「向量库未连接」 |
| （整体）Empty | 无任务时步骤条不显示 | — |

**禁止假百分比**（Docling 不支持细粒度进度）；连接器按完成度着色。

---

## 8. 空状态（Empty）

| 场景 | 视觉 | 文案 + 行动 |
|---|---|---|
| 知识库无文档（全局） | `FileText`(24px) + 引导 | 「拖入 PDF，开始构建你的可溯源知识库」+ 上传按钮 |
| 问答区（KB 空） | 问答区禁用 + 半透明遮罩 | 「请先上传文档」+ 上传入口 |
| 评测看板无运行 | `BarChart3`(24px) | 「还没有评测运行，先在设置配置评测集」+ 入口 |
| 搜索无结果 | `SearchX`(24px) | 「未找到匹配的文档，试试其他关键词」 |

---

## 9. 对话消息（Chat Message）

| 态 | 视觉 | 交互 |
|---|---|---|
| Default | 用户：右对齐 surface-2 气泡；助手：左对齐 surface 气泡，内联引用角标 `[n]` | — |
| Hover | 气泡边框略亮 | — |
| Focus | 消息区 `focus-ring`（可选） | — |
| Active | — | — |
| Disabled | 问答区整体禁用（KB 空时） | 见 §8 |
| Loading | 助手：流式打字机 + 末端闪烁光标；首屏骨架 | — |
| Error | danger 边气泡 + 原因 + `重试` | 「检索服务不可用，请稍后重试」 |
| Empty | 引导首问 + 真实示例问题（如「本文档第三章主要结论是什么？」） | — |
| Success | 回答完成 + 引用溯源列表（[1] 文档名 · p.12 · 片段） | 溯源列表可点击跳转 |

---

## 10. 评测看板卡片（Eval Card）

| 态 | 视觉 |
|---|---|
| Default | surface 卡片：评测集名 + 指标（EM/F1/召回@K，mono 数字）+ 运行时间 |
| Hover | border → accent 极淡 |
| Focus | `focus-ring` |
| Active | 选中展开明细 |
| Disabled | — |
| Loading | 卡片骨架屏（shimmer） |
| Error | danger 边 + 原因（如「评测集缺失字段」）+ 重试 |
| Empty | 见 §8 |
| Success | 指标达标绿色标记 + 趋势 |
