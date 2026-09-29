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
    @ObservationIgnored private let submissionCoordinator: StorySubmissionCoordinator
    @ObservationIgnored private let renderDelivery:
        (@Sendable (VoiceRenderRecipeDTO) async throws -> Void)?
    @ObservationIgnored private let makeASRConnection: @Sendable () -> SpeechRailRealtimeASRConnection
    @ObservationIgnored private let makePlayback: @Sendable () -> NativePlaybackActor
    @ObservationIgnored private var captureSession: VoiceInputPTTSession?
    @ObservationIgnored private var playback: NativePlaybackActor?
    @ObservationIgnored private var renderGeneration: Int64 = 0
    @ObservationIgnored private var busy = false
    /// Speech units this controller has already tried to speak, oldest first.
    ///
    /// The App re-reads a turn's post-COMMIT projection until the work settles,
    /// so the same ready delivery is offered again and again. Without this the
    /// player would hear their own turn repeated once per poll.
    @ObservationIgnored private var spokenSpeechUnits: [String] = []
    @ObservationIgnored private static let spokenHistoryLimit = 64

    public init(
        client: EngineIPCClient,
        submissionCoordinator: StorySubmissionCoordinator? = nil,
        renderDelivery: (@Sendable (VoiceRenderRecipeDTO) async throws -> Void)? = nil,
        makeASRConnection: @escaping @Sendable () -> SpeechRailRealtimeASRConnection = {
            SpeechRailRealtimeASRConnection()
        },
        makePlayback: @escaping @Sendable () -> NativePlaybackActor = {
            NativePlaybackActor(backend: AVAudioEnginePCMPlaybackBackend())
        }
    ) {
        self.client = client
        self.submissionCoordinator = submissionCoordinator
            ?? StorySubmissionCoordinator(client: client)
        self.renderDelivery = renderDelivery
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
        return await submitFinalTranscript(transcript, context: context)
    }

    /// Submit an already-final transcript through the shared frozen-request
    /// owner. Kept internal so tests can exercise the post-ASR boundary without
    /// opening a real microphone or SpeechRail connection.
    @discardableResult
    func submitFinalTranscript(_ transcript: String, context: TurnContext) async -> String? {
        guard transcript.unicodeScalars.contains(where: { !$0.properties.isWhitespace }),
              !transcript.unicodeScalars.contains("\u{0}"),
              transcript.utf8.count <= StoryControl.maxRawInput else {
            busy = false
            phase = .idle
            return nil
        }
        lastTranscript = transcript
        phase = .committing
        let frozen = await submissionCoordinator.submit(
            rawInput: transcript,
            inputMode: .voice,
            sessionId: context.sessionId,
            expectedStoryRevision: context.storyRevision,
            expectedStoreRevision: context.storeRevision
        )
        guard let frozen,
              submissionCoordinator.state == .committed,
              submissionCoordinator.latestReceipt?.inputTurnId == frozen.inputTurnId else {
            busy = false
            switch submissionCoordinator.state {
            case .outcomeUnknown, .querying:
                phase = .unavailable(reason: "outcome_unknown")
            case .blocked(let code):
                phase = .unavailable(reason: code)
            case .received, .notFound:
                phase = .unavailable(reason: "submission_pending")
            case .idle, .selectingMethod, .submitting, .committed:
                phase = .unavailable(reason: "submission_not_committed")
            }
            return nil
        }

        let committed = submissionCoordinator.latestResult
        guard let committed,
              let delivery = committed.delivery,
              delivery.state == .ready,
              let recipe = delivery.renderRecipe else {
            // The turn committed. Only the audible rendering is missing, and the
            // Engine said so explicitly rather than pretending it succeeded.
            busy = false
            if let delivery = committed?.delivery, delivery.state == .unavailable {
                phase = .unavailable(reason: delivery.reason ?? "voice_unavailable")
            } else {
                phase = .idle
            }
            return transcript
        }

        phase = .rendering
        do {
            if let renderDelivery {
                try await renderDelivery(recipe)
            } else {
                try await renderAndPlay(recipe: recipe)
            }
            lastSpokenText = recipe.spokenText
            phase = .idle
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

    /// Speak a turn's already-committed delivery.
    ///
    /// Strictly post-COMMIT, exactly like the push-to-talk path: the recipe is
    /// a projection of a SpeechUnit the Engine already sealed, so this renders
    /// and plays audio without creating, querying or replaying any world fact.
    /// That is what lets the audio start the moment it is ready and overlap the
    /// text, instead of waiting for the player's next turn.
    ///
    /// Each speech unit is attempted once. A failure is reported honestly and
    /// left to the Engine's explicit `work.retry`, never retried on the App's
    /// own polling cadence — a renderer that is failing must not be hammered
    /// once a second, and the text has to keep working regardless.
    public func speakDelivery(_ recipe: VoiceRenderRecipeDTO) async {
        // Never talk over the player, and never render two things at once.
        guard captureSession == nil, !busy else { return }
        guard !spokenSpeechUnits.contains(recipe.speechUnitId) else { return }
        spokenSpeechUnits.append(recipe.speechUnitId)
        if spokenSpeechUnits.count > Self.spokenHistoryLimit {
            spokenSpeechUnits.removeFirst(spokenSpeechUnits.count - Self.spokenHistoryLimit)
        }
        phase = .rendering
        do {
            if let renderDelivery {
                try await renderDelivery(recipe)
            } else {
                try await renderAndPlay(recipe: recipe)
            }
            lastSpokenText = recipe.spokenText
            phase = .idle
        } catch {
            phase = .unavailable(reason: "render_failed")
        }
    }

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
