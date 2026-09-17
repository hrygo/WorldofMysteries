import SwiftUI

/// Visual regression and design-system showcase for the Wave B visual asset stack.
struct VisualSystemGallerySection: View {
    @State private var isCardHovered = false

    var body: some View {
        ComponentGallerySection(title: "11 · 视觉资产系统 (Visual Asset System)") {
            VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                customIconGrid
                platformIconRows
                buttonVariants
                surfaceSamples
            }
        }
    }

    private var customIconGrid: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("世界观矢量资产")
                .womSectionHeaderStyle()

            LazyVGrid(
                columns: Array(repeating: GridItem(.fixed(74), spacing: DesignTokens.Spacing.sm), count: 6),
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                ForEach(WOMIconAsset.allCases, id: \.rawValue) { asset in
                    VStack(spacing: DesignTokens.Spacing.xs) {
                        WOMIcon(asset, size: .prominent)
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)

                        Text(assetLabel(asset.rawValue))
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                            .lineLimit(1)
                    }
                    .frame(width: 70, height: 58)
                    .background(
                        WOMPanelBackground(
                            tone: .card,
                            cornerRadius: DesignTokens.Radii.sm
                        )
                    )
                }
            }
        }
    }

    private var platformIconRows: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            WOMDividerOrnament()

            HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    Text("平台行为")
                        .womSectionHeaderStyle()

                    HStack(spacing: DesignTokens.Spacing.md) {
                        ForEach(WOMSystemIcon.allCases, id: \.rawValue) { icon in
                            WOMIcon(system: icon, size: .standard, accessibilityLabel: icon.rawValue)
                                .foregroundStyle(Color.Mystic.textPrimary)
                                .frame(width: 28, height: 28)
                        }
                    }
                }

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    Text("状态语义")
                        .womSectionHeaderStyle()

                    HStack(spacing: DesignTokens.Spacing.md) {
                        ForEach(WOMStatusIcon.allCases, id: \.rawValue) { icon in
                            WOMIcon(status: icon, size: .standard, accessibilityLabel: icon.rawValue)
                                .foregroundStyle(statusColor(icon))
                                .frame(width: 28, height: 28)
                        }
                    }
                }
            }
        }
    }

    private var buttonVariants: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            WOMDividerOrnament()

            Text("按钮语义与密度")
                .womSectionHeaderStyle()

            HStack(spacing: DesignTokens.Spacing.sm) {
                Button("主操作") {}
                    .buttonStyle(WOMButtonStyle(.primary))
                Button("次操作") {}
                    .buttonStyle(WOMButtonStyle(.secondary))
                Button("低干扰") {}
                    .buttonStyle(WOMButtonStyle(.tertiary))
                Button("危险") {}
                    .buttonStyle(WOMButtonStyle(.danger))
                Button("仪式") {}
                    .buttonStyle(WOMButtonStyle(.ritual))

                Button {} label: {
                    WOMIcon(system: .more, size: .standard, accessibilityLabel: "更多")
                }
                .buttonStyle(WOMIconButtonStyle())

                Button {} label: {
                    WOMIcon(system: .search, size: .compact, accessibilityLabel: "搜索")
                }
                .buttonStyle(WOMToolbarButtonStyle())
            }
        }
    }

    private var surfaceSamples: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            WOMDividerOrnament()

            Text("Surface + Texture")
                .womSectionHeaderStyle()

            HStack(spacing: DesignTokens.Spacing.md) {
                surfaceSample("Panel", tone: .panel, texture: .sacredSlate)
                surfaceSample("Card", tone: .card, texture: .velvet)
                surfaceSample("Floating", tone: .floating, texture: .foolVeil)
                surfaceSample("Ritual", tone: .ritual, texture: .foolVeil)
                surfaceSample("Codex", tone: .parchment, texture: .parchment)
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Label("Hover / selection chrome", systemImage: "sparkles")
                    .foregroundStyle(Color.Mystic.textPrimary)
                Text("该卡片验证 CardChrome 的 hover 边框与微光。")
                    .mysticCaptionStyle()
            }
            .padding(DesignTokens.LayoutInsets.compactCardPadding)
            .womCardChrome(
                tone: .card,
                texture: .gold,
                isSelected: false,
                isHovered: isCardHovered
            )
            .onHover { isCardHovered = $0 }
        }
    }

    private func surfaceSample(
        _ title: String,
        tone: WOMSurfaceTone,
        texture: WOMTextureAsset
    ) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text(title)
                .font(Font.Mystic.caption)
                .foregroundStyle(tone == .parchment ? Color.Mystic.parchmentInk : Color.Mystic.textPrimary)
            Text(texture.rawValue)
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(
                    tone == .parchment
                        ? Color.Mystic.parchmentInkSecondary
                        : Color.Mystic.textTertiary
                )
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .frame(width: 126, height: 72, alignment: .leading)
        .background(
            WOMPanelBackground(
                tone: tone,
                cornerRadius: DesignTokens.Radii.sm,
                texture: texture,
                textureOpacity: 0.08
            )
        )
    }

    private func assetLabel(_ rawValue: String) -> String {
        rawValue
            .replacingOccurrences(of: "wom.icon.", with: "")
            .replacingOccurrences(of: "grayfog", with: "gray fog")
    }

    private func statusColor(_ icon: WOMStatusIcon) -> Color {
        switch icon {
        case .warning:
            Color.Mystic.statusWarning
        case .success:
            Color.Mystic.statusOnline
        case .locked:
            Color.Mystic.textSecondary
        case .active:
            Color.Mystic.brassGoldPrimary
        case .cooldown:
            Color.Mystic.spiritualBlue
        }
    }
}
