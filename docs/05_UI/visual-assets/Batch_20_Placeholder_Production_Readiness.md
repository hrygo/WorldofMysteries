# Visual Asset System — Wave D / Batch 20：Placeholder Production Readiness

> 分支：`feat/wom-visual-system-wave-d`  
> 状态：READINESS MATRIX DEFINED / ROUTES NOT PROMOTED

## 1. 目的

视觉系统已经为 9 个一级入口提供一致的 icon / surface / button / accessibility 基础，但视觉成熟不等于领域功能完成。本批明确哪些入口已经具备生产路由，哪些仍应保持 placeholder，以及从 placeholder 升级所需的最低条件。

## 2. 当前生产路由

| NavigationItem | 当前状态 | 说明 |
| --- | --- | --- |
| `world` | Production | `ContentView.worldHomeContent` 已有真实生产入口 |
| `fate` | Production | 命运干预 + Artifact 链路已接入 |
| `gallery` | Production tooling | Component Gallery 是设计系统真实回归入口 |
| `settings` | Production shell | 当前承载 Engine / Storage HUD |

## 3. 当前 placeholder 与可复用组件

| NavigationItem | 已有视觉组件 | 尚缺生产能力 |
| --- | --- | --- |
| `character` | `CharacterCodexCard` | 真实人物身份/途径/职业/位置/灵性/理智/traits 状态源；人物选择；Advice target 绑定 |
| `storyBook` | `NarrativeChronicleView` | 已 COMMIT 的叙事条目流；speaker/timestamp/audio 状态；分页或章节选择；空/加载/错误来源 |
| `cards` | `TarotCardView` | 卡牌发现状态模型；收藏列表；卡牌详情路由；持久化发现进度 |
| `worldline` | `WorldlineNodeView` | 持久化世界线分支事件；canonical/diverged/active/pruned 状态；分支选择与历史读取 |
| `notes` | `TingenCityDossierCard`、`CitrinePendulumScryingCard`、`CluePinboardNodeView` | 调查笔记/线索数据源；占卜事件桥接；选择与持久化；空/加载/错误状态 |

这些组件可以作为生产页面的视图 primitive，但不能仅用静态样例数据拼成页面后宣称功能完成。

## 4. 从 Placeholder 升级为 Production 的最低门槛

每个入口至少同时满足：

1. **领域数据事实源**：来自 AppState / Local Engine / 持久化存储或明确的只读领域接口，而不是 View 内硬编码 demo；
2. **Selection / Navigation**：存在稳定的列表→详情或节点选择行为，不只是孤立组件展示；
3. **状态完整性**：具备 empty / loading / error / unavailable 的真实处理；
4. **持久化边界**：涉及用户世界状态的修改必须进入既有持久化/IPC 契约，不在 View 中虚构提交；
5. **可访问性**：键盘焦点、VoiceOver label/value 与 Reduced Motion 等规则继续成立；
6. **测试**：至少有领域/路由 contract test 与 Swift 6 / Xcode target 编译验证；
7. **产品真实性**：只有达到以上条件后才可移除 `genericWorkspacePlaceholder` 的“功能占位”声明。

## 5. 本轮决定

Wave D **不把** `character / storyBook / cards / worldline / notes` 强行升级成生产页面。本轮只完成视觉资产、键盘导航、Focus 与 readiness 契约；后续每个领域入口应在真实领域数据/IPC 方案具备后独立迁移。
