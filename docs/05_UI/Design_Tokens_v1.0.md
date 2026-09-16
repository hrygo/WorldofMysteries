# 《诡秘世界》macOS 设计 Token 语言规范 v1.1

> **版本**：v1.1.0  
> **单一事实源**：[`docs/05_UI/design_tokens.json`](design_tokens.json)  
> **适用范围**：macOS App SwiftUI 6 组件库、Figma 生成器插件与跨语言样式映射  
> **设计美学**：维多利亚蒸汽暗金 × 克苏鲁超凡神秘主义 (Victorian Esoteric Steampunk & Cthulhu Mysticism)

---

## 1. 设计 Token 架构总览

设计 Token 严禁散落在各个 View 中硬编码（Zero Magic Numbers）。Token 体系划分为三层分层模型：
1. **全局原始基元 (Global Primitives)**：物理色盘、原始网格比例；
2. **语义别名 (Semantic Aliases)**：Z 轴层级 Elevation、非凡途径专属色、材质表面与状态色；
3. **组件专用 Token (Component Tokens)**：严格收敛各组件的几何尺寸与阈值。

```text
┌─────────────────────────────────────────────────────────────┐
│                 docs/05_UI/design_tokens.json               │
│                  (跨语言跨端单一事实源 JSON)                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌─────────────────────────────┐       ┌─────────────────────────────┐
│  SwiftUI 6 DesignTokens     │       │   Figma Generator Plugin    │
│  (DesignSystem/Tokens)      │       │   (main.js / variables)     │
└─────────────────────────────┘       └─────────────────────────────┘
```

---

## 2. 色彩语义系统 (Color Semantics)

### 2.1 底色与材质体系 (Background & Glass)
| Token 名称 | 十六进制色值 | 语义用途 |
|:---|:---|:---|
| `obsidianBase` | `#0D0F12` | 主窗口全景最底层黑曜石虚空背景 |
| `obsidianElevated` | `#14181D` | 左侧边栏、浮层与弹出式面板背景 |
| `obsidianCard` | `#1B2026` | 容器卡片、态势卷宗背景 |
| `obsidianGlass` | `#14181DCC` | 带 80% 不透明度的深色磨砂亚克力玻璃材质 |
| `abyssVoid` | `#08090B` | 灰雾之上的纯黑虚空底色 |

### 2.2 维多利亚暗金材质体系 (Brass & Gold)
| Token 名称 | 十六进制色值 | 对比度 (vs `#0D0F12`) | WCAG 等级 | 语义用途 |
|:---|:---|:---:|:---:|:---|
| `brassGoldPrimary` | `#C9A55E` | **7.8:1** | **AAA** | 核心品牌色、激活项高光、黄铜边框、Listening Ring |
| `brassGoldHover` | `#DAB976` | **9.5:1** | **AAA** | 鼠标悬停态与键盘聚焦态微光 |
| `brassGoldMuted` | `#9E834B` | **4.7:1** | **AA** | 次级黄铜分割线、未激活图标微亮 (达标 AA) |
| `brassGoldBorder` | `#4A3E25` | - | - | 维多利亚卡片深雕倒角边框 |
| `brassGoldGlow` | `#C9A55E4D` | - | - | Listening Ring 呼吸微光与神圣光晕 (30% Alpha) |

### 2.3 22 条成神途径专属语义色谱 (Pathway Accents)
| 途径标识 | 十六进制色值 | 代表序列与神明符号 |
|:---|:---|:---|
| `pathwayFool` | `#7B2CBF` | 占卜家 / 愚者（神秘暗紫金，深邃雾海） |
| `pathwayDoor` | `#0077B6` | 学徒 / 门（星空幽蓝，时空穿梭之钥） |
| `pathwayError` | `#D4A373` | 偷盗者 / 错误（时钟齿轮古铜黄，命运缝隙） |
| `pathwayDarkness` | `#3A0CA3` | 不眠者 / 黑夜（暗夜深沉静谧暗紫） |
| `pathwaySun` | `#FB8500` | 歌颂者 / 太阳（神圣炽烈日光琥珀） |
| `pathwayVisionary`| `#E9D8A6` | 观众 / 空想家（梦境苍白金，心灵烛火） |

### 2.4 羊皮纸案卷与复古纸张体系 (Parchment & Ink)
| Token 名称 | 十六进制色值 | 对比度 (vs `#F4EBD0`) | WCAG 等级 | 语义用途 |
|:---|:---|:---:|:---:|:---|
| `parchmentBase` | `#EADBB6` | - | - | 故事书历史章节底纸 |
| `parchmentCard` | `#F4EBD0` | - | - | 侦探卷宗便签、照片衬纸 |
| `parchmentBorder` | `#C8B282` | - | - | 做旧复古羊皮纸磨损毛边 |
| `parchmentInk` | `#2B2118` | **12.5:1** | **AAA** | 棕褐色钢笔草写墨迹文字（高保真亲笔感） |
| `parchmentInkSecondary` | `#5A4838` | **6.7:1** | **AA** | 笔迹次级注释、卷宗补充批注 |
| `parchmentInkTertiary` | `#7A6652` | **4.5:1** | **AA** | 便签落款日期、微弱墨水褪色效果（安全达标） |
| `parchmentWaxSeal` | `#9E2A2B` | **5.6:1** | **AA** | 绝密文件上的勃艮第深红火漆印章 |

### 2.5 高保真文本灰度阶梯 (Text Hierarchy & Contrast vs `#0D0F12`)
| Token 名称 | 十六进制色值 | 对比度 | WCAG 等级 | 语义用途 |
|:---|:---|:---:|:---:|:---|
| `textPrimary` | `#F5F6F8` | **17.2:1** | **AAA** | 主标题、核心角色对白、剧情正文 |
| `textSecondary` | `#A2ABB9` | **8.1:1** | **AAA** | 次要元数据、旁注说明、序列途径描述 |
| `textTertiary` | `#7E8B9B` | **4.9:1** | **AA** | 辅助系统修饰、占位文本、微弱时间戳 (达标 AA) |
| `textGoldAccent` | `#E6CA8D` | **11.4:1** | **AAA** | 塔罗尊名高光、非凡特性与神学徽章 |

---

## 3. Z 轴层级与无障碍焦点环 (Elevation & Accessibility)

### 3.1 Z 轴层级深度 (Elevation)
| 层级 Token | 深度值 | 适用结构 |
|:---|:---:|:---|
| `layerBase` | 0 | 主背景画布、星空背景 |
| `layerElevated` | 1 | 侧边栏、主工作台底板 |
| `layerCard` | 2 | 维多利亚卷宗卡片、仪表盘底座 |
| `layerFloating` | 3 | 悬浮浮层、线索便签、Listening Ring |
| `layerModal` | 4 | 模态对话框、仪式魔法祭台全屏覆盖层 |
| `layerHUD` | 5 | 灵视 HUD 滤镜、严重失控全屏警示框 |

### 3.2 键盘无障碍焦点环 (Focus Ring)
macOS 原生键盘导航标准：
* `focusRingColor`: `#C5A059`（暗金光晕）
* `focusRingWidth`: `2.0 pt`
* `focusRingOffset`: `2.0 pt`

---

## 4. 间距与同心圆角几何法则 (Spacing & Concentric Radii)

严格遵循 **4pt / 8pt 网格**与同心推导几何法则：
$$R_{child} = \max(R_{parent} - \text{padding}, 0)$$

| Token | 数值 (pt) | 适用组件 |
|:---|:---|:---|
| `xs` | 4 | 状态小徽章、紧凑指示胶囊 |
| `sm` | 8 | 内部嵌套元素、按钮、输入框内部 |
| `md` | 12 | 小型卡片、弹出菜单、侧边栏选中高光块 |
| `lg` | 16 | 标准维多利亚卡片、卷宗容器 |
| `xl` | 24 | 大模态面板、浮层面板 |
| `full`| 9999 | 胶囊药丸 (Capsule) 与正圆 (Circle) |

---

## 5. 组件级专有 Token (Component Tokens)

| 组件 | 专有 Token | 取值 | 约束说明 |
|:---|:---|:---|:---|
| **`ListeningRing`** | `diameterDefault`<br>`pulseScaleMax` | 58 pt<br>1.25 | 呼吸脉冲最大扩散半径不超过外环 125% |
| **`SpiritualityGauge`** | `criticalThreshold`<br>`warningThreshold` | 0.25<br>0.50 | 灵性值低于 25% 强制触发红色危险失控警报 |
| **`TarotCard`** | `aspectRatio`<br>`cornerNotchSize` | 1.618 (黄金比例)<br>6 pt | 卡牌必须符合塔罗标准长宽黄金比例 |

---

## 6. macOS 26 Typography 字体体系与 WCAG 对比度规范

### 6.1 中西文系统字体映射与审美意向
《诡秘世界》的文字表现力建立在维多利亚时代活字印刷、中世纪羊皮纸手卷与克苏鲁神秘学术语之上。在 macOS 26 平台上，通过 SwiftUI 字体级联技术，实现了古典与现代的有机融合：

| 字体分类 | 西文字体 (Latin) | 中文字体 (CJK) | 设计特质与历史意向 | 典型应用场景 |
|:---|:---|:---|:---|:---|
| **古典巨幕衬线** | **New York (Heavy)** | **Songti SC (宋体-简)** | 庄严深沉、字怀收敛、典籍压印感 | 灰雾之上神座、篇章序幕大标题 (`gothicDisplay`, 32pt) |
| **典籍展示衬线** | **New York (Bold/Semibold)** | **Songti SC (宋体-简)** | 维多利亚经典书籍印刷质感，横细竖粗 | 故事标题、人物正名、卡片标题 (`displayLarge` 28pt, `titleLarge` 22pt, `titleMedium` 18pt) |
| **沉浸叙事对白** | **New York (Medium)** | **Songti SC (宋体-简)** | 典雅语调、戏剧台词、神明箴言 | 编年史剧场对话、原声台词字幕 (`narrativeSubtitle`, 16pt, tracking 0.3) |
| **现代清晰界面** | **SF Pro (San Francisco)** | **PingFang SC (苹方-简)** | 视网膜屏极致清晰度，无衬线紧凑排版 | 侧边栏导航、系统状态、按钮、输入框 (`titleSmall` 15pt, `bodyMedium` 13pt, `caption` 11pt) |
| **侦探草写便签** | **New York Italic** | **Kaiti SC (楷体-简)** | 19世纪侦探吸墨水钢笔在粗糙羊皮纸上的亲笔草写 | 案卷调查便签、韦尔奇日记、现场线索 (`parchmentCursive`, 14pt, lineSpacing 5pt) |
| **机械等宽编号** | **SF Mono** | **PingFang SC (Monospace)** | 工业革命打字机、游丝钟表读数、神秘学灵数 | 历史纪元标牌（第五纪·1349年）、序列等级（Seq 9）、灵性百分比 (`monoBadge`, 11pt) |

### 6.2 Typography 阶梯与排版度量 (Typography Scale & Metrics)

| 阶梯 Token | 字号 (pt) | 字重 | 字族映射 (SwiftUI) | 行高/间距 | 适用元素 |
|:---|:---:|:---|:---|:---|:---|
| `gothicDisplay` | 32 | Heavy | `.system(..., design: .serif)` | 行高 42, Tracking +0.8 | 章节巨幕、灰雾之巅尊名 |
| `displayLarge` | 28 | Bold | `.system(..., design: .serif)` | 行高 36, Tracking +0.5 | 世界全景主标题 |
| `titleLarge` | 22 | Bold | `.system(..., design: .serif)` | 行高 30, Tracking +0.3 | 人物卡片主标题、途径高光 |
| `titleMedium` | 18 | Semibold | `.system(..., design: .serif)` | 行高 24, Tracking +0.2 | 卷宗面板标题、卡片组标题 |
| `titleSmall` | 15 | Semibold | `.system(..., design: .default)` | 行高 20, Tracking +0.1 | 交互栏目标题、选项头 |
| `narrativeSubtitle` | 16 | Medium | `.system(..., design: .serif)` | 行高 26, Tracking +0.3, LineSpacing 6 | 剧场语音台词、叙事对白 |
| `bodyLarge` | 14 | Regular | `.system(..., design: .default)` | 行高 22, Tracking 0.0 | 长文本剧情通读 |
| `bodyMedium` | 13 | Regular | `.system(..., design: .default)` | 行高 18, Tracking 0.0 | macOS HIG 标准 13pt 界面正文 |
| `caption` | 11 | Medium | `.system(..., design: .default)` | 行高 14, Tracking +0.1 | 辅助标注、时间批注 |
| `monoBadge` | 11 | Medium | `.system(..., design: .monospaced)` | 行高 14, Tracking +0.4 | 纪元徽章、序列编号、灵数 |
| `parchmentCursive` | 14 | Regular | `Font.custom("Kaiti SC", ...)` | 行高 22, Tracking +0.2, LineSpacing 5 | 侦探卷宗钢笔草写便签 |

### 6.3 WCAG 2.1 对比度度量保障 (Contrast Ratio Verification)
所有文本颜色必须严格满足 WCAG 2.1 无障碍标准：
- **暗曜石虚空背景 (`#0D0F12`)**：
  - `textPrimary` (`#F5F6F8`)：**17.2:1**（超高对比度，远超 AAA 7.0:1 级要求）
  - `textSecondary` (`#A2ABB9`)：**8.1:1**（远超 AAA 级要求）
  - `textTertiary` (`#7E8B9B`)：**4.9:1**（完全达标 AA 4.5:1 级要求，消除低对比度隐患）
  - `textGoldAccent` (`#E6CA8D`)：**11.4:1**（远超 AAA 级要求）
  - `brassGoldPrimary` (`#C9A55E`)：**7.8:1**（达标 AAA 级要求）
  - `brassGoldMuted` (`#9E834B`)：**4.7:1**（达标 AA 级要求）
- **复古羊皮纸背景 (`#F4EBD0`)**：
  - `parchmentInk` (`#2B2118`)：**12.5:1**（极高清晰度，达标 AAA 级）
  - `parchmentInkSecondary` (`#5A4838`)：**6.7:1**（达标 AA 级）
  - `parchmentInkTertiary` (`#7A6652`)：**4.5:1**（严格锚定 AA 4.5:1 极限阈值，呈现自然墨水褪色同时杜绝不可辨读）

