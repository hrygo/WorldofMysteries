import SwiftUI

/// 廷根市区域关键地标
public enum TingenLocation: String, CaseIterable, Identifiable, Sendable {
    case zotlandStreet = "佐特兰街 36 号"
    case daffodilStreet = "水仙花街"
    case welchBedroom = "韦尔奇卧房 (案发现场)"
    case hoyUniversity = "霍伊大学历史系"
    
    public var id: String { rawValue }
    
    public var note: String {
        switch self {
        case .zotlandStreet: return "黑荆棘安保公司 · 地下查尼斯门"
        case .daffodilStreet: return "班森与梅丽莎的家 · 水仙花寓意安宁"
        case .welchBedroom: return "转轮手枪、未燃尽信件与红月"
        case .hoyUniversity: return "古代赫密斯语与第四纪所罗门帝国文献"
        }
    }
    
    public var systemIcon: String {
        switch self {
        case .zotlandStreet: return "shield.checkered"
        case .daffodilStreet: return "house.fill"
        case .welchBedroom: return "moon.stars.fill"
        case .hoyUniversity: return "graduationcap.fill"
        }
    }
}

/// 廷根市 · 工业与大学之城调查卷宗卡（纯净材质底质 + 纯原生 SwiftUI 动态排版，零硬编码死文字）
public struct TingenCityDossierCard: View {
    public var onLocationSelected: (@MainActor (TingenLocation) -> Void)?
    
    @State private var selectedLocation: TingenLocation = .zotlandStreet
    @State private var hoveredLocation: TingenLocation? = nil
    
    public init(onLocationSelected: (@MainActor (TingenLocation) -> Void)? = nil) {
        self.onLocationSelected = onLocationSelected
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
            // 顶部卷宗标头：深邃红夜拱窗氛围底板（纯净无文字背景）
            ZStack(alignment: .bottomLeading) {
                // 纯净材质背景
                ZStack {
                    LinearGradient(
                        colors: [
                            Color(red: 45/255, green: 15/255, blue: 22/255), // 绯红微暗
                            Color.Mystic.obsidianElevated
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    
                    // 若存在纯净暗夜天鹅绒材质，进行微妙正片叠底
                    if NSImage(named: "TextureVelvet") != nil {
                        Image("TextureVelvet")
                            .resizable(resizingMode: .tile)
                            .blendMode(.multiply)
                            .opacity(0.4)
                    }
                    
                    // 维多利亚拱窗与微弱绯红光晕
                    HStack {
                        Spacer()
                        ZStack {
                            Circle()
                                .fill(Color.Mystic.crimsonGlow.opacity(0.25))
                                .frame(width: 120, height: 120)
                                .blur(radius: 20)
                            
                            Image(systemName: "moon.fill")
                                .font(.system(size: 44, weight: .light))
                                .foregroundStyle(Color.Mystic.crimsonStar.opacity(0.8))
                                .shadow(color: Color.Mystic.crimsonStar.opacity(0.6), radius: 12)
                        }
                        .padding(.trailing, DesignTokens.Spacing.xl)
                    }
                }
                .frame(height: 110)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                
                // 城市标牌与气象微态势（全原生动态渲染）
                VStack(alignment: .leading, spacing: DesignTokens.TypographyMetrics.compactLineSpacing) {
                    HStack(spacing: 6) {
                        Text("鲁恩王国 · 阿霍瓦郡")
                            .mysticCaptionStyle(color: Color.Mystic.brassGoldMuted)
                        
                        Circle()
                            .fill(Color.Mystic.crimsonStar)
                            .frame(width: 4, height: 4)
                        
                        Text("红月笼罩")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundStyle(Color.Mystic.crimsonStar)
                    }
                    
                    Text("廷根市 · 调查据点卷宗")
                        .mysticTitleStyle(font: Font.Mystic.titleMedium)
                    
                    Text("阿霍瓦细雨 · 煤气路灯长明 · 能见度 65%")
                        .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                }
                .padding(DesignTokens.LayoutInsets.compactCardPadding)
            }
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(Color.Mystic.brassGoldBorder.opacity(0.6), lineWidth: 1)
            )
            
            // 查尼斯门与值夜者警戒态势条
            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
                statusPill(
                    title: "查尼斯门状态",
                    value: "安宁 (圣赛缪尔骨灰封印)",
                    icon: "lock.shield",
                    color: Color.Mystic.statusOnline
                )
                
                statusPill(
                    title: "当前核心调查",
                    value: "追查《安提哥努斯笔记》",
                    icon: "magnifyingglass",
                    color: Color.Mystic.brassGoldPrimary
                )
            }
            
            // 四大关键地标列表选择
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("重要地标与驻点 (Key Locations)：")
                    .mysticCaptionStyle(color: Color.Mystic.textTertiary)
                
                VStack(spacing: DesignTokens.Spacing.xs) {
                    ForEach(TingenLocation.allCases) { loc in
                        locationRow(loc)
                    }
                }
            }
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .background(
            Color.Mystic.obsidianElevated
                .overlay(
                    LinearGradient(
                        colors: [Color.Mystic.brassGoldMuted.opacity(0.04), Color.clear],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
        )
    }
    
    @ViewBuilder
    private func statusPill(title: String, value: String, icon: String, color: Color) -> some View {
        HStack(spacing: DesignTokens.Spacing.xs) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(color)
            
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 9))
                    .foregroundStyle(Color.Mystic.textTertiary)
                Text(value)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(color)
            }
            
            Spacer()
        }
        .padding(.horizontal, DesignTokens.LayoutInsets.badgePaddingHorizontal + 2)
        .padding(.vertical, 6)
        .background(Color.Mystic.obsidianCard)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                .stroke(color.opacity(0.3), lineWidth: 1)
        )
    }
    
    @ViewBuilder
    private func locationRow(_ loc: TingenLocation) -> some View {
        let isSelected = selectedLocation == loc
        let isHovered = hoveredLocation == loc
        
        Button {
            withAnimation(DesignTokens.Interaction.selectionSpring) {
                selectedLocation = loc
            }
            onLocationSelected?(loc)
        } label: {
            HStack(spacing: DesignTokens.Spacing.sm) {
                Image(systemName: loc.systemIcon)
                    .font(.system(size: 12))
                    .foregroundStyle(isSelected ? Color.Mystic.brassGoldPrimary : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textTertiary))
                    .frame(width: 18)
                
                VStack(alignment: .leading, spacing: DesignTokens.TypographyMetrics.compactLineSpacing) {
                    Text(loc.rawValue)
                        .font(Font.Mystic.bodyMedium)
                        .fontWeight(isSelected ? .semibold : .regular)
                        .foregroundStyle(isSelected ? Color.Mystic.textPrimary : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textSecondary))
                        .tracking(DesignTokens.TypographyMetrics.bodyTracking)
                    
                    Text(loc.note)
                        .mysticCaptionStyle(color: isSelected ? Color.Mystic.brassGoldMuted : Color.Mystic.textTertiary)
                }
                
                Spacer()
                
                if isSelected {
                    Circle()
                        .fill(Color.Mystic.brassGoldPrimary)
                        .frame(width: 6, height: 6)
                        .shadow(color: Color.Mystic.brassGoldPrimary, radius: 4)
                }
            }
            .mysticRowItem(
                isSelected: isSelected,
                isHovered: isHovered,
                cornerRadius: DesignTokens.Radii.sm,
                showsLeadingIndicator: true
            )
        }
        .mysticPressable()
        .onHover { hovering in
            hoveredLocation = hovering ? loc : nil
        }
    }
}

#Preview("Tingen City Dossier Card") {
    TingenCityDossierCard()
        .frame(width: 440)
        .padding()
        .background(Color.Mystic.obsidianBase)
}
