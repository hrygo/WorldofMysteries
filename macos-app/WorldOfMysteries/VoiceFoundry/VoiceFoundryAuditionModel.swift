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
    public private(set) var selectedTaskId: String?
    public private(set) var assets: [VoiceFoundryAssetKind: VoiceFoundryAssetResponseDTO] = [:]
    /// What actually reached the speakers. A verdict requires this to cover
    /// both assets — a fetch is not a listen.
    public private(set) var heard: Set<VoiceFoundryAssetKind> = []
    public private(set) var phase: Phase = .idle
    public private(set) var lastPublishedVoiceId: String?

    /// Tasks a person could act on right now, newest state first. Everything
    /// else in the list is history, and mixing the two is how a half-finished
    /// casting gets mistaken for one awaiting judgement.
    public var awaitingReviewTasks: [VoiceFoundryTaskDTO] {
        tasks.filter { $0.stage == "awaiting_review" && $0.auditionedCandidate != nil }
    }

    public var selectedTask: VoiceFoundryTaskDTO? {
        guard let selectedTaskId else { return nil }
        return tasks.first { $0.taskId == selectedTaskId }
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
    }

    public func select(_ taskId: String?) {
        guard selectedTaskId != taskId else { return }
        selectedTaskId = taskId
        assets = [:]
        heard = []
        reviewCommandId = nil
        lastPublishedVoiceId = nil
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
