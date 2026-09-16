# Canon Content Accuracy Baseline v1.0

> **状态**：内容正确性基线  
> **目的**：保证工程团队消费的 Lore / Canon / Character Snapshot 不把推测、改编、用户世界生成内容或测试夹具误标为原著事实。

## 1. 内容层级

所有内容必须属于且只属于以下一种语义层：

```text
CanonFact
CanonInterpretation
DerivedRule
CreativeLore
GeneratedWorldFact
TestFixture
```

### CanonFact
原著或正式授权设定明确支持的事实。

### CanonInterpretation
基于多个 Canon 证据作出的合理理解。不能作为硬 Canon Validator 的唯一依据。

### DerivedRule
从已验证 CanonFact 编译出的可执行规则，例如能力最低序列、时间有效范围。

### CreativeLore
产品为 Canon 空白区域稳定设计的原创内容。

### GeneratedWorldFact
用户个人世界在运行中产生并 Commit 的事实。

### TestFixture
仅用于 Golden / Eval / Benchmark 的数据，不具有 Canon 含义。

---

## 2. CanonFact 最低字段

进入 `canon.db` 的硬事实至少具有：

```text
fact_id
subject
predicate
object/value
valid_from
valid_until
source_id
source_locator
evidence_type
verification_status
spoiler_marker
```

`verification_status=verified` 才能被 Canon Guard 作为硬约束使用。

---

## 3. Evidence

Evidence 类型：

```text
explicit
strong_inference
weak_inference
contradiction
```

硬 Canon 默认需要 `explicit`，或经内容审核批准的多源 `strong_inference`。

`weak_inference` 不进入 hard Canon validation。

---

## 4. Character Canon Snapshot

原著人物不能使用“一份全时期人物简介”。

必须按时间编译：

```text
Character
+ CanonicalTime
+ CanonProfile
→ CanonicalCharacterSnapshot
```

Snapshot 至少限定：

- identity；
- current sequence；
- available capabilities；
- organization membership；
- current relationships；
- canonical knowledge；
- canonical memories；
- active aliases；
- known locations / public status。

未来知识不能提前注入。

---

## 5. Pathway / Sequence

能力数据必须区分：

```text
sequence capability
character-specific capability
item capability
blessing/gift
temporary capability
```

序列能力还区分：

```text
introduced
inherited
enhanced
transformed
```

不能把“某角色曾经做到”自动归纳为“该序列所有人都能做到”。

---

## 6. Source Profile

不同来源不默认混合：

```text
main_novel
sequel
adaptation_animation
adaptation_game
adaptation_comic
licensed_reference
```

每个 Canon Pack 明确 `CanonProfile` 和 precedence。

改编原创设定不能静默污染小说 Canon Profile。

---

## 7. Golden / Test Content

Golden Scenario 001 是 **TestFixture**：

- 伊芙琳·格雷：原创测试角色；
- Morris / Jonathan：原创测试 NPC；
- 《不存在的预约》：原创测试 Episode；
- Morris Clinic：测试地点；
- occult group：测试叙事元素。

这些对象用于测试 World/Character/Story/Memory/Knowledge 机制，不声称来自《诡秘之主》原著。

Golden 001 使用的 Canon-compatible 能力约束只有：

```text
Fool Pathway
Sequence 9 = Seer / 占卜家
```

Golden 001 不承担完整途径能力说明，测试行动不得依赖未录入且未验证的具体 Canon 能力。

---

## 8. 内容生产管线

```text
Source
  ↓
Candidate Claim
  ↓
Entity Linking
  ↓
Evidence Linking
  ↓
Time / Profile Normalization
  ↓
Content Review
  ↓
Verified CanonFact / CanonRule
  ↓
Content Pack
```

LLM 可以辅助 Candidate Claim 抽取，不能自行把 Claim 升级为 `verified`。

---

## 9. 矛盾处理

发现来源冲突时生成：

```text
CanonConflict
```

冲突未解决期间：

- 不静默覆盖；
- 不让 Story 依赖争议结论作为 Hard Commitment；
- Context Compiler 标注 disputed / uncertain；
- Canon Guard 使用已解决的稳定事实。

---

## 10. 工程门禁

Canon/Lore 数据进入 Release Content Pack 前必须通过：

1. stable ID；
2. source exists；
3. locator valid；
4. evidence linked；
5. timeline normalized；
6. CanonProfile assigned；
7. spoiler marker；
8. verification status；
9. no unresolved duplicate fact；
10. no cross-profile silent merge。

---

## 11. 内容扩展策略

采用 Vertical Lore Slice：

```text
Golden / Feature Scenario
        ↓
Required Canon Scope
        ↓
Build & Verify Lore Slice
        ↓
Run Canon / Knowledge / Character Eval
        ↓
Expand
```

不以“先完整抽取整部小说”为工程启动前提。

---

## 12. 不变量

1. Canon 不由 Story 生成。
2. TestFixture 不等于 Canon。
3. CreativeLore 不等于 Canon。
4. User World 不反向修改 Canon。
5. Interpretation 不伪装成 verified Fact。
6. Character Snapshot 必须时间敏感。
7. Ability 必须保留来源与能力类型。
8. 每个硬 Canon 约束可追溯 Evidence。
