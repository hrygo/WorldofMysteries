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
| Token 名称 | 十六进制色值 | 语义用途 |
|:---|:---|:---|
| `brassGoldPrimary` | `#C5A059` | 核心品牌色、激活项高光、黄铜边框、Listening Ring |
| `brassGoldHover` | `#D4B26F` | 鼠标悬停态与键盘聚焦态微光 |
| `brassGoldMuted` | `#8C733E` | 次级黄铜分割线、未激活图标微亮 |
| `brassGoldBorder` | `#4A3E25` | 维多利亚卡片深雕倒角边框 |
| `brassGoldGlow` | `#C5A0594D` | Listening Ring 呼吸微光与神圣光晕 (30% Alpha) |

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
| Token 名称 | 十六进制色值 | 语义用途 |
|:---|:---|:---|
| `parchmentBase` | `#EADBB6` | 故事书历史章节、案卷线索卡背景 |
| `parchmentBorder` | `#C8B282` | 做旧复古羊皮纸磨损毛边 |
| `parchmentInk` | `#2B2118` | 棕褐色钢笔草写墨迹文字 |
| `parchmentWaxSeal` | `#9E2A2B` | 绝密文件上的勃艮第深红火漆印章 |

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
