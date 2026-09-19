import SwiftUI

/// 场景页头的几何契约。
public nonisolated enum WOMSceneHeroMetrics: Sendable {
    /// 场景页头的最小高度：低于该高度时 wide 派生图会退化成一条色带，失去场景可辨识度。
    public static let minimumHeight: CGFloat = 132
}

/// 真实游戏场景的入口页头：已批准的 W1–W6 场景美术 + 场景身份文本。
///
/// 契约：
/// - 只加载运行时可加载的场景派生图（`wideHeader`），绝不解析生产 master；
/// - 图片始终是承托而不是可读元素：`WOMArtworkView` 不接收 accessibility label，
///   场景身份完全由图标、标题与说明文本承担；
/// - Reduce Transparency 下削减图片权重，让底色承托接管；Increased Contrast 下加粗边界，
///   而不是把整幅图压黑；
/// - 空间不足时 `ViewThatFits` 退回纵向排列，不压缩文字、不缩小字号。
public struct WOMSceneHeroHeader<Accessory: View>: View {
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    private let declaration: WOMSceneArtworkDeclaration
    private let icon: WOMIconSource
    private let title: String
    private let accessory: Accessory

    public init(
        scene: WOMSceneIdentity,
        icon: WOMIconSource,
        title: String,
        @ViewBuilder accessory: () -> Accessory
    ) {
        self.declaration = WOMSceneArtworkRegistry.declaration(for: scene)
        self.icon = icon
        self.title = title
        self.accessory = accessory()
    }

    public init(
        scene: WOMSceneIdentity,
        icon: WOMIconSource,
        title: String
    ) where Accessory == EmptyView {
        self.init(scene: scene, icon: icon, title: title) { EmptyView() }
    }

    public var body: some View {
        ZStack(alignment: .leading) {
            WOMArtworkView(
                assetName: declaration.assetName,
                fallback: .icon(declaration.fallbackIcon),
                fallbackTint: Color.Mystic.brassGoldMuted,
                contentMode: .fill
            )
            .opacity(artworkOpacity)
            .frame(maxWidth: .infinity)
            .frame(minHeight: WOMSceneHeroMetrics.minimumHeight)
            .allowsHitTesting(false)

            WOMArtworkScrim(edge: .leading, strength: scrimStrength)

            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
                    sceneIdentity
                    Spacer(minLength: DesignTokens.Spacing.md)
                    accessory
                }

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    sceneIdentity
                    accessory
                }
            }
            .padding(DesignTokens.LayoutInsets.compactCardPadding)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.md, style: .continuous)
                .stroke(
                    Color.Mystic.brassGoldBorder.opacity(
                        colorSchemeContrast == .increased ? 0.72 : 0.3
                    ),
                    lineWidth: colorSchemeContrast == .increased
                        ? DesignTokens.Borders.standard
                        : DesignTokens.Borders.hairline
                )
        }
        .accessibilityElement(children: .contain)
    }

    private var sceneIdentity: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
            WOMIcon(source: icon, size: .prominent, accessibilityLabel: nil)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
                .padding(.top, DesignTokens.Spacing.xxs)

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                Text(title)
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                    .fixedSize(horizontal: false, vertical: true)

                Text(declaration.caption)
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: 620, alignment: .leading)
    }

    /// Reduce Transparency 下场景图退居为极轻的纹理，可读性交给底色。
    private var artworkOpacity: Double {
        reduceTransparency ? 0.14 : 0.32
    }

    private var scrimStrength: Double {
        reduceTransparency ? 0.96 : 0.9
    }
}

#Preview("Scene Hero Headers") {
    ScrollView {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            ForEach(WOMSceneIdentity.allCases, id: \.rawValue) { scene in
                WOMSceneHeroHeader(
                    scene: scene,
                    icon: scene.fallbackIcon,
                    title: scene.rawValue
                )
            }
        }
        .padding(DesignTokens.Spacing.xl)
    }
    .frame(width: 900, height: 900)
    .background(Color.Mystic.obsidianBase)
}
