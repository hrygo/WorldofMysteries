# Batch 25 — Wave H：Visual QA Source Guards

> 状态：IN PROGRESS  
> 上游：Wave G / PR #33  
> Visual QA：`Visual_QA_Contract_v1.0.md`  
> Source Guard：`Visual_QA_Source_Guards_v1.0.md`

## 1. 目标

Wave A–G 已通过追溯整改和响应式布局治理，但当前多数回归测试仍是“点名组件”的契约。Wave H 把用户明确要求的可读性/不重叠/macOS 原生性进一步升级为**生产视觉源码自动 Guard**，使未来新增组件默认受约束。

## 2. Guard 范围

扫描：

- DesignSystem
- Components
- Artifacts
- ContentView
- MyApp

Guard 只覆盖表达层，不修改 Engine / DB / IPC / schema。

## 3. Guard 规则

### H25.1 — Small Type Guard

生产视觉 `.font(.system(size: ...))` 中，小于 10pt 直接失败。

### H25.2 — No Shrink-to-Fit Guard

禁止 `.minimumScaleFactor(...)`。

### H25.3 — Negative Padding Layout Guard

在 Components / Artifacts / ContentView 禁止负 padding；DesignSystem 不 blanket-ban，因为 focus ring 外扩属于合法基础样式实现。

### H25.4 — Native Window Guard

禁止普通视觉代码直接引入 `NSPanel / NSWindow / NSViewRepresentable`。

### H25.5 — Guard Contract Self-Test

测试辅助方法必须能：

- 递归扫描目录；
- 只读取 `.swift` 生产文件；
- 排除 Tests；
- 返回路径 + 行号 + 违规片段，便于定位。

## 4. 不做的过度限制

不全局禁止：

- `.offset`
- `.lineLimit(1)`
- `.opacity`
- 10pt 短标签
- 图标固定尺寸

原因：这些存在合法视觉场景，不能用粗暴字符串规则代替语义审查。

## 5. 验收

- 新 Guard 在 Wave G stacked head 上应无违规；
- Guard 自身不得扫描测试文件造成自我命中；
- Guard 失败必须输出可定位的相对路径与行号；
- 不新增生产行为；
- 最终合并前仍需完整 `MACOS_APP_P0`。

## 6. 交付策略

1. 总体规则 / Batch / Capsule 先落远端；
2. 立即开 stacked Draft PR；
3. `VisualQASourceGuardTests.swift` 独立原子提交；
4. 若 Guard 首次发现历史残留，按问题类别继续原子修复；
5. 上游 #31 → #32 → #33 合并后，Wave H retarget `main`、重签 Capsule、最终 CI。
