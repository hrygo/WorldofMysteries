# Visual Asset System — Batch 10：Component Gallery 接入

> Task：`MAC-VISUAL-SYSTEM-GALLERY`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 目标

将 Wave B 的资产与 primitive 真正接入 Component Gallery，使画廊承担设计系统展示与视觉回归入口，而不是只保留底层 API。

## 2. 展示覆盖

新增 `VisualSystemGallerySection`，集中展示：

- `WOMIconAsset` 全部世界观图标；
- `WOMSystemIcon` 平台行为图标；
- `WOMStatusIcon` 状态语义；
- Primary / Secondary / Tertiary / Danger / Ritual 按钮；
- Icon Button / Toolbar Button；
- Panel / Card / Floating / Ritual / Parchment surfaces；
- Parchment / Gold / Fool Veil / Sacred Slate / Velvet 纹理；
- `WOMCardChrome` hover 反馈；
- Section Header / Divider ornament。

## 3. 架构处理

原 Wave B Capsule 只授权 `DesignSystem/`、`Assets.xcassets/` 与文档目录。本批新增独立 `MAC-VISUAL-SYSTEM-GALLERY` Capsule，显式授权 Component Gallery 文件，保持权限边界可审计。

## 4. 后续

Gallery 稳定后进入真实生产页面迁移。优先顺序：

1. Sidebar；
2. Ritual；
3. Codex；
4. Artifact。

每个页面迁移使用新的页面级 Capsule，不扩大底层 DesignSystem Capsule。
