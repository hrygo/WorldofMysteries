import SwiftUI

/// Interactive presentation-only fixtures; no engine or domain action is invoked.
struct ControlRecoveryGallerySection: View {
    @State private var selection = "archive"
    @State private var hidesArchive = false
    @State private var clearsOptions = false
    @State private var retryCount = 0

    var body: some View {
        ComponentGallerySection(title: "12 · 控件恢复与反馈边界 (Control Recovery)") {
            ComponentGallerySpecimenStage(
                title: "控件恢复压力台",
                summary: "验证选项消失、空列表、窄面板反馈与辅助朗读边界；重置会恢复完整选项和零次重试。",
                mode: .stateMatrix,
                controls: {
                    Button("重置恢复样例") {
                        selection = "archive"
                        hidesArchive = false
                        clearsOptions = false
                        retryCount = 0
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
            ) {
                WOMAdaptivePair(
                    trailingIdealWidth: 220,
                    primaryIdealWidth: 320,
                    spacing: DesignTokens.Spacing.lg
                ) {
                    selectionSpecimen
                } secondary: {
                    feedbackSpecimens
                }
            }
        }
    }

    private var selectionSpecimen: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("选项暂时消失不应改写选中值；恢复后继续显示原选择。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            WOMAdaptiveSegmentedPicker("示例查看范围", selection: $selection, options: visibleOptions)
                .frame(maxWidth: 220, alignment: .leading)

            Toggle("暂时移除档案选项", isOn: $hidesArchive)
            Toggle("模拟选项列表为空", isOn: $clearsOptions)

            Text("调用方选中值：\(selection)")
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textPrimary)

            Button("恢复档案选中值") { selection = "archive" }
                .buttonStyle(WOMButtonStyle(.secondary))
        }
    }

    private var feedbackSpecimens: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            WOMLoadingState(
                title: "索引准备示例",
                message: "辅助朗读应保留这段进度说明，而不是仅朗读标题。"
            )
            WOMStatusBanner(
                tone: .warning,
                title: "需要重试的窄面板示例",
                message: "长中文说明与操作应在窄宽度下改为纵向排列。",
                actionTitle: "重试示例操作"
            ) { retryCount += 1 }
            WOMEmptyState(
                source: .system(.search),
                title: "尚无匹配项",
                message: "空白操作标题不应生成无名称按钮。",
                actionTitle: "   "
            ) { retryCount += 1 }
            Text("示例重试次数：\(retryCount)")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
        }
        .frame(maxWidth: 220, alignment: .leading)
    }

    private var visibleOptions: [WOMSegmentedOption<String>] {
        guard !clearsOptions else { return [] }
        let options = [
            WOMSegmentedOption(value: "world", title: "世界", systemImage: "globe"),
            WOMSegmentedOption(value: "archive", title: "档案", systemImage: "books.vertical"),
            WOMSegmentedOption(value: "archive", title: "重复档案（应被去重）"),
            WOMSegmentedOption(value: "chronicle", title: "章回与长期叙事记录"),
        ]
        return hidesArchive ? options.filter { $0.value != "archive" } : options
    }
}
