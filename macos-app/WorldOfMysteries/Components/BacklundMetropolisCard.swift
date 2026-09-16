import SwiftUI

/// 贝克兰德五大城区与势力分布
public enum BacklundDistrict: String, CaseIterable, Identifiable, Sendable {
    case cherwood = "乔伍德区 (Cherwood)"
    case bridge = "贝克兰德桥区 (Bridge Area)"
    case eastEnd = "东区 (East End)"
    case empress = "皇后区与北区 (Empress & North)"
    
    public var id: String { rawValue }
    
    public var description: String {
        switch self {
        case .cherwood: return "明斯克街 15 号 · 夏洛克·莫里亚蒂侦探事务所"
        case .bridge: return "铁门街勇敢者酒吧 · 非凡聚会与地下线人"
        case .eastEnd: return "蒸汽工厂巨型烟囱 · 大雾霾核心与黑帮暗流"
        case .empress: return "伯爵府邸贵族沙龙 · 圣赛缪尔大教堂主教座"
        }
    }
    
    public var dangerLevel: String {
        switch self {
        case .cherwood: return "中度警戒"
        case .bridge: return "非凡混杂"
        case .eastEnd: return "高危贫民窟"
        case .empress: return "官方重兵"
        }
    }
    
    public var dangerColor: Color {
        switch self {
        case .cherwood: return Color.Mystic.brassGoldPrimary
        case .bridge: return Color.Mystic.statusWarning
        case .eastEnd: return Color.Mystic.crimsonStar
        case .empress: return Color.Mystic.statusOnline
        }
    }
}

/// 贝克兰德 · 万都之都全景态势卡（纯净材质底质 + 纯原生 SwiftUI 动态排版，零硬编码死文字）
public struct BacklundMetropolisCard: View {
    public var onDistrictSelected: (@MainActor (BacklundDistrict) -> Void)?
    
    @State private var selectedDistrict: BacklundDistrict = .cherwood
    @State private var smogLevel: Double = 0.78
    
    public init(onDistrictSelected: (@MainActor (BacklundDistrict) -> Void)? = nil) {
        self.onDistrictSelected = onDistrictSelected
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            // 顶部横幅：哥特主教座与万都之都夜色氛围（纯净无文字背景）
            ZStack(alignment: .bottomLeading) {
                ZStack {
                    LinearGradient(
                        colors: [
                            Color(red: 16/255, green: 28/255, blue: 44/255), // 塔索克河深冷蓝
                            Color.Mystic.obsidianElevated
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    
                    // 灰雾流光与石质底纹有机融合
                    if NSImage(named: "TextureFoolVeil") != nil {
                        Image("TextureFoolVeil")
                            .resizable(resizingMode: .tile)
                            .blendMode(.screen)
                            .opacity(0.12)
                    }
                    
                    // 哥特主教尖顶与钟楼纯净剪影
                    HStack {
                        Spacer()
                        ZStack(alignment: .bottomTrailing) {
                            Circle()
                                .fill(Color.Mystic.spiritualBlue.opacity(0.2))
                                .frame(width: 140, height: 140)
                                .blur(radius: 24)
                            
                            Image(systemName: "building.columns.circle")
                                .font(.system(size: 64, weight: .ultraLight))
                                .foregroundStyle(Color.Mystic.brassGoldPrimary.opacity(0.35))
                        }
                        .padding(.trailing, DesignTokens.Spacing.lg)
                    }
                }
                .frame(height: 120)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                
                // 城市名与核心概览（全原生动态渲染）
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text("鲁恩王国首都 · 万都之都")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.brassGoldMuted)
                        
                        Text("Hope & Fall")
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .foregroundStyle(Color.Mystic.textTertiary)
                    }
                    
                    Text("贝克兰德 · 全景态势视窗")
                        .font(Font.Mystic.titleMedium)
                        .fontWeight(.bold)
                        .foregroundStyle(Color.Mystic.textPrimary)
                    
                    Text("塔索克河水雾 · 蒸汽烟囱轰鸣 · 500 万人口之城")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
                .padding(DesignTokens.Spacing.md)
            }
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(Color.Mystic.brassGoldBorder.opacity(0.6), lineWidth: 1)
            )
            
            // 大雾霾浓度与势力警戒条
            HStack(spacing: DesignTokens.Spacing.md) {
                // 大雾霾指数
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Image(systemName: "smoke.fill")
                            .font(.system(size: 11))
                            .foregroundStyle(Color.Mystic.statusWarning)
                        Text("贝克兰德大雾霾")
                            .font(.system(size: 10))
                            .foregroundStyle(Color.Mystic.textSecondary)
                        Spacer()
                        Text("\(Int(smogLevel * 100))%")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundStyle(Color.Mystic.statusWarning)
                    }
                    
                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Color.Mystic.obsidianCard)
                            Capsule()
                                .fill(
                                    LinearGradient(
                                        colors: [Color.Mystic.statusWarning, Color.Mystic.crimsonStar],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    )
                                )
                                .frame(width: proxy.size.width * smogLevel)
                        }
                    }
                    .frame(height: 4)
                }
                .padding(DesignTokens.Spacing.sm)
                .background(Color.Mystic.obsidianCard)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
                
                // 塔索克河航运与官方警戒
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Image(systemName: "ferry.fill")
                            .font(.system(size: 11))
                            .foregroundStyle(Color.Mystic.spiritualBlue)
                        Text("塔索克河航运")
                            .font(.system(size: 10))
                            .foregroundStyle(Color.Mystic.textSecondary)
                        Spacer()
                        Text("通航中")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(Color.Mystic.statusOnline)
                    }
                    
                    Text("代罚者与军情九处巡航中")
                        .font(.system(size: 9))
                        .foregroundStyle(Color.Mystic.textTertiary)
                }
                .padding(DesignTokens.Spacing.sm)
                .background(Color.Mystic.obsidianCard)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
            }
            
            // 四大核心城区与侦探据点列表
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("重点城区与暗线据点 (Boroughs & Safehouses)：")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textTertiary)
                
                VStack(spacing: DesignTokens.Spacing.xs) {
                    ForEach(BacklundDistrict.allCases) { district in
                        districtRow(district)
                    }
                }
            }
        }
        .padding(DesignTokens.Spacing.lg)
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
    private func districtRow(_ district: BacklundDistrict) -> some View {
        let isSelected = selectedDistrict == district
        
        Button {
            withAnimation(DesignTokens.Motion.smoothSpring) {
                selectedDistrict = district
            }
            onDistrictSelected?(district)
        } label: {
            HStack(spacing: DesignTokens.Spacing.sm) {
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 6) {
                        Text(district.rawValue)
                            .font(Font.Mystic.bodyMedium)
                            .fontWeight(isSelected ? .semibold : .regular)
                            .foregroundStyle(isSelected ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
                        
                        Text(district.dangerLevel)
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(district.dangerColor)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(district.dangerColor.opacity(0.15))
                            .clipShape(RoundedRectangle(cornerRadius: 2))
                    }
                    
                    Text(district.description)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textTertiary)
                }
                
                Spacer()
                
                if isSelected {
                    Circle()
                        .fill(Color.Mystic.brassGoldPrimary)
                        .frame(width: 6, height: 6)
                        .shadow(color: Color.Mystic.brassGoldPrimary, radius: 4)
                }
            }
            .padding(.horizontal, DesignTokens.Spacing.md)
            .padding(.vertical, DesignTokens.Spacing.xs)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                    .fill(isSelected ? Color.Mystic.obsidianCard : Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                            .stroke(isSelected ? Color.Mystic.brassGoldBorder : Color.clear, lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
    }
}

#Preview("Backlund Metropolis Card") {
    BacklundMetropolisCard()
        .frame(width: 460)
        .padding()
        .background(Color.Mystic.obsidianBase)
}
