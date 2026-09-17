# Visual Asset System — 执行总体方案与持久化规则

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 本文件：视觉资产系统的 **Living Plan / 执行总体方案**。

## 1. 执行规则

- 长期视觉原则、Token 边界与技术方向以 `Visual_Asset_System_v1.0.md` 为准；当前实施顺序与状态以本文件为准。
- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- PR 不要求最小化；同一工作流使用长期持久化 PR。
- 原子 commit 是最小审查/回滚单元。
- 涉及方案时必须同步提交：总体计划 + Batch 记录 + 实际资产/代码。
- 稳定增量尽早推远端；准备合并时对最终 head 统一运行完整 `MACOS_APP_P0`。

## 2. 技术边界

- 世界观图形：原创 vector asset + typed registry，命名 `wom.icon.* / wom.ornament.* / wom.texture.*`。
- 平台行为与通用状态：SF Symbols + `WOMSystemIcon` / `WOMStatusIcon`。
- Hover / Pressed / Selected / Focused / Disabled / Loading：由 SwiftUI style + Design Token 控制，不复制状态位图。
- Surface：程序化 fill/stroke/shadow + 少量纹理；Reduced Transparency 有稳定退化。
- macOS Focus / contrast / active appearance 优先读取 SwiftUI 系统 environment，不自建第二套平台状态机。

## 3. 已合入 main 的阶段

| 阶段 | PR | 内容 | 状态 |
|---|---|---|---|
| Foundation | #21–#25 | 视觉资产基础、核心/导航图标、Living Plan、系统行为语义 | 已合入 |
| Wave B | #26 | Icon / Button / Surface primitives、Gallery、Sidebar、Ritual、Codex/Archive、Artifact/Fate、Content Shell | 已合入 `main@d0de662e` |

Wave B 最终只对最终 head 跑一次权威门禁，Capsule Audit、Architecture/Contracts、Python、Swift 6、Xcode App Target、PR Gate Reporter 全部通过。

## 4. 生产入口事实

- **Sidebar**：真实生产组件，已迁移。
- **Ritual**：当前没有独立一级路由；已迁移真实 Ritual 组件，不制造空页面。
- **Story Book / Cards**：`ContentView` 仍有 generic placeholder；真实 Codex / Archive 组件已迁移，但功能完成度不得虚报。
- **Artifact**：继续作为 Fate 中的命运干预工具；Preview / Live / Unavailable 与 IPC 边界保持不变。
- **ContentView Shell**：视觉壳已迁移；placeholder 明确标注功能仍待正式接入。

## 5. 当前持久化工作流：Wave C

分支：`feat/wom-visual-system-wave-c`。

目标：从“视觉系统能用”进一步收口到“macOS 原生交互与辅助功能状态完整”。

### Batch 17 — Focus / Contrast / Accessibility State

1. Button chrome 读取 `isFocused`，增加 token 驱动 focus ring；
2. `colorSchemeContrast == .increased` 时增强边框与 Surface 层级；
3. `accessibilityDifferentiateWithoutColor` 时 selected / danger / ritual 不仅靠颜色区分；
4. `appearsActive == false` 时降低 glow/accent，符合非活跃窗口视觉；
5. Component Gallery 增加 Accessibility State specimen；
6. `DesignSystemTests` 补 typed registry / size scale / compatibility assertions。

### 后续候选

- keyboard navigation / focused scene command 收口；
- placeholder 页面正式数据接入条件；
- 图标与 raw `Image(systemName:)` 使用审计；
- high contrast / reduced transparency / reduced motion 视觉回归矩阵。

## 6. Wave C 原子 commit 计划

```text
docs(macos): persist visual system wave C plan
feat(macos): add focus and contrast aware button chrome
feat(macos): harden accessible surface states
feat(macos): add accessibility specimens to gallery
test(macos): cover visual system semantic registries
```

## 7. 恢复入口

依次读取：

1. `docs/05_UI/Visual_Asset_System_v1.0.md`
2. 本文件
3. 最新 `Batch_xx_*.md`
4. 当前 Wave Task Capsule
5. `DesignSystem/WOM*`
6. `Assets.xcassets/wom.*`
7. 当前长期 PR 的原子 commit 历史

目标：执行环境完全丢失后，仅依赖仓库和开放 PR 即可继续推进。
