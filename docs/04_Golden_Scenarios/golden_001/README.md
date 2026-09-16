# Golden Scenario 001 — 《不存在的预约》

> **状态**：可执行回归夹具

## 目的

验证第一条完整纵向链路：

```text
World
→ Character
→ Memory / Knowledge
→ Story
→ PlayerAdvice
→ ActionIntent
→ Resolver
→ StateDelta
→ Validate
→ Commit
→ Director
→ Narrative
→ Episode Finalization
→ Restart Persistence
```

## 固定条件

- 原创主角：伊芙琳·格雷
- Fool Pathway / Sequence 9: Seer（愚者途径 / 序列 9：占卜家）
- 贝克兰德东区 Morris Clinic
- 5 个固定 PlayerAdvice
- 结局类型：partial_truth
- 不产生 Major Canon Divergence

## Schema

- `character.json` → `character.schema.json`
- `knowledge/*.json` → `character_knowledge.schema.json`
- `seed.json` → `story_seed.schema.json`
- `world.json` → `world_snapshot.schema.json`
- `turns/*_advice.json` → `player_advice.schema.json`
- `expected_episode.json` → `episode.schema.json`

`*_expected.json` 是测试期望，不是 Domain persistence object。

## 关键行为

用户的猜测不会自动成为世界事实；Morris 隐瞒信息但不是幕后组织者；Secret 04 保持 hidden；Closure 不创建新重大冲突。

Golden Scenario 是架构回归规格，不是最终文学脚本。
