import SwiftUI

/// Component Gallery 的体验舞台：为真实组件补充上下文、交互模式和可选控制，
/// 但不接管组件内部状态，也不伪造生产能力。
enum ComponentGallerySpecimenMode {
    case live
    case stateMatrix
    case reference

    var label: String {
        switch self {
        case .live: "LIVE"
        case .stateMatrix: "STATE MATRIX"
        case .reference: "REFERENCE"
        }
    }

    var tone: MysticTone {
        switch self {
        case .live: .teal
        case .stateMatrix: .gold
        case .reference: .neutral
        }
    }

    var systemIcon: String {
        switch self {
        case .live: "cursorarrow.click.2"
        case .stateMatrix: "square.grid.2x2"
        case .reference: "book.pages"
        }
    }
}

struct ComponentGallerySpecimenStage<Content: View, Controls: View>: View {
    let title: String
    let summary: String
    let mode: ComponentGallerySpecimenMode
    private let controls: Controls
    private let content: Content

    init(
        title: String,
        summary: String,
        mode: ComponentGallerySpecimenMode,
        @ViewBuilder controls: () -> Controls,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.summary = summary
        self.mode = mode
        self.controls = controls()
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
                    identity
                    Spacer(minLength: DesignTokens.Spacing.md)
                    controls
                }

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    identity
                    controls
                }
            }

            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .background(
            WOMPanelBackground(
                tone: .panel,
                cornerRadius: DesignTokens.Radii.lg,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(
                    Color.Mystic.brassGoldBorder.opacity(0.32),
                    lineWidth: DesignTokens.Borders.hairline
                )
        }
    }

    private var identity: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                MysticBadge(
                    mode.label,
                    tone: mode.tone,
                    variant: .panel,
                    systemIcon: mode.systemIcon
                )

                Text(title)
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)
            }

            Text(summary)
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

extension ComponentGallerySpecimenStage where Controls == EmptyView {
    init(
        title: String,
        summary: String,
        mode: ComponentGallerySpecimenMode,
        @ViewBuilder content: () -> Content
    ) {
        self.init(
            title: title,
            summary: summary,
            mode: mode,
            controls: { EmptyView() },
            content: content
        )
    }
}
