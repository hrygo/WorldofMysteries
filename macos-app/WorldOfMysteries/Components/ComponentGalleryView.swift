import SwiftUI

/// 组件全景画廊视图（集中预览核心 UI、通用原语与 15 件特殊物品玩法组件）。
///
/// 画廊按职责拆分为独立子树，避免单个超大 `body` 带来的类型检查与预览重建开销；
/// 交互状态也下沉到所属分组，减少局部操作引发的无关视图失效。
public struct ComponentGalleryView: View {
    public init() {}

    public var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: DesignTokens.Spacing.xxl) {
                ComponentGalleryHeader()
                ComponentGalleryInteractionGroup()
                ComponentGalleryWorldGroup()
                ComponentGalleryDesignSystemGroup()
                ComponentGalleryArtifactGroup()
            }
            .padding(DesignTokens.Spacing.xxl)
        }
        .background(Color.Mystic.obsidianBase.ignoresSafeArea())
    }
}

private struct ComponentGalleryHeader: View {
    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text("《诡秘世界》UI 组件全景画廊")
                .font(Font.Mystic.gothicDisplay)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)

            Text("集中展示 16 大核心组件、15 件特殊物品玩法组件与 8 项通用原语 · 单一 Canvas 会话")
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textSecondary)
        }
        .padding(.bottom, DesignTokens.Spacing.md)
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
