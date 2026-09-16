# 《诡秘世界》Lore / Canon Engine v1.0

> **状态**：Domain Engine 规范基线  
> **权威持久层**：只读 `canon.db`

> **定位**：世界法典与可执行设定层；不负责创作，不拥有用户个人世界历史。

## 1. 核心职责

Lore Engine 回答：某个设定是否属于 Canon、在什么时间成立、依据是什么、谁允许知道、它能编译成哪些运行约束。

内容分层：

1. `CanonFact`：原著明确成立的事实；
2. `CanonInterpretation`：基于原著的合理解释；
3. `DerivedRule`：从 Canon 编译出的机器约束；
4. `CreativeLore`：产品补充但非 Canon 的稳定内容；
5. `GeneratedWorldFact`：用户个人世界运行后产生的事实。

五类内容必须保留来源和命名空间，禁止混为“设定”。

## 2. 时间敏感 Canon

Canon 必须支持 `valid_from / valid_until`。人物身份、序列、知识、关系、组织状态等均按时间查询。

关键接口：

```text
canonicalSnapshot(character, canonicalTime, canonProfile)
canonicalKnowledge(character, canonicalTime)
capabilities(pathway, sequence, character?)
```

Story 不加载“人物全部资料”，只加载目标时间点的 Canon Snapshot。

## 3. Evidence 与 Source

重要 Canon 必须可追溯：

```text
Source ↔ Evidence ↔ CanonFact
```

Evidence 类型至少：`explicit / strong_inference / weak_inference / contradiction`。

Fact 状态至少：`verified / probable / interpretation / disputed / unknown / deprecated`。

运行时硬约束默认只由 `verified` 或已审核的 `DerivedRule` 产生。

## 4. Entity Registry

所有 Canon 实体使用稳定 ID：

```text
character.*
location.*
organization.*
pathway.*
sequence.*
ability.*
item.*
event.*
```

名称、别名、称号、化名与翻译属于 Alias，不作为实体主键。

## 5. Pathway / Sequence / Ability

能力图谱必须区分：

- introduced
- inherited
- enhanced
- transformed

同时区分：

- Sequence Capability
- Character-specific Capability
- Item Capability
- Blessing / Gift
- Temporary Capability

防止把特定人物、物品或临时状态误认为通用序列能力。

## 6. Executable Lore

Lore 不只服务 RAG。可确认的规则应编译为确定性 Constraint，例如：

```json
{
  "rule": "minimum_sequence",
  "ability": "ability.a",
  "sequence": 7
}
```

供 Capability / Canon / Divergence Validator 消费。

## 7. Knowledge 与 Spoiler

必须分别执行：

```text
Lore Fact
  ↓
User Spoiler Gate
  ↓
Character Knowledge Gate
```

“用户读过”不等于“角色知道”。角色知识只能通过 Canon 状态或运行中的观察、对话、阅读、调查、能力、记忆等渠道获得。

## 8. Canon Profile

不同原作/续作/改编层必须独立。运行时明确选择 `CanonProfile`，避免改编设定污染小说 Canon。

## 9. Content Pack

运行时使用只读内容包：

```text
lotm-canon-pack/
  canon.db
  manifest.json
  indexes/
  assets/
```

`canon.db` 只读，`world.db` 可写。用户世界永不反向修改 Canon。

## 10. Vertical Lore Slice

MVP 不先把全书做成知识图谱。围绕 Golden Scenario 按需建立最小 Lore Slice，验证后再扩展。

---

## 11. Canon 与 Retrieval

`canon.db` 保存 Canon Truth；全文和向量索引属于 `retrieval.db` 的可重建 Projection。

任何语义检索命中都不能直接升级为 Canon Fact。Canon Fact 只来自：

```text
Source
→ Evidence
→ normalized claim
→ verified CanonFact
```

## 12. Canon Pack 版本

每个 Content Pack 固定：

- `pack_id`
- `pack_version`
- `schema_version`
- `source_profile`
- `content_hash`

User World 记录其创建和最后兼容的 Canon Pack 版本。Content Pack 升级不原地修改用户世界历史。
