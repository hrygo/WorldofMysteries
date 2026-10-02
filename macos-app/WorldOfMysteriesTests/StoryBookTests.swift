import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// Story Book (PRD §20) is a pure read of a finalized Episode. These tests pin
/// the two halves of that promise at the App edge: the DTO mirrors the wire
/// contract exactly, and the model never invents a book the engine did not
/// commit.

// MARK: - Doubles

final class FakeStoryBookClient: StoryBookClient, @unchecked Sendable {
    private let lock = NSLock()
    private var result: Result<StoryBookDTO, any Error>
    private var requestedSessionIds: [String] = []

    init(result: Result<StoryBookDTO, any Error>) {
        self.result = result
    }

    var sessionIds: [String] {
        lock.withLock { requestedSessionIds }
    }

    func storyBook(sessionId: String, traceId: String) async throws -> StoryBookDTO {
        let pending = lock.withLock { () -> Result<StoryBookDTO, any Error> in
            requestedSessionIds.append(sessionId)
            return result
        }
        return try await pending.get()
    }
}

private enum StoryBookFixture {
    static let wire = """
    {
      "schema_version": "1.0",
      "episode_id": "episode-001",
      "world_id": "world-tingen",
      "worldline_id": "wl-1349-main",
      "title": "红月案发夜",
      "protagonist_ids": ["protagonist-klein"],
      "start_world_time": "1349-08-28 20:00",
      "end_world_time": "1349-08-29 02:00",
      "chapters": [
        {
          "block_id": "block-1",
          "scene_id": "welch-bedroom",
          "segments": [
            { "type": "narration", "speaker": null, "text": "枪声在韦尔奇卧室内炸开。" },
            { "type": "character", "speaker": "克莱恩·莫雷蒂", "text": "我醒过来了。" }
          ]
        }
      ],
      "ending": { "type": "partial", "main_problem": "笔记本仍下落不明" },
      "unresolved_threads": ["安提哥努斯家族笔记的下落"]
    }
    """

    static func makeBook() throws -> StoryBookDTO {
        try JSONDecoder().decode(StoryBookDTO.self, from: Data(wire.utf8))
    }

    static func serviceError(_ code: String) -> StoryControlServiceError {
        StoryControlServiceError(code: code, retryable: false)
    }
}

// MARK: - Contract

@Suite("Story Book contract mirror")
struct StoryBookContractTests {
    @Test("StoryBookDTO decodes the snake_case wire shape")
    func decodesWireShape() throws {
        let book = try StoryBookFixture.makeBook()

        #expect(book.schemaVersion == "1.0")
        #expect(book.episodeId == "episode-001")
        #expect(book.worldId == "world-tingen")
        #expect(book.worldlineId == "wl-1349-main")
        #expect(book.title == "红月案发夜")
        #expect(book.protagonistIds == ["protagonist-klein"])
        #expect(book.startWorldTime == "1349-08-28 20:00")
        #expect(book.endWorldTime == "1349-08-29 02:00")
        #expect(book.unresolvedThreads == ["安提哥努斯家族笔记的下落"])

        let chapter = try #require(book.chapters.first)
        #expect(book.chapters.count == 1)
        #expect(chapter.blockId == "block-1")
        #expect(chapter.sceneId == "welch-bedroom")
        #expect(chapter.segments.count == 2)

        let narration = try #require(chapter.segments.first)
        #expect(narration.type == "narration")
        #expect(narration.speaker == nil)
        #expect(narration.text == "枪声在韦尔奇卧室内炸开。")

        let spoken = try #require(chapter.segments.last)
        #expect(spoken.type == "character")
        #expect(spoken.speaker == "克莱恩·莫雷蒂")

        #expect(book.ending.type == "partial")
        #expect(book.ending.mainProblem == "笔记本仍下落不明")
    }

    @Test("Optional Story Book fields may be absent")
    func decodesMinimalShape() throws {
        let json = """
        {
          "schema_version": "1.0",
          "episode_id": "episode-002",
          "world_id": "world-tingen",
          "worldline_id": "wl-1349-main",
          "title": "无解的一夜",
          "protagonist_ids": ["protagonist-klein"],
          "chapters": [
            {
              "block_id": "block-9",
              "segments": [{ "type": "transition", "text": "天亮了。" }]
            }
          ],
          "ending": { "type": "closed" }
        }
        """
        let book = try JSONDecoder().decode(StoryBookDTO.self, from: Data(json.utf8))

        #expect(book.startWorldTime == nil)
        #expect(book.endWorldTime == nil)
        #expect(book.unresolvedThreads == nil)
        #expect(book.chapters.first?.sceneId == nil)
        #expect(book.chapters.first?.segments.first?.speaker == nil)
        #expect(book.ending.mainProblem == nil)
    }

    @Test("StoryBookRequestDTO encodes exactly the two fields the engine validates")
    func encodesRequest() throws {
        let encoded = try JSONEncoder().encode(StoryBookRequestDTO(sessionId: "session-7"))
        let wire = try JSONDecoder().decode(
            [String: String].self,
            from: encoded
        )

        #expect(wire == ["schema_version": "1.0", "session_id": "session-7"])
    }

    @Test("Story Book is a live entry, its archive siblings stay honestly planned")
    func navigationAvailabilityIsHonest() {
        // Visual_QA_Source_Guards_v1 §4: an entry marked `planned` must say so
        // in the sidebar, the menu and its landing page. Now that the page reads
        // a committed Episode, the badge would be a false claim.
        #expect(NavigationItem.storyBook.availability == .available)
        #expect(!NavigationItem.storyBook.isPlanned)

        for item: NavigationItem in [.character, .cards, .worldline, .notes] {
            #expect(item.isPlanned)
        }
    }
}

// MARK: - Model

@Suite("Story Book model state mapping")
@MainActor
struct StoryBookModelTests {
    @Test("A committed book loads into .loaded")
    func loadsCommittedBook() async throws {
        let book = try StoryBookFixture.makeBook()
        let client = FakeStoryBookClient(result: .success(book))
        let model = StoryBookModel(client: client, idFactory: { "trace-1" })

        #expect(model.state == .idle)
        await model.load(sessionId: "session-7")

        #expect(model.state == .loaded(book))
        #expect(client.sessionIds == ["session-7"])
    }

    @Test("An unfinalized session is .notFinalized, not a failure")
    func mapsNotActiveToNotFinalized() async {
        let client = FakeStoryBookClient(
            result: .failure(StoryBookFixture.serviceError("story_session_not_active"))
        )
        let model = StoryBookModel(client: client)

        await model.load(sessionId: "session-7")

        #expect(model.state == .notFinalized)
    }

    @Test("Any other service code surfaces as .failed with that code")
    func mapsOtherServiceCodesToFailed() async {
        let client = FakeStoryBookClient(
            result: .failure(StoryBookFixture.serviceError("storage_failure"))
        )
        let model = StoryBookModel(client: client)

        await model.load(sessionId: "session-7")

        #expect(model.state == .failed(code: "storage_failure"))
    }

    @Test("A transport fault degrades to service_unavailable")
    func mapsTransportFault() async {
        let client = FakeStoryBookClient(
            result: .failure(EngineConnectionError.notConnected)
        )
        let model = StoryBookModel(client: client)

        await model.load(sessionId: "session-7")

        #expect(model.state == .failed(code: "service_unavailable"))
    }

    @Test("An empty session id fails closed without calling the engine")
    func rejectsEmptySessionId() async {
        let client = FakeStoryBookClient(
            result: .failure(StoryBookFixture.serviceError("storage_failure"))
        )
        let model = StoryBookModel(client: client)

        await model.load(sessionId: "")

        #expect(model.state == .failed(code: "schema_invalid"))
        #expect(client.sessionIds.isEmpty)
    }

    @Test("Losing the session clears the rendered book instead of freezing it")
    func resetDropsStaleBook() async throws {
        let book = try StoryBookFixture.makeBook()
        let client = FakeStoryBookClient(result: .success(book))
        let model = StoryBookModel(client: client)

        await model.load(sessionId: "session-7")
        #expect(model.state == .loaded(book))

        // The transport dropped: `storyModel.view` is gone, so the view resets.
        model.reset()
        #expect(model.state == .idle)
    }
}
