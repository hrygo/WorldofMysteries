# 《诡秘世界》macOS 设计 Token 语言规范 v1.0

> **版本**：v1.0.0  
> **单一事实源**：[`docs/05_UI/design_tokens.json`](file:///Users/hrygo/Documents/WorldofMysteries/docs/05_UI/design_tokens.json)  
> **适用范围**：macOS App SwiftUI 6 组件库、Figma 生成器插件与跨语言样式映射  
> **设计美学**：维多利亚蒸汽暗金 × 克苏鲁超凡神秘主义 (Victorian Esoteric Steampunk & Cthulhu Mysticism)

---

## 1. 设计 Token 架构总览

设计 Token 严禁散落在各个 View 中硬编码（Zero Magic Numbers）。所有样式均从 `DesignTokens` 派生，遵循同心圆角推导与语义化分层：

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

### 2.2 维多利亚暗金材质体系 (Brass & Gold)
| Token 名称 | 十六进制色值 | 语义用途 |
|:---|:---|:---|
| `brassGoldPrimary` | `#C5A059` | 核心品牌色、激活项高光、黄铜边框、Listening Ring |
| `brassGoldHover` | `#D4B26F` | 鼠标悬停态与键盘聚焦态微光 |
| `brassGoldMuted` | `#8C733E` | 次级黄铜分割线、未激活图标微亮 |
| `brassGoldBorder` | `#4A3E25` | 维多利亚卡片深雕倒角边框 |
| `brassGoldGlow` | `#C5A0594D` | Listening Ring 呼吸微光与神圣光晕 (30% Alpha) |

### 2.3 超凡灵性与绯红星辰体系 (Spirituality & Crimson)
| Token 名称 | 十六进制色值 | 语义用途 |
|:---|:---|:---|
| `spiritualBlue` | `#4A90E2` | 灵视状态（Spirit Vision）、灵摆回旋涟漪 |
| `spiritualGlow` | `#64B5F666` | 灵性之墙半透明屏障、超凡占卜水波 |
| `crimsonStar` | `#E63946` | 灰雾之上的深红星辰、祈祷共鸣指示 |
| `crimsonThread` | `#B71C1C` | 侦探案卷推演板上的证据红线 |

### 2.4 羊皮纸案卷与复古纸张体系 (Parchment & Ink)
| Token 名称 | 十六进制色值 | 语义用途 |
|:---|:---|:---|
| `parchmentBase` | `#EADBB6` | 故事书历史章节、案卷线索卡背景 |
| `parchmentBorder` | `#C8B282` | 做旧复古羊皮纸磨损毛边 |
| `parchmentInk` | `#2B2118` | 棕褐色钢笔草写墨迹文字 |

---

## 3. 间距与网格系统 (Spacing Grid)

严格遵循 **4pt / 8pt 网格**体系，杜绝奇数间距：

| Token | 数值 (pt) | 适用场景 |
|:---|:---|:---|
| `xxs` | 2 | 极细微偏移、指示灯与文字间隙 |
| `xs` | 4 | 紧凑图标与徽章间隙、标签内边距 |
| `sm` | 8 | 列表项内部元素间距、卡片紧凑内边距 |
| `md` | 12 | 默认栅格步长、侧边栏项目垂直间隙 |
| `lg` | 16 | 标准卡片内边距 (Padding)、段落间距 |
| `xl` | 24 | 大模块间距、三栏工作区主内边距 |
| `xxl` | 32 | 页面区块隔离、模态弹窗外边距 |
| `xxxl` | 48 | 全局窗口边距、沉浸场景留白 |

---

## 4. 同心圆角体系 (Concentric Radii)

圆角必须遵循**同心推导几何法则**：
$$R_{child} = \max(R_{parent} - \text{padding}, 0)$$

| Token | 数值 (pt) | 适用组件 |
|:---|:---|:---|
| `xs` | 4 | 状态小徽章、紧凑指示胶囊 |
| `sm` | 8 | 内部嵌套元素、按钮、输入框内部 |
| `md` | 12 | 小型卡片、弹出菜单、侧边栏选中高光块 |
| `lg` | 16 | 标准维多利亚卡片、卷宗容器 |
| `xl` | 24 | 大模态面板、浮层面板 |
| `full`| 9999 | 胶囊胶囊药丸 (Capsule) 与正圆 (Circle) |

---

## 5. 交互运行态与动效时间规范 (Motion)

组件状态与 `docs/05_UI/Interaction_Runtime_State_v1.0.md` 完全映射：
* **`listeningPulseDuration`**: `2.4s`（Listening Ring 在待命与聆听态下的呼吸循环周期，采用 `easeInOut`）；
* **`voiceWaveformResponse`**: `0.12s`（声纹波动实时响应平滑窗口）；
* **`stateTransitionDuration`**: `0.35s`（视图与交互态切换缓动时间）；
* **`pendulumSwingPeriod`**: `3.2s`（黄水晶灵摆占卜的物理摆动与回旋周期）。
