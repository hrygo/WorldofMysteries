import Foundation

/// One push-to-talk voice turn, end to end.
///
/// The order below is the contract, not a convenience:
///
/// 1. capture microphone PCM and stream it to SpeechRail ASR;
/// 2. commit the transcript through `story.turn.submit` as an **input**, so the
///    Domain commit happens on the same durable path as a typed turn;
/// 3. only after that commit, ask the Engine to render the sealed SpeechUnit;
/// 4. stream the Engine's PCM out over the media channel and play it locally.
///
/// Steps 3 and 4 are strictly post-COMMIT. If either fails, the turn stays
/// committed and the player simply does not hear it; nothing here can un-commit
/// a world fact.
///
/// **Device policy.** This controller never enumerates, ranks or selects an
/// input or an output. It uses the system default capture device and the system
/// default output through `AVAudioEngine`, so every machine works with whatever
/// hardware the player happens to own. Changing devices is the OS's job, done in
/// System Settings, and the App follows.
@MainActor
@Observable
public final class VoiceTurnController {
    public enum Phase: Sendable, Equatable {
        case idle
        case listening
        case transcribing
        case committing
        case rendering
        case speaking
        case unavailable(reason: String)

        public var isBusy: Bool {
            switch self {
            case .listening, .transcribing, .committing, .rendering, .speaking: true
            case .idle, .unavailable: false
            }
        }
    }

    /// Everything the controller needs from the session it is attached to.
    public struct TurnContext: Sendable, Equatable {
        public let sessionId: String
        public let storyRevision: Int
        public let storeRevision: Int

        public init(sessionId: String, storyRevision: Int, storeRevision: Int) {
            self.sessionId = sessionId
            self.storyRevision = storyRevision
            self.storeRevision = storeRevision
        }
    }

    public private(set) var phase: Phase = .idle
    public private(set) var lastTranscript: String?
    public private(set) var lastSpokenText: String?

    @ObservationIgnored private let client: EngineIPCClient
    @ObservationIgnored private let makeASRConnection: @Sendable () -> SpeechRailRealtimeASRConnection
    @ObservationIgnored private let makePlayback: @Sendable () -> NativePlaybackActor
    @ObservationIgnored private var captureSession: VoiceInputPTTSession?
    @ObservationIgnored private var playback: NativePlaybackActor?
    @ObservationIgnored private var renderGeneration: Int64 = 0
    @ObservationIgnored private var busy = false

    public init(
        client: EngineIPCClient,
        makeASRConnection: @escaping @Sendable () -> SpeechRailRealtimeASRConnection = {
            SpeechRailRealtimeASRConnection()
        },
        makePlayback: @escaping @Sendable () -> NativePlaybackActor = {
            NativePlaybackActor(backend: AVAudioEnginePCMPlaybackBackend())
        }
    ) {
        self.client = client
        self.makeASRConnection = makeASRConnection
        self.makePlayback = makePlayback
    }

    /// The Engine renders at the W-V03 fixed rate; the App must ask for exactly
    /// that format or the media grant is rejected before a socket is opened.
    public static let renderFormat = MediaFormat(codec: "pcm_s16le", sampleRate: 24_000, channels: 1)

    /// Whether the connected Engine advertised the whole sealed-render path.
    public func isAvailable() async -> Bool {
        await client.voiceRenderAvailable
    }

    // MARK: - Push to talk

    public func startListening() async {
        guard !busy, phase == .idle || isUnavailable else { return }
        guard await isAvailable() else {
            phase = .unavailable(reason: "voice_not_ready")
            return
        }
        do {
            // The system default capture device, never a chosen one: the App
            // supports whatever hardware the player owns.
            let microphone = try MicrophoneCaptureSession()
            let session = VoiceInputPTTSession(
                connection: makeASRConnection(),
                microphone: microphone
            )
            captureSession = session
            phase = .listening
            busy = true
            _ = try await session.start()
        } catch {
            captureSession = nil
            phase = .unavailable(reason: "capture_unavailable")
        }
    }

    /// Stop capture, transcribe, commit and speak. The returned transcript is
    /// the text that was actually committed, or `nil` when nothing was.
    @discardableResult
    public func finishAndSpeak(context: TurnContext) async -> String? {
        guard busy, let session = captureSession else { return nil }
        captureSession = nil
        phase = .transcribing
        let terminal = await session.finish()

        let transcript: String
        switch terminal {
        case .transcript(let final):
            transcript = final.text
        case .empty, .cancelled:
            busy = false
            phase = .idle
            return nil
        case .failed:
            busy = false
            phase = .unavailable(reason: "asr_failed")
            return nil
        }
        lastTranscript = transcript

        phase = .committing
        let committed: StoryAdviceSubmitViewDTO
        do {
            committed = try await client.storyTurnSubmit(
                try StoryTurnSubmitRequestDTO(
                    sessionId: context.sessionId,
                    inputTurnId: UUID().uuidString,
                    rawInput: transcript,
                    inputMode: .voice,
                    expectedStoryRevision: context.storyRevision,
                    expectedStoreRevision: context.storeRevision
                )
            )
        } catch {
            busy = false
            phase = .unavailable(reason: "commit_failed")
            return nil
        }

        guard let delivery = committed.delivery, delivery.state == .ready,
              let recipe = delivery.renderRecipe else {
            // The turn committed. Only the audible rendering is missing, and the
            // Engine said so explicitly rather than pretending it succeeded.
            busy = false
            phase = .idle
            return transcript
        }

        phase = .rendering
        do {
            try await renderAndPlay(recipe: recipe)
            lastSpokenText = recipe.spokenText
            phase = .speaking
        } catch {
            phase = .unavailable(reason: "render_failed")
        }
        busy = false
        return transcript
    }

    public func cancel() async {
        guard let session = captureSession else { return }
        captureSession = nil
        await session.cancel()
        busy = false
        phase = .idle
    }

    // MARK: - Post-COMMIT rendering

    private func renderAndPlay(recipe: VoiceRenderRecipeDTO) async throws {
        renderGeneration += 1
        let generation = renderGeneration

        // The media identity must exist before `voice.render`: the Engine binds
        // the sealed unit to exactly one stream, and the media server only
        // accepts a stream whose ticket was minted for that same id.
        let grant = try await client.openMedia(
            direction: .engineToApp,
            generation: generation,
            format: Self.renderFormat
        )
        _ = try await client.renderVoice(
            VoiceRenderControlRequestDTO(
                recipe: recipe,
                mediaStreamId: grant.streamId,
                generation: Int(grant.generation)
            )
        )

        let playback = makePlayback()
        self.playback = playback
        let session = EngineMediaPlaybackSession(
            grant: grant,
            playback: playback,
            playbackMode: .normal
        )
        switch await session.run() {
        case .ended:
            self.playback = nil
        case .cancelled, .failed:
            self.playback = nil
        }
    }

    private var isUnavailable: Bool {
        if case .unavailable = phase { return true }
        return false
    }
}
