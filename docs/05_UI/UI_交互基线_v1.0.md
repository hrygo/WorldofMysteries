# UI / Interaction Baseline v1.0

> **状态**：交互基线  
> **视觉原则**：世界优先、UI 退后；语音优先、操作可见但不喧闹；重要状态以世界语义表达，不以后台技术术语表达。

## 1. 信息架构

一级体验：

```text
World
Character
Fate
Story Book
Card Collection
Worldline
Notes
Settings
```

Story 属于 World，不作为独立“游戏大厅”。

## 2. World Home

目的：观察正在存在的世界。

必须包含：

- 中央世界场景；
- 当前可观察 World Pulse；
- 与用户当前兴趣有关的事件；
- 克制的角色锚点；
- Voice Listening Ring。

World Home 读取 `WorldObservation`，不读取 Hidden World Truth。

概念参考：`assets/01_世界首页_概念参考.png`

## 3. Character

目的：查看一个“持续存在的人”，而不是 NPC 属性面板。

信息：

- identity；
- current state；
- pathway/sequence（在用户已知范围内）；
- relationship；
- important experiences；
- biography；
- discovered card state；
- voice conversation entry。

概念参考：`assets/02_人物档案_概念参考.png`

## 4. Fate Intervention

Fate 页是从“观察世界”进入“干预一个正在发生的局面”的过渡层。

中心内容：

```text
Current Situation
Known Facts
Uncertainty
Involved Characters
Pressure
Potential Consequences
```

Voice 是主入口：

> 用户给人物建议，而不是向系统下命令。

不得做成：
- Character dossier；
- RPG quest list；
- three-button-only choice UI；
- chat window。

当前视觉实现依据本节设计；
概念参考：`assets/03_命运干预_概念参考.png`

## 5. Story Player

Story Player 是沉浸体验页。

正常状态：
- 场景占据主要画面；
- Narrative / dialogue 使用克制字幕；
- ambient / character voice 驱动体验；
- UI chrome 最小化。

命运节点：
- 可浮现建议方向；
- 用户可直接自由说话；
- Listening Ring 表示世界正在聆听；
- 选择不是强制按钮集合。

必须区分：
- narrative playing；
- character speaking；
- listening；
- thinking/resolving；
- waiting for user。

不得做成：
- Character dashboard；
- Chat transcript；
- Dense RPG HUD。

当前视觉实现依据本节设计；
概念参考：`assets/04_故事沉浸_概念参考.png`

## 6. Story Book

Episode 完成后成为私人历史。

包含：
- title / cover；
- chapter / narrative blocks；
- key interventions；
- revealed knowledge；
- involved characters；
- world changes；
- unresolved threads；
- audio replay。

Story Book 使用实际 committed NarrativeBlock，不在 Episode 结束后重新编造历史。

概念参考：`assets/07_故事书_概念参考.png`

## 7. Card Collection

卡牌是世界认知与遭遇记录，不是抽卡系统。

### Card Detail
概念参考：`assets/05_卡牌详情_概念参考.png`

### Card Hall / Collection
概念参考：`assets/06_卡牌馆_概念参考.png`

卡牌状态由发现程度变化：

```text
Unknown
→ silhouette / fragment
→ identified
→ partially revealed
→ established biography
```

Character 存在不依赖 Card 是否已完整揭示。

## 8. Voice Interaction

三种主模式：

- Observe Voice：询问当前世界；
- Fate Voice：向人物提供 Advice；
- Story Voice：在命运节点自由介入。

内部技术状态不直接显示 `ASR/TTS/LLM loading`。

视觉语义使用：
- listening ring；
- quiet pulse；
- ambient continuity；
- subtle state transition。

## 9. Commit Boundary UX

### PRE_COMMIT
用户打断可以取消未提交的建议处理。

### POST_COMMIT
用户打断只停止表达，不撤销已经发生的世界事实。

UI 不提供“重新生成结果”按钮。允许：
- replay audio；
- regenerate presentation when necessary；
- continue with a new advice。

## 10. Approved Visual References

本基线批准八张核心概念参考：

1. `assets/01_世界首页_概念参考.png` (World Home)
2. `assets/02_人物档案_概念参考.png` (Character)
3. `assets/03_命运干预_概念参考.png` (Fate Intervention)
4. `assets/04_故事沉浸_概念参考.png` (Story Player)
5. `assets/05_卡牌详情_概念参考.png` (Card Detail)
6. `assets/06_卡牌馆_概念参考.png` (Card Collection)
7. `assets/07_故事书_概念参考.png` (Story Book)
8. `assets/08_世界线_概念参考.png` (Worldline Nexus)

概念参考约束视觉方向，不替代产品交互规格和最终实施稿。

## 11. Runtime State

交互运行态以 `Interaction_Runtime_State_v1.0.md` 为唯一状态映射规范。
