# Visual Asset System — Batch 07：统一 WOMIcon

> Task：`MAC-VISUAL-SYSTEM-WAVE-B`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 目标

建立一个 SwiftUI 统一图标入口，让调用侧不再关心图标来自 Asset Catalog 还是 SF Symbols。

## 2. Source Model

`WOMIconSource` 支持：

```text
asset(WOMIconAsset)
navigation(WOMNavigationIconAsset)
system(WOMSystemIcon)
status(WOMStatusIcon)
```

这样世界观 SVG、导航 SVG、系统行为和状态图标共享同一渲染层。

## 3. 尺寸规范

`WOMIconSize` 固化第一版尺寸 scale：

| Token | points | 典型场景 |
|---|---:|---|
| compact | 16 | compact label / inline |
| standard | 20 | 普通按钮 / sidebar |
| prominent | 24 | 主导航 / 强操作 |
| large | 32 | 空状态 / hero 辅助图形 |

## 4. 渲染策略

- 所有图标统一 template rendering；
- custom SVG 与 SF Symbols 都使用同一 frame/scale policy；
- 颜色由外层 `foregroundStyle` / semantic token 控制；
- selected / hover / pressed 不复制资产，由 ButtonStyle / surrounding component 控制。

## 5. Accessibility

`WOMIcon` 接受可选 `accessibilityLabel`：

- 有 label：作为可读语义暴露；
- 无 label：默认 `accessibilityHidden(true)`，按装饰性图形处理；
- 带可见文字的按钮通常让文字承担可访问性名称，避免图标重复朗读。

## 6. 后续

下一原子 commit 进入 Batch 08：按钮样式 primitives 与状态模型。
