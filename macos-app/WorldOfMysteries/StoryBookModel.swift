import Foundation
import Observation

/// Minimal client surface the Story Book model needs. Kept separate from
/// `StoryEngineClient` so the view can be exercised with a tiny fake.
public protocol StoryBookClient: Sendable {
    func storyBook(sessionId: String, traceId: String) async throws -> StoryBookDTO
}

extension EngineIPCClient: StoryBookClient {}

/// Loads one finalized session's Story Book (PRD §20.1). The book is a pure
/// read of committed facts — the App never asks the model to rewrite anything.
@Observable
@MainActor
public final class StoryBookModel {
    public enum State: Equatable, Sendable {
        case idle
        case loading
        case loaded(StoryBookDTO)
        /// The session has no finalized Episode yet — a normal state, not a bug.
        case notFinalized
        case failed(code: String)
    }

    public private(set) var state: State = .idle

    @ObservationIgnored private let client: any StoryBookClient
    @ObservationIgnored private let idFactory: @Sendable () -> String

    public init(
        client: any StoryBookClient,
        idFactory: @escaping @Sendable () -> String = { UUID().uuidString }
    ) {
        self.client = client
        self.idFactory = idFactory
    }

    public func load(sessionId: String) async {
        guard !sessionId.isEmpty else {
            state = .failed(code: "schema_invalid")
            return
        }
        state = .loading
        do {
            let book = try await client.storyBook(sessionId: sessionId, traceId: idFactory())
            state = .loaded(book)
        } catch let error as StoryControlServiceError {
            // A session that has not been finalized has no book yet — that is
            // a first-class outcome, distinct from a transport/storage fault.
            state = error.code == "story_session_not_active" ? .notFinalized : .failed(code: error.code)
        } catch {
            state = .failed(code: "service_unavailable")
        }
    }

    /// Drop the rendered book when the session behind it goes away.
    ///
    /// Without this, a transport loss (which clears `storyModel.view`) would
    /// leave the previous session's Episode on screen as if it were still the
    /// committed truth — the one thing this page must never imply.
    public func reset() {
        state = .idle
    }
}
