# Visual Asset System — Batch 02：导航语义图标

> Task：`MAC-VISUAL-ASSET-02`  
> 总体设计：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 总进度：[`README.md`](README.md)  
> 上游：Batch 01 / PR #22  
> 状态：IMPLEMENTED IN STACKED PR / CI DEFERRED UNTIL RETARGET TO MAIN

## 1. 本批目的

在 Batch 01 的四个核心语义图标基础上，继续优先落盘主导航所需的第二组资产，同时保持 PR 足够小，不把行为图标、状态图标或真实页面迁移混入同一批。

## 2. 本批实际交付

| Asset | 视觉母题 | 用途 |
|---|---|---|
| `wom.icon.character` | 人物轮廓 + 微型星芒 | 角色、人物档案、角色导航 |
| `wom.icon.clue` | 放大镜 + 中心秘纹/星芒 | 线索、调查、证据入口 |
| `wom.icon.inventory` | 古典器物箱 / 档案匣 | 背包、持有物、库存 |
| `wom.icon.settings` | 克制的机械齿轮刻度 | 设置、偏好、系统配置 |

共同规格继续继承 Batch 01：

```text
canvas: 24 × 24
format: SVG
rendering intent: template
vector preservation: true
state color: SwiftUI / Design Token controlled
```

## 3. 注册表变化

`WOMIconAsset` 从 4 个语义扩展为 8 个：

```text
world
ritual
codex
artifact
character
clue
inventory
settings
```

注册表仍只承担 Asset Catalog 稳定语义名，不提前引入 `WOMIcon` View 或页面依赖。

## 4. 为什么本批只做 4 个

原总体路线把导航补充与 8 个行为图标放在同一 Batch。为落实“小步、分批 PR”，本批主动收窄：

- Batch 02：Character / Clue / Inventory / Settings；
- Batch 03：Add / Remove / Edit / Search / Close / Back / Favorite / More。

这样每个 PR 都能在数分钟内理解和审查，失败时也能独立回滚。

## 5. 明确不做

- 不迁移 Sidebar 或其他真实页面；
- 不新增 ButtonStyle；
- 不新增行为/状态图标；
- 不修改 Design Token 数值；
- 不修改 Xcode project；
- 不触碰 Engine / DB / IPC / contracts。

## 6. 版权与来源

四个图标均为本任务创建的原创几何 UI 图形，不复制官方商业美术、第三方图标包或受限素材。

## 7. Stacked PR 与 CI 状态

Batch 02 分支从 Batch 01 head 创建，PR #23 的 base 指向 `feat/wom-visual-assets-01`，因此 PR diff 只包含本批增量。

已确认当前仓库的 PR CI 对 `main` 目标分支触发，stacked base 不会立即产生同一套工作流。因此当前状态必须理解为：**资产已持久化并可审查，但权威 CI 尚未执行。**

当 PR #22 合并到 `main` 后：

1. 将 PR #23 base retarget 到 `main`；
2. 重新读取 `main` 最新 SHA；
3. 若 base SHA 改变，生成 Task Capsule 修订版；
4. 再次回读 changed files；
5. 等待 Capsule Gate、Architecture Fitness、Swift 6 与 Xcode App Target build 全绿后才标记 DONE。

## 8. 当前验证

提交前静态验证已完成：

- 4 个 imageset `Contents.json` 可解析；
- 4 个 SVG XML 可解析；
- 更新后的 `WOMIconAsset.swift` 可被 Swift parser 接受；
- 相对 Batch 01 head：ahead 1 / behind 0；
- changed files 仅在 Capsule scope 内。

上游 PR #22 的三条 GitHub Actions 工作流均已通过；该事实只证明 Batch 01，不替代 Batch 02 自身在 retarget 后必须执行的 CI。

## 9. 下一批入口

Batch 03：基础行为图标。

```text
wom.icon.add
wom.icon.remove
wom.icon.edit
wom.icon.search
wom.icon.close
wom.icon.back
wom.icon.favorite
wom.icon.more
```

仍坚持资产先落盘，不提前和真实页面迁移绑定。
