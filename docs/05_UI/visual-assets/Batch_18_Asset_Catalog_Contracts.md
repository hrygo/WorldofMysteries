# Visual Asset System — Wave D / Batch 18：Asset Catalog Contract

> 当前阶段：Wave D  
> 分支：`feat/wom-visual-system-wave-d`  
> 状态：PLAN PERSISTED / IMPLEMENTATION STARTED

## 1. 目标

Wave B 已建立视觉资产与组件 primitive，Wave C 已补齐 Focus / Increased Contrast / Differentiate Without Color / active appearance 与语义回归。Wave D 第一优先级转为 **资产目录契约化**：避免后续执行环境、人工重构或 Asset Catalog 调整让 Swift typed registry 与 `Assets.xcassets` 悄悄漂移。

## 2. 需要守护的契约

### 世界观 SVG

对所有 `WOMIconAsset` / `WOMNavigationIconAsset` 语义验证：

- 对应 `<rawValue>.imageset` 必须存在；
- `Contents.json` 必须可解析；
- 必须声明 template rendering intent；
- 必须保留 vector representation；
- 对应 SVG 必须存在；
- `wom.icon.*` 命名不得出现 registry 指向不存在资源。

### Texture

对 `WOMTextureAsset` 验证：

- `rawValue` 对应 imageset 必须存在；
- compatibility aliases `foolVeil / gold` 不得产生第二份大型纹理；
- `semanticKey` 继续作为稳定语义层，不与 Asset Catalog 文件名耦合。

### 平台系统图标

`WOMSystemIcon` / `WOMStatusIcon` 继续只记录 SF Symbol 语义，不在 Asset Catalog 复制平台 glyph。

## 3. 测试路线

优先新增 Swift Testing 的仓库级资产契约测试：

- 从 `#filePath` 定位 repository root；
- 读取 `WorldOfMysteries/Assets.xcassets`；
- 对 typed registry 与实际 imageset 进行双向核验；
- JSON 元数据做结构断言；
- 不做像素截图比较，不绑定具体 macOS 渲染器。

如 Swift Package 测试无法稳定访问 repo 文件系统，再退回独立 Python 静态检查脚本；不修改 `.github` / gate profile 作为第一步。

## 4. 后续 Wave D

Batch 18 完成后继续：

1. 键盘导航与 Focus 路径审计；
2. raw `Image(systemName:)` 使用边界审计：世界观语义必须 typed，局部内容 glyph 可保留；
3. placeholder 页面的正式接入条件文档化，视觉完成不能代替功能完成；
4. Component Gallery 增加资产契约/来源说明；
5. 最终 head 统一执行 `MACOS_APP_P0`。

## 5. 提交模型

继续采用长期 PR + 原子 commit：

```text
docs(macos): persist visual asset wave D plan
test(macos): verify asset catalog contracts
docs(macos): define typed icon usage boundaries
feat(macos): harden keyboard focus paths
```

关键方案、测试与实际修改都必须持续推送远端，不依赖聊天状态。
