import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// A story turn is up to three sequential authorized model calls, each bounded
/// by the Engine's own 45s stage budget, followed by commit and publish. The
/// Engine therefore admits turns of roughly 135s, and a client that gives up
/// sooner is the layer cutting a turn the Engine would still have completed.
///
/// The client's timeout is a patience ceiling, not a latency budget: a reply
/// that arrives early returns immediately, so a generous ceiling costs nothing
/// and protects the slow path.
@Suite("Local Engine request patience")
struct EngineIPCClientTimeoutTests {
    /// 3 sequential authorized calls x the Engine's 45s stage budget.
    static let fullTurnBudget: TimeInterval = 135

    @Test("The default client timeout outlives a whole turn")
    func defaultTimeoutAccommodatesAFullTurn() {
        #expect(EngineIPCClient().requestTimeout >= Self.fullTurnBudget)
    }

    @Test("AppState's default client is not the layer that gives up first")
    @MainActor
    func appStateUsesTheSameDefault() {
        #expect(AppState().ipcClient.requestTimeout >= Self.fullTurnBudget)
    }

    @Test("An unusable timeout falls back to the full-turn ceiling, not to a short one")
    func invalidTimeoutFallsBackToTheFullTurnCeiling() {
        for invalid in [0, -1, .nan, .infinity] {
            #expect(EngineIPCClient(requestTimeout: invalid).requestTimeout >= Self.fullTurnBudget)
        }
    }

    @Test("An explicit short timeout is still honoured for deliberate probing")
    func explicitTimeoutIsHonoured() {
        #expect(EngineIPCClient(requestTimeout: 0.25).requestTimeout == 0.25)
    }
}
