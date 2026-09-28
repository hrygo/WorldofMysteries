import SwiftUI

/// 工程验证 · 固定五轮面板。
///
/// 它只驱动真实 IPC：开场、五轮提交、恢复都来自本地引擎的持久事实。未接线
/// 的示例页面继续保留「示例数据」标记，本面板不把它们改名为真实数据。
public struct StorySessionPanel: View {
    @Bindable public var model: StorySessionModel
    /// Optional so the deterministic-only surfaces keep rendering unchanged.
    private let voice: VoiceTurnController?
    private let turnContext: VoiceTurnController.TurnContext?

    public init(
        model: StorySessionModel,
        voice: VoiceTurnController? = nil,
        turnContext: VoiceTurnController.TurnContext? = nil
    ) {
        self.model = model
        self.voice = voice
        self.turnContext = turnContext
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
            Text("工程验证 · 固定五轮")
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

            if let submissionStatus = model.submissionStatusText {
                Text(submissionStatus)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .accessibilityIdentifier("storySubmissionStatus")
            }

            if let view = model.view {
                sessionSummary(view)
                expressionContent
            }
            actions
            Text("领域事实在提交时保存；叙事与语音由提交后工作独立推进。")
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

    @ViewBuilder
    private var expressionContent: some View {
        if let work = model.postCommitWork {
            postCommitWorkContent(work)
        } else if let expression = model.expression {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("本轮叙事")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)

                switch expression.narrativeState {
                case .pending:
                    Text("尚无已保存的文字叙事。")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                case .ready:
                    ForEach(Array(expression.segments.enumerated()), id: \.offset) { item in
                        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                            Text(segmentLabel(item.element))
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.textSecondary)
                            Text(item.element.text)
                                .font(Font.Mystic.bodyMedium)
                                .foregroundStyle(Color.Mystic.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .accessibilityIdentifier("storyExpressionSegment.\(item.offset)")
                    }
                case .unavailable:
                    Text("文字叙事不可用（\(expression.reason ?? "unknown")）。")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
            }
            .accessibilityIdentifier("storyExpression")
        }

        if model.postCommitWorkLoading {
            Text("正在读取提交后工作状态…")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .accessibilityIdentifier("storyPostCommitWorkLoading")
        }

        if model.postCommitWorkReadFailed {
            Text("提交后工作状态读取失败；已提交事实仍保留，查询没有重新提交或生成内容。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .accessibilityIdentifier("storyPostCommitWorkReadFailure")
        }

        if model.expressionReadFailed {
            Text("文字叙事读取失败；已提交轮次仍保留，未重新提交。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .accessibilityIdentifier("storyExpressionReadFailure")
        }

        if model.postCommitWork == nil,
           let reason = model.audioUnavailableReason ?? voiceUnavailableReason {
            Text("语音不可用（\(reason)）。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .accessibilityIdentifier("storyAudioUnavailable")
        }
    }

    @ViewBuilder
    private func postCommitWorkContent(
        _ work: StoryTurnWorkGetResponseDTO
    ) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text("本轮叙事")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)

            switch work.narrativeState {
            case .pending:
                Text("叙事等待处理。")
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)
            case .running:
                Text("叙事处理中。")
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)
            case .blocked:
                Text("叙事处理受阻（\(work.narrativeReason ?? "unknown")）。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            case .ready:
                ForEach(Array(work.narrativeSegments.enumerated()), id: \.offset) { item in
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                        Text(segmentLabel(item.element))
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                        Text(item.element.text)
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityIdentifier("storyPostCommitNarrativeSegment.\(item.offset)")
                }
            }

            Text("语音")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)

            switch work.audioState {
            case .pending:
                Text("语音等待处理。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            case .running:
                Text("语音准备中。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            case .unavailable:
                Text("语音不可用（\(work.audioReason ?? "unknown")）。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .accessibilityIdentifier("storyAudioUnavailable")
            case .ready:
                Text("语音配方已就绪，等待后续回放。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .accessibilityIdentifier("storyAudioReady")
            }
        }
        .accessibilityIdentifier("storyPostCommitWork")
    }

    private var voiceUnavailableReason: String? {
        guard let voice, case .unavailable(let reason) = voice.phase else { return nil }
        return reason
    }

    private func segmentLabel(_ segment: StoryExpressionSegmentDTO) -> String {
        switch segment.type {
        case .narration:
            return "旁白"
        case .character:
            return segment.speakerDisplayName ?? "对白"
        }
    }

    /// Push-to-talk. The App never picks a microphone or a speaker: it uses the
    /// system defaults, so whatever hardware the player owns just works.
    @ViewBuilder
    private var pushToTalk: some View {
        if let voice, let turnContext {
            Button(voice.phase == .listening ? "松开结束" : "按住说话") {
                Task {
                    if voice.phase == .listening {
                        _ = await voice.finishAndSpeak(context: turnContext)
                        await model.reloadSession()
                    } else {
                        await voice.startListening()
                    }
                }
            }
            .buttonStyle(WOMButtonStyle(voice.phase == .listening ? .primary : .secondary))
            .disabled(voice.phase.isBusy && voice.phase != .listening)
            .accessibilityIdentifier("voicePushToTalk")
        } else {
            Text("语音不可用")
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
                onSubmitAdvice: { advice in
                    // `AdviceDraftSubmission` empties the binding as soon as this
                    // handler returns, so the delivered text — not the draft —
                    // has to reach the Engine.
                    Task { await model.submit(advice: advice) }
                }
            )
            HStack(spacing: DesignTokens.Spacing.sm) {
                Button("填入本轮建议") { model.fillSupportedAdvice() }
                    .buttonStyle(WOMButtonStyle(.secondary))
                pushToTalk
            }
        case .completed:
            Text("固定五轮验证已完成；已提交的 5 轮可以随时重新读取。")
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
        case .recovering:
            if model.canRecover {
                Button("查询是否已保存") {
                    Task { await model.recover() }
                }
                .buttonStyle(WOMButtonStyle(.primary))
            }
        case .unavailable, .loading, .opening:
            EmptyView()
        }
    }
}
