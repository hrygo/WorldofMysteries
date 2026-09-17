# Visual Asset System — Batch 01：核心语义图标

> Task：`MAC-VISUAL-ASSET-01`  
> 总体方案：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 状态：IMPLEMENTED IN PR / WAITING FOR AUTHORITATIVE CI

## 1. 本批目的

以最小可合并范围建立第一批真正落盘的 World of Mysteries 视觉资产，并验证后续资产系统所需的基本约束：

- Asset Catalog 使用稳定 `wom.icon.*` 语义命名；
- 原始图标使用可缩放 SVG；
- 图标保持 template rendering，由组件和 Token 决定颜色/状态；
- Swift 调用侧通过类型化注册表避免散落字符串；
- 不把首次资产落地和页面迁移绑成一个大 PR。

## 2. 本批实际交付

### 2.1 Core Icon Assets

| Asset | 视觉母题 | 用途 |
|---|---|---|
| `wom.icon.world` | 世界球体 + 顶部星芒 | 世界、世界状态、主导航 |
| `wom.icon.ritual` | 圆环 + 三角秘仪核心 + 方位刻度 | 仪式、秘仪、施行入口 |
| `wom.icon.codex` | 展开的古典文献 + 微型星芒 | 知识、Codex、档案 |
| `wom.icon.artifact` | 圆环内切晶体 / 封存物 | 遗物、Artifact、特殊物品 |

共同规格：

```text
canvas: 24 × 24
format: SVG
rendering intent: template
vector preservation: true
primary stroke: ~1.35–1.5
state color: SwiftUI / Design Token controlled
```

### 2.2 Swift Semantic Registry

新增：

```text
macos-app/WorldOfMysteries/DesignSystem/WOMIconAsset.swift
```

当前语义：

```text
world
ritual
codex
artifact
```

注册表只负责稳定 Asset 名称，不负责 SwiftUI rendering、尺寸、Hover 或 Accessibility。后者留给后续独立 `WOMIcon` 批次。

### 2.3 持久化资料

本批同时提交：

- `docs/05_UI/Visual_Asset_System_v1.0.md`：完整总体方案；
- 本文件：Batch 01 的范围、实现与后续入口。

从本批开始，视觉系统不再依赖聊天或临时环境保存方案。

## 3. 明确不做

本批不包含：

- 真实页面替换；
- Sidebar / Component Gallery 改动；
- 新增 `WOMIcon` SwiftUI View；
- 新增 ButtonStyle / Surface；
- 修改 Design Token 数值；
- 修改 Xcode project 配置；
- 修改 Engine、数据库、IPC 或产品契约。

## 4. 版权与来源

四个图标均为本任务中创建的原创几何 UI 图形，只表达抽象语义母题；没有复制小说官方插画、动漫影视商业美术、第三方图标包或其他受限素材。

## 5. 本地可验证项

在非 macOS/Xcode 执行环境可完成：

- Asset `Contents.json` JSON 结构解析；
- SVG XML 结构解析；
- `WOMIconAsset.swift` Swift 语法解析；
- 改动路径与 Task Capsule scope 对照；
- PR diff 回读。

`MACOS_APP_P0` 仍要求 macOS 上的 SwiftUI/Xcode App Target 构建；当前执行环境不能替代该阶段，最终结论以仓库 GitHub Actions required checks 为准。

## 6. 下一批入口

**Batch 02：扩充基础图标资产。**

优先落盘：

```text
wom.icon.character
wom.icon.clue
wom.icon.inventory
wom.icon.settings
wom.icon.add
wom.icon.remove
wom.icon.edit
wom.icon.search
wom.icon.close
wom.icon.back
wom.icon.favorite
wom.icon.more
```

Batch 02 仍以“资产先落盘”为主，不提前把大量页面迁移混入图标资产 PR。

## 7. 完成定义

本批只有在以下条件同时满足后才标记为 DONE：

1. Task Capsule、总体方案、Batch 记录、4 个 SVG、4 个 imageset metadata 与 Swift 注册表进入同一 PR；
2. PR base/head 与 changed files 回读正确；
3. Capsule Audit / CI required checks 给出权威通过结果；
4. 不存在超出本批 scope 的顺带修改。
