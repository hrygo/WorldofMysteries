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

概念参考：`assets/01_概念参考/01_世界首页_概念参考.png`

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

概念参考：`assets/01_概念参考/02_人物档案_概念参考.png`

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
概念参考：`assets/01_概念参考/03_命运干预_概念参考.png`

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
概念参考：`assets/01_概念参考/04_故事沉浸_概念参考.png`

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

概念参考：`assets/01_概念参考/07_故事书_概念参考.png`

## 7. Card Collection

卡牌是世界认知与遭遇记录，不是抽卡系统。

### Card Detail
概念参考：`assets/01_概念参考/05_卡牌详情_概念参考.png`

### Card Hall / Collection
概念参考：`assets/01_概念参考/06_卡牌馆_概念参考.png`

卡牌状态由发现程度变化：

```text
Unknown
→ silhouette / fragment
→ identified
→ partially revealed
→ established biography
```

Character 存在不依赖 Card 是否已完整揭示。

## 8. Notes & Detective Dossier

目的：管理非凡侦探线索、调查证据与灵摆占卜。

包含：
- 案件线索钉板（Pinboard），羊皮纸草图、案件现场照片与暗红丝线拓扑关联；
- 钢笔手写笔记条目与未解线索列表；
- 交互式灵摆占卜浮层（Spirit Pendulum Divination）：天然黄水晶吊坠、纯银细链与灵性回旋涟漪（顺时针肯定 / 逆时针否定）；
- Listening Ring：通过语音提问推演或追加调查日志。

概念参考：`assets/01_概念参考/09_调查笔记_概念参考.png`

## 9. Settings & System HUD

目的：系统偏好设置、本地引擎探针与数据健康度监视。

包含：
- 偏好分段控制：常规 (General)、本地音频 (SpeechRail Audio)、四库数据内核 (Data Kernel)、世界线保护 (Worldline Guard)；
- SpeechRail 本地语音服务：WebSocket 实时连接指示灯、音色模型切换与音频延迟监控；
- SQLite 四库物理隔离监控面板：`canon.db`（正典底座·只读）、`world.db`（现实世界·WAL）、`retrieval.db`（异步投影·100% 幂等重建按钮）、`runtime.db`（易失会话）；
- 灵视模式（Spirit Vision）渲染开关与排版滑块。

概念参考：`assets/01_概念参考/10_系统设置_概念参考.png`

## 10. Transcendental Scenes (高光非凡场景)

### 10.1 Above the Gray Fog (灰雾之上与塔罗聚会)
- 场景：苍茫翻滚的灰白雾海、巍峨黑曜石巨人宫殿、斑驳青铜长桌与 22 张高背椅；
- 主座：浓雾环绕的愚者王座（无瞳之眼象征符号）；
- 席位：塔罗主牌投影虚影（正义、倒吊人、太阳、世界等）；
- 空间：虚空中脉动的深红星辰，触摸以聆听信件与祈祷回响。

概念参考：`assets/01_概念参考/11_灰雾之上_概念参考.png`

### 10.2 Ritual Magic & Altar Divination (仪式魔法与祭台)
- 祭台：三层天鹅绒祭布、幽蓝火焰草药蜡烛、纯银灵性小刀划出的半球形“灵性之墙”屏障；
- 交互：三段式尊名祈祷咒文浮层、黄铜香炉草药青烟、黄铜灵性计量表（Spirituality Gauge）；
- 语音：底部金色 Listening Ring 响应尊名吟诵与启示。

概念参考：`assets/01_概念参考/12_仪式魔法_概念参考.png`

## 11. Voice Interaction

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

## 12. Commit Boundary UX

### PRE_COMMIT
用户打断可以取消未提交的建议处理。

### POST_COMMIT
用户打断只停止表达，不撤销已经发生的世界事实。

UI 不提供“重新生成结果”按钮。允许：
- replay audio；
- regenerate presentation when necessary；
- continue with a new advice。

## 13. Approved Visual References

本基线正式批准十二张全景核心高保真原型参考：

1. `assets/01_概念参考/01_世界首页_概念参考.png` (World Home - 贝克兰德晨雾全景与世界脉动)
2. `assets/01_概念参考/02_人物档案_概念参考.png` (Character Codex - 克莱恩·莫雷蒂卡片与秘偶状态)
3. `assets/01_概念参考/03_命运干预_概念参考.png` (Fate Intervention - 韦尔奇卧室红月案发现场与 Advice)
4. `assets/01_概念参考/04_故事沉浸_概念参考.png` (Story Player - 占卜俱乐部雨景全幅沉浸对话)
5. `assets/01_概念参考/05_卡牌详情_概念参考.png` (Card Detail - 占卜家序列 9 塔罗秘纹与六维属性)
6. `assets/01_概念参考/06_卡牌馆_概念参考.png` (Card Collection - 22 条成神途径神殿与卡槽陈列)
7. `assets/01_概念参考/07_故事书_概念参考.png` (Story Book - 历史章节羊皮卷、干预抉择与原声回放)
8. `assets/01_概念参考/08_世界线_概念参考.png` (Worldline Nexus - 1349 正典主轴与星盘分叉演化网络)
9. `assets/01_概念参考/09_调查笔记_概念参考.png` (Notes - 维多利亚案卷推演板与黄水晶灵摆占卜)
10. `assets/01_概念参考/10_系统设置_概念参考.png` (Settings - SpeechRail 探针与四库隔离状态 HUD)
11. `assets/01_概念参考/11_灰雾之上_概念参考.png` (Above Gray Fog - 青铜长桌、塔罗聚会与深红星辰)
12. `assets/01_概念参考/12_仪式魔法_概念参考.png` (Ritual Magic - 灵性之墙、尊名祈祷与祭台灵性表)

概念参考约束视觉方向，不替代产品交互规格和最终实施稿。

## 14. Runtime State

交互运行态以 `Interaction_Runtime_State_v1.0.md` 为唯一状态映射规范。
