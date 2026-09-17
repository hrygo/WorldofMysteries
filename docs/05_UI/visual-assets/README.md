# Visual Asset System — 执行总体方案与持久化规则

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 本文件：视觉资产系统的 **Living Plan / 执行总体方案**。

## 1. 执行规则

- 长期原则与 Token 边界看 `Visual_Asset_System_v1.0.md`；当前实施顺序与状态以本文件为准。
- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- PR 不要求最小化；PR #26 作为 Wave B 的长期持久化工作区。
- 原子 commit 是最小审查/回滚单元。
- 涉及方案时同步提交总体计划 + Batch 记录 + 实际资产/代码。
- 稳定增量尽早推远端；准备合并时对最终 head 统一跑完整 `MACOS_APP_P0`。

## 2. 技术边界

- 世界观图形：原创 vector asset + typed registry，命名 `wom.icon.* / wom.ornament.* / wom.texture.*`。
- 平台行为与通用状态：SF Symbols + `WOMSystemIcon` / `WOMStatusIcon`。
- 状态表现：SwiftUI style + Design Token，不复制 hover/pressed/selected 位图。
- Surface：程序化 fill/stroke/shadow + 少量纹理；reduced transparency 有实色/弱纹理退化。

## 3. 已合入 main 的基线

| PR | 内容 |
|---|---|
| #22 | Visual Asset System 基线；World / Ritual / Codex / Artifact |
| #21 | Character / Fate / Worldline / Notes |
| #23 + #25 | Clue / Inventory / Settings；Living Plan |
| #24 + #25 | Add / Remove / Edit / Search 系统行为语义 |

## 4. PR #26 — Wave B

| Batch | 内容 | 状态 |
|---|---|---|
| 04 | Close / Back / Favorite / More | 已实现 |
| 05 | 状态语义 + Divination / Spirituality / Gray Fog / Seal / Card | 已实现 |
| 06 | `WOMTextureAsset` | 已实现 |
| 07 | `WOMIcon` | 已实现 |
| 08 | Button Style primitives | 已实现 |
| 09 | Panel / Card / Texture / Section Chrome | 已实现 |
| 10 | Component Gallery 视觉回归入口 | 已实现 |
| 11 | Sidebar 生产迁移 | 已实现 |
| 12 | Ritual：祭坛祈祷 + 黄水晶灵摆 | 已实现 |
| 13 | Codex / Archive：人物档案 + 廷根卷宗 + 叙事编年史 | 已实现 |
| 14 | Artifact / Fate：生产快捷入口 + 15 件 Showcase | 已实现 |
| 15+ | ContentView shell、可访问性最终收口 | 下一阶段 |

## 5. 生产入口事实

- **Sidebar**：真实生产组件，已迁移。
- **Ritual**：当前没有独立一级路由；迁移真实 Ritual 组件，不制造空页面。
- **Story Book / Cards**：当前 `ContentView` 仍是 generic placeholder；真实 Codex / Archive 组件已迁移，但页面功能不得虚报完成。
- **Artifact**：继续作为 Fate 中的命运干预工具；Preview/Live/Unavailable 三态和 IPC 边界保持不变。

## 6. 原子 commit 历史语义

```text
docs(macos): persist visual system wave B plan
feat(macos): complete system action icon semantics
feat(macos): add occult state and interaction icon assets
feat(macos): register texture assets
feat(macos): add unified WOMIcon component
feat(macos): add button style primitives
feat(macos): add panel and card surface primitives
feat(macos): expose visual system in component gallery
feat(macos): migrate sidebar to visual system
feat(macos): migrate ritual components to visual system
feat(macos): migrate codex and archive components
feat(macos): migrate artifact and fate surfaces
```

## 7. 下一阶段

1. `ContentView` shell：Engine 状态栏、主工作区背景、Advice / Listening Ring 底栏；
2. placeholder 页面定义正式接入条件，视觉系统不得掩盖功能缺失；
3. accessibility / keyboard / reduced motion / reduced transparency / high contrast 收口；
4. PR #26 最终 head 统一执行权威门禁并回读 diff。

## 8. 恢复入口

稳定设计基线 → 本文件 → 最新 Batch 文档 → Task Capsules → `DesignSystem/WOM*` → `Assets.xcassets/wom.*` → PR #26 原子 commit 历史。
