import Foundation
import Testing
@testable import WorldOfMysteriesCore

private final class VoiceJournal: StoryJournalWriting, @unchecked Sendable {
    private let lock = NSLock()
    private var storedRecord: StoryRequestRecord?

    func load() throws -> StoryRequestRecord? {
        lock.withLock { storedRecord }
    }

    func save(_ record: StoryRequestRecord) throws {
        lock.withLock { storedRecord = record }
    }

    func clear() throws {
        lock.withLock { storedRecord = nil }
    }
}

private final class VoiceSubmissionClient: StorySubmissionClient, @unchecked Sendable {
    private let lock = NSLock()
    private var result: StoryAdviceSubmitViewDTO?
    private var submitError: (any Error)?
    private var textRequests: [StoryAdviceSubmitRequestDTO] = []
    private var voiceRequests: [StoryTurnSubmitRequestDTO] = []
    private var adviceQueries = 0

    init(result: StoryAdviceSubmitViewDTO?) {
        self.result = result
    }

    func setSubmitError(_ error: (any Error)?) {
        lock.withLock { submitError = error }
    }

    var textRequestCount: Int { lock.withLock { textRequests.count } }
    var voiceRequestCount: Int { lock.withLock { voiceRequests.count } }
    var queryCount: Int { lock.withLock { adviceQueries } }
    var lastVoiceRequest: StoryTurnSubmitRequestDTO? { lock.withLock { voiceRequests.last } }

    func storySubmit(
        _ request: StoryAdviceSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        let state = lock.withLock { () -> ((any Error)?, StoryAdviceSubmitViewDTO?) in
            textRequests.append(request)
            return (submitError, result)
        }
        if let error = state.0 { throw error }
        guard let result = state.1 else { throw EngineConnectionError.invalidFrame }
        return result
    }

    func storyTurnSubmit(
        _ request: StoryTurnSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        let state = lock.withLock { () -> ((any Error)?, StoryAdviceSubmitViewDTO?) in
            voiceRequests.append(request)
            return (submitError, result)
        }
        if let error = state.0 { throw error }
        guard let result = state.1 else { throw EngineConnectionError.invalidFrame }
        return result
    }

    func storyAdvice(
        sessionId: String,
        inputTurnId: String
    ) async throws -> StoryAdviceGetViewDTO {
        lock.withLock { adviceQueries += 1 }
        throw EngineConnectionError.timedOut
    }
}

@MainActor
@Suite("Voice input through the shared submission coordinator")
struct VoiceTurnControllerTests {
    private func readyDelivery() throws -> StoryTurnDeliveryDTO {
        let recipeJSON = """
        {
          "speech_unit_id": "speech_1",
          "turn_id": "turn_first_001",
          "story_revision": 1,
          "narrative_block_id": "narrative_1",
          "segment_index": 0,
          "performance_plan_id": "plan_1",
          "spoken_text": "雨停了。",
          "voice_id": "voice_1",
          "expected_voice_revision": "voice_revision_1",
          "expected_model_revision": "model_revision_1",
          "speed": 1.0,
          "language": "zh-CN"
        }
        """
        let recipe = try JSONDecoder().decode(
            VoiceRenderRecipeDTO.self,
            from: Data(recipeJSON.utf8)
        )
        return try StoryTurnDeliveryDTO(
            state: .ready,
            narrativeBlockId: "narrative_1",
            speechUnitId: "speech_1",
            spokenText: "雨停了。",
            renderRecipe: recipe
        )
    }

    private func makeController(
        client: VoiceSubmissionClient,
        journal: VoiceJournal,
        renderDelivery: @escaping @Sendable (VoiceRenderRecipeDTO) async throws -> Void
    ) -> (VoiceTurnController, StorySubmissionCoordinator) {
        let coordinator = StorySubmissionCoordinator(
            client: client,
            journal: journal,
            idFactory: { "input_turn_1" }
        )
        let controller = VoiceTurnController(
            client: EngineIPCClient(),
            submissionCoordinator: coordinator,
            renderDelivery: renderDelivery
        )
        return (controller, coordinator)
    }

    private let context = VoiceTurnController.TurnContext(
        sessionId: "session_1",
        storyRevision: 0,
        storeRevision: 1
    )

    @Test("A final transcript is submitted once with voice mode and raw bytes")
    func finalTranscriptSubmitsOnce() async throws {
        let result = try StorySessionModelTests.submitResult(turn: 1)
        let client = VoiceSubmissionClient(result: result)
        let journal = VoiceJournal()
        let (controller, coordinator) = makeController(
            client: client,
            journal: journal,
            renderDelivery: { _ in }
        )

        let transcript = "  ASR 原始转写  "
        let committed = await controller.submitFinalTranscript(transcript, context: context)

        #expect(committed == transcript)
        #expect(client.voiceRequestCount == 1)
        #expect(client.textRequestCount == 0)
        #expect(client.lastVoiceRequest?.inputMode == .voice)
        #expect(client.lastVoiceRequest?.rawInput == transcript)
        #expect(client.lastVoiceRequest?.inputTurnId == "input_turn_1")
        #expect(coordinator.state == .committed)
    }

    @Test("A disconnect keeps the frozen voice identity and never invents a replacement")
    func disconnectPreservesVoiceIdentity() async throws {
        let client = VoiceSubmissionClient(result: nil)
        client.setSubmitError(EngineConnectionError.timedOut)
        let journal = VoiceJournal()
        let (controller, coordinator) = makeController(
            client: client,
            journal: journal,
            renderDelivery: { _ in }
        )

        #expect(await controller.submitFinalTranscript("ASR 原文", context: context) == nil)
        let before = try #require(try journal.load()?.frozenSubmission)
        coordinator.detachForConnectionChange()
        let after = try #require(try journal.load()?.frozenSubmission)

        #expect(before == after)
        #expect(before.inputMode == .voice)
        #expect(before.inputTurnId == "input_turn_1")
        #expect(client.voiceRequestCount == 1)
        #expect(client.queryCount == 1)
    }

    @Test("A playback error leaves the committed turn committed and does not resubmit")
    func playbackFailureDoesNotResubmitDomainTurn() async throws {
        let delivery = try readyDelivery()
        let result = try StorySessionModelTests.submitResult(turn: 1, delivery: delivery)
        let client = VoiceSubmissionClient(result: result)
        let journal = VoiceJournal()
        let (controller, coordinator) = makeController(
            client: client,
            journal: journal,
            renderDelivery: { _ in throw EngineConnectionError.timedOut }
        )

        let transcript = await controller.submitFinalTranscript("ASR 原文", context: context)

        #expect(transcript == "ASR 原文")
        #expect(controller.phase == .unavailable(reason: "render_failed"))
        #expect(coordinator.state == .committed)
        #expect(client.voiceRequestCount == 1)
        #expect(client.queryCount == 0)
    }

    @Test("An empty ASR transcript creates no identity or journal entry")
    func emptyTranscriptCreatesNoSubmission() async throws {
        let client = VoiceSubmissionClient(result: nil)
        let journal = VoiceJournal()
        let (controller, _) = makeController(
            client: client,
            journal: journal,
            renderDelivery: { _ in }
        )

        #expect(await controller.submitFinalTranscript(" \n ", context: context) == nil)
        #expect(client.voiceRequestCount == 0)
        #expect(try journal.load() == nil)
    }

    @Test("A committed delivery speaks as soon as it is ready")
    func deliverySpeaksWithoutResubmitting() async throws {
        let client = VoiceSubmissionClient(result: nil)
        let rendered = RenderLog()
        let (controller, coordinator) = makeController(
            client: client,
            journal: VoiceJournal(),
            renderDelivery: { recipe in rendered.append(recipe) }
        )
        let recipe = try #require(try readyDelivery().renderRecipe)

        await controller.speakDelivery(recipe)

        #expect(rendered.recipes.map(\.speechUnitId) == ["speech_1"])
        #expect(controller.lastSpokenText == "雨停了。")
        #expect(controller.phase == .idle)
        // Speaking audio projects an already committed turn: it must never
        // create, query or replay a domain submission.
        #expect(coordinator.state == .idle)
        #expect(client.voiceRequestCount == 0)
        #expect(client.textRequestCount == 0)
        #expect(client.queryCount == 0)
    }

    @Test("Re-reading the same delivery does not speak it twice")
    func deliverySpeaksOnce() async throws {
        let client = VoiceSubmissionClient(result: nil)
        let rendered = RenderLog()
        let (controller, _) = makeController(
            client: client,
            journal: VoiceJournal(),
            renderDelivery: { recipe in rendered.append(recipe) }
        )
        let recipe = try #require(try readyDelivery().renderRecipe)

        // The App re-reads the projection until the work settles, so the same
        // ready delivery is offered many times over.
        for _ in 0..<5 {
            await controller.speakDelivery(recipe)
        }

        #expect(rendered.recipes.count == 1)
    }

    @Test("A later turn's own delivery still speaks")
    func eachDeliverySpeaksOnce() async throws {
        let client = VoiceSubmissionClient(result: nil)
        let rendered = RenderLog()
        let (controller, _) = makeController(
            client: client,
            journal: VoiceJournal(),
            renderDelivery: { recipe in rendered.append(recipe) }
        )
        let first = try #require(try readyDelivery().renderRecipe)
        let second = try Self.recipe(speechUnitId: "speech_2", turnId: "turn_first_002")

        await controller.speakDelivery(first)
        await controller.speakDelivery(second)
        await controller.speakDelivery(first)

        #expect(rendered.recipes.map(\.speechUnitId) == ["speech_1", "speech_2"])
    }

    @Test("A failed render is reported once and not retried on every re-read")
    func deliveryFailureIsBoundedAndHonest() async throws {
        let client = VoiceSubmissionClient(result: nil)
        let attempts = RenderLog()
        let (controller, coordinator) = makeController(
            client: client,
            journal: VoiceJournal(),
            renderDelivery: { recipe in
                attempts.append(recipe)
                throw EngineConnectionError.timedOut
            }
        )
        let recipe = try #require(try readyDelivery().renderRecipe)

        for _ in 0..<4 {
            await controller.speakDelivery(recipe)
        }

        #expect(attempts.recipes.count == 1)
        #expect(controller.phase == .unavailable(reason: "render_failed"))
        #expect(coordinator.state == .idle)
        #expect(client.voiceRequestCount == 0)
    }

    @Test("The panel starts a sealed delivery as soon as the work reports it ready")
    func panelStartsDeliveryWhenAudioIsReady() throws {
        let panel = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("macos-app/WorldOfMysteries/StorySessionPanel.swift"),
            encoding: .utf8
        )

        // Without this the sealed recipe is rendered by nobody and the player
        // only ever reads the turn.
        #expect(panel.contains("work.audioState == .ready"))
        #expect(panel.contains("voice.speakDelivery(recipe)"))
    }

    private static func recipe(
        speechUnitId: String,
        turnId: String
    ) throws -> VoiceRenderRecipeDTO {
        try JSONDecoder().decode(
            VoiceRenderRecipeDTO.self,
            from: Data(
                """
                {
                  "speech_unit_id": "\(speechUnitId)",
                  "turn_id": "\(turnId)",
                  "story_revision": 1,
                  "narrative_block_id": "narrative_1",
                  "segment_index": 0,
                  "performance_plan_id": "performance_1",
                  "spoken_text": "雨停了。",
                  "voice_id": "voice_1",
                  "expected_voice_revision": "voice_revision_1",
                  "expected_model_revision": "model_revision_1",
                  "speed": 1.0,
                  "language": "zh-CN"
                }
                """.utf8
            )
        )
    }
}

private final class RenderLog: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [VoiceRenderRecipeDTO] = []

    func append(_ recipe: VoiceRenderRecipeDTO) {
        lock.withLock { storage.append(recipe) }
    }

    var recipes: [VoiceRenderRecipeDTO] {
        lock.withLock { storage }
    }
}
