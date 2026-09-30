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
    var listError: VoiceFoundryServiceError?
    var commandError: VoiceFoundryServiceError?
    private(set) var submitted: [(commandId: String, action: String, payload: Any)] = []

    init(tasks: [VoiceFoundryTaskDTO], assets: [VoiceFoundryAssetKind: VoiceFoundryAssetResponseDTO]) {
        self.tasks = tasks
        self.assets = assets
    }

    func voiceFoundryTask(_ taskId: String) async throws -> VoiceFoundryGetResponseDTO {
        VoiceFoundryGetResponseDTO(schemaVersion: "1.0", task: tasks[0])
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
