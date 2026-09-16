import SwiftUI

/// 黄水晶吊坠原画视窗（正典「克莱恩执链占卜」原画）
///
/// - 黄水晶几何中心恒定锚定视窗正中（由 `CitrineArtworkGeometry` 保证）；
/// - 仅「银链 + 黄水晶」条带绕捏链点摆动：手、衣料、红茶杯与桌面保持静止，
///   与真实悬垂灵摆的物理直觉一致，且整幅原画取景不被旋转余量蚕食；
/// - 原画素材缺失时优雅降级为纯代码矢量占卜纹章。
public struct CitrinePendulumArtwork: View {
    /// 摆动角度（度）。正值向右偏摆，负值向左。
    public let swingAngle: Double
    /// 黄水晶灵光强度 0...1
    public let glowIntensity: Double
    public let cornerRadius: CGFloat
    /// 原画素材；默认取资产目录中的 `PendulumCitrine`，缺失时自动降级为矢量纹章
    public let artworkImage: NSImage?
    
    public init(
        swingAngle: Double = 0,
        glowIntensity: Double = 0.30,
        cornerRadius: CGFloat = DesignTokens.Radii.md,
        artworkImage: NSImage? = NSImage(named: "PendulumCitrine")
    ) {
        self.swingAngle = swingAngle
        self.glowIntensity = glowIntensity
        self.cornerRadius = cornerRadius
        self.artworkImage = artworkImage
    }
    
    public var body: some View {
        GeometryReader { geo in
            let artwork = CitrineArtworkGeometry.canonical
            let layout = artwork.resolveLayout(in: geo.size)
            
            ZStack {
                Color.Mystic.obsidianBase
                
                if let artworkImage {
                    // 静态层：整幅原画，仅在灵摆条带处挖出羽化缺口
                    artworkLayer(artwork: artwork, layout: layout, image: artworkImage)
                        .mask(stationaryMask(artwork: artwork, layout: layout))
                    
                    // 灵摆层：同一原画绕手指捏链点摆动，再套用**固定**条带遮罩。
                    // 遮罩必须位于旋转之后：遮罩若随内容旋转，会与静态层缺口错位成月牙鬼影。
                    artworkLayer(artwork: artwork, layout: layout, image: artworkImage)
                        .rotationEffect(
                            // SwiftUI 正角为屏幕顺时针（y 轴向下），取负使正角语义化为「向右偏摆」
                            .degrees(-swingAngle),
                            anchor: UnitPoint(
                                x: layout.swingAnchorUnitPoint.x,
                                y: layout.swingAnchorUnitPoint.y
                            )
                        )
                        .mask(swingingMask(artwork: artwork, layout: layout))
                } else {
                    vectorFallback
                }
                
                // 灵光呼吸：黄水晶恒在视窗正中，故灵光同样以视窗中心为圆心
                RadialGradient(
                    colors: [
                        Color.Mystic.brassGoldPrimary.opacity(glowIntensity),
                        Color.Mystic.brassGoldPrimary.opacity(0)
                    ],
                    center: .center,
                    startRadius: 0,
                    endRadius: geo.size.width * 0.45
                )
                .blendMode(.plusLighter)
                .allowsHitTesting(false)
                
                // 底部暗室渐隐，令视窗与卡片底板自然衔接
                LinearGradient(
                    colors: [Color.clear, Color.Mystic.obsidianBase.opacity(0.55)],
                    startPoint: .center,
                    endPoint: .bottom
                )
                .allowsHitTesting(false)
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .clipped()
        }
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: cornerRadius)
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
        )
        .accessibilityElement()
        .accessibilityLabel("黄水晶吊坠灵摆原画视窗")
    }
    
    // MARK: - 原画层
    
    private func artworkLayer(
        artwork: CitrineArtworkGeometry,
        layout: CitrineArtworkGeometry.Layout,
        image: NSImage
    ) -> some View {
        Image(nsImage: image)
            .resizable()
            .interpolation(.high)
            .frame(
                width: artwork.imageSize.width * layout.scale,
                height: artwork.imageSize.height * layout.scale
            )
    }
    
    // MARK: - 遮罩
    
    /// 静态层遮罩：整幅可见，灵摆条带处形成羽化缺口
    private func stationaryMask(
        artwork: CitrineArtworkGeometry,
        layout: CitrineArtworkGeometry.Layout
    ) -> some View {
        let strip = stripRectInImageSpace(artwork: artwork, layout: layout)
        
        return Rectangle()
            .fill(Color.white)
            .overlay(alignment: .topLeading) {
                Ellipse()
                    .fill(Color.black)
                    .frame(width: strip.width, height: strip.height)
                    .blur(radius: DesignTokens.Spacing.xs / 2)
                    .offset(x: strip.minX, y: strip.minY)
            }
    }
    
    /// 灵摆层遮罩：反向选择同一羽化条带
    private func swingingMask(
        artwork: CitrineArtworkGeometry,
        layout: CitrineArtworkGeometry.Layout
    ) -> some View {
        let strip = stripRectInImageSpace(artwork: artwork, layout: layout)
        
        return Color.black
            .overlay(alignment: .topLeading) {
                Ellipse()
                    .fill(Color.white)
                    .frame(width: strip.width, height: strip.height)
                    .blur(radius: DesignTokens.Spacing.xs / 2)
                    .offset(x: strip.minX, y: strip.minY)
            }
    }
    
    /// 摆动条带在原画自身坐标系中的位置（遮罩坐标空间 = 原画视图坐标空间）
    private func stripRectInImageSpace(
        artwork: CitrineArtworkGeometry,
        layout: CitrineArtworkGeometry.Layout
    ) -> CGRect {
        let strip = layout.swingStripFrame
        return CGRect(
            x: strip.minX - layout.imageOrigin.x,
            y: strip.minY - layout.imageOrigin.y,
            width: strip.width,
            height: strip.height
        )
    }
    
    /// 素材缺失时的纯代码矢量占卜纹章（不产生空白视窗）
    private var vectorFallback: some View {
        ZStack {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                .fill(Color.Mystic.obsidianElevated)
            
            Circle()
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
                .frame(width: 96, height: 96)
            
            VStack(spacing: DesignTokens.Spacing.xs) {
                Image(systemName: "circle.circle")
                    .font(.system(size: 34))
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                Image(systemName: "sparkles")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.Mystic.brassGoldMuted)
            }
        }
        .rotationEffect(.degrees(swingAngle * 1.5))
    }
}

#Preview("Citrine Pendulum Artwork") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        
        HStack(spacing: DesignTokens.Spacing.lg) {
            CitrinePendulumArtwork(swingAngle: 0, glowIntensity: 0.22)
                .frame(width: 156, height: 310)
            CitrinePendulumArtwork(swingAngle: 6, glowIntensity: 0.45)
                .frame(width: 156, height: 310)
            CitrinePendulumArtwork(swingAngle: -6, glowIntensity: 0.45)
                .frame(width: 156, height: 310)
        }
        .padding()
    }
}
