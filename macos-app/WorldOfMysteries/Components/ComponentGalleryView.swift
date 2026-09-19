import SwiftUI

/// 组件全景画廊视图（集中预览核心 UI、通用原语与 15 件特殊物品玩法组件）。
///
/// 画廊按职责拆分为独立子树，避免单个超大 `body` 带来的类型检查与预览重建开销；
/// 交互状态也下沉到所属分组，减少局部操作引发的无关视图失效。
///
/// 滚动所有权：画廊不自带滚动容器。它被挂载在工作区唯一的滚动容器内，
/// 嵌套滚动会同时破坏虚拟化与滚动语义（历史缺陷：内外两层纵向滚动容器）。
public struct ComponentGalleryView: View {
    @State private var focus: ComponentGalleryFocus = .all

    public init() {}

    public var body: some View {
        LazyVStack(alignment: .leading, spacing: DesignTokens.Spacing.xxl) {
            ComponentGalleryHeader(focus: $focus)
            focusedContent
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var focusedContent: some View {
        switch focus {
        case .all:
            ComponentGalleryInteractionGroup()
            ComponentGalleryWorldGroup()
            ComponentGalleryDesignSystemGroup()
            ControlRecoveryGallerySection()
            ComponentGalleryArtifactGroup()
        case .interaction:
            ComponentGalleryInteractionGroup()
        case .world:
            ComponentGalleryWorldGroup()
        case .system:
            ComponentGalleryDesignSystemGroup()
            ControlRecoveryGallerySection()
        case .artifacts:
            ComponentGalleryArtifactGroup()
        }
    }
}

private enum ComponentGalleryFocus: String, CaseIterable, Hashable {
    case all
    case interaction
    case world
    case system
    case artifacts

    var title: String {
        switch self {
        case .all: "全部"
        case .interaction: "交互"
        case .world: "世界"
        case .system: "系统"
        case .artifacts: "特殊物品"
        }
    }

    var summary: String {
        switch self {
        case .all: "13 个区块完整浏览；适合视觉回归和全局检查。"
        case .interaction: "01–04 · 输入、调查、灵性占卜与世界线。"
        case .world: "05–08 · 灰雾仪式、人物档案、导航与地域。"
        case .system: "09–12 · UX 标尺、通用原语、视觉系统与恢复边界。"
        case .artifacts: "13 · 15 件 Canon 特殊物品的真实玩法工作台。"
        }
    }

    var countLabel: String {
        switch self {
        case .all: "13 Sections"
        case .interaction: "4 Sections"
        case .world: "4 Sections"
        case .system: "4 Sections"
        case .artifacts: "15 Artifacts"
        }
    }
}

private struct ComponentGalleryHeader: View {
    @Binding var focus: ComponentGalleryFocus

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("《诡秘世界》UI 组件全景画廊")
                    .font(Font.Mystic.gothicDisplay)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)

                Text("真实组件优先 · 可交互 specimen · 自适应布局 · 15 件特殊物品玩法 · 单一 Canvas 会话")
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)
            }

            ViewThatFits(in: .horizontal) {
                HStack(spacing: DesignTokens.Spacing.md) {
                    focusPicker(style: .segmented)
                    focusSummary
                }

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    focusPicker(style: .menu)
                    focusSummary
                }
            }
        }
        .padding(.bottom, DesignTokens.Spacing.md)
    }

    private enum FocusPickerStyle {
        case segmented
        case menu
    }

    @ViewBuilder
    private func focusPicker(style: FocusPickerStyle) -> some View {
        let picker = Picker("画廊范围", selection: $focus) {
            ForEach(ComponentGalleryFocus.allCases, id: \.rawValue) { option in
                Text(option.title).tag(option)
            }
        }
        .labelsHidden()

        switch style {
        case .segmented:
            picker
                .pickerStyle(.segmented)
                .fixedSize()
        case .menu:
            picker
                .pickerStyle(.menu)
                .frame(minWidth: 180, maxWidth: 240, alignment: .leading)
        }
    }

    private var focusSummary: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
            MysticBadge(focus.countLabel, tone: focus == .artifacts ? .gold : .teal, variant: .panel)

            Text(focus.summary)
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct ComponentGallerySection<Content: View>: View {
    private let title: String
    private let content: Content

    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            MysticSectionHeader(title: title, isProminent: true)
            content
            MysticDivider()
                .padding(.top, DesignTokens.Spacing.md)
        }
    }
}

#Preview("Component Gallery + Artifact Components") {
    ComponentGalleryView()
        .frame(minWidth: 800, minHeight: 900)
}
