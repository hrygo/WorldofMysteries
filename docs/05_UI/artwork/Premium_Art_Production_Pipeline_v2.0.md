# Premium Art Production Pipeline v2.0

> 状态：**LOCKED FOR PRODUCTION**  
> 适用范围：PR #39 及后续 World / Scene / Artifact premium artwork。  
> 本文定义“如何生产合格图片”；PR 粒度、原子提交和里程碑 CI 节奏继续由 `Premium_Art_Delivery_Workflow_v1.0.md` 管理。  
> 目标：把生成模型的不确定性限制在“构图与视觉语义”，把最终交付转化为可 QA、可复算、可版本化的生产流水线。

---

## 1. 核心原则

正式生产统一遵循以下原则：

1. **生成不追求最终像素，追求正确的世界、构图和气质。**
2. **编辑不重新设计世界，只修正局部错误和画布比例。**
3. **超分不重新解释构图，只恢复/增强细节。**
4. **Production Master 不直接进入运行时。**
5. **Runtime derivative 必须来自同一个 Master，不允许再次独立生成。**
6. **任何图片未通过 Image Contract 与 QA Gates，不得进入 Git。**
7. **不允许用 UI primitive、说明文档或低质占位图代替 shipping artwork。**
8. **《诡秘之主》视觉气质必须存在，但不能退化成通用高奇幻、游戏海报或魔法奇观。**

标准生产链：

```text
Canon / Visual Contract
        ↓
Composition Generation
        ↓
Semantic QA
        ↓
Composition / Outpaint
        ↓
Local Inpaint / Structural Repair
        ↓
Super Resolution
        ↓
Material / Detail Restoration
        ↓
Color Grade
        ↓
Production Master
        ↓
Deterministic Derivatives
        ↓
Runtime / Crop / Contrast QA
        ↓
Provenance
        ↓
Asset Catalog
```

---

## 2. 系列视觉哲学：神秘现实主义，而不是高奇幻

《诡秘世界》的 premium art 统一采用三层视觉结构。

### 2.1 Physical Reality — 现实物质层

用于建立可信世界：

- 晚维多利亚 / 早期工业时代视觉基础；
- 湿石、煤烟砖、黑铁、氧化黄铜、旧木、玻璃、纸张、皮革；
- 煤气灯、暖窗光、阴天蓝灰环境光；
- 城市、教堂、钟楼、烟囱、桥梁、河岸工业设施、档案室、仪式空间等具体环境；
- 人物仅承担尺度和生活感，不默认成为海报主角。

### 2.2 Occult Pressure — 神秘学内压

用于建立《诡秘之主》气质：

- 教会、秘密结社、占卜、仪式、封印物、古老知识的存在感；
- 被观察、被窥见、命运被轻微拨动的感觉；
- 神秘学痕迹以“渗透”方式出现，而不是贴满符文；
- 世界表面有秩序，但秩序下面存在更深层的超凡结构。

### 2.3 Controlled Anomaly — 受控异常

异常必须局部、稀缺、可描述：

- 无来源的冷银蓝反射；
- 与风向轻微相反的局部薄雾；
- 不符合普通透视的远景深度；
- 一处不合逻辑的窗口/倒影关系；
- 极轻微的因果线、星点、空间断层。

禁止把异常做成：

- 巨型魔法阵；
- 满天符文；
- 紫色能量瀑布；
- 巨大月亮/星门；
- 浮空城堡；
- tentacle wallpaper；
- MMORPG / mobile game key art。

### 2.4 建议比例

W1 / 普通世界主视觉：

```text
现实物质世界       65–70%
神秘学气场         20–25%
显性异常            5–10%
```

W2 / 灰雾高位空间：

```text
现实材质锚点       ~20%
灰雾 / 高位空间    ~55%
神秘秩序 / 异常    ~25%
```

比例是艺术指导尺度，不是像素统计硬规则。

---

## 3. Image Contract：先定义验收，再生成

每个 artwork 在生成前必须拥有可读、可复算的 Image Contract。

示例：W1

```yaml
id: W1_WORLD_HERO

semantic:
  primary: late_victorian_industrial_city
  atmosphere: occult_mystery_realism
  anomaly_level: subtle

composition:
  aspect_ratio: 16:10
  quiet_zone:
    x: [0.00, 0.35]
  focal_zone:
    x: [0.55, 0.78]
    y: [0.28, 0.72]

palette:
  dominant:
    - blue_gray
    - charcoal
    - wet_stone
  secondary:
    - aged_brass
    - muted_amber
    - cold_silver

forbidden:
  typography: true
  fantasy_castle: true
  floating_island: true
  giant_magic_circle: true
  dominant_character: true
  neon_palette: true

master:
  width: 4096
  height: 2560

runtime:
  - 2560x1600
  - 2400x900
```

**Prompt 是生成指令；Image Contract 才是验收标准。**

---

## 4. Prompt 架构：物理描述优先，抽象形容词降权

禁止使用一个长 prompt 同时塞入项目名、W1/W2、Asset Catalog、尺寸、UI、世界观、QA 等全部上下文。

生成 prompt 拆为三层。

### Layer A — Scene Truth

只描述：

- 年代；
- 建筑；
- 材质；
- 天气；
- 光线；
- 透视；
- 空间结构；
- 人物尺度。

例如 W1 的核心是“1890 年代工业都市”，而不是“World of Mysteries hero”。

### Layer B — Lord of Mysteries Atmosphere

把“诡秘”翻译为可执行的视觉现象：

- ordinary life hides churches, secret societies, divination and sealed knowledge;
- restrained sense of being watched;
- occult systems are implied through material and atmosphere rather than overt spell effects;
- reality remains believable while hidden supernatural order is perceptible.

不要依赖：

- epic fantasy；
- magical kingdom；
- dark fantasy poster；
- mysterious game world；
- cosmic spectacle。

### Layer C — Controlled Anomaly

每张普通世界图默认只允许 1–2 个明确异常。

例如：

> 湿石路上的一小段冷银蓝反光没有对应现实光源；附近一缕雾的运动方向与风向略有冲突。

### Negative Prompt 原则

禁止项主要由 QA 拦截，不把几十个 forbidden object 全塞回 prompt。

生成阶段只保留 4 类高危约束：

- no typography;
- no fantasy architecture;
- no dominant hero character;
- no overt magical spectacle.

这样减少“越禁止越把禁用元素带回语义空间”的风险。

---

## 4A. G-CTX — Generation Context Gate

Before any production candidate batch, the image-generation context itself must be validated.

This gate exists because a long-lived project conversation can accumulate strong visual priors from:

- earlier rejected candidates;
- other World / Scene concepts;
- Artifact / card imagery;
- cosmic entities;
- project naming and UI discussions.

When the generator infers from the entire conversation, those priors can override an otherwise correct immediate prompt.

### Clean-context requirements

A production generation context must contain only:

1. the single artwork Image Contract;
2. the isolated generation pack for that artwork;
3. the selected candidate direction;
4. no prior rejected candidate images;
5. no other World / Scene / Artifact generation work;
6. no GitHub / SwiftUI / Asset Catalog engineering discussion;
7. no unrelated cosmic-entity / card-art history.

### Control probe

Before the real 4–6 candidate batch, run one inexpensive control probe that requests an ordinary historically grounded late-19th-century industrial-city environment **without occult semantics**.

Reject the context if the control result contains two or more of:

- monumental fantasy cathedral / castle;
- readable slogans or invented organization names;
- occult banners / sigils;
- celestial halo / portal / impossible moon;
- floating architecture or fantasy landscape;
- promotional game-key-art composition.

A failed control probe means:

> abort that generation context; do not keep tuning prompt wording inside it.

### Context lifecycle

Use separate generation contexts for:

- W1;
- W2;
- each Artifact production batch.

Do not use W1 failures as references for W2, and do not keep dozens of rejected visual priors inside one image-generation thread.

Production gate order is therefore:

```text
G-CTX Generation Context
        ↓
G0 Semantic
        ↓
G1 Canon / Atmosphere
        ↓
G2 Composition
        ↓
G3 Structure
        ↓
G4 Production
        ↓
G5 Runtime
```

## 5. 候选生成：批量探索，不做单发押宝

每一个 Visual Contract 的 Composition Stage 默认生成 **4–6 个候选**。

```text
Visual Contract
      │
      ├── Candidate A
      ├── Candidate B
      ├── Candidate C
      ├── Candidate D
      └── Candidate E/F
               │
               ▼
         Blind Semantic QA
               │
         Select 1–2 only
```

### Blind Semantic QA

评审时先隐藏：

- W1/W2 名称；
- 项目名；
- prompt；
- 设计意图。

只看图回答：

1. 这是什么地方？
2. 第一视觉语义是什么？
3. 是否首先读成 generic fantasy？
4. 是否有海报/游戏 key art 感？
5. 是否存在烘焙文字？
6. 主焦点位于哪里？
7. 是否能感到“现实下面存在隐秘超凡秩序”？

W1 第一语义应接近：

> 阴雨、煤烟和煤气灯中的晚维多利亚工业都市。

第二语义才应出现：

> 城市似乎隐藏着秘密宗教、仪式或不可见力量。

若第一语义直接成为：

- fantasy kingdom；
- magical ruins；
- floating islands；
- mystical castle；

则直接淘汰，**不进入修图阶段**。

---

## 6. 重新生成、Outpaint、Inpaint 的决策规则

| 问题 | 操作 |
|---|---|
| 世界类型错误 | 重新生成 |
| 高奇幻 / 工业现实方向错误 | 重新生成 |
| 主构图完全错误 | 优先重新生成 |
| Quiet Zone 不足 | Outpaint / recomposition |
| 比例错误但语义正确 | Crop / Outpaint |
| 局部建筑透视错误 | Local Inpaint |
| 窗户、烟囱、铁栏杆重复/畸变 | Local Inpaint |
| 小人物、马车结构错误 | Local Inpaint / 删除 |
| 伪文字 / AI gibberish | 局部清除 |
| 仅像素不足 | Super Resolution |
| 材质偏软 | Detail Restoration |
| 色调不统一 | Color Grade |

规则：

> **Inpaint 用于修局部错误，不能拯救错误的美术方向。**

---

## 7. 画布比例：先修构图，再超分

模型原生最大像素受限是可接受条件。

例如源图：

```text
1536 × 1024  (3:2)
```

目标 Master：

```text
4096 × 2560  (16:10)
```

禁止：

```text
1536×1024 → resize → 4096×2560
```

正确流程：

```text
Native Source
    ↓
Semantic QA
    ↓
Crop / Outpaint → 16:10
    ↓
Composition QA
    ↓
Local Repair
    ↓
Super Resolution
```

W1 需要扩画时优先扩充：

- 左侧 quiet zone；
- 非关键边缘区域；

避免重新生成或移动右侧主焦点。

---

## 8. 超分架构：SR ≠ Resize ≠ Generative Reconstruction

三类操作必须分开。

### 8.1 Deterministic Resize

用途：

- 最终精确尺寸；
- derivative；
- downsample。

推荐：

- Lanczos；
- libvips；
- ImageMagick；
- Python/Pillow 在验证用途下使用。

### 8.2 Conservative Super Resolution

用途：

- 恢复砖石、铁艺、湿石、木材、玻璃、烟雾的高频细节；
- 不改变已批准构图和物体身份。

优先考虑：

- Topaz Gigapixel Art & CGI；
- High Fidelity 系列；
- Real-ESRGAN；
- SwinIR。

### 8.3 Generative Detail Reconstruction

只在源图信息严重不足时使用：

- 极软细节；
- 无法辨认的局部结构；
- 必须重建的表面信息。

使用后必须重新进入 Structural QA。

禁止多轮无限 generative upscale：

```text
AI upscale → AI upscale → AI upscale → ...
```

生产默认上限：

```text
source
  ↓
必要时 1 次 generative repair
  ↓
1 次 primary SR
  ↓
deterministic resize / downsample
```

---

## 9. Oversample → Downsample

World / Scene 最终 Master：

```text
4096 × 2560
```

推荐中间工作尺寸：

```text
≈ 6144 × 3840
```

即：

```text
16:10 repaired source
       ↓
2× / 4× SR
       ↓
≈6K working image
       ↓
material cleanup
       ↓
Lanczos downsample
       ↓
4096×2560 Production Master
```

目的：

- 压制过锐化；
- 减少 AI 微纹理毛刺；
- 改善栏杆/屋顶/砖纹 aliasing；
- 统一局部细节密度。

---

## 10. Master / Runtime 分离

### World / Scene

```text
4096×2560 Production Master
        │
        ├── 2560×1600 Runtime
        │     wom.art.world.*
        │
        └── 2400×900 Wide
              wom.art.world.*.wide
```

Master：

- 不进入 runtime selector；
- 不由 SwiftUI 加载；
- 用于 future derivative、provenance、重制。

Runtime derivative：

- 由 Master 确定性生成；
- 才进入 `Assets.xcassets`。

### Artifact

```text
4096×4096 Artifact Master
        │
        ├── 1024×1024 detail
        └── 512×512 thumbnail
```

同一件 Artifact 的 thumbnail 和 detail 必须来自同一个 Master。

禁止分别重新生成两个版本。

---

## 11. Semantic Crop Contract

Wide derivative 禁止使用无脑 `centerCrop()`。

每个 artwork 都应有 Crop Contract，例如：

```json
{
  "focus": {
    "x": 0.67,
    "y": 0.50
  },
  "quiet_zone": {
    "x0": 0.00,
    "x1": 0.35
  },
  "protected_region": {
    "x0": 0.54,
    "x1": 0.80,
    "y0": 0.27,
    "y1": 0.74
  }
}
```

Wide crop 必须确保：

- quiet zone 仍存在；
- 主焦点不被切除；
- 关键 anomaly 仍存在；
- skyline / 空间身份仍可辨认；
- 无唯一语义主体位于危险边缘。

---

## 12. Color Management

推荐分层：

### Production Master

优先：

- 16-bit/channel；
- Display P3 或明确记录的工作色域；
- PNG / TIFF；
- 保留 ICC profile。

### Runtime v1

默认：

- 8-bit PNG；
- sRGB；
- 明确尺寸；
- 便于跨设备、截图测试和 CI 重现。

P3 runtime variant 作为后续优化，不在 A1 阶段增加不必要复杂度。

---

## 13. 六层 QA Gate

任何 shipping artwork 必须按顺序通过。

### G0 — Semantic Gate

验证第一视觉语义。

W1：

- 必须首先读成工业时代现实城市；
- 其次才读出隐秘神秘学；
- 不得首先读成 fantasy kingdom / RPG key art。

### G1 — Canon / Atmosphere Gate

建议人工 5 分制：

- 时代可信度 ≥ 4/5；
- 《诡秘之主》神秘学气质 ≥ 4/5；
- generic fantasy ≤ 1/5；
- 世界观明确矛盾 = 0。

### G2 — Composition Gate

检查：

- quiet zone；
- focal centroid；
- edge density；
- bright-spot distribution；
- protected region；
- crop survival。

可自动化指标示例：

```text
edgeDensity(leftQuietZone)
<
edgeDensity(focusZone) × threshold
```

用于辅助判断，不替代人工艺术判断。

### G3 — Structural Gate

100% / 200% 检查：

- 建筑透视；
- 窗户；
- 烟囱；
- 栏杆；
- 灯柱；
- 马车；
- 小人物；
- 重复纹理；
- AI gibberish；
- 伪文字；
- 不合理融合。

### G4 — Production Gate

机器验证：

- pixel dimensions；
- aspect ratio；
- ICC profile；
- alpha；
- file format；
- asset name；
- sha256；
- imageset manifest；
- registry mapping。

### G5 — Runtime Gate

真实 macOS UI 检查：

- 2560×1600；
- 2400×900；
- 1180×760；
- 960×640；
- Increased Contrast；
- Reduce Transparency（如适用）；
- title/body copy 对比度；
- SwiftUI scrim 与 quiet zone 配合。

### 固定观察比例

人工最终检查必须至少看：

- 25%：整体构图、色块、氛围；
- 100%：真实运行时质量；
- 200%：AI artifact 和结构错误。

---

## 14. 工具栈与职责边界

### Composition Generation

职责：

- 世界语义；
- 环境；
- 构图；
- 光线；
- 神秘学气质。

**不负责最终像素。**

### Outpaint / Inpaint

推荐：

- Photoshop Generative Expand / Fill；
- 高质量编辑模型；
- ComfyUI inpaint pipeline。

职责：

- 画布比例；
- quiet zone；
- 局部结构修正；
- 删除乱码。

### Super Resolution

人工精品优先：

- Topaz Gigapixel Art & CGI；
- High Fidelity 类模型。

批处理 / 开源 fallback：

- ComfyUI；
- Real-ESRGAN；
- SwinIR。

### Deterministic Processing

推荐：

- libvips；
- ImageMagick；
- Python tooling。

职责：

- exact resize；
- semantic crop；
- ICC / metadata 检查；
- SHA256；
- manifest；
- QA automation。

### 依赖约束

不把存在用途/许可限制的模型作为 shipping pipeline 的默认硬依赖。

例如 SUPIR 可作为研究参考，但在商业许可边界明确前，不进入正式默认链路。

---

## 15. Provenance

每张最终 artwork 应产生独立 provenance record：

```json
{
  "artwork_id": "W1_WORLD_HERO",
  "generator": "<generator>",
  "generation_id": "<id>",
  "source_sha256": "<sha256>",
  "visual_contract_revision": 2,
  "postprocess": [
    "outpaint",
    "local_inpaint",
    "primary_super_resolution",
    "color_grade",
    "lanczos_downsample"
  ],
  "master": {
    "size": "4096x2560",
    "color_profile": "<profile>"
  },
  "derivatives": [
    "2560x1600",
    "2400x900"
  ],
  "qa": {
    "semantic": "passed",
    "canon": "passed",
    "composition": "passed",
    "structure": "passed",
    "production": "passed",
    "runtime": "passed"
  }
}
```

当前阶段最低要求：

- JSON provenance；
- source/master/derivative SHA256；
- generation method；
- postprocess history；
- QA verdict。

C2PA / Content Credentials 可作为后续增强，不阻塞 A1–A3。

---

## 16. 仓库资产分层

推荐逻辑结构：

```text
workbench/                      # 本机资产，留在项目目录内、由 .gitignore 排除
  ├── world-scenes/             # W1-W6 的 crop / SR / grade / 4096x2560 master
  ├── artifacts/                # A01-A15 的同构产物
  └── local_store_manifest.json # 路径 + SHA256 索引（可随仓库分发）

master/
  └── production masters
      （即上述 workbench 内的 4K/6K 母版；已定案：不使用 Git LFS）

provenance/
  ├── W1.json
  └── W2.json

qa/
  ├── W1.json
  └── W2.json

macos-app/WorldOfMysteries/Assets.xcassets/
  ├── wom.art.world.hero.imageset
  ├── wom.art.world.hero.wide.imageset
  ├── wom.art.world.gray-fog.imageset
  ├── wom.art.world.gray-fog.wide.imageset
  └── ...
```

原则：

- workbench candidate 不入 Git，但必须留在项目目录内（不得只放在 /tmp 或仓库之外）；
- 6K 中间文件不进 Asset Catalog；
- Asset Catalog 只存运行时 derivative；
- Master 不被 Swift selector 加载；
- 策略细则、校验方式与「可校验但不可重建」的边界声明见
  [`Asset_Storage_Policy_v1.0.md`](Asset_Storage_Policy_v1.0.md)。

---

## 17. W1 正式生产流程

W1 的生产顺序锁定为：

1. 冻结 W1 Image Contract；
2. 生成 4–6 个 composition candidates；
3. Blind Semantic QA；
4. 只保留 1–2 个方向；
5. 16:10 recomposition / outpaint；
6. Composition Gate；
7. 局部 structural repair；
8. Structural Gate；
9. primary SR 到约 6K working image；
10. material/detail restoration；
11. color grade；
12. downsample 得到 4096×2560 Master；
13. 生成 2560×1600 runtime；
14. 依据 Crop Contract 生成 2400×900 wide；
15. G0–G5 全量 QA；
16. provenance + SHA256；
17. 加入 Asset Catalog；
18. 原子提交：

```text
art(world): add W1 world hero artwork
```

**W1 没完成前，不进入 W2 的正式生产。**

---

## 18. W2 与后续 World / Scene

W2 只有在 W1 shipping 后开始。

W2 不得成为“W1 加更多雾”。

它需要独立的：

- high-order spatial logic；
- impossible depth；
- gray fog layering；
- weathered stone / dark metal / aged brass anchors；
- restrained causal hints；
- 左侧 quiet zone；
- 与 W1 明确可区分的空间语义。

完成顺序：

```text
W1
↓
W2
↓
W3–W6
↓
World 6/6 milestone CI
```

---

## 19. Artifact 正式生产流程

每件 Artifact：

```text
Image Contract
↓
4–6 square candidates
↓
Semantic / Canon QA
↓
local repair
↓
SR
↓
4096×4096 Master
↓
1024×1024 detail
↓
512×512 thumbnail
↓
QA / provenance
↓
Asset Catalog
```

优先里程碑：

```text
Artifact P0 7/7
↓
milestone CI
↓
Artifact 15/15
↓
final milestone CI
```

Artifact artwork 不能改变现有 `ArtifactID`、gameplay truth、RealityKit 交互主语义。

---

## 20. Git / PR 纪律

### 禁止提交

- 被 QA 拒绝的候选图；
- prompt 试验图；
- moodboard crop 冒充 shipping asset；
- 纯 resize 得到的伪 4K；
- 带烘焙文字/Logo/UI 的生成图；
- 与 Image Contract 不一致但“看起来不错”的图片。

### 允许提交

只有：

```text
approved master-derived runtime asset
+ provenance
+ QA evidence
+ Asset Catalog metadata
```

图像生产顺序固定：

```text
Generate
→ QA
→ Repair
→ SR
→ QA
→ Derivatives
→ QA
→ Provenance
→ Commit
```

而不是：

```text
Generate
→ Commit
→ 在 App 里看
→ 再返工
```

---

## 21. PR #39 当前执行结论

当前工程轨道已经具备：

- typed World / Artifact artwork registry；
- Artifact art-first fallback；
- runtime pixel contract；
- W1 / W2 runtime consumption points；
- Capsule R2 + Work Receipt。

因此后续优先级严格切换为：

1. **W1 shipping artwork**
2. **W2 shipping artwork**
3. **W3–W6**
4. **Artifact P0**
5. **Artifact 15/15**
6. final provenance / QA / milestone gates

在 W1 真正通过 Image Contract 前，不再增加与 shipping artwork 无直接关系的 UI primitive。

---

## 22. 最终定义

本项目的 premium artwork 不以“生成模型原生是否能输出 4K”作为质量边界。

最终质量由以下乘积决定：

```text
Visual / Canon correctness
× Composition quality
× Controlled repair
× Super-resolution quality
× Deterministic derivative pipeline
× QA discipline
```

生成模型只负责它最擅长且最不可控的一段；后处理、尺寸、裁切、验证和交付全部工程化。

**Production rule：没有通过 Image Contract 和 G0–G5 的图片，不是 shipping artwork。**
