# Visual Asset System — Batch 11：Sidebar 迁移

> Task：`MAC-VISUAL-SIDEBAR`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 范围

本批只迁移 Sidebar 的视觉表达与 accessibility，不改变：

- `NavigationSection` 分组语义；
- `NavigationItem` 路由语义；
- `selection` binding；
- `badgeCounts` 数据；
- `isCollapsed` binding；
- `⌘1`–`⌘9` 快捷键编号。

## 2. 图标迁移

新增 `NavigationItem.iconSource`，生产 Sidebar 开始使用 `WOMIconSource`：

- World → `WOMIconAsset.world`
- Character → `WOMNavigationIconAsset.character`
- Fate → `WOMNavigationIconAsset.fate`
- Story Book → `WOMIconAsset.codex`
- Cards → `WOMIconAsset.card`
- Worldline → `WOMNavigationIconAsset.worldline`
- Notes → `WOMNavigationIconAsset.notes`
- Gallery / Settings → `WOMSystemIcon`

`NavigationItem.systemIcon` 暂时保留作为兼容层，等全局调用点完成迁移后再单独清理。

## 3. Sidebar Chrome

- 根 Surface：`WOMPanelBackground(.panel)` + 极弱 `SacredSlate` 纹理；
- 品牌徽记：自有 `Seal` 图标替换通用 eye glyph；
- Header / Footer 分隔：`WOMDividerOrnament`；
- 折叠控制：`WOMToolbarButtonStyle` + 类型化 Sidebar SF Symbol；
- Footer：`WOMPanelBackground(.card)` + 极弱 Velvet 纹理；
- 灵性状态：复用 `wom.icon.spirituality`。

## 4. 交互与 Accessibility

- 折叠与选择动画尊重 `accessibilityReduceMotion`；
- 折叠态导航项明确暴露 `accessibilityLabel`；
- badge 数量作为 accessibility value；
- 灵性进度条作为单一语义元素暴露 `85%`；
- 折叠头像组合成一个 VoiceOver 元素；
- 带可见标题的世界观图标继续按装饰性图形处理，避免重复朗读。

## 5. 边界

本批不修改 App 路由、页面状态、Engine、DB、IPC、contract；仅迁移视觉与可访问性。

## 6. 后续

下一生产页面按独立 Capsule 推进 Ritual / Codex / Artifact，继续写入同一个 PR #26 的原子 commit 历史。
