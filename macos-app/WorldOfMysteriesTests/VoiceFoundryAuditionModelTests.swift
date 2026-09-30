import Foundation
import Testing
@testable import WorldOfMysteriesCore

// MARK: - Doubles

/// Stands in for the output device so the review path can be exercised end to
/// end without an audio engine. The rule under test is about attention, and it
/// only means something if "played" is a fact the model can actually be wrong
/// about.
@MainActor
private final class RecordingPlayback: VoiceFoundryAuditionPlayback {
    private(set) var played: [(rate: Int, frames: Int)] = []
    var failsToPlay = false

    func play(sampleRate: Int, channels: Int, pcm: Data, frameCount: Int) async throws {
        if failsToPlay { throw VoiceFoundryClientError.audioNotPlayable }
        played.append((sampleRate, frameCount))
    }

    func stop() async {}
}

@MainActor
private final class FakeFoundryClient: VoiceFoundryEngineClient {
    var tasks: [VoiceFoundryTaskDTO]
    var assets: [VoiceFoundryAssetKind: VoiceFoundryAssetResponseDTO]
    var designs: [VoiceDesignDTO] = [sampleDesign()]
    var listError: VoiceFoundryServiceError?
    var commandError: VoiceFoundryServiceError?
    var castError: VoiceFoundryServiceError?
    private(set) var casts: [(sessionId: String, designId: String)] = []
    private(set) var submitted: [(commandId: String, action: String, payload: Any)] = []

    init(tasks: [VoiceFoundryTaskDTO], assets: [VoiceFoundryAssetKind: VoiceFoundryAssetResponseDTO]) {
        self.tasks = tasks
        self.assets = assets
    }

    func voiceFoundryTask(_ taskId: String) async throws -> VoiceFoundryGetResponseDTO {
        VoiceFoundryGetResponseDTO(schemaVersion: "1.0", task: tasks[0])
    }

    func voiceFoundryDesigns() async throws -> VoiceFoundryDesignsResponseDTO {
        VoiceFoundryDesignsResponseDTO(
            schemaVersion: "1.0",
            catalogVersion: "test",
            designs: designs
        )
    }

    func voiceFoundryCastDesign(
        sessionId: String,
        designId: String
    ) async throws -> VoiceFoundryCastResponseDTO {
        casts.append((sessionId, designId))
        if let castError { throw castError }
        // A design nobody has cast yet opens a task; a design already spoken
        // for answers with none, which is a success and not a failure.
        guard !tasks.contains(where: { $0.scope.presentationIdentity == designId }) else {
            return VoiceFoundryCastResponseDTO(schemaVersion: "1.0", task: nil)
        }
        let task = queuedTask(identity: designId)
        tasks = [task] + tasks
        return VoiceFoundryCastResponseDTO(schemaVersion: "1.0", task: task)
    }

    func voiceFoundryList(
        pageSize: Int,
        stage: String?,
        pageToken: String?
    ) async throws -> VoiceFoundryListResponseDTO {
        if let listError { throw listError }
        return VoiceFoundryListResponseDTO(
            schemaVersion: "1.0",
            tasks: tasks,
            nextPageToken: nil
        )
    }

    func voiceFoundryAsset(
        taskId: String,
        candidateId: String,
        kind: VoiceFoundryAssetKind
    ) async throws -> VoiceFoundryAssetResponseDTO {
        guard let asset = assets[kind] else {
            throw VoiceFoundryServiceError(code: "audition_asset_not_recorded", retryable: false)
        }
        return asset
    }

    func voiceFoundryCommand<Payload: Codable & Sendable>(
        _ command: VoiceFoundryCommandDTO<Payload>
    ) async throws -> VoiceFoundryCommandResponseDTO {
        submitted.append((command.commandId, command.action, command.payload))
        if let commandError { throw commandError }
        return VoiceFoundryCommandResponseDTO(
            schemaVersion: "1.0",
            taskId: command.taskId,
            commandId: command.commandId,
            accepted: true,
            replayed: false,
            task: published(tasks[0])
        )
    }

    private func published(_ task: VoiceFoundryTaskDTO) -> VoiceFoundryTaskDTO {
        VoiceFoundryTaskDTO(
            schemaVersion: task.schemaVersion,
            taskId: task.taskId,
            requestId: task.requestId,
            requestDigest: task.requestDigest,
            scope: task.scope,
            stage: "published",
            taskRevision: task.taskRevision + 1,
            cancelRequested: false,
            operationStatus: "confirmed",
            requiredActions: [],
            reasonCode: nil,
            candidates: task.candidates.map { candidate in
                VoiceFoundryCandidateDTO(
                    candidateId: candidate.candidateId,
                    slot: candidate.slot,
                    seed: candidate.seed,
                    state: "published",
                    previewAudioDigest: candidate.previewAudioDigest,
                    providerCandidateId: candidate.providerCandidateId,
                    providerCandidateRevision: candidate.providerCandidateRevision
                )
            }
        )
    }
}

// MARK: - Fixtures

private func auditionWav(frames: Int = 480) -> Data {
    var out = Data("RIFF".utf8)
    let pcm = Data(repeating: 0x11, count: frames * 2)
    func append32(_ value: UInt32) {
        out.append(contentsOf: [
            UInt8(value & 0xFF),
            UInt8((value >> 8) & 0xFF),
            UInt8((value >> 16) & 0xFF),
            UInt8((value >> 24) & 0xFF),
        ])
    }
    func append16(_ value: UInt16) {
        out.append(contentsOf: [UInt8(value & 0xFF), UInt8(value >> 8)])
    }
    append32(UInt32(36 + pcm.count))
    out.append(Data("WAVEfmt ".utf8))
    append32(16)
    append16(1)
    append16(1)
    append32(24_000)
    append32(48_000)
    append16(2)
    append16(16)
    out.append(Data("data".utf8))
    append32(UInt32(pcm.count))
    out.append(pcm)
    return out
}

private let REFERENCE_DIGEST = String(repeating: "9", count: 64)
private let VALIDATION_DIGEST = String(repeating: "d", count: 64)
private let VALIDATION_ID = "vv_" + String(repeating: "e", count: 24)

private func sampleDesign(
    designId: String = "narrator",
    displayName: String = "旁白"
) -> VoiceDesignDTO {
    VoiceDesignDTO(
        schemaVersion: "1.0",
        designId: designId,
        displayName: displayName,
        presentationIdentity: designId,
        usage: "narration",
        locale: "zh-CN",
        designRevision: 1,
        publicTraits: ["低沉", "克制"],
        voiceDescription: "低沉克制，语速偏慢。",
        referenceText: "夜色沉下来，港口的灯一盏盏亮起。",
        validationText: "枪响了三次，然后归于安静。"
    )
}

/// A task that has been registered and is being cast, with nobody waiting on
/// anything. This is what the automatic path produces before it stops at the
/// one gate a person owns.
private func queuedTask(identity: String) -> VoiceFoundryTaskDTO {
    VoiceFoundryTaskDTO(
        schemaVersion: "1.0",
        taskId: "task-\(identity)",
        requestId: "req-\(identity)",
        requestDigest: String(repeating: "f", count: 64),
        scope: VoiceFoundryScopeDTO(
            ownerId: "owner",
            worldId: "world",
            worldlineId: "line",
            presentationIdentity: identity,
            phase: "narration",
            locale: "zh-CN"
        ),
        stage: "requested",
        taskRevision: 1,
        cancelRequested: false,
        operationStatus: "prepared",
        requiredActions: [],
        reasonCode: nil,
        candidates: [
            VoiceFoundryCandidateDTO(
                candidateId: "task-\(identity):candidate:0",
                slot: 1,
                seed: 0,
                state: "ready",
                previewAudioDigest: String(repeating: "b", count: 64),
                providerCandidateId: nil,
                providerCandidateRevision: nil
            )
        ]
    )
}

private func parkedTask(candidates: Int = 1) -> VoiceFoundryTaskDTO {
    VoiceFoundryTaskDTO(
        schemaVersion: "1.0",
        taskId: "task-1",
        requestId: "req-1",
        requestDigest: String(repeating: "a", count: 64),
        scope: VoiceFoundryScopeDTO(
            ownerId: "owner",
            worldId: "world",
            worldlineId: "line",
            presentationIdentity: "narrator",
            phase: "narration",
            locale: "zh-CN"
        ),
        stage: "awaiting_review",
        taskRevision: 7,
        cancelRequested: false,
        operationStatus: "confirmed",
        requiredActions: ["listen_reference", "listen_validation", "review"],
        reasonCode: nil,
        candidates: (0 ..< candidates).map { index in
            VoiceFoundryCandidateDTO(
                candidateId: "task-1:candidate:\(index)",
                slot: index,
                seed: index,
                state: "reviewing",
                previewAudioDigest: String(repeating: "b", count: 64),
                providerCandidateId: "vd_" + String(repeating: "a", count: 24),
                providerCandidateRevision: "vr_" + String(repeating: "c", count: 32)
            )
        }
    )
}

private func asset(_ kind: VoiceFoundryAssetKind, wav: Data) -> VoiceFoundryAssetResponseDTO {
    VoiceFoundryAssetResponseDTO(
        schemaVersion: "1.0",
        taskId: "task-1",
        candidateId: "task-1:candidate:0",
        kind: kind,
        candidateRevision: "vr_" + String(repeating: "c", count: 32),
        validationId: kind == .validation ? VALIDATION_ID : nil,
        audioDigest: kind == .validation ? VALIDATION_DIGEST : REFERENCE_DIGEST,
        audioBytes: wav.count,
        audioBase64: wav.base64EncodedString()
    )
}

// MARK: - Tests

@Suite("Voice Foundry audition")
struct VoiceFoundryAuditionModelTests {
    @MainActor
    private func loadedModel(
        candidates: Int = 1,
        playback: RecordingPlayback = RecordingPlayback()
    ) async -> (VoiceFoundryAuditionModel, FakeFoundryClient) {
        let wav = auditionWav()
        let client = FakeFoundryClient(
            tasks: [parkedTask(candidates: candidates)],
            assets: [
                .reference: asset(.reference, wav: wav),
                .validation: asset(.validation, wav: wav),
            ]
        )
        let model = VoiceFoundryAuditionModel(playback: playback)
        await model.load(using: client)
        model.select("task-1")
        return (model, client)
    }

    /// The one rule this type exists for. A fetch is not a listen, and a verdict
    /// about audio nobody heard is not a verdict.
    @MainActor
    @Test("a verdict cannot be signed before both clips have been heard")
    func cannotSignBeforeHearing() async {
        let playback = RecordingPlayback()
        let (model, _) = await loadedModel(playback: playback)
        #expect(model.canSubmitReview == false)

        await model.listen(.reference, using: FakeFoundryClient(
            tasks: [parkedTask()],
            assets: [.reference: asset(.reference, wav: auditionWav())]
        ))
        #expect(model.canSubmitReview == false)

        let client = FakeFoundryClient(
            tasks: [parkedTask()],
            assets: [
                .reference: asset(.reference, wav: auditionWav()),
                .validation: asset(.validation, wav: auditionWav()),
            ]
        )
        await model.listen(.validation, using: client)
        #expect(model.canSubmitReview == true)
        #expect(  playback.played.count == 2)
    }

    /// Audio that decoded but never reached the output is not a listen either.
    @MainActor
    @Test("a clip that failed to play does not count as heard")
    func failedPlaybackIsNotHeard() async {
        let playback = RecordingPlayback()
        playback.failsToPlay = true
        let client = FakeFoundryClient(
            tasks: [parkedTask()],
            assets: [.reference: asset(.reference, wav: auditionWav())]
        )
        let model = VoiceFoundryAuditionModel(playback: playback)
        await model.load(using: client)
        model.select("task-1")

        await model.listen(.reference, using: client)

        #expect(model.heard.isEmpty)
        #expect(model.canSubmitReview == false)
        #expect(model.phase == .failed(code: "audio_not_playable"))
    }

    /// The digests go back describing the bytes this listener actually heard.
    /// Anything else and the verdict is about a different recording.
    @MainActor
    @Test("the verdict carries the digests and id of the audio that played")
    func verdictCarriesPlayedAssets() async throws {
        let (model, client) = await loadedModel()
        await model.listen(.reference, using: client)
        await model.listen(.validation, using: client)

        await model.submitReview(
            identity: "pass",
            naturalness: "pass",
            using: client
        )

        let submitted = client.submitted
        #expect(submitted.count == 1)
        #expect(submitted[0].action == "review")
        let review = try #require(submitted[0].payload as? VoiceFoundryReviewPayloadDTO)
        #expect(review.humanReview.validationId == VALIDATION_ID)
        #expect(review.humanReview.referenceAudioDigest == REFERENCE_DIGEST)
        #expect(review.humanReview.validationAudioDigest == VALIDATION_DIGEST)
    }

    /// A retry after a dropped connection has to replay the authorization the
    /// person already gave, not ask them to authorize a second one.
    @MainActor
    @Test("a retried verdict replays the same command identity")
    func retryReplaysSameCommand() async throws {
        let (model, client) = await loadedModel()
        await model.listen(.reference, using: client)
        await model.listen(.validation, using: client)
        client.commandError = VoiceFoundryServiceError(
            code: "foundry_transient",
            retryable: true
        )

        await model.submitReview(identity: "pass", naturalness: "pass", using: client)
        #expect(model.phase == .failed(code: "foundry_transient"))
        client.commandError = nil
        await model.submitReview(identity: "pass", naturalness: "pass", using: client)

        let submitted = client.submitted
        #expect(submitted.count == 2)
        #expect(submitted[0].commandId == submitted[1].commandId)
    }

    /// "No voice cast yet" and "the provider is unreachable" call for opposite
    /// next moves, so the engine's own reason is what reaches the operator.
    @MainActor
    @Test("an engine refusal is shown in the engine's own words")
    func showsEngineReason() async {
        let client = FakeFoundryClient(tasks: [], assets: [:])
        client.listError = VoiceFoundryServiceError(
            code: "foundry_unauthorized",
            retryable: false
        )
        let model = VoiceFoundryAuditionModel(playback: RecordingPlayback())

        await model.load(using: client)

        #expect(model.phase == .failed(code: "foundry_unauthorized"))
        #expect(model.awaitingReviewTasks.isEmpty)
    }

    /// Several candidates means nothing was put in front of a listener, so
    /// there is nothing to audition and nothing to judge.
    @MainActor
    @Test("a task holding several candidates is not offered for review")
    func ambiguousTaskIsNotOffered() async {
        let client = FakeFoundryClient(tasks: [parkedTask(candidates: 2)], assets: [:])
        let model = VoiceFoundryAuditionModel(playback: RecordingPlayback())

        await model.load(using: client)

        #expect(model.tasks.count == 1)
        #expect(model.awaitingReviewTasks.isEmpty)
    }
}

// MARK: - Casting

@Suite("Voice Foundry casting")
struct VoiceFoundryCastingTests {
    /// The button and the silent trigger are two doors into one casting. The
    /// App asks with a session and a design and nothing else; every fact about
    /// what gets cast is the engine's to resolve, because the App is never told
    /// the world id and so cannot name a world of its own.
    @MainActor
    @Test("casting sends a session and a design and nothing else")
    func castingSendsOnlySessionAndDesign() async {
        let client = FakeFoundryClient(tasks: [], assets: [:])
        let model = VoiceFoundryAuditionModel(playback: RecordingPlayback())
        await model.load(using: client)

        await model.cast(
            sampleDesign(),
            sessionId: "session-1",
            using: client
        )

        #expect(client.casts.count == 1)
        #expect(client.casts[0].sessionId == "session-1")
        #expect(client.casts[0].designId == "narrator")
    }

    /// A voice that already exists is the system working. Reporting it as a
    /// failure is what teaches a person to press the button twice.
    @MainActor
    @Test("casting somebody who already has a voice is not an error")
    func existingVoiceIsNotAFailure() async {
        let client = FakeFoundryClient(tasks: [parkedTask()], assets: [:])
        let model = VoiceFoundryAuditionModel(playback: RecordingPlayback())
        await model.load(using: client)

        await model.cast(
            sampleDesign(),
            sessionId: "session-1",
            using: client
        )

        #expect(model.phase == .ready)
        #expect(model.castNotice?.contains("未重复铸造") == true)
    }

    /// A new task has to appear without a refresh. The cast *is* the answer,
    /// and re-listing could sort it out of view before anybody read it.
    @MainActor
    @Test("a fresh cast shows up on the desk straight away")
    func freshCastIsVisibleWithoutRefreshing() async {
        let client = FakeFoundryClient(tasks: [], assets: [:])
        let model = VoiceFoundryAuditionModel(playback: RecordingPlayback())
        await model.load(using: client)
        #expect(model.outstandingTasks.isEmpty)

        await model.cast(sampleDesign(), sessionId: "session-1", using: client)

        #expect(model.outstandingTasks.count == 1)
        #expect(model.outstandingTasks.first?.stage == "requested")
    }

    /// With no session there is no world to cast into, and the engine must not
    /// be asked to guess one.
    @MainActor
    @Test("casting without a session asks the engine nothing")
    func noSessionNoRequest() async {
        let client = FakeFoundryClient(tasks: [], assets: [:])
        let model = VoiceFoundryAuditionModel(playback: RecordingPlayback())
        await model.load(using: client)

        await model.cast(sampleDesign(), sessionId: "", using: client)

        #expect(client.casts.isEmpty)
        #expect(model.castNotice != nil)
    }

    /// Registration with the provider costs a real call and cannot be undone
    /// for that candidate, so it is the one step the automatic path stops at
    /// and a person has to press.
    @MainActor
    @Test("a previewed candidate is offered for selection, quoting its digest")
    func candidateSelectionQuotesThePreviewDigest() async throws {
        let task = queuedTask(identity: "narrator")
        let client = FakeFoundryClient(tasks: [task], assets: [:])
        let model = VoiceFoundryAuditionModel(playback: RecordingPlayback())
        await model.load(using: client)
        model.select(task.taskId)

        #expect(model.canSelectCandidate)
        await model.selectCandidate(using: client)

        let submitted = client.submitted
        #expect(submitted.count == 1)
        #expect(submitted[0].action == "select")
        let payload = try #require(
            submitted[0].payload as? VoiceFoundrySelectPayloadDTO
        )
        #expect(payload.candidateId == "task-narrator:candidate:0")
        #expect(payload.previewAudioDigest == String(repeating: "b", count: 64))
    }

    /// A finished or failed task with nothing owed is history. A row on screen
    /// that no button in it can act on is worse than no row.
    @MainActor
    @Test("only tasks that owe something or are in flight are listed")
    func onlyOutstandingTasksAreListed() {
        #expect(
            VoiceFoundryAuditionModel.pendingSummary(for: queuedTask(identity: "旁白"))
                == "旁白 · 铸造中（已登记）"
        )
        #expect(
            VoiceFoundryAuditionModel.pendingSummary(for: parkedTask())
                == "narrator · 待听审"
        )
        #expect(VoiceFoundryAuditionModel.stageLabel("validating") == "跨文本复验")
    }
}
