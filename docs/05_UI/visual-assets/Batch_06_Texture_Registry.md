# Visual Asset System — Batch 06：纹理注册与资产盘点

> Task：`MAC-VISUAL-SYSTEM-WAVE-B`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 结论

仓库已经存在 5 组高质量纹理资产，本批不重新导入、不复制二进制文件，而是建立稳定的语义注册层：

| Semantic | 当前 Asset Catalog 名称 | 建议用途 |
|---|---|---|
| `parchment` | `TextureParchment` | 档案、Codex、纸质 Surface |
| `gold` | `TextureGold` | 黄铜/金属高光、少量 accent |
| `foolVeil` | `TextureFoolVeil` | 灰雾、帷幕、世界级背景 |
| `sacredSlate` | `TextureSacredSlate` | 深色石板、仪式/Inspector Surface |
| `velvet` | `TextureVelvet` | 收藏、遗物、卡牌展示衬底 |

## 2. 新增 API

`WOMTextureAsset` 隐藏现有 Catalog 名字：

```swift
WOMTextureAsset.parchment
WOMTextureAsset.gold
WOMTextureAsset.foolVeil
WOMTextureAsset.sacredSlate
WOMTextureAsset.velvet
```

调用侧不再需要直接依赖 `TextureParchment` 等历史命名。

## 3. 为什么暂不重命名二进制资产

现有纹理体积较大，直接重命名/重导入会制造低价值二进制 diff。先通过类型化 registry 建立语义边界，未来需要统一到 `wom.texture.*` 时可以在单独的资产迁移 commit 中完成。

## 4. 使用约束

- 纹理只用于质感补强，不承担按钮状态或布局结构；
- 高频控件不叠加重 blur + 大纹理 mask；
- 默认由 `WOMTextureLayer` 控制 opacity / blend / reduced transparency；
- 不在页面直接写 Asset Catalog 字符串。

## 5. 后续

下一原子 commit 进入 Batch 07：实现统一 `WOMIcon` source model 和 SwiftUI View。
