# Visual Asset System — Wave D Recovery Index

> Durable workspace: PR #28 / `feat/wom-visual-system-wave-d`  
> 状态：DRAFT / IMPLEMENTATION COMPLETE / FINAL CI PENDING

## 1. 本阶段目的

Wave D 把 Wave B / C 建立的设计系统变成可长期维护的工程契约：

1. Asset Catalog 与 typed registry 自动一致；
2. 自有 SVG 的 template/vector 属性不可静默回退；
3. 平台动作继续由 SF Symbols 提供，不复制成自有资产；
4. typed icon 与局部 raw SF Symbol 的职责边界明确；
5. 一级导航、Section 与 ⌘1–⌘9 结构保持稳定；
6. Commands / Sidebar / placeholder 共享 typed navigation semantic source；
7. ⌘K 能真实将焦点送到 Advice TextField；
8. placeholder 页面必须达到明确 production-readiness 条件后才允许升级。

## 2. 当前已落盘

### 方案与恢复资料

- `Batch_18_Asset_Catalog_Contracts.md`
- `Typed_Icon_Usage_Boundaries_v1.0.md`
- `Batch_19_Keyboard_Navigation_Contracts.md`
- `Batch_20_Placeholder_Production_Readiness.md`
- `Wave_D_Recovery_Index.md`
- `.agents/capsules/MAC-VISUAL-SYSTEM-WAVE-D.json`

### 测试实现

- `VisualAssetCatalogContractTests.swift`
  - typed custom icon registry ↔ `wom.icon.*.imageset`
  - SVG template rendering intent
  - vector preservation
  - SVG payload existence
  - texture imageset/payload existence
  - texture alias reuse
  - platform action glyph 不复制成 custom imageset

- `VisualNavigationContractTests.swift`
  - 9 个一级入口
  - shortcut 1...9 唯一覆盖
  - NavigationSection 完整且无重复覆盖
  - Sidebar / ContentView / Commands 关键入口继续使用 typed `iconSource`
  - ⌘K Advice action ↔ scene focus request ↔ `@FocusState` 连通

### 真实实现

- `AppMenuBarCommands`：数字导航继续由 `NavigationItem.allCases + shortcutNumber` 驱动；菜单图标改为 `item.iconSource`；
- `MyApp`：增加 scene-scoped `adviceFocusRequestID`；
- `AdviceInputField`：通过 Environment 接收 focus request，使用原生 `@FocusState` 聚焦 TextField；
- Sidebar `⌥⌘S` help 与 Commands shortcut 已核对一致；
- 不使用 NotificationCenter，不新增第二套快捷键或焦点状态机。

## 3. Placeholder 事实边界

当前仍保持 placeholder：

- `character`
- `storyBook`
- `cards`
- `worldline`
- `notes`

仓库已有对应视觉 primitive，但尚缺生产级领域数据、选择/导航、持久化、状态处理或 IPC 接入。详见 `Batch_20_Placeholder_Production_Readiness.md`。不得以静态 demo 数据移除 placeholder 声明。

## 4. 当前未宣称完成的事项

- 新测试尚未执行最终 `MACOS_APP_P0`，不得标记为通过；
- Xcode App Target 尚未对 Wave D 最终 head 做权威编译验证；
- PR #28 尚未转 Ready；
- PR 尚未合并。

## 5. 下一恢复动作

新执行环境从此处恢复后按顺序：

1. 回读 PR #28 base/head 与 changed files；
2. 确认 `main` 未漂移；
3. 静态回读 Asset Catalog / Navigation contract tests；
4. 检查最终 diff 仅覆盖 Capsule write scope；
5. 更新 PR body 为最终真实 head / commit / changed-files 状态；
6. PR 转 Ready；
7. 对最终 head 运行一次完整 `MACOS_APP_P0`；
8. 若失败，只对最终 head 做原子 fix；
9. 全部门禁通过后启用/执行受保护合并；
10. 回读 `main` 验证 merge commit 与关键文件。

## 6. 完成判定

Wave D 只有同时满足以下条件才算完成：

- Asset Catalog contract tests 编译并通过；
- navigation/focus contract tests 编译并通过；
- Task Capsule scope 覆盖最终 diff；
- Architecture / Contracts / Python / Swift 6 / Xcode App Target / PR Gate Reporter 全绿；
- PR 最终 diff 无 Engine / DB / IPC / schema 越界；
- 主线合并后回读 `main` 确认目标提交存在。
