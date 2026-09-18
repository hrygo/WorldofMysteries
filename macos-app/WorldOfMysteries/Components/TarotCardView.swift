import SwiftUI

/// 依据 `docs/05_UI/UI_交互基线_v1.0.md` 第 7 节“Card Collection”
public enum CardDiscoveryStage: String, Sendable {
    case unknown = "unknown"                       // 完全未知，迷雾笼罩
    case silhouette = "silhouette"                 // 剪影碎片
    case identified = "identified"                 // 确认序列名称
    case partiallyRevealed = "partially_revealed"   // 部分魔药配方揭示
    case established = "established"               // 完整生平传记建立
}

/// 塔罗秘纹序列卡牌组件（对应原型 05 卡牌详情与 06 卡牌馆）
public struct TarotCardView: View {
    @FocusState private var isCardFocused: Bool

    public let pathwayName: String
    public let sequenceNumber: Int
    public let sequenceTitle: String
    public let stage: CardDiscoveryStage
    public let pathwayColor: Color
    public var onCardTapped: (@MainActor () -> Void)?
    
    public init(
        pathwayName: String = "占卜家途径",
        sequenceNumber: Int = 9,
        sequenceTitle: String = "占卜家",
        stage: CardDiscoveryStage = .established,
        pathwayColor: Color = Color.Mystic.Pathways.fool,
        onCardTapped: (@MainActor () -> Void)? = nil
    ) {
        self.pathwayName = pathwayName
        self.sequenceNumber = sequenceNumber
        self.sequenceTitle = sequenceTitle
        self.stage = stage
        self.pathwayColor = pathwayColor
        self.onCardTapped = onCardTapped
    }
    
    public var body: some View {
        Button {
            onCardTapped?()
        } label: {
            VStack(spacing: DesignTokens.Spacing.sm) {
                // 顶部塔罗罗马数字与途径名
                HStack {
                    Text("Seq.\(sequenceNumber)")
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.textGoldAccent)
                    Spacer()
                    Text(pathwayName)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
                
                Spacer()
                
                // 中央卡面立绘区域（根据发现程度变化）
                ZStack {
                    Circle()
                        .stroke(pathwayColor.opacity(0.4), lineWidth: DesignTokens.Borders.standard)
                        .frame(
                            width: DesignTokens.ComponentMetrics.TarotCard.emblemDiameter,
                            height: DesignTokens.ComponentMetrics.TarotCard.emblemDiameter
                        )
                    
                    if stage == .unknown {
                        WOMIcon(status: .unknown, size: .prominent)
                            .foregroundStyle(Color.Mystic.textTertiary)
                    } else if stage == .silhouette {
                        WOMIcon(status: .concealed, size: .prominent)
                            .foregroundStyle(pathwayColor.opacity(0.6))
                    } else {
                        WOMIcon(status: .active, size: .prominent)
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    }
                }
                
                Spacer()
                
                // 底部序列名称与状态
                VStack(spacing: DesignTokens.Spacing.xxs) {
                    Text(stage == .unknown ? "？？？" : sequenceTitle)
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.textPrimary)
                    
                    Text(stageText)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(stageColor)
                }
            }
            .padding(DesignTokens.Spacing.md)
            .frame(
                width: DesignTokens.ComponentMetrics.TarotCard.width,
                height: DesignTokens.ComponentMetrics.TarotCard.width
                    * DesignTokens.ComponentMetrics.TarotCard.aspectRatio
            )
            .background(Color.Mystic.obsidianCard)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(
                        stage == .established ? Color.Mystic.brassGoldPrimary : Color.Mystic.brassGoldBorder,
                        lineWidth: DesignTokens.Borders.standard
                    )
            )
            .overlay(
                RoundedRectangle(
                    cornerRadius: DesignTokens.Radii.md,
                    style: .continuous
                )
                .inset(by: -DesignTokens.Accessibility.focusRingOffset)
                .stroke(
                    Color.Mystic.textGoldAccent,
                    lineWidth: DesignTokens.Accessibility.focusRingWidth
                )
                .opacity(isCardFocused && onCardTapped != nil ? 1 : 0)
            )
            .shadow(
                color: pathwayColor.opacity(
                    stage == .established
                        ? DesignTokens.ComponentMetrics.TarotCard.establishedShadowOpacity
                        : DesignTokens.ComponentMetrics.TarotCard.restingShadowOpacity
                ),
                radius: DesignTokens.ComponentMetrics.TarotCard.shadowRadius
            )
        }
        .mysticPressable()
        .focused($isCardFocused)
        .disabled(onCardTapped == nil)
        .accessibilityLabel("\(pathwayName)，序列 \(sequenceNumber) \(stage == .unknown ? "未知" : sequenceTitle)")
        .accessibilityValue(stageText)
    }
    
    private var stageText: String {
        switch stage {
        case .unknown: return "未探索"
        case .silhouette: return "残片感知"
        case .identified: return "已知序列"
        case .partiallyRevealed: return "配方解析中"
        case .established: return "正典已确立"
        }
    }
    
    private var stageColor: Color {
        switch stage {
        case .unknown: return Color.Mystic.textTertiary
        case .silhouette: return Color.Mystic.statusWarning
        case .identified, .partiallyRevealed: return Color.Mystic.spiritualBlue
        case .established: return Color.Mystic.statusOnline
        }
    }
}

#Preview("Tarot Cards") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        HStack(spacing: DesignTokens.Spacing.lg) {
            TarotCardView(stage: .unknown)
            TarotCardView(stage: .silhouette)
            TarotCardView(stage: .identified)
            TarotCardView(stage: .established)
        }
        .padding(DesignTokens.Spacing.xl)
    }
}
