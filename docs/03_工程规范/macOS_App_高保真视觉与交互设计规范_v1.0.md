# 《诡秘世界》macOS App 高保真视觉与交互设计规范 v1.0

> **版本**：v1.0 (Design Baseline)  
> **制定角色**：`AGT-MAC` (macOS App 极客) · `AGT-ARB` (主架构师)  
> **目标系统**：macOS 26+ (Apple Silicon arm64)  
> **核心框架**：SwiftUI (Liquid Glass / Vibrant Material) + Swift 6 严格并发 + @Observable  

---

## 1. 核心设计哲学：古典神秘学手稿与现代原生界面的碰撞

《诡秘世界》macOS 原生客户端的设计理念拒绝千篇一律的通用对话框（Chatbot UI），贯彻三大设计信条：

1. **手稿隐喻高于气泡对话 (Manuscript Over Bubbles)**：
   剧情呈现采用维多利亚暗黑羊皮纸手稿（Dark Victorian Parchment）版式，配合衬线排版，让玩家感知到自己正在翻阅一份正在书写的隐秘侦探卷宗与历史日记。
2. **命运丝线声学微动效 (Threads of Fate Acoustics)**：
   语音交互拒绝生硬的音频柱状图，采用如灵性丝线、星光微粒交织的流体动态波形，呼应原著中占卜家与命运途径的“灵体之线”。
3. **Advice ≠ Command 认知透明化 (Cognitive Transparency)**：
   玩家的输入窗口清晰定义为“Whisper Advice to Character”（向角色低语建议）。输入后动态反馈角色的三重心理倾向（直觉警示、记忆共鸣、行动意图），直观展示角色的自主性。

---

## 2. 三大核心视区与组件架构

### 2.1 主应用沉浸工作台 (Main Narrative Workspace & Chronicle)
- **左侧：实体状态盘 (Entity Codex)**
  - 角色头像与序列标识：如克莱恩·莫雷蒂（序列 9 · 占卜家）；
  - 圆环形理智值仪表盘 (Circular Sanity Gauge)：墨绿色稳定微光（92%），理智下降时过渡为暗红色边缘噪点扰动；
  - 灵性储备指示条 (Spirituality Bar) 与物理锚定物（精密镀银怀表，指针实时对应世界时钟）；
- **中间：沉浸叙事流 (Immersive Narrative Chronicle)**
  - 流式剧情正文渲染，段落伴随微光渐入动效；
  - 命运分支与环境细节以古典分隔线切分；
- **右侧：秘祈与 Advice 网关 (Voice & Advice Gateway)**
  - 实时语音波形监听与录入；
  - 启示建议卡片与动机倾向预览（如 `Cautious 65%`）。

### 2.2 秘祈与语音交互中枢特写 (Occult Voice & Advice Gateway Detail)
- 命运丝线流体波形：根据麦克风输入与 TTS 下发音频流实时计算 FFT 频谱，呈现星光粒子微光涟漪；
- 启示建议输入器 (Advice Input Card)：嵌入神秘符文微光外边框，输入时符文轻微呼吸发光；
- 认知动机评估浮层 (Cognitive Motive Evaluation)：
  - `Intuitive Alertness`：直觉警惕度评估；
  - `Memory Echo`：相关历史记忆/日记残页共鸣提取；
  - `Intended Action`：角色最终裁决的行动意向（如谨慎遵从、表面敷衍、曲解执行）。

### 2.3 灰雾之上·青铜长桌神殿全景 (Above the Gray Fog / Divine Palace)
- 宏观世界线视角与塔罗会界面：
  - 巍峨石柱与翻滚的灰白雾海作为主背景；
  - 斑驳古老的青铜长桌与二十二张高背椅（愚者、正义、倒吊人等星座图腾）；
  - 悬浮半透明玻璃 HUD：
    - `[WORLDLINE NEXUS]`：世界线纪年（1349 稳定态）与灵性共振指数；
    - `[CRIMSON STARS & PRAYER SPARKS]`：来自现实世界的深红星光与祈祷光点列表（如贝克兰德奥黛丽的请求）。

---

## 3. 映射到 Swift 6 / SwiftUI 领域契约

```swift
// 客户端核心可观察状态模型
@Observable
@MainActor
public final class WorldSessionUIState {
    // 1. 角色状态盘
    public var currentCharacter: CharacterDTO?
    public var sanityRatio: Double = 0.92
    public var spiritualityRatio: Double = 0.85
    public var activeAnchorName: String = "镀银怀表"

    // 2. 叙事卷宗流
    public var chronicleParagraphs: [NarrativeChronicleItem] = []

    // 3. 语音与 Advice 状态
    public var isAudioListening: Bool = false
    public var audioWaveformAmplitudes: [Float] = []
    public var pendingAdviceText: String = ""
    public var predictedMotive: MotiveEvaluationDTO?

    // 4. 世界线宏观视图
    public var isAboveGrayFog: Bool = false
    public var activeTarotMembers: [TarotMemberDTO] = []
    public var incomingPrayers: [PrayerSparkDTO] = []
}
```
