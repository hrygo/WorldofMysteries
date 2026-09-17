# Visual Asset System — 执行总体方案与持久化规则

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 本文件：视觉资产系统的 **Living Plan / 执行总体方案**。

## 1. 权威性

- 长期视觉语言、Token 原则、技术边界：以 `Visual_Asset_System_v1.0.md` 为准。
- 当前实施顺序、资产落盘进度、依赖和恢复入口：以本文件为准。
- 单批设计与实现细节：以对应 `Batch_xx_*.md`、Task Capsule、原子 commit 为准。
- 关键设计判断不得只存在于聊天、临时工作区或 PR 描述中。

## 2. 持久化与提交模型

1. 尽早建立远端分支/PR；
2. PR 不要求最小化，可承载同一工作流多个阶段；
3. 原子 commit 是最小审查/回滚单元；
4. 涉及方案时同步维护 Living Plan + Batch 文档；
5. 稳定资产/代码增量尽快落 Git；
6. 同类低风险增量持续推入长期 PR，准备合并时对最终 head 执行完整门禁。

## 3. 资产技术边界

- 世界观图形：原创 vector asset + typed registry，命名 `wom.icon.* / wom.ornament.* / wom.texture.*`；
- 平台标准行为/状态：SF Symbols + `WOMSystemIcon` / `WOMStatusIcon`；
- hover / pressed / selected / focused / disabled / loading：由 SwiftUI style + Design Token 控制，不复制位图状态。

## 4. 已合入 main 的基线

| 阶段 | 内容 |
|---|---|
| PR #22 | Visual Asset System 基线；World / Ritual / Codex / Artifact；`WOMIconAsset` |
| PR #21 | Character / Fate / Worldline / Notes；`WOMNavigationIconAsset` |
| PR #23 + #25 | Clue / Inventory / Settings；Living Plan |
| PR #24 + #25 | Add / Remove / Edit / Search 系统行为语义 |

## 5. PR #26 — Wave B 当前进度

| Batch | 内容 | 状态 |
|---|---|---|
| 04 | Close / Back / Favorite / More | 已实现 |
| 05 | 状态语义 + Divination / Spirituality / Gray Fog / Seal / Card | 已实现 |
| 06 | `WOMTextureAsset` | 已实现 |
| 07 | `WOMIcon` | 已实现 |
| 08 | Button Style primitives | 已实现 |
| 09 | Panel / Card / Texture / Section Chrome | 已实现 |
| 10 | Component Gallery 展示与视觉回归入口 | 已实现 |
| 11 | Sidebar 生产迁移 | 已实现 |
| 12 | Ritual 真实组件：祭坛祈祷 + 黄水晶灵摆 | 已实现 |
| 13 | Codex / Archive：人物档案 + 廷根卷宗 + 叙事编年史 | 已实现 |
| 14+ | Artifact / Fate、ContentView shell、可访问性最终收口 | 下一阶段 |

## 6. 生产入口事实

- **Sidebar**：真实生产组件，已迁移。
- **Ritual**：当前没有独立一级导航；已迁移真实 `BronzeAltarPrayerCard` 与 `CitrinePendulumScryingCard`，不制造空路由。
- **Story Book / Cards**：当前 `ContentView` 仍进入 generic placeholder；已先迁移真实 Codex/Archive 组件，不虚报页面完成。
- **Artifact**：产品基线明确作为 Fate 中的命运干预工具嵌入，不新增一级“道具背包”导航。

## 7. 原子 commit 序列

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
```

## 8. 下一阶段

1. Artifact / Fate 真实组件迁移；
2. ContentView shell 顶部状态栏与底部常驻交互 chrome 收口；
3. 对 placeholder 页面定义正式接入条件，不用视觉壳掩盖功能未完成；
4. accessibility / keyboard / reduced motion / reduced transparency / high contrast 收口；
5. 最终 head 统一运行 `MACOS_APP_P0`。

## 9. 恢复入口

依次读取：稳定设计基线 → 本文件 → 最新 Batch 文档 → Task Capsules → `DesignSystem/WOM*` → `Assets.xcassets/wom.*` → PR #26 原子 commit 历史。
