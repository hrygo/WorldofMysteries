# Visual Asset System — Wave E / Batch 21：Overlay & Feedback Chrome

> Task：`MAC-VISUAL-SYSTEM-WAVE-E`  
> Base：`main@51a9b2679420edbf1fb9b12189033a2a6cdc8567`  
> 状态：PLANNED / PERSISTING

## 1. 背景

Foundation、Wave B/C/D 已经完成图标、纹理、Button/Surface、真实组件迁移、辅助功能状态、Asset Catalog 契约、导航/Commands/Focus 收口。当前缺口主要集中在**应用级 Overlay 与反馈状态**：Inspector、Popover、Sheet 内容虽然可以使用现有 surface 拼装，但尚无统一 chrome；Loading/Status/Empty State 也尚未形成完整 typed 语义。

## 2. 核心原则

### 2.1 系统负责“呈现”，WOM 负责“皮肤”

- `.sheet`
- `.popover`
- `.inspector`

继续由 SwiftUI 原生 API 负责生命周期、窗口层级、键盘、Focus、VoiceOver 与平台行为。

本 Batch 不实现伪窗口、伪弹层或自定义 modal coordinator。`WOMOverlayPanel` 只负责内容区域视觉 chrome。

### 2.2 Feedback 不复制平台状态机

- Loading：系统 `ProgressView` 为主；
- Focus / active appearance / Increase Contrast / Reduced Transparency / Reduced Motion：读取环境；
- Status：typed icon + text + geometry，不能只靠颜色；
- Empty：兼容现有 raw SF Symbol API，同时向 typed `WOMIconSource` 迁移。

## 3. 目标 API

### `WOMOverlayRole`

```text
inspector / popover / sheet / hud
```

只表达视觉层级和默认密度，不表达 presentation 生命周期。

### `WOMOverlayPanel<Content>`

统一：

- surface tone
- texture policy
- padding
- corner radius
- semantic border
- active/inactive appearance
- Increase Contrast / Reduced Transparency 退化

### `WOMLoadingState`

覆盖：

- indeterminate loading
- waiting for engine / IPC
- background preparation

要求：系统 `ProgressView`；不添加强制无限旋转动画；title/message 可读；可选 typed icon。

### `WOMStatusBanner`

覆盖：

```text
info / success / warning / danger
```

要求：typed status icon、文本语义、非颜色几何区分、可选 action。

### `MysticEmptyState` typed upgrade

- 保留 `init(systemIcon: String, ...)`，避免破坏已有调用；
- 新增 `init(source: WOMIconSource, ...)`；
- 新代码优先 typed source；
- 旧调用可逐步迁移，不做一次性全仓库替换。

## 4. Component Gallery

新增 Overlay / Feedback specimen，集中观察：

- Inspector / Popover / Sheet / HUD chrome；
- Loading；
- Success / Warning / Danger / Info；
- Empty State typed icon；
- Increase Contrast / Reduced Transparency / Reduced Motion / inactive window 行为。

Gallery 只承担设计系统回归观察，不代表业务 modal/inspector 已经正式接入。

## 5. 测试策略

新增 `VisualOverlayContractTests`，优先锁定**语义契约**而非像素截图：

1. `WOMOverlayRole` case 集合稳定；
2. Status semantic mapping 稳定；
3. Overlay 只使用已有 `WOMSurfaceTone` / `WOMTextureAsset`，不复制第二套资源；
4. `MysticEmptyState` raw initializer 与 typed initializer 同时存在；
5. Gallery 必须包含 Overlay / Feedback specimen；
6. 不在 visual overlay primitive 内出现 `.sheet` / `.popover` / `.inspector` presentation coordinator，实现层不得接管系统生命周期。

## 6. Scope

允许修改：

- `docs/05_UI/Visual_Asset_System_v1.0.md`
- `docs/05_UI/visual-assets/`
- `macos-app/WorldOfMysteries/DesignSystem/`
- `macos-app/WorldOfMysteries/Components/MysticPrimitives.swift`
- `macos-app/WorldOfMysteries/Components/ComponentGalleryVisualSystemSection.swift`
- `macos-app/WorldOfMysteriesTests/`

禁止：Engine / DB / IPC / schema / Gate workflow 变更。

## 7. 原子 commit 计划

```text
docs(macos): persist visual system wave E plan
feat(macos): add native overlay visual chrome
feat(macos): add loading and status feedback primitives
refactor(macos): add typed empty-state icon source
feat(macos): add overlay feedback gallery specimens
test(macos): cover overlay visual system contracts
```

实际 commit 可根据静态审计拆分或合并，但每个 commit 必须保持单一语义目的。

## 8. 完成判定

- 总方案、Living Plan、Batch 与 Capsule 已落盘；
- Overlay / Feedback API 编译；
- Empty State 向后兼容；
- Gallery specimen 可观察；
- semantic tests 通过；
- 最终 diff 无 Engine/DB/IPC/schema 越界；
- 最终 head 完整 `MACOS_APP_P0` 全绿；
- 远端 readback 与 PR metadata 一致。
