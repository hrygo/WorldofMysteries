import SwiftUI

/// 音色供给听审台 (Voice Supply Audition Desk).
///
/// This is a production surface, so it lives inside the engine/storage HUD
/// rather than as a page of its own: a person casting a voice is not a player
/// reading their world, and giving the tool a top-level slot in the narrative
/// sidebar would say otherwise.
///
/// The one rule the layout enforces is that a verdict cannot be signed before
/// both clips have been heard. Everything else on this screen exists to make
/// that possible — fetch the audio, play it, and send back exactly what was
/// played.
public struct VoiceFoundryAuditionSection: View {
    @Environment(AppState.self) private var appState
    @State private var model = VoiceFoundryAuditionModel()
    @State private var identityVerdict = "pass"
    @State private var naturalnessVerdict = "pass"
    @State private var supported: Bool?

    public init() {}

    public var body: some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                header
                if supported == false {
                    unavailable
                } else {
                    castBar
                    taskList
                    if model.selectedTask != nil {
                        if model.selectableCandidate != nil {
                            selection
                        }
                        if model.selectedTask?.stage == "awaiting_review" {
                            audition
                            verdict
                        }
                    }
                }
            }
        }
        .task { await bootstrap() }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            WOMIcon(system: .voiceAdvice, size: .prominent)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("音色供给听审台 (Voice Supply Audition Desk)")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                Text("试听与评审只在引擎可达时呈现。签名回传的是刚刚真正播放过的那份音频摘要。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: DesignTokens.Spacing.sm)
            Button {
                Task { await model.load(using: appState.ipcClient) }
            } label: {
                WOMIcon(system: .refresh, size: .standard)
            }
            .buttonStyle(.plain)
            .disabled(model.phase == .loading)
            .accessibilityLabel("刷新音色供给列表")
        }
    }

    private var unavailable: some View {
        Text("未接入：当前引擎未声明音色供给能力。")
            .font(Font.Mystic.caption)
            .foregroundStyle(Color.Mystic.textSecondary)
    }

    // MARK: - Tasks

    /// The explicit door into casting, next to the automatic one.
    ///
    /// It is a menu of the catalog rather than a free-text field because the
    /// brief is engine-side: the App shows who it would cast and sends the id.
    /// A client that could also write the description would eventually send a
    /// description the engine never agreed to.
    @ViewBuilder
    private var castBar: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                Menu {
                    ForEach(model.designs) { design in
                        Button {
                            Task {
                                await model.cast(
                                    design,
                                    sessionId: appState.storyModel.view?.sessionId ?? "",
                                    using: appState.ipcClient
                                )
                            }
                        } label: {
                            Text(design.pickerSummary)
                        }
                    }
                } label: {
                    Text(model.phase == .submitting ? "铸造中…" : "铸造音色")
                }
                .disabled(!model.canCast)
                .accessibilityLabel("铸造音色")

                if let notice = model.castNotice {
                    statusLine(notice)
                }
            }
            if let code = model.catalogCode {
                statusLine("音色目录不可用：\(code)。已存在的任务不受影响。")
            } else if model.designs.isEmpty && supported == true {
                statusLine("音色目录为空。名录只收录已听审签署的角色；其余人首次出场时由系统自动合成简报。")
            }
        }
    }

    @ViewBuilder
    private var taskList: some View {
        let tasks = model.outstandingTasks
        if case .failed(let code) = model.phase {
            statusLine("引擎拒绝：\(code)")
        } else if tasks.isEmpty {
            statusLine("当前没有待处理或铸造中的音色任务。")
        } else {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                ForEach(tasks, id: \.taskId) { task in
                    Button {
                        model.select(task.taskId)
                    } label: {
                        HStack(spacing: DesignTokens.Spacing.sm) {
                            WOMIcon(system: .audioReplay, size: .standard)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(VoiceFoundryAuditionModel.pendingSummary(for: task))
                                    .font(Font.Mystic.bodyMedium)
                                    .foregroundStyle(Color.Mystic.textGoldAccent)
                                Text("\(task.scope.phase) · \(task.scope.locale) · rev \(task.taskRevision)")
                                    .font(Font.Mystic.caption)
                                    .foregroundStyle(Color.Mystic.textSecondary)
                            }
                            Spacer(minLength: DesignTokens.Spacing.sm)
                            if model.selectedTaskId == task.taskId {
                                Text("已选中")
                                    .font(Font.Mystic.caption)
                                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                            }
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    // MARK: - Audition

    /// The one decision that must stay a person's.
    ///
    /// Everything else about a casting may run unattended, but registering the
    /// voice with the provider costs a real call and is irreversible for that
    /// candidate, so it waits here. The engine mints exactly one candidate per
    /// task today, so this is a confirmation rather than a comparison — the
    /// copy says so rather than dressing one option up as a choice.
    @ViewBuilder
    private var selection: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("选定候选 (Select Candidate)")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            Text("候选音色已经生成，但尚未向服务商注册。选定后才会真正铸造；这一步不会自动替你做。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            if let candidate = model.selectableCandidate {
                HStack(spacing: DesignTokens.Spacing.sm) {
                    WOMIcon(system: .audioReplay, size: .standard)
                    Text("候选 \(candidate.slot) · seed \(candidate.seed) · rev \(candidate.providerCandidateRevision ?? "未注册")")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                    Spacer(minLength: DesignTokens.Spacing.sm)
                    Button {
                        Task { await model.selectCandidate(using: appState.ipcClient) }
                    } label: {
                        Text(model.phase == .submitting ? "提交中…" : "选定并铸造")
                    }
                    .disabled(!model.canSelectCandidate)
                }
            }
        }
    }

    @ViewBuilder
    private var audition: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("试听 (Audition)")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            Text("两段都必须真正播放过才能签名。读取到音频不等于听过它。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: DesignTokens.Spacing.md) {
                listenButton(.reference, title: "参考音频", hint: "这是不是被描述的那个声音")
                listenButton(.validation, title: "跨文本复验", hint: "换一段没听过的文本还成不成立")
            }

            if let validation = model.assets[.validation], let id = validation.validationId {
                Text("复验编号 \(id) · 修订 \(validation.candidateRevision)")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            }
        }
    }

    private func listenButton(
        _ kind: VoiceFoundryAssetKind,
        title: String,
        hint: String
    ) -> some View {
        let isPlaying = model.phase == .playing(kind)
        let wasHeard = model.heard.contains(kind)
        return Button {
            Task { await model.listen(kind, using: appState.ipcClient) }
        } label: {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                HStack(spacing: DesignTokens.Spacing.xs) {
                    WOMIcon(system: .audioReplay, size: .standard)
                    Text(title)
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textGoldAccent)
                    if wasHeard {
                        Text("已听")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    }
                }
                Text(isPlaying ? "播放中…" : hint)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(DesignTokens.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                WOMPanelBackground(
                    tone: .floating,
                    cornerRadius: DesignTokens.Radii.sm,
                    texture: .sacredSlate,
                    textureOpacity: 0.02
                )
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(isPlaying || model.phase == .submitting)
    }

    // MARK: - Verdict

    @ViewBuilder
    private var verdict: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("人工评审 (Human Review)")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            verdictPicker("身份", selection: $identityVerdict)
            verdictPicker("自然度", selection: $naturalnessVerdict)

            if case .failed(let code) = model.phase {
                statusLine("引擎拒绝：\(code)")
            }

            HStack(spacing: DesignTokens.Spacing.sm) {
                Button {
                    Task {
                        await model.submitReview(
                            identity: identityVerdict,
                            naturalness: naturalnessVerdict,
                            using: appState.ipcClient
                        )
                    }
                } label: {
                    Text(model.canSubmitReview ? "提交评审" : "需先听完两段")
                }
                .disabled(!model.canSubmitReview)

                if model.selectedTask?.stage == "published" {
                    Button {
                        Task { await model.publish(using: appState.ipcClient) }
                    } label: {
                        Text("发布并绑定")
                    }
                    .disabled(model.phase == .submitting)
                }
            }

            if let reason = model.selectedTask?.reasonCode, !reason.isEmpty {
                statusLine("原因：\(reason)")
            }
        }
    }

    private func verdictPicker(_ title: String, selection: Binding<String>) -> some View {
        Picker(title, selection: selection) {
            Text("通过").tag("pass")
            Text("否决").tag("reject")
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .accessibilityLabel("\(title)评审结论")
    }

    private func statusLine(_ text: String) -> some View {
        Text(text)
            .font(Font.Mystic.caption)
            .foregroundStyle(Color.Mystic.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func bootstrap() async {
        // Capabilities are optional handshake entries. Asking before the
        // handshake has landed would report "not connected" for a method that
        // is in fact served, and send an operator hunting for a missing switch.
        supported = await appState.ipcClient.supportsVoiceFoundryMethod(
            "voice.foundry.asset.get"
        )
        guard supported == true else { return }
        await model.load(using: appState.ipcClient)
    }
}
