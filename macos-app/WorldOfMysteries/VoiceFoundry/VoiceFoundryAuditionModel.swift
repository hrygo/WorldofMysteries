import Foundation
import Observation

/// Where an audition clip is actually played.
///
/// The rule being modelled here is about attention, not audio, so the model
/// takes the output device as a dependency: a test can then stand in for it
/// and exercise the whole review path without an audio engine, and the
/// production path stays exactly the backend the rest of the app already plays
/// through.
public protocol VoiceFoundryAuditionPlayback: Sendable {
    func play(sampleRate: Int, channels: Int, pcm: Data, frameCount: Int) async throws
    func stop() async
}

extension AVAudioEnginePCMPlaybackBackend: VoiceFoundryAuditionPlayback {
    public func play(
        sampleRate: Int,
        channels: Int,
        pcm: Data,
        frameCount: Int
    ) async throws {
        try await start(sampleRate: sampleRate, channels: channels, outputGain: 1.0)
        try await enqueue(pcm16: pcm, frameCount: frameCount)
    }
}

/// Drives one human review of one voice.
///
/// The whole point of this type is that it cannot be talked into signing for
/// audio nobody heard. A verdict is only accepted once *both* assets have been
/// fetched and actually played, and the digests and validation id sent with it
/// are read back off the responses that carried the audio — never assembled
/// from anything the model remembers wanting to be true.
@MainActor
@Observable
public final class VoiceFoundryAuditionModel {
    public enum Phase: Equatable {
        case idle
        case loading
        case ready
        case playing(VoiceFoundryAssetKind)
        case submitting
        case failed(code: String)
    }

    public private(set) var tasks: [VoiceFoundryTaskDTO] = []
    public private(set) var designs: [VoiceDesignDTO] = []
    public private(set) var selectedTaskId: String?
    public private(set) var assets: [VoiceFoundryAssetKind: VoiceFoundryAssetResponseDTO] = [:]
    /// What actually reached the speakers. A verdict requires this to cover
    /// both assets — a fetch is not a listen.
    public private(set) var heard: Set<VoiceFoundryAssetKind> = []
    public private(set) var phase: Phase = .idle
    public private(set) var lastPublishedVoiceId: String?
    /// What the last cast attempt actually did, said in the words a person
    /// would use. Casting has outcomes that are not failures — a voice that
    /// already exists is the system working — and collapsing them into a red
    /// error is what makes a person press the button twice.
    public private(set) var castNotice: String?
    /// Why the picker is empty, when it is empty for a reason. `nil` means the
    /// catalog loaded and genuinely has nobody in it yet.
    public private(set) var catalogCode: String?

    /// Tasks a person could act on right now, newest state first. Everything
    /// else in the list is history, and mixing the two is how a half-finished
    /// casting gets mistaken for one awaiting judgement.
    public var awaitingReviewTasks: [VoiceFoundryTaskDTO] {
        tasks.filter { $0.stage == "awaiting_review" && $0.auditionedCandidate != nil }
    }

    /// Tasks where a person is genuinely the bottleneck.
    ///
    /// Read from `required_actions`, never re-derived from the stage: whoever
    /// last moved the task decided what a person owes next, and a second
    /// opinion here could contradict the buttons this very screen renders. A
    /// task still being cast has none and stays invisible — which is the whole
    /// difference between casting automatically and interrupting.
    public var pendingTasks: [VoiceFoundryTaskDTO] {
        tasks.filter { !$0.requiredActions.isEmpty }
    }

    /// The four stages the driver advances on its own, plus `binding`. A person
    /// watching the desk should see casting *happen*; a task in one of these is
    /// not waiting on anybody, it is simply not finished.
    private static let automaticStages: Set<String> = [
        "requested", "previewing", "provisioning", "validating", "binding",
    ]

    /// Everything the desk has a reason to show: tasks that owe a person a
    /// decision, and tasks being cast right now. A published or failed task
    /// with nothing owed is history, and listing it would put a row on screen
    /// that no button in it can act on.
    public var outstandingTasks: [VoiceFoundryTaskDTO] {
        tasks.filter {
            !$0.requiredActions.isEmpty || Self.automaticStages.contains($0.stage)
        }
    }

    /// Why a task is on screen, in one line, so the reason is legible rather
    /// than merely announced.
    public static func pendingSummary(for task: VoiceFoundryTaskDTO) -> String {
        let who = task.scope.presentationIdentity
        if task.requiredActions.contains("select_candidate") {
            return "\(who) · 待选定候选音色"
        }
        if task.requiredActions.contains("review") {
            return "\(who) · 待听审"
        }
        if !task.requiredActions.isEmpty {
            return "\(who) · \(task.requiredActions.joined(separator: "、"))"
        }
        return "\(who) · 铸造中（\(stageLabel(task.stage))）"
    }

    /// Stage names are engine vocabulary. They are shown to a person deciding
    /// whether to wait, so they are translated rather than leaked.
    public static func stageLabel(_ stage: String) -> String {
        switch stage {
        case "requested": "已登记"
        case "previewing": "生成候选"
        case "provisioning": "铸造音色"
        case "validating": "跨文本复验"
        case "binding": "写入绑定"
        default: stage
        }
    }

    public var selectedTask: VoiceFoundryTaskDTO? {
        guard let selectedTaskId else { return nil }
        return tasks.first { $0.taskId == selectedTaskId }
    }

    /// The candidate a person is being asked to choose, when the task is asking
    /// them to. `ready` is the provider's own word for "previewed and not yet
    /// spoken for", so it is read from the record rather than counted here.
    public static func selectableCandidate(
        for task: VoiceFoundryTaskDTO
    ) -> VoiceFoundryCandidateDTO? {
        task.candidates.first { $0.state == "ready" }
    }

    public var selectableCandidate: VoiceFoundryCandidateDTO? {
        selectedTask.flatMap(Self.selectableCandidate(for:))
    }

    /// The digest goes back with the choice so the engine can check that the
    /// decision names a preview that exists. The App cannot hear the preview —
    /// the engine does not serve candidate audio — so it echoes the digest it
    /// was given rather than inventing one, and the guard downstream is what
    /// makes the echo mean anything.
    public var canSelectCandidate: Bool {
        phase != .submitting && selectableCandidate != nil
    }

    /// The verdict is submittable only after both clips were played. This is
    /// the one rule the model exists to enforce.
    public var canSubmitReview: Bool {
        phase != .submitting
            && selectedTask != nil
            && assets[.reference] != nil
            && assets[.validation] != nil
            && heard == [.reference, .validation]
    }

    /// The button is live when there is somebody to cast and nothing in flight
    /// is mid-request. An empty catalog disables it rather than hiding it: a
    /// missing picker and a missing reason read very differently.
    public var canCast: Bool {
        !designs.isEmpty && phase != .submitting && phase != .loading
    }

    /// Stable for one audition. A retry after a dropped connection must
    /// present the same command id, or the engine journals a second review
    /// instead of replaying the first.
    private var reviewCommandId: String?
    private let playback: any VoiceFoundryAuditionPlayback

    public init(playback: any VoiceFoundryAuditionPlayback = AVAudioEnginePCMPlaybackBackend()) {
        self.playback = playback
    }

    public func load(using client: any VoiceFoundryEngineClient) async {
        phase = .loading
        do {
            let page = try await client.voiceFoundryList(pageSize: 50, stage: nil, pageToken: nil)
            tasks = page.tasks
            if let selectedTaskId, !tasks.contains(where: { $0.taskId == selectedTaskId }) {
                self.selectedTaskId = nil
            }
            phase = .ready
        } catch {
            // The engine's own reason code is shown rather than a generic
            // failure: "no voice has been cast" and "the provider is
            // unreachable" call for completely different next moves.
            phase = .failed(code: Self.reason(for: error))
        }
        await loadCatalog(using: client)
    }

    /// The catalog and the task list are fetched apart on purpose. The catalog
    /// is a convenience for casting somebody new; the task list is what a
    /// person came to this screen to act on. A catalog that will not load must
    /// not blank out the reviews that are already waiting.
    private func loadCatalog(using client: any VoiceFoundryEngineClient) async {
        do {
            designs = try await client.voiceFoundryDesigns().designs
            catalogCode = nil
        } catch {
            designs = []
            catalogCode = Self.reason(for: error)
        }
    }

    /// Cast one designed identity on a session the engine already owns.
    ///
    /// The request carries a session and a design id and nothing else. The App
    /// is never told the world id, so it cannot name a world: the engine
    /// resolves the scope from the session, which also means the button and the
    /// silent first-appearance trigger arrive at the same casting rather than
    /// two rival ones.
    public func cast(
        _ design: VoiceDesignDTO,
        sessionId: String,
        using client: any VoiceFoundryEngineClient
    ) async {
        guard !sessionId.isEmpty else {
            castNotice = "当前没有进行中的会话，无法铸造音色。"
            return
        }
        phase = .submitting
        do {
            let response = try await client.voiceFoundryCastDesign(
                sessionId: sessionId,
                designId: design.designId
            )
            if let task = response.task {
                // Folded in rather than reloaded: the cast *is* the answer, and
                // a fresh page could sort it out of view before it is read.
                if !tasks.contains(where: { $0.taskId == task.taskId }) {
                    tasks.insert(task, at: 0)
                }
                castNotice = task.reasonCode.flatMap { $0.isEmpty ? nil : $0 }
                    ?? "已为 \(task.scope.presentationIdentity) 发起铸造。"
            } else {
                // No task because a voice is already bound. Pressing the button
                // again is not a failure and must not read as one.
                castNotice = "\(design.displayName) 已有可用音色，未重复铸造。"
            }
            phase = .ready
        } catch {
            let code = Self.reason(for: error)
            castNotice = "铸造未发起：\(code)"
            phase = .failed(code: code)
        }
    }

    public func select(_ taskId: String?) {
        guard selectedTaskId != taskId else { return }
        selectedTaskId = taskId
        assets = [:]
        heard = []
        reviewCommandId = nil
        lastPublishedVoiceId = nil
        castNotice = nil
    }

    public func listen(
        _ kind: VoiceFoundryAssetKind,
        using client: any VoiceFoundryEngineClient
    ) async {
        guard let task = selectedTask, let candidate = task.auditionedCandidate else { return }
        phase = .playing(kind)
        do {
            let asset = try await client.voiceFoundryAsset(
                taskId: task.taskId,
                candidateId: candidate.candidateId,
                kind: kind
            )
            let pcm = try WavPcmDecoder.decode(asset.decodedAudio())
            try await play(pcm)
            assets[kind] = asset
            // Marked heard only after the samples reached the output device.
            // A decode that succeeded but never played is not a listen.
            heard.insert(kind)
            reviewCommandId = nil
            phase = .ready
        } catch {
            phase = .failed(code: Self.reason(for: error))
        }
    }

    public func submitReview(
        identity: String,
        naturalness: String,
        using client: any VoiceFoundryEngineClient
    ) async {
        guard canSubmitReview, let task = selectedTask,
              let reference = assets[.reference],
              let validation = assets[.validation],
              let validationId = validation.validationId
        else { return }
        reviewCommandId = reviewCommandId ?? UUID().uuidString
        phase = .submitting
        do {
            let command = try VoiceFoundryCommandDTO(
                commandId: reviewCommandId!,
                taskId: task.taskId,
                expectedTaskRevision: task.taskRevision,
                action: "review",
                payload: VoiceFoundryReviewPayloadDTO(
                    humanReview: VoiceFoundryHumanReviewDTO(
                        validationId: validationId,
                        referenceAudioDigest: reference.audioDigest,
                        validationAudioDigest: validation.audioDigest,
                        identity: identity,
                        naturalness: naturalness
                    )
                )
            )
            let accepted = try await client.voiceFoundryCommand(command)
            tasks = tasks.map { $0.taskId == accepted.task.taskId ? accepted.task : $0 }
            assets = [:]
            heard = []
            reviewCommandId = nil
            lastPublishedVoiceId = accepted.task.candidates
                .first { $0.state == "published" }?
                .candidateId
            phase = .ready
        } catch {
            // The command id survives a failure on purpose: the caller is very
            // likely pressing Retry, and that retry has to be a replay of the
            // same authorization rather than a second one.
            phase = .failed(code: Self.reason(for: error))
        }
    }

    /// Choose the candidate to carry forward, and start provisioning it.
    ///
    /// This is the gate before the provider is asked to register a real voice,
    /// so it stays a person's button even though casting is otherwise allowed
    /// to run by itself: spending another provider call on a voice nobody
    /// chose is exactly the cost the automatic path is meant to avoid.
    public func selectCandidate(using client: any VoiceFoundryEngineClient) async {
        guard let task = selectedTask,
              let candidate = selectableCandidate
        else { return }
        phase = .submitting
        do {
            let command = try VoiceFoundryCommandDTO(
                commandId: UUID().uuidString,
                taskId: task.taskId,
                expectedTaskRevision: task.taskRevision,
                action: "select",
                payload: VoiceFoundrySelectPayloadDTO(
                    candidateId: candidate.candidateId,
                    previewAudioDigest: candidate.previewAudioDigest
                )
            )
            let accepted = try await client.voiceFoundryCommand(command)
            tasks = tasks.map { $0.taskId == accepted.task.taskId ? accepted.task : $0 }
            phase = .ready
        } catch {
            phase = .failed(code: Self.reason(for: error))
        }
    }

    public func publish(
        using client: any VoiceFoundryEngineClient
    ) async {
        guard let task = selectedTask,
              let candidate = task.auditionedCandidate,
              let revision = candidate.providerCandidateRevision
        else { return }
        phase = .submitting
        do {
            let command = try VoiceFoundryCommandDTO(
                commandId: UUID().uuidString,
                taskId: task.taskId,
                expectedTaskRevision: task.taskRevision,
                action: "publish",
                payload: VoiceFoundryPublishPayloadDTO(
                    providerCandidateRevision: revision
                )
            )
            let accepted = try await client.voiceFoundryCommand(command)
            tasks = tasks.map { $0.taskId == accepted.task.taskId ? accepted.task : $0 }
            phase = .ready
        } catch {
            phase = .failed(code: Self.reason(for: error))
        }
    }

    public func stopPlayback() async {
        await playback.stop()
    }

    // MARK: - Playback

    private func play(_ pcm: WavPcmDecoder.Pcm) async throws {
        await playback.stop()
        try await playback.play(
            sampleRate: pcm.sampleRate,
            channels: pcm.channels,
            pcm: pcm.samples,
            frameCount: pcm.frameCount
        )
    }

    // MARK: - Failure text

    private static func reason(for error: any Error) -> String {
        if let service = error as? VoiceFoundryServiceError { return service.code }
        if let client = error as? VoiceFoundryClientError {
            return client == .audioNotPlayable ? "audio_not_playable" : "asset_payload_mismatch"
        }
        if let control = error as? StoryControlServiceError { return control.code }
        return "service_unavailable"
    }
}
