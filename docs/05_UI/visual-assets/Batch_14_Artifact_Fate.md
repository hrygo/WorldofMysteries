# Visual Asset System — Batch 14：Artifact / Fate 入口迁移

> Task：`MAC-VISUAL-ARTIFACT-FATE`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 产品边界

Artifact 继续遵循既定产品定位：高影响特殊物品作为 Fate 的命运干预工具嵌入当前 Story / World 上下文，不新增一级“道具背包”导航。

本批迁移两个真实入口：

- `FateArtifactInterventionView`：生产 Fate 快捷入口；
- `ArtifactShowcaseView`：15 件 Canon Artifact 组件库展示入口。

## 2. Fate Artifact Intervention

- 根容器切换为 `WOMCardChrome` + Sacred Slate；
- Header 引入 `wom.icon.artifact`；
- 快捷 Artifact 卡片使用统一 CardChrome 与 hover；
- hover 动画尊重 reduced motion；
- Preview / Live 的状态点在 reduced motion 下停止脉冲；
- unavailable sheet 使用统一 Panel surface。

以下语义保持原样：

- `ArtifactRuntimeAvailability`；
- Preview / Live / Unavailable 三态；
- `activeArtifactContext`；
- Engine IPC Adapter；
- Preview Resolver 不持久化世界事实；
- 各 Artifact model / resolver / orchestrator。

## 3. Artifact Showcase

- Header 使用 typed Artifact icon；
- 搜索框包裹统一 Card surface；
- Artifact selector 使用 `WOMCardChrome` selected state；
- 根容器使用 Panel + Sacred Slate；
- selector selection animation 尊重 reduced motion；
- 15 件 Artifact 的 `selectedComponent` 分发、preview context 和示例数据保持原样。

## 4. 明确不做

- 不修改 Artifact Engine / IPC；
- 不修改 `ArtifactRegistry`；
- 不改 Canon Artifact 数量或身份；
- 不把 Preview 数据误写入世界；
- 不新增 Inventory 一级导航。

## 5. 后续

下一阶段迁移 `ContentView` shell：顶部 Engine 状态、主工作区背景、底部 Advice / Listening Ring chrome，同时保持连接与 Advice 业务逻辑不变。
