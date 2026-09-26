import SwiftUI

/// 工程验证 · 固定首轮面板。
///
/// 它只驱动真实 IPC：开场、提交、恢复都来自本地引擎的持久事实。未接线的
/// 示例页面继续保留「示例数据」标记，本面板不把它们改名为真实数据。
public struct StorySessionPanel: View {
    @Bindable public var model: StorySessionModel

    public init(model: StorySessionModel) {
        self.model = model
    }

    public var body: some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                header
                Divider().overlay(Color.Mystic.brassGoldBorder)
                content
            }
        }
        .accessibilityIdentifier("storySessionPanel")
    }

    private var header: some View {
        HStack(spacing: DesignTokens.Spacing.xs) {
            WOMIcon(system: .advice, size: .compact)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            Text("工程验证 · 固定首轮")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            Text("固定模式")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
            Spacer()
        }
    }

    @ViewBuilder
    private var content: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text(model.statusText)
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            if let view = model.view {
                sessionSummary(view)
            }
            actions
            Text("固定模式只接受指定首轮建议；输入持久化、领域裁决与事务执行真实代码，不是生成叙事。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func sessionSummary(_ view: StoryPublicViewDTO) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("\(view.protagonist.displayName) · \(view.scene.displayName)")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
            Text("已提交轮次：\(view.turn) · 线索：\(clueText(view))")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
        }
    }

    private func clueText(_ view: StoryPublicViewDTO) -> String {
        let names = view.discoveredClues.map(\.displayName)
        return names.isEmpty ? "无" : names.joined(separator: "、")
    }

    @ViewBuilder
    private var actions: some View {
        switch model.state {
        case .notStarted:
            Button("开始可信开场") {
                Task { await model.startStory() }
            }
            .buttonStyle(WOMButtonStyle(.primary))
            .disabled(!model.canStartStory)
        case .ready, .submitting:
            AdviceInputField(
                text: $model.draft,
                targetCharacter: model.view?.protagonist.displayName ?? "当前角色",
                onVoiceTapped: nil,
                onSubmitAdvice: { _ in
                    Task { await model.submit() }
                }
            )
            HStack(spacing: DesignTokens.Spacing.sm) {
                Button("填入首轮建议") { model.fillSupportedAdvice() }
                    .buttonStyle(WOMButtonStyle(.secondary))
                Text("语音仍禁用")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            }
        case .completed:
            Text("后续回合尚未开放；已提交的第 1 轮可以随时重新读取。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case .pending:
            if model.canContinuePending {
                Button("继续同一请求") {
                    Task { await model.continuePendingRequest() }
                }
                .buttonStyle(WOMButtonStyle(.primary))
            } else {
                Text("服务端已有待处理请求，但本地冻结文本已遗失；当前验证无法自动继续。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .failed:
            HStack(spacing: DesignTokens.Spacing.sm) {
                if model.canRecover {
                    Button("查询是否已保存") {
                        Task { await model.recover() }
                    }
                    .buttonStyle(WOMButtonStyle(.primary))
                }
                if model.canRetrySameRequest {
                    Button("重试同一请求") {
                        Task { await model.retryFrozenSubmission() }
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
            }
        case .unavailable, .loading, .opening, .recovering:
            EmptyView()
        }
    }
}
