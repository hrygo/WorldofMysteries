import SwiftUI

// MARK: - DesignTokens Namespace v1.2

/// 《诡秘世界》跨端同源设计 Token 语言体系 (Single Source of Truth)
/// 对齐 `docs/05_UI/design_tokens.json`（v1.1.0）。
/// v1.2 增补族（`LayoutInsets` / `Interaction` / `ComponentMetrics.CitrineArtwork`）与排版度量扩项
/// 尚未回写该 JSON：`docs/` 属 AGT-ARB 管辖，需扩权或架构评审后同步，避免出现第二份事实源。
///
/// `nonisolated`：本模块启用默认 MainActor 隔离（`SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`），
/// 单纯 `Sendable` 合规不会豁免隔离。令牌是无 actor 亲和状态的编译期常量，
/// 必须可从非隔离上下文（如 `nonisolated` 纯函数、Swift Testing 用例）读取。
public nonisolated enum DesignTokens: Sendable {
    
    // MARK: - Spacing Grid (4pt / 8pt 阶梯)
    public enum Spacing: Sendable {
        public static let xxs: CGFloat = 2
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        public static let xl: CGFloat = 24
        public static let xxl: CGFloat = 32
        public static let xxxl: CGFloat = 48
    }
    
    // MARK: - Radii (同心圆角推导)
    public enum Radii: Sendable {
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        public static let xl: CGFloat = 24
        public static let full: CGFloat = 9999
        
        /// 同心圆角几何推导：R_child = max(R_parent - padding, 0)
        public static func concentric(parent: CGFloat, padding: CGFloat) -> CGFloat {
            max(parent - padding, 0)
        }
    }
    
    // MARK: - Borders
    public enum Borders: Sendable {
        public static let hairline: CGFloat = 0.5
        public static let standard: CGFloat = 1.0
        public static let chamfer: CGFloat = 1.5
        public static let heavy: CGFloat = 2.0
    }
    
    // MARK: - Elevation & Z-Index
    public enum Elevation: Sendable {
        public static let base: Double = 0
        public static let elevated: Double = 1
        public static let card: Double = 2
        public static let floating: Double = 3
        public static let modal: Double = 4
        public static let hud: Double = 5
    }
    
    // MARK: - Accessibility & Focus
    public enum Accessibility: Sendable {
        public static let focusRingWidth: CGFloat = 2.0
        public static let focusRingOffset: CGFloat = 2.0
    }
    
    // MARK: - Component Specific Metrics
    public enum ComponentMetrics: Sendable {
        public enum ListeningRing: Sendable {
            public static let diameterDefault: CGFloat = 58
            public static let diameterCompact: CGFloat = 42
            public static let middleRingDiameter: CGFloat = 46
            public static let innerCircleDiameter: CGFloat = 38
            public static let pulseScaleMax: CGFloat = 1.25
            public static let audioScaleGain: CGFloat = 0.30
            public static let breathingScaleMax: CGFloat = 1.08
            public static let breathingScaleMin: CGFloat = 0.96
            public static let reducedMotionOpacity: Double = 0.62
            public static let breathingOpacityMax: Double = 0.90
            public static let breathingOpacityMin: Double = 0.40
            public static let reducedMotionShadowRadius: CGFloat = 3
            public static let idleShadowRadius: CGFloat = 4
            public static let activeShadowRadius: CGFloat = 8
            public static let fullRotationDegrees: Double = 360
        }
        
        public enum Sidebar: Sendable {
            public static let width: CGFloat = 200
            public static let itemHeight: CGFloat = 36
            public static let iconSize: CGFloat = 14
        }
        
        public enum Gauge: Sendable {
            public static let diameter: CGFloat = 88
            public static let innerDiameter: CGFloat = 74
            public static let arcDiameter: CGFloat = 60
            public static let arcLineWidth: CGFloat = 4
            public static let needleWidth: CGFloat = 2
            public static let needleLength: CGFloat = 26
            public static let hubDiameter: CGFloat = 8
            public static let shadowRadius: CGFloat = 6
            public static let criticalThreshold: Double = 0.25
            public static let warningThreshold: Double = 0.50
            public static let arcStartDegrees: Double = 180
            public static let arcEndDegrees: Double = 360
            public static let needleMinimumDegrees: Double = -90
            public static let needleMaximumDegrees: Double = 90
        }
        
        public enum TarotCard: Sendable {
            public static let width: CGFloat = 140
            public static let aspectRatio: CGFloat = 1.618 // 黄金比例
            public static let emblemDiameter: CGFloat = 64
            public static let cornerNotchSize: CGFloat = 6
            public static let shadowRadius: CGFloat = 8
            public static let establishedShadowOpacity: Double = 0.25
            public static let restingShadowOpacity: Double = 0.05
        }
        
        /// 黄水晶吊坠原画几何（正典「克莱恩执链占卜」原画重构图）
        /// 视窗锚定黄水晶几何中心，摆动枢轴取手指捏链点，保证摇晃时不漂移出画
        public enum CitrineArtwork: Sendable {
            public static let imageWidth: CGFloat = 340
            public static let imageHeight: CGFloat = 676
            
            /// 黄水晶几何中心（原画像素坐标）
            public static let subjectCenterX: CGFloat = 170
            public static let subjectCenterY: CGFloat = 338
            
            /// 手指捏链点（链条垂下之处，即灵摆摆动枢轴）
            public static let chainGripX: CGFloat = 184
            public static let chainGripY: CGFloat = 87
            
            /// 标准视窗宽度（高度按原画比例推导，确保整幅原画无裁切）
            public static let panelWidth: CGFloat = 156
            
            /// 覆盖安全系数：抵消像素取整造成的边缘缝隙
            public static let coverageGuard: CGFloat = 1.01
            
            /// 摆动条带：仅「银链 + 黄水晶」参与摇晃，静态场景保持不动
            public static let swingStripWidth: CGFloat = 72
            public static let swingStripBottomOffset: CGFloat = 112
        }
    }
    
    // MARK: - Motion
    public enum Motion: Sendable {
        public static let listeningPulseDuration: Double = 2.4
        public static let voiceWaveformResponse: Double = 0.12
        public static let stateTransitionDuration: Double = 0.35
        public static let pendulumSwingPeriod: Double = 3.2
        public static let typewriterInterval: Double = 0.04
        public static let pendulumSwingMaxDegrees: Double = 6.0
        public static let pendulumSwingInterval: Double = 0.85
        public static let listeningRippleDuration: Double = 0.8
        public static let listeningDecisionRotationDuration: Double = 3.0
        
        public static var smoothSpring: Animation {
            .spring(response: 0.35, dampingFraction: 0.82)
        }
        
        public static var listeningBreathing: Animation {
            .easeInOut(duration: listeningPulseDuration).repeatForever(autoreverses: true)
        }
    }
    
    // MARK: - Typography Metrics (Line Spacing & Tracking)
    public enum TypographyMetrics: Sendable {
        // Line Spacing (行间距)
        public static let narrativeLineSpacing: CGFloat = 6.0
        public static let parchmentLineSpacing: CGFloat = 5.0
        public static let bodyLineSpacing: CGFloat = 4.0
        public static let titleLineSpacing: CGFloat = 3.0
        public static let compactLineSpacing: CGFloat = 2.0
        
        // Tracking / Letter Spacing (字间距)
        public static let gothicDisplayTracking: CGFloat = 0.6
        public static let displayTracking: CGFloat = 0.5
        public static let titleTracking: CGFloat = 0.25
        public static let monoTracking: CGFloat = 0.4
        public static let captionTracking: CGFloat = 0.2
        public static let bodyTracking: CGFloat = 0.0
    }
    
    // MARK: - Layout Insets & Padding Standard (边距与填充)
    public enum LayoutInsets: Sendable {
        public static let cardPadding: CGFloat = Spacing.lg             // 16pt 标准卡片内边距
        public static let compactCardPadding: CGFloat = Spacing.md      // 12pt 紧凑卡片内边距
        public static let panelPadding: CGFloat = Spacing.xl            // 24pt 模态与大面板内边距
        
        public static let rowPaddingHorizontal: CGFloat = Spacing.md    // 12pt 列表/菜单行横向内边距
        public static let rowPaddingVertical: CGFloat = Spacing.sm      // 8pt 列表/菜单行纵向内边距
        
        public static let badgePaddingHorizontal: CGFloat = 6.0        // 6pt 紧凑状态徽章横向边距
        public static let badgePaddingVertical: CGFloat = 2.0          // 2pt 紧凑状态徽章纵向边距
        
        public static let stackSpacingSm: CGFloat = Spacing.sm          // 8pt 紧凑元素间距
        public static let stackSpacingMd: CGFloat = Spacing.md          // 12pt 中等模块间距
        public static let stackSpacingLg: CGFloat = Spacing.lg          // 16pt 卡片级纵向间距
    }
    
    // MARK: - Interaction & UX Feedback (交互反馈与状态规范)
    public enum Interaction: Sendable {
        // 按下与点击微物理反馈
        public static let pressedScale: CGFloat = 0.98
        public static let pressedOpacity: Double = 0.88
        
        // 悬停态视觉反馈
        public static let hoverBrightness: Double = 0.06
        public static let hoverBackgroundOpacity: Double = 0.08
        public static let hoverBorderOpacity: Double = 0.35
        
        // 选中态高光与阴影
        public static let selectedBorderWidth: CGFloat = 1.5
        public static let selectedShadowRadius: CGFloat = 6.0
        public static let selectedGlowOpacity: Double = 0.30
        
        // 动画过渡曲线
        public static var clickSpring: Animation {
            .spring(response: 0.22, dampingFraction: 0.75)
        }
        public static var hoverAnimation: Animation {
            .easeInOut(duration: 0.18)
        }
        public static var selectionSpring: Animation {
            .spring(response: 0.32, dampingFraction: 0.82)
        }
    }
}

// MARK: - Color Tokens Extension

public extension Color {
    enum Mystic: Sendable {
        // Backgrounds
        public static let obsidianBase = Color(red: 13/255, green: 15/255, blue: 18/255)       // #0D0F12
        public static let obsidianElevated = Color(red: 20/255, green: 24/255, blue: 29/255)   // #14181D
        public static let obsidianCard = Color(red: 27/255, green: 32/255, blue: 38/255)       // #1B2026
        public static let obsidianGlass = Color(red: 20/255, green: 24/255, blue: 29/255).opacity(0.8)
        public static let abyssVoid = Color(red: 8/255, green: 9/255, blue: 11/255)            // #08090B
        public static let shadowBase = Color.black
        
        // Victorian Brass & Gold
        public static let brassGoldPrimary = Color(red: 201/255, green: 165/255, blue: 94/255) // #C9A55E (7.8:1 AAA vs #0D0F12)
        public static let brassGoldHover = Color(red: 218/255, green: 185/255, blue: 118/255) // #DAB976
        public static let brassGoldMuted = Color(red: 178/255, green: 150/255, blue: 90/255)  // #B2965A (5.8:1 AA vs #1B2026 卡片面)
        public static let brassGoldBorder = Color(red: 74/255, green: 62/255, blue: 37/255)   // #4A3E25 仅装饰描边（不承担可辨识边界职责）
        /// 承担「可辨识边界」职责的边框：输入框轮廓、hover/选中态描边等。
        ///
        /// 装饰性发丝线继续使用 `brassGoldBorder`（约 1.6:1，仅作氛围）。
        /// 本令牌对 obsidianCard 达 3.6:1、对 obsidianBase 达 4.2:1，满足 WCAG 1.4.11 的非文本对比度底线；
        /// 使用时不得低于 0.9 不透明度，否则边界会重新跌回不可辨识区间。
        public static let brassGoldBoundary = Color(red: 138/255, green: 114/255, blue: 72/255) // #8A7248
        public static let brassGoldGlow = Color(red: 201/255, green: 165/255, blue: 94/255).opacity(0.3)
        
        // Spirituality & Void
        public static let spiritualBlue = Color(red: 74/255, green: 144/255, blue: 226/255)   // #4A90E2
        public static let spiritualGlow = Color(red: 100/255, green: 181/255, blue: 246/255).opacity(0.4)
        public static let deepVoid = Color(red: 29/255, green: 53/255, blue: 87/255)          // #1D3557
        public static let spiritWall = Color(red: 128/255, green: 216/255, blue: 255/255).opacity(0.25) // #80D8FF
        
        // Crimson Astral & Threads
        public static let crimsonStar = Color(red: 230/255, green: 57/255, blue: 70/255)       // #E63946 装饰语义（光晕、星点）
        public static let crimsonThread = Color(red: 183/255, green: 28/255, blue: 28/255)    // #B71C1C
        public static let crimsonGlow = Color(red: 230/255, green: 57/255, blue: 70/255).opacity(0.4)
        /// 承载文字的徽标底色：白字对其达 5.8:1，满足 10pt 小字的 AA 底线。
        /// `crimsonStar` 作为文字底色仅 4.2:1，因此禁止直接用于计数徽标。
        public static let crimsonBadge = Color(red: 193/255, green: 39/255, blue: 45/255)     // #C1272D (5.8:1 AA with #FFFFFF)
        
        // Parchment & Ink (WCAG Compliant)
        public static let parchmentBase = Color(red: 234/255, green: 219/255, blue: 182/255)   // #EADBB6
        public static let parchmentCard = Color(red: 244/255, green: 235/255, blue: 208/255)   // #F4EBD0
        public static let parchmentBorder = Color(red: 200/255, green: 178/255, blue: 130/255) // #C8B282
        public static let parchmentInk = Color(red: 43/255, green: 33/255, blue: 24/255)       // #2B2118 (12.5:1 AAA vs #F4EBD0)
        public static let parchmentInkSecondary = Color(red: 90/255, green: 72/255, blue: 56/255)   // #5A4838 (6.7:1 AA vs #F4EBD0)
        public static let parchmentInkTertiary = Color(red: 122/255, green: 102/255, blue: 82/255) // #7A6652 (4.5:1 AA vs #F4EBD0)
        public static let parchmentWaxSeal = Color(red: 158/255, green: 42/255, blue: 43/255)  // #9E2A2B
        
        // Text (WCAG Compliant Hierarchy)
        public static let textPrimary = Color(red: 245/255, green: 246/255, blue: 248/255)     // #F5F6F8 (17.2:1 AAA vs #0D0F12)
        public static let textSecondary = Color(red: 162/255, green: 171/255, blue: 185/255)  // #A2ABB9 (8.1:1 AAA vs #0D0F12)
        public static let textTertiary = Color(red: 147/255, green: 161/255, blue: 178/255)   // #93A1B2 (6.2:1 AA vs #1B2026 卡片面，覆盖 10-11pt 元数据)
        public static let textGoldAccent = Color(red: 230/255, green: 202/255, blue: 141/255) // #E6CA8D (11.4:1 AAA vs #0D0F12)
        
        // Status Indicators
        public static let statusOnline = Color(red: 46/255, green: 196/255, blue: 182/255)     // #2EC4B6
        public static let statusWarning = Color(red: 255/255, green: 159/255, blue: 28/255)    // #FF9F1C
        public static let statusDanger = Color(red: 231/255, green: 29/255, blue: 54/255)      // #E71D36
        public static let statusImmutable = Color(red: 72/255, green: 149/255, blue: 239/255)  // #4895EF
        
        // 22 条成神途径专属色彩体系 (Pathway Semantics)
        public enum Pathways: Sendable {
            public static let fool = Color(red: 123/255, green: 44/255, blue: 191/255)       // #7B2CBF (占卜家/愚者)
            public static let door = Color(red: 0/255, green: 119/255, blue: 182/255)        // #0077B6 (学徒/门)
            public static let error = Color(red: 212/255, green: 163/255, blue: 115/255)     // #D4A373 (偷盗者/错误)
            public static let darkness = Color(red: 58/255, green: 12/255, blue: 163/255)    // #3A0CA3 (不眠者/黑夜)
            public static let sun = Color(red: 251/255, green: 133/255, blue: 0/255)         // #FB8500 (歌颂者/太阳)
            public static let visionary = Color(red: 233/255, green: 216/255, blue: 166/255) // #E9D8A6 (观众/空想家)
        }
    }
}

// MARK: - Typography Extension

public extension Font {
    enum Mystic: Sendable {
        /// 维多利亚古典巨幕大标题（32pt 衬线黑体，西文 New York + 中文 Songti SC，灰雾之上神座）
        public static let gothicDisplay = Font.system(size: 32, weight: .heavy, design: .serif)

        /// 典籍展示大标题（28pt 衬线粗体，西文 New York + 中文 Songti SC，对应篇章标题与世界主标题）
        public static let displayLarge = Font.system(size: 28, weight: .bold, design: .serif)

        /// 一级重要标题（22pt 衬线粗体，对应人物正名与成神途径高光）
        public static let titleLarge = Font.system(size: 22, weight: .bold, design: .serif)

        /// 卡片与模块标题（18pt 衬线半粗，对应维多利亚卡片、局势面板）
        public static let titleMedium = Font.system(size: 18, weight: .semibold, design: .serif)

        /// 界面操控与条目标题（15pt 现代非衬线，SF Pro + 苹方，用于高清晰度交互）
        public static let titleSmall = Font.system(size: 15, weight: .semibold, design: .default)

        /// 沉浸叙事台词与对白（16pt 衬线中粗，用于剧情编年史字幕与非凡言灵）
        public static let narrativeSubtitle = Font.system(size: 16, weight: .medium, design: .serif)

        /// 叙事正文长阅读（14pt 现代非衬线，舒适易读）
        public static let bodyLarge = Font.system(size: 14, weight: .regular, design: .default)

        /// macOS HIG 标准控件与正文（13pt 现代非衬线）
        public static let bodyMedium = Font.system(size: 13, weight: .regular, design: .default)

        /// 辅助修饰与时间说明（11pt 现代非衬线）
        public static let caption = Font.system(size: 11, weight: .medium, design: .default)

        /// 机械等宽（11pt SF Mono，用于纪元年代、灵数、哈希追踪）
        public static let monoBadge = Font.system(size: 11, weight: .medium, design: .monospaced)

        /// 19世纪侦探钢笔草写体（优先 macOS 系统 楷体-简 Kaiti SC，回退衬线）
        public static let parchmentCursive = Font.custom("Kaiti SC", size: 14, relativeTo: .body)
    }
}
