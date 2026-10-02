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
    /// Shaped like what the Engine actually projects — all four reading-list
    /// sections included.
    ///
    /// It used to stop at `unresolved_threads`, which is exactly why the App
    /// shipped a Story Book it could not open: `StoryBookDTO` mirrors the wire
    /// strictly, the projection has always emitted these four keys, and a
    /// fixture that omitted them kept `swift test` green against a decoder
    /// that rejected the real payload. A fixture is a claim about the producer;
    /// when it stops resembling the producer it stops being evidence.
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
      "unresolved_threads": ["安提哥努斯家族笔记的下落"],
      "discovered_secrets": [
        {
          "proposition": "克莱恩·莫雷蒂并非本人",
          "holder": "克莱恩·莫雷蒂",
          "certainty": 0.95,
          "status": "confirmed",
          "acquired_world_time": "1349-08-29 01:20"
        }
      ],
      "key_characters": [
        { "label": "克莱恩·莫雷蒂", "change_count": 3 }
      ],
      "relationship_changes": [
        {
          "from": "克莱恩·莫雷蒂",
          "to": "邓林·史密斯",
          "dimensions": { "trust": 0.4, "fear": 0.2 }
        }
      ],
      "world_impacts": [
        {
          "event_type": "waypoint_gateway_opened",
          "world_time": "1349-08-29 02:00",
          "importance": "world",
          "persistence": "world",
          "actors": ["克莱恩·莫雷蒂"],
          "targets": []
        }
      ]
    }
    """

    static func makeBook() throws -> StoryBookDTO {
        try JSONDecoder().decode(StoryBookDTO.self, from: Data(wire.utf8))
    }

    /// The wire payload produced by the real `project_story_book`, committed so
    /// the App is checked against its producer rather than against a human's
    /// memory of it.
    ///
    /// The Engine owns it: `test_storybook_projection.py` rebuilds this payload
    /// from the live projection and fails when the two disagree, so the file
    /// cannot rot into a snapshot of a producer that no longer exists.
    static func shippedWire() -> Data? {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return try? Data(
            contentsOf: root
                .appendingPathComponent("macos-app/WorldOfMysteriesTests/Fixtures/storybook_wire.json")
        )
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

        let secret = try #require(book.discoveredSecrets.first)
        #expect(book.discoveredSecrets.count == 1)
        #expect(secret.proposition == "克莱恩·莫雷蒂并非本人")
        #expect(secret.holder == "克莱恩·莫雷蒂")
        #expect(secret.certainty == 0.95)
        #expect(secret.status == "confirmed")
        #expect(secret.acquiredWorldTime == "1349-08-29 01:20")

        let character = try #require(book.keyCharacters.first)
        #expect(character.label == "克莱恩·莫雷蒂")
        #expect(character.changeCount == 3)

        let relationship = try #require(book.relationshipChanges.first)
        #expect(relationship.from == "克莱恩·莫雷蒂")
        #expect(relationship.to == "邓林·史密斯")
        #expect(relationship.dimensions.trust == 0.4)
        #expect(relationship.dimensions.changed.map(\.name) == ["信任", "恐惧"])

        let impact = try #require(book.worldImpacts.first)
        #expect(impact.eventType == "waypoint_gateway_opened")
        #expect(impact.importance == "world")
        #expect(impact.persistence == "world")
        #expect(impact.actors == ["克莱恩·莫雷蒂"])
        #expect(impact.targets.isEmpty)
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
        // A book written before these sections existed still decodes, and reads
        // as four empty sections — which is what the Engine projected for it.
        #expect(book.discoveredSecrets.isEmpty)
        #expect(book.keyCharacters.isEmpty)
        #expect(book.relationshipChanges.isEmpty)
        #expect(book.worldImpacts.isEmpty)
    }

    @Test("Protagonist labels decode positionally, and an unnamed one stays unnamed")
    func decodesProtagonistLabels() throws {
        let json = """
        {
          "schema_version": "1.0",
          "episode_id": "episode-005",
          "world_id": "world-tingen",
          "worldline_id": "wl-1349-main",
          "title": "两个主角",
          "protagonist_ids": ["char_named", "char_unnamed"],
          "protagonist_labels": ["克莱恩·莫雷蒂", null],
          "chapters": [
            { "block_id": "block-1", "segments": [{ "type": "narration", "text": "夜。" }] }
          ],
          "ending": { "type": "closed" }
        }
        """
        let book = try JSONDecoder().decode(StoryBookDTO.self, from: Data(json.utf8))

        // Position is the whole meaning: index i names protagonistIds[i]. The
        // unnamed one keeps its slot as nil — never the canonical id.
        #expect(book.protagonistLabels.count == book.protagonistIds.count)
        #expect(book.protagonistLabels[0] == "克莱恩·莫雷蒂")
        #expect(book.protagonistLabels[1] == nil)
    }

    @Test("A book written before protagonist labels existed reads as no labels")
    func absentProtagonistLabelsReadAsEmpty() throws {
        let json = """
        {
          "schema_version": "1.0",
          "episode_id": "episode-006",
          "world_id": "world-tingen",
          "worldline_id": "wl-1349-main",
          "title": "旧书",
          "protagonist_ids": ["char_named"],
          "chapters": [
            { "block_id": "block-1", "segments": [{ "type": "narration", "text": "夜。" }] }
          ],
          "ending": { "type": "closed" }
        }
        """
        let book = try JSONDecoder().decode(StoryBookDTO.self, from: Data(json.utf8))

        #expect(book.protagonistLabels.isEmpty)
    }

    @Test("A misaligned protagonist label array is refused, not silently shifted")
    func refusesMisalignedProtagonistLabels() {
        let json = """
        {
          "schema_version": "1.0",
          "episode_id": "episode-007",
          "world_id": "world-tingen",
          "worldline_id": "wl-1349-main",
          "title": "错位",
          "protagonist_ids": ["char_a", "char_b"],
          "protagonist_labels": ["只有一個名字"],
          "chapters": [
            { "block_id": "block-1", "segments": [{ "type": "narration", "text": "夜。" }] }
          ],
          "ending": { "type": "closed" }
        }
        """
        // One label for two protagonists would put the only name on the wrong
        // character. Refusing the book beats rendering a confident lie.
        #expect(throws: StoryControlError.self) {
            try JSONDecoder().decode(StoryBookDTO.self, from: Data(json.utf8))
        }
    }

    @Test("The protagonist line renders names, and an unnamed one still occupies its slot")
    func protagonistLineRendersNamesAndKeepsUnnamedSlots() {
        #expect(StoryBookDTO.protagonistLine([]) == nil)
        #expect(StoryBookDTO.protagonistLine(["克莱恩·莫雷蒂"]) == "主角 · 克莱恩·莫雷蒂")
        #expect(
            StoryBookDTO.protagonistLine(["克莱恩·莫雷蒂", nil])
                == "主角 · 克莱恩·莫雷蒂、某人"
        )
        // The function takes labels and has no way to be handed an id, which
        // is the point: the zero-knowledge rule is enforced by the signature,
        // not by everyone remembering it at the call site.
    }

    @Test("An unnamed holder reads as unknown, never as a canonical id")
    func unnamedHolderStaysUnknown() throws {
        let json = """
        {
          "schema_version": "1.0",
          "episode_id": "episode-003",
          "world_id": "world-tingen",
          "worldline_id": "wl-1349-main",
          "title": "无名的知情者",
          "protagonist_ids": ["protagonist-klein"],
          "chapters": [
            { "block_id": "b1", "segments": [{ "type": "narration", "text": "风穿过走廊。" }] }
          ],
          "ending": { "type": "closed" },
          "discovered_secrets": [
            {
              "proposition": "有人来过",
              "holder": null,
              "certainty": 0.4,
              "status": "probable"
            }
          ]
        }
        """
        let book = try JSONDecoder().decode(StoryBookDTO.self, from: Data(json.utf8))

        let secret = try #require(book.discoveredSecrets.first)
        #expect(secret.holder == nil)
        #expect(secret.acquiredWorldTime == nil)
        #expect(!json.contains("char_"))
    }

    @Test("The App reads a wire payload the Engine actually produced")
    func decodesTheShippedWireFixture() throws {
        // Every other test in this file decodes a payload somebody typed. That
        // is how the App shipped a Story Book it could not open: `StoryBookDTO`
        // mirrors the wire strictly, `project_story_book` has always emitted
        // these four keys, and the typed fixtures omitted them — so the suite
        // stayed green against a decoder that rejected the real payload.
        //
        // This one reads `Fixtures/storybook_wire.json`, which is generated
        // from the real `project_story_book`. A typo in a fixture can no longer
        // stand in for the producer, because the producer is the fixture.
        let fixture = try #require(
            StoryBookFixture.shippedWire(),
            "Fixtures/storybook_wire.json 缺失——用 WOM_REGEN_STORYBOOK_FIXTURE=1 跑 engine 的 test_storybook_projection.py 重新生成"
        )

        let book = try JSONDecoder().decode(StoryBookDTO.self, from: fixture)

        #expect(book.title == "哈维诊所的停顿")
        #expect(book.discoveredSecrets.count == 4)
        #expect(book.keyCharacters.count == 1)
        #expect(book.relationshipChanges.count == 1)
        #expect(book.worldImpacts.count == 1)
        // The Engine projects only the axes that moved; a null `affection` must
        // not become a rendered zero.
        #expect(
            book.relationshipChanges.first?.dimensions.changed.map(\.name) == ["信任", "恐惧"]
        )
        // The world event's free-form `payload` is model-authored internal data
        // and must never have been projected in the first place.
        #expect(!String(decoding: fixture, as: UTF8.self).contains("model-authored"))
    }

    /// A book carrying exactly one discovered secret, so the refusal tests
    /// below differ from one another only in the row under test.
    private static func book(withSecret secret: String) -> Data {
        Data(
            """
            {
              "schema_version": "1.0",
              "episode_id": "episode-004",
              "world_id": "world-tingen",
              "worldline_id": "wl-1349-main",
              "title": "t",
              "protagonist_ids": ["protagonist-klein"],
              "chapters": [
                { "block_id": "b1", "segments": [{ "type": "narration", "text": "x" }] }
              ],
              "ending": { "type": "closed" },
              "discovered_secrets": [\(secret)]
            }
            """.utf8
        )
    }

    @Test("A certainty outside [0, 1] is refused")
    func impossibleCertaintyIsRefused() {
        #expect(throws: StoryControlError.invalidPayload) {
            try JSONDecoder().decode(
                StoryBookDTO.self,
                from: Self.book(withSecret: #"{ "proposition": "p", "holder": null, "certainty": 1.5, "status": "confirmed" }"#)
            )
        }
    }

    @Test("A status outside the closed set is refused")
    func unknownStatusIsRefused() {
        // "probably" reads like a status and is not one. Accepting it would put
        // a word on the page whose meaning the App cannot vouch for.
        #expect(throws: StoryControlError.invalidPayload) {
            try JSONDecoder().decode(
                StoryBookDTO.self,
                from: Self.book(withSecret: #"{ "proposition": "p", "holder": null, "certainty": 1.0, "status": "probably" }"#)
            )
        }
    }

    @Test("An undeclared key is refused by the wire check, not by a value guard")
    func undeclaredKeyIsRefusedByTheWireCheck() {
        // `proposition_id` is exactly what must never reach the page, and the
        // only thing that stops it is refusing the row rather than quietly
        // ignoring the field. Pinning *which* check fires matters: if this ever
        // starts throwing `invalidPayload` instead, the row is being stopped by
        // something other than the declaration check, and a future relaxation
        // of the value guards would let the id through unnoticed.
        #expect(throws: IPCContractError.invalidEnvelope) {
            try JSONDecoder().decode(
                StoryBookDTO.self,
                from: Self.book(withSecret: #"{ "proposition": "p", "holder": null, "certainty": 1.0, "status": "confirmed", "proposition_id": "fact.p" }"#)
            )
        }
    }

    @Test("A relationship that moved no dimension is refused")
    func emptyRelationshipIsRefused() {
        // The contract sets minProperties: 1. "The relationship changed" with
        // nothing to show is not something this book can honestly report, and
        // accepting it would put an empty claim on the page.
        let json = """
        {
          "schema_version": "1.0",
          "episode_id": "episode-005",
          "world_id": "world-tingen",
          "worldline_id": "wl-1349-main",
          "title": "t",
          "protagonist_ids": ["protagonist-klein"],
          "chapters": [
            { "block_id": "b1", "segments": [{ "type": "narration", "text": "x" }] }
          ],
          "ending": { "type": "closed" },
          "relationship_changes": [
            { "from": "甲", "to": "乙", "dimensions": {} }
          ]
        }
        """
        #expect(throws: StoryControlError.invalidPayload) {
            try JSONDecoder().decode(StoryBookDTO.self, from: Data(json.utf8))
        }
    }

    @Test("A relationship between two unnamed people is refused")
    func namelessRelationshipIsRefused() {
        let json = """
        {
          "schema_version": "1.0",
          "episode_id": "episode-006",
          "world_id": "world-tingen",
          "worldline_id": "wl-1349-main",
          "title": "t",
          "protagonist_ids": ["protagonist-klein"],
          "chapters": [
            { "block_id": "b1", "segments": [{ "type": "narration", "text": "x" }] }
          ],
          "ending": { "type": "closed" },
          "relationship_changes": [
            { "from": null, "to": null, "dimensions": { "trust": 0.1 } }
          ]
        }
        """
        #expect(throws: StoryControlError.invalidPayload) {
            try JSONDecoder().decode(StoryBookDTO.self, from: Data(json.utf8))
        }
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
