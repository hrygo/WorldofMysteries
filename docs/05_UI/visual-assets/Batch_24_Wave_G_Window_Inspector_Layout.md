# Batch 24 — Wave G：Window / Inspector / Responsive Workspace Layout

> 状态：IMPLEMENTATION COMPLETE / RETARGET + FINAL CI PENDING  
> 上游：Wave F / PR #32  
> Visual QA：`Visual_QA_Contract_v1.0.md`

## 1. 目标

Wave G 不新造业务页面，也不模拟 AppKit 窗口系统；它把已经在多个页面重复出现的“宽屏双栏 → 窄屏纵向”“Inspector 宽度”“默认窗口尺寸”收口成稳定的 macOS 布局契约。

核心目标：

1. 保持 960×640 为硬性最小可用尺寸，不通过抬高最小窗口掩盖布局问题；
2. 提供更舒适的首次默认窗口尺寸，用户仍可自由 resize；
3. 统一 Inspector 的 min / ideal / max 宽度；
4. 提供可复用的 `WOMAdaptivePair`，避免每个页面复制 `ViewThatFits` 双栏逻辑；
5. 使用真实 SwiftUI `.inspector` 做独立 Visual QA Preview，不制造自定义侧栏伪装 Inspector；
6. 所有新布局继续满足 Visual QA Contract：字体清晰、无覆盖、基线整齐、长文本可增长。

## 2. Apple 原生边界

Wave G 依据 SwiftUI 官方行为：

- `.inspector(isPresented:content:)` 由系统决定 trailing column / sheet 等适配方式；
- `.inspectorColumnWidth(min:ideal:max:)` 用于 trailing-column 的灵活宽度；
- Scene `.defaultSize(width:height:)` 只影响首次默认尺寸与新建窗口，不阻止用户 resize；
- `WindowGroup` 继续由系统管理状态恢复和窗口行为。

因此：

- **WOM 不实现 NSPanel / NSWindow coordinator**；
- **WOM 不固定 Inspector 为不可变宽度**；
- **WOM 不为了“对仗”禁止用户 resize**；
- WOM 只提供布局度量、responsive fallback 与视觉 chrome。

## 3. 尺寸契约

### App Window

- minimum: **960 × 640**；
- default: **1180 × 760**；
- 默认尺寸是舒适起点，不是强制尺寸。

### Inspector

- minimum: **280pt**；
- ideal: **320pt**；
- maximum: **420pt**。

设计理由：

- 280pt 足以容纳 13pt 正文、11pt metadata 和标准 padding；
- 320pt 为常规属性/状态 Inspector 的舒适宽度；
- 420pt 避免 Inspector 反客为主挤压主内容。

## 4. 已实现

### G24.1 — `WOMWindowMetrics` — DONE

- 960×640 minimum；
- 1180×760 default；
- metrics 成为 App shell 的单一事实源。

### G24.2 — `WOMAdaptivePair` — DONE

两块内容的 responsive primitive：

- 宽空间：水平、顶部对齐、统一 gap；
- 空间不足：自动纵向；
- trailing 区可指定 ideal width；
- 不做负 offset / absolute positioning。

### G24.3 — `WOMInspectorContent` — DONE

- 内部复用 `WOMOverlayPanel(role: .inspector)`；
- 采用 `.inspectorColumnWidth(min:ideal:max:)`；
- 内容可滚动；
- 不管理 presented state。

### G24.4 — Production shell alignment — DONE

- `ContentView` min size 改为 `WOMWindowMetrics`；
- Fate 局势双栏复用 `WOMAdaptivePair`；
- `WorldOfMysteriesApp` 设置舒适 default size；
- 不改变业务导航、IPC、状态机。

### G24.5 — Native Inspector QA Preview + Contract Tests — DONE

- 采用独立 `#Preview("Native Inspector · Visual QA")`，真实执行 `.inspector`；
- Inspector 放入长中文/英文、Relation、Cooldown 压力内容；
- 不继续膨胀已经较大的 Component Gallery 单文件；
- `VisualWindowLayoutContractTests` 锁定 960×640、1180×760、280/320/420；
- 锁定 `ViewThatFits` / `inspectorColumnWidth` / `defaultSize`；
- 禁止 NSPanel / NSWindow / fake inspector coordinator。

## 5. Visual QA 验收

- Inspector 280pt 时文字不得重叠或裁掉关键语义；
- 13pt 正文 / 11pt metadata 基线不降级；
- 960×640 主窗口仍能正常工作；
- 双栏自动降级时保持相同内容顺序与 spacing；
- Inspector / main content 的视觉重量清晰，Inspector 不压过主工作区；
- Increased Contrast / Reduce Transparency 下边界仍清楚。

## 6. 多窗口策略

本批**不新增第二个 WindowGroup**。只有当 Character / Codex / Story Book 等具备真实独立工作流、独立选择状态与恢复语义后，才评估 standalone window。不能为了“看起来像专业 macOS App”提前制造没有领域意义的窗口。

## 7. 原子 commit

```text
docs(macos): persist visual system wave G window layout plan
feat(macos): add native workspace and inspector layout primitives
feat(macos): apply comfortable default app window size
refactor(macos): centralize minimum window and fate split layout
feat(macos): add native inspector visual QA preview
test(macos): cover native window and inspector layout contracts
```

## 8. 下一动作

当前 PR 为 stacked Draft。待 #31 → #32 依次合并后：

1. retarget Wave G 到 `main`；
2. reissue/reconcile Capsule base；
3. 回读纯 Wave G diff；
4. Mark Ready；
5. 对最终 head 执行一次完整 `MACOS_APP_P0`。
