# Batch 25 — Wave H：Visual QA Source Guards

> 状态：IMPLEMENTATION COMPLETE / UPSTREAM RECONCILE + FINAL CI PENDING  
> 上游：Wave G / PR #33  
> Visual QA：`Visual_QA_Contract_v1.0.md`  
> Source Guard：`Visual_QA_Source_Guards_v1.0.md`

## 1. 目标

Wave A–G 已通过追溯整改和响应式布局治理，但此前多数回归测试仍是“点名组件”的契约。Wave H 把用户明确要求的可读性/不重叠/对比度/macOS 原生性升级为**生产视觉源码自动 Guard + Token 数学契约**，使未来新增组件和 Token 改动默认受约束。

## 2. Guard 范围

扫描生产表达层：

- DesignSystem
- Components
- Artifacts
- ContentView
- MyApp

Guard 不修改 Engine / DB / IPC / schema。

## 3. 已实现

### H25.1 — Small Type Guard — DONE

- 递归扫描直接 `.font(.system(size: ...))`；
- `< 10pt` 失败；
- 10pt 仍允许短数字/快捷键/极短标签。

### H25.2 — No Shrink-to-Fit Guard — DONE

- 生产视觉源码禁止 `.minimumScaleFactor(...)`；
- 空间不足必须通过换行 / adaptive Grid / `ViewThatFits` / 纵向 fallback 解决。

### H25.3 — Negative Padding Layout Guard — DONE

- Components / Artifacts / ContentView 禁止负 padding；
- DesignSystem 不 blanket-ban，因为 focus ring 外扩属于合法基础样式实现。

### H25.4 — Native Window Guard — DONE

- 普通视觉源码禁止 `NSPanel / NSWindow / NSViewRepresentable`；
- Window / Inspector / Sheet / Popover 继续走 SwiftUI/macOS 原生机制。

### H25.5 — Generic Scanner Infrastructure — DONE

- 递归读取 production `.swift`；
- Tests 不进入生产扫描；
- 违规在 CI 输出 `relative/path.swift:line: detail :: snippet`；
- 不全局禁止 offset / lineLimit / opacity 等存在合法场景的 API。

### H25.6 — Approved Contrast Matrix — DONE

`VisualContrastContractTests.swift`：

- 直接解析 `DesignTokens.swift` RGB Token；
- 使用 WCAG relative luminance / contrast ratio 公式；
- AAA/长文本优先组合锁定 >= 7:1；
- 常规可读文字组合锁定 >= 4.5:1；
- Danger Button 锁定 `textPrimary / crimsonThread`；
- Parchment primary/secondary/tertiary ink 层级分别验证。

动态 Pathway/accent/status 色若要新增正文职责，必须先进入 Approved Contrast Matrix。

### H25.7 — Typography Token Floors — DONE

`VisualTypographyContractTests.swift` 防止 Typography Token 自身被未来改小：

- `bodyMedium >= 13pt`；
- `bodyLarge >= 14pt`；
- `caption / monoBadge >= 11pt`；
- `titleSmall >= 15pt`；
- title / display / narrative roles 保持现有可读性下限；
- `parchmentCursive >= 14pt`；
- narrative / parchment / body / title / compact line spacing 均有最低阈值。

## 4. 明确不做的过度限制

不全局禁止：

- `.offset`
- `.lineLimit(1)`
- `.opacity`
- 10pt 短标签
- 图标固定尺寸

这些存在合法视觉场景，不能用粗暴字符串规则代替语义审查。

## 5. 当前交付

- `.agents/capsules/MAC-VISUAL-QA-SOURCE-GUARDS.json`
- `docs/05_UI/visual-assets/Visual_QA_Source_Guards_v1.0.md`
- `docs/05_UI/visual-assets/Batch_25_Wave_H_Visual_QA_Source_Guards.md`
- `macos-app/WorldOfMysteriesTests/VisualQASourceGuardTests.swift`
- `macos-app/WorldOfMysteriesTests/VisualContrastContractTests.swift`
- `macos-app/WorldOfMysteriesTests/VisualTypographyContractTests.swift`
- Living Plan 更新。

## 6. 原子 commit

```text
docs(macos): persist visual QA source guard plan wave H
test(macos): add generic visual QA source guards
test(macos): enforce approved visual contrast token pairs
docs(macos): add approved contrast matrix to visual QA guards
docs(macos): close wave H source guard implementation scope
docs(macos): advance living plan through wave H QA guards
test(macos): lock visual typography readability floors
```

## 7. 验收状态

当前是 stacked PR，尚未把“实现已写入”表述成“最终 CI 已通过”。

待上游 #31 → #32 → #33 依次合并后：

1. retarget Wave H 到 `main`；
2. reconcile/reissue Capsule base；
3. 回读纯 Wave H diff；
4. Mark Ready；
5. 对最终 head 执行一次完整 `MACOS_APP_P0`；
6. 若 Source Guard 首次执行发现历史残留，则按问题类别追加原子修复，不放宽规则掩盖问题。
