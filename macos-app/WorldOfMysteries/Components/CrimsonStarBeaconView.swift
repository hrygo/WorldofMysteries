import SwiftUI

/// 灰雾之上深红星辰与信徒祈祷信标（对应 11 灰雾之上 Above the Gray Fog）
public struct CrimsonStarBeaconView: View {
    public let starName: String
    public let prayerPreview: String
    public let unheardEchoesCount: Int
    public var onTapStar: (@MainActor () -> Void)?
    
    @State private var isHovered: Bool = false
    @State private var pulseScale: CGFloat = 1.0
    @State private var pulseOpacity: Double = 0.6
    
    public init(
        starName: String,
        prayerPreview: String,
        unheardEchoesCount: Int = 1,
        onTapStar: (@MainActor () -> Void)? = nil
    ) {
        self.starName = starName
        self.prayerPreview = prayerPreview
        self.unheardEchoesCount = unheardEchoesCount
        self.onTapStar = onTapStar
    }
    
    public var body: some View {
        Button {
            onTapStar?()
        } label: {
            HStack(spacing: DesignTokens.Spacing.md) {
                // 左侧多层脉动深红星辰
                ZStack {
                    // 外层扩散红光光晕
                    Circle()
                        .fill(Color.Mystic.crimsonGlow)
                        .frame(width: 38, height: 38)
                        .scaleEffect(pulseScale)
                        .opacity(pulseOpacity)
                    
                    // 中层深红核心
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [Color(red: 255/255, green: 110/255, blue: 120/255), Color.Mystic.crimsonStar, Color.Mystic.crimsonThread],
                                center: .center,
                                startRadius: 2,
                                endRadius: 14
                            )
                        )
                        .frame(width: 20, height: 20)
                        .shadow(color: Color.Mystic.crimsonStar, radius: 8)
                    
                    // 内部神圣十字光芒
                    Image(systemName: "sparkle")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Color.white)
                    
                    // 未读祈祷回响角标
                    if unheardEchoesCount > 0 {
                        Text("\(unheardEchoesCount)")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(Color.white)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.Mystic.crimsonThread)
                            .clipShape(Capsule())
                            .offset(x: 12, y: -12)
                    }
                }
                .frame(width: 44, height: 44)
                
                // 右侧信徒与祈祷信息
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                    HStack {
                        Text(starName)
                            .font(Font.Mystic.titleSmall)
                            .foregroundStyle(isHovered ? Color.Mystic.textGoldAccent : Color.Mystic.textPrimary)
                        
                        Spacer()
                        
                        Text("灰雾共鸣")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.crimsonStar)
                    }
                    
                    Text("“\(prayerPreview)”")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .lineLimit(2)
                        .lineSpacing(2)
                }
            }
            .padding(DesignTokens.Spacing.md)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .fill(isHovered ? Color.Mystic.obsidianElevated : Color.Mystic.obsidianCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(
                        isHovered ? Color.Mystic.crimsonStar.opacity(0.8) : Color.Mystic.brassGoldBorder.opacity(0.4),
                        lineWidth: isHovered ? DesignTokens.Borders.chamfer : DesignTokens.Borders.standard
                    )
            )
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
            .shadow(color: isHovered ? Color.Mystic.crimsonStar.opacity(0.2) : Color.black.opacity(0.3), radius: 8)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            withAnimation(DesignTokens.Motion.smoothSpring) {
                isHovered = hovering
            }
        }
        .onAppear {
            withAnimation(
                .easeInOut(duration: 1.8)
                .repeatForever(autoreverses: true)
            ) {
                pulseScale = 1.35
                pulseOpacity = 0.2
            }
        }
    }
}

#Preview("Crimson Star Beacons") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        
        VStack(spacing: DesignTokens.Spacing.md) {
            CrimsonStarBeaconView(
                starName: "深红星辰 · 正义小姐 (奥黛丽·霍尔)",
                prayerPreview: "不属于这个时代的愚者先生，贝克兰德即将举行一场非凡者聚会，我希望能向您献祭一页罗塞尔日记以换取启示...",
                unheardEchoesCount: 2
            )
            
            CrimsonStarBeaconView(
                starName: "深红星辰 · 倒吊人 (阿尔杰·威尔逊)",
                prayerPreview: "风暴之主的信徒在苏尼亚海发现了幽灵船的踪迹，似乎与齐林格斯有关，请求伟大的愚者指引方向...",
                unheardEchoesCount: 1
            )
            
            CrimsonStarBeaconView(
                starName: "微弱光点 · 廷根老尼尔",
                prayerPreview: "虔诚祈求隐秘的庇佑，希望能用纯银小刀驱散那些缠绕在我耳边的呢喃呓语...",
                unheardEchoesCount: 0
            )
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 580)
    }
}
