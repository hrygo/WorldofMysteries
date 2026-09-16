# Content Provenance & Release Gate v1.0

> **状态**：内容资产与分发边界基线  
> **目的**：保证 Canon、Creative Lore、UI、音频和卡牌素材的来源、证据、授权状态和可分发范围可追溯。

## 1. 内容命名空间

```text
canon.*
creative.*
generated.*
user.*
```

不能用 `canon.*` 存储未经验证的解释或产品原创。

## 2. Canon Fact

每条重要 Canon Fact 必须关联：
- source_id；
- locator；
- evidence type；
- authority；
- verification state；
- spoiler marker。

## 3. Content Pack Inclusion

进入可分发 Content Pack 的对象额外具有：

```text
distribution_status
rights_basis
source_category
text_reproduction_policy
asset_license
```

“模型可以读取”与“产品可以重新分发”是两个不同判断。

## 4. 原文

Content Pack 以结构化 Fact / Rule / Snapshot 为运行主体。

原始来源文本：
- 不因检索方便自动进入发布包；
- 长文本引用需独立 Rights Review；
- Source locator 可以保留，不等于携带全文。

## 5. Creative Lore

产品原创内容必须：
- namespace=creative；
- 与 Canon Fact 分离；
- 不声称来自原著；
- 建立稳定 entity id；
- 有内部 author/provenance metadata。

## 6. Generated World Content

用户世界运行生成：
- namespace=generated/user-world；
- 不反向写入 Canon Pack；
- 可在用户 export 中出现；
- Promotion 到 Curated Creative Lore 需要独立内容审核。

## 7. Visual / Audio

每个分发资产至少记录：
- asset_id；
- source；
- creator/tool；
- license/rights status；
- modifications；
- permitted distribution scope。

## 8. Third-party Dependencies

发布包必须生成：
- third-party software list；
- licenses；
- model/provider attribution requirements；
- font/image/audio notices where applicable。

## 9. Release Gate

`GATE-CONTENT = PASS`：

- Canon Pack manifest 完整；
- source/evidence traceable；
- 未审核原始长文本不进入 distribution artifact；
- UI/image/audio provenance 完整；
- third-party license notice 完整；
- public release 内容范围经过相应权利/合规审查。
