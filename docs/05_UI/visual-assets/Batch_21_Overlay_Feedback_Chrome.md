# Visual Asset System — Wave E / Batch 21：Overlay & Feedback Chrome

> Task：`MAC-VISUAL-SYSTEM-WAVE-E`  
> Base：`main@51a9b2679420edbf1fb9b12189033a2a6cdc8567`  
> PR：#29  
> 状态：IMPLEMENTED / FINAL AUDIT PENDING

## 1. 背景

Foundation、Wave B/C/D 已经完成图标、纹理、Button/Surface、真实组件迁移、辅助功能状态、Asset Catalog 契约、导航/Commands/Focus 收口。Wave E 补齐应用级 Overlay 与反馈状态：Inspector、Popover、Sheet 内容 chrome、Loading、Status、Empty State，以及对应 Gallery 与语义契约测试。

## 2. 核心原则

### 2.1 系统负责“呈现”，WOM 负责“皮肤”

- `.sheet`
- `.popover`
- `.inspector`

继续由 SwiftUI 原生 API 负责生命周期、窗口层级、键盘、Focus、VoiceOver 与平台行为。

本 Batch 不实现伪窗口、伪弹层或自定义 modal coordinator。`WOMOverlayPanel` 只负责内容区域视觉 chrome。

### 2.2 Feedback 不复制平台状态机

- Loading：系统 `ProgressView`；
- Focus / active appearance / Increase Contrast / Reduced Transparency / Reduced Motion：沿用已有 environment 策略；
- Status：typed icon + text + geometry，不能只靠颜色；
- Empty：新 WOM 调用使用 typed `WOMIconSource`，旧 `MysticEmptyState(systemIcon:)` 保留兼容。

## 3. 已实现 API

### `WOMOverlayRole`

```text
inspector / popover / sheet / hud
```

只表达视觉层级和默认密度，不表达 presentation 生命周期。

### `WOMOverlayPanel<Content>`

统一：

- surface tone；
- texture policy；
- padding；
- corner radius；
- 复用 `WOMPanelBackground` 的 active/inactive、Increase Contrast、Reduced Transparency 行为。

### `WOMFeedbackTone`

```text
info / success / warning / danger
```

并扩展 `WOMStatusIcon`：

```text
info.circle / checkmark.circle / exclamationmark.triangle / exclamationmark.octagon
```

### `WOMLoadingState`

- 使用系统 `ProgressView`；
- 可选 typed `WOMIconSource`；
- 不创建第二套无限 spinner；
- title/message 进入统一 Card surface。

### `WOMStatusBanner`

- Info / Success / Warning / Danger；
- typed status icon；
- 左侧 semantic rail；
- Differentiate Without Color 下使用不同 dash pattern；
- Increase Contrast 下加强边框；
- 可选 action。

### `WOMEmptyState`

实际实现没有直接修改 legacy `MysticEmptyState`，而是新增 typed canonical API：

```swift
WOMEmptyState(source: WOMIconSource, ...)
```

这样：

- 新视觉系统可使用 custom vector / navigation / system / status 四类 typed source；
- 旧 `MysticEmptyState(systemIcon: String, ...)` 完全不变；
- 不会因为 stored property 迁移破坏已有调用；
- 后续旧调用可按需迁移，而不是一次性机械替换。

## 4. Component Gallery

已新增 `overlayFeedbackSamples`，可观察：

- Inspector / Popover / Sheet / HUD 四类 chrome；
- Info / Success / Warning / Danger 四类 banner；
- Loading；
- typed Empty State；
- Increase Contrast / Differentiate Without Color 与现有 surface accessibility 行为。

Gallery 只承担设计系统回归观察，不代表业务 modal/inspector 已经正式接入。

## 5. 测试

新增 `VisualOverlayContractTests.swift`：

1. `WOMOverlayRole` case 集合稳定；
2. Feedback tone → platform status symbol 映射稳定；
3. Overlay primitive 不包含 `.sheet(isPresented:)` / `.popover(isPresented:)` / `.inspector(isPresented:)` coordinator，也不直接创建 `NSPanel` / `NSWindow`；
4. `WOMEmptyState` typed API 与 legacy `MysticEmptyState` 同时存在；
5. Gallery 必须保留 Overlay / Loading / Status / Empty specimen。

## 6. Scope 回读

实际修改仅涉及：

- 总体方案 / Living Plan / Batch 21；
- Wave E Task Capsule；
- `WOMStatusIcon.swift`；
- `WOMOverlayPrimitives.swift`；
- `ComponentGalleryVisualSystemSection.swift`；
- `VisualOverlayContractTests.swift`。

没有 Engine / DB / IPC / schema / Gate workflow 修改。

## 7. 原子 commit

```text
docs(macos): persist visual system wave E plan
feat(macos): add native overlay visual chrome
feat(macos): add typed empty and feedback states
feat(macos): add overlay feedback gallery specimens
test(macos): cover overlay visual system contracts
```

## 8. 下一步

1. 同步总体方案 / Living Plan 到真实实现状态；
2. 最终静态审计 Swift 6/API 使用；
3. 回读 `main...head` diff 与 Capsule scope；
4. PR #29 转 Ready；
5. 只对最终 head 运行完整 `MACOS_APP_P0`；
6. 失败只做原子 fix，不扩大 Wave E 范围。
