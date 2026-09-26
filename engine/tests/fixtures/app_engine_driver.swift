import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// Compiled with the ACTUAL production files by pytest; this is not a mock client.
@main
struct AppEngineDriver {
    static func main() async throws {
        let args = CommandLine.arguments
        let mode = args[1]
        if mode.hasPrefix("story-") {
            try await runStoryMode(mode: mode, args: args)
            return
        }
        if mode == "peer" {
            let variant = args[4]
            // Fragment reassembly is not a 300ms latency benchmark. Deliberate
            // per-fragment sleeps accumulate differently across target schedulers.
            // Only the dedicated deadline case uses the short timeout; production
            // defaults and its half-frame deadline remain unchanged.
            let client = EngineIPCClient(requestTimeout: variant == "timeout" ? 0.3 : 5)
            try await client.connect(socketPath: args[2])
            try await client.performHandshake(sessionToken: String(repeating: "a", count: 64))
            do {
                _ = try await client.health()
                guard args[3] == "ok" else { fatalError("Malformed peer was accepted") }
            } catch {
                guard args[3] == "error", let failure = error as? EngineConnectionError else { throw error }
                let expected: EngineConnectionError
                switch variant {
                case "timeout": expected = .timedOut
                case "wrong-trace", "wrong-request": expected = .correlationMismatch
                default: expected = .invalidFrame
                }
                guard failure == expected else { throw error }
            }
            await client.disconnect()
            print("PASS peer \(args[3])")
            return
        }

        let manager = EngineProcessManager(configuration: EngineLaunchConfiguration(
            executableURL: URL(fileURLWithPath: args[2]), moduleDirectory: URL(fileURLWithPath: args[3]),
            runtimeRoot: URL(fileURLWithPath: args[4])))
        let client = EngineIPCClient(requestTimeout: 2)
        if mode.hasPrefix("app-") {
            let app = AppState(ipcClient: client, processManager: manager)
            do {
                if mode == "app-stop-during-start" {
                    let task = Task { await app.startAndConnect() }
                    while app.connectionState == .idle { await Task.yield() }
                    await app.shutdown()
                    await task.value
                    guard app.connectionState == .idle, await !manager.isRunning else { fatalError("Stale startup escaped stop barrier") }
                }
                await app.startAndConnect()
                guard app.connectionState == .transportReady, !app.isEngineReady, app.isShowingDemoData,
                      app.engineHealth?.worldReady == false else { fatalError("Incorrect App readiness") }
                if mode == "app-reconnect" || mode == "app-bounded-reconnect" {
                    let crashes = mode == "app-reconnect" ? 1 : 3
                    for index in 0..<crashes {
                        guard let pid = await manager.runningProcessIdentifier else { fatalError("Missing owned process") }
                        _ = kill(pid, SIGKILL)
                        if index < 2 {
                            let deadline = ContinuousClock.now.advanced(by: .seconds(8))
                            var recovered = false
                            while ContinuousClock.now < deadline {
                                try await Task.sleep(for: .milliseconds(25))
                                if let next = await manager.runningProcessIdentifier, next != pid,
                                   app.connectionState == .transportReady, await client.isConnected {
                                    recovered = true; break
                                }
                            }
                            guard recovered else { fatalError("App failed to recover transport") }
                        } else {
                            try await Task.sleep(for: .seconds(1))
                            guard case .failed = app.connectionState, await !manager.isRunning else { fatalError("Crash loop did not stop") }
                        }
                    }
                }
                await app.shutdown()
                guard app.connectionState == .idle, app.engineHealth == nil, await !manager.isRunning else { fatalError("App shutdown incomplete") }
                print("PASS \(mode)")
                return
            } catch {
                await app.shutdown()
                throw error
            }
        }
        do {
            if mode == "cancel-start" {
                let startup = Task { try await manager.startEngine() }
                startup.cancel()
                _ = await startup.result
                await manager.terminateEngine()
                guard await !manager.isRunning else { fatalError("Cancelled launch survived") }
            }
            let launch = try await manager.startEngine()
            if mode == "hold" {
                let record: [String: Any] = ["pid": launch.processIdentifier, "socket": launch.socketPath]
                var bytes = try JSONSerialization.data(withJSONObject: record)
                bytes.append(10)
                try FileHandle.standardOutput.write(contentsOf: bytes)
                try await Task.sleep(for: .seconds(300))
            }
            try await client.connect(socketPath: launch.socketPath)
            let welcome = try await client.performHandshake(sessionToken: launch.token)
            guard welcome.capabilities == ["system.health", "system.shutdown"] else { fatalError("Invented capabilities") }
            let health = try await client.health()
            guard health.transportReady, !health.worldReady, !health.modelReady, !health.voiceReady else { fatalError("False readiness") }
            try await withThrowingTaskGroup(of: Bool.self) { group in
                for _ in 0..<12 { group.addTask { try await client.health().transportReady } }
                for try await ready in group { guard ready else { fatalError("Lost correlated response") } }
            }
            let duplicate = try await manager.startEngine()
            guard duplicate.identifier == launch.identifier else { fatalError("Duplicate child") }
            do {
                _ = try await client.send(envelope: IPCEnvelope(kind: "request", traceId: "t", requestId: "r", method: "story.submit_advice"))
                fatalError("Unsupported business method succeeded")
            } catch EngineConnectionError.methodUnavailable { }
            if mode == "wrong-token" {
                await client.disconnect()
                try await client.connect(socketPath: launch.socketPath)
                let wrong = (launch.token.first == "a" ? "b" : "a") + launch.token.dropFirst()
                do {
                    try await client.performHandshake(sessionToken: wrong)
                    fatalError("Invalid credential accepted")
                } catch EngineConnectionError.authenticationFailed { }
                try await client.connect(socketPath: launch.socketPath)
                try await client.performHandshake(sessionToken: launch.token)
            }
            if mode == "crash" {
                let stream = try await client.eventStream()
                _ = kill(launch.processIdentifier, SIGKILL)
                do { for try await _ in stream { } } catch { }
                guard await !client.isConnected else { fatalError("Crash left a live connection") }
                await manager.terminateEngine()
                let restarted = try await manager.startEngine()
                guard restarted.token != launch.token, restarted.identifier != launch.identifier else { fatalError("Credential reused") }
                try await client.connect(socketPath: restarted.socketPath)
                do {
                    try await client.performHandshake(sessionToken: launch.token)
                    fatalError("Old launch credential accepted")
                } catch EngineConnectionError.authenticationFailed { }
                try await client.connect(socketPath: restarted.socketPath)
                try await client.performHandshake(sessionToken: restarted.token)
                _ = try await client.health()
            }
            await client.disconnect()
            await manager.terminateEngine()
            guard await !manager.isRunning else { fatalError("Child survived shutdown") }
            guard !FileManager.default.fileExists(atPath: launch.socketPath) else { fatalError("Socket survived cleanup") }
            print("PASS \(mode)")
        } catch {
            await client.disconnect()
            await manager.terminateEngine()
            throw error
        }
    }

    // MARK: - Real Swift App → independent Engine → disk first turn

    /// Drives the production AppState/StorySessionModel against a real child
    /// Engine process. Every mode prints one `STORY {json}` fact line so the
    /// pytest launcher can compare processes and the on-disk database.
    @MainActor
    private static func runStoryMode(mode: String, args: [String]) async throws {
        let manager = EngineProcessManager(configuration: EngineLaunchConfiguration(
            executableURL: URL(fileURLWithPath: args[2]), moduleDirectory: URL(fileURLWithPath: args[3]),
            runtimeRoot: URL(fileURLWithPath: args[4]), dataRoot: URL(fileURLWithPath: args[5])))
        let app = AppState(ipcClient: EngineIPCClient(requestTimeout: 5), processManager: manager)
        do {
            await app.startAndConnect()
            guard app.connectionState == .transportReady, app.engineHealth?.worldReady == true else {
                fatalError("Story engine never reported world readiness")
            }
            let model = app.storyModel
            try await performStoryAction(mode: mode, model: model)
            guard await waitForStory(mode: mode, model: model, seconds: 25) else {
                fatalError("Story mode \(mode) never reached its expected outcome: \(stateName(model.state))")
            }
            try emitStoryFacts(mode: mode, model: model)
            await app.shutdown()
            print("PASS \(mode)")
        } catch {
            await app.shutdown()
            throw error
        }
    }

    @MainActor
    private static func performStoryAction(mode: String, model: StorySessionModel) async throws {
        switch mode {
        case "story-open", "story-open-lost-ack":
            guard model.state == .notStarted else {
                fatalError("Expected an unopened scenario, saw \(stateName(model.state))")
            }
            await model.startStory()
        case "story-submit", "story-submit-lost-ack", "story-submit-unsupported",
             "story-submit-interrupted":
            guard model.state == .ready, model.view?.turn == 0 else {
                fatalError("Expected a ready turn=0 session, saw \(stateName(model.state))")
            }
            model.fillSupportedAdvice()
            guard !model.draft.isEmpty else { fatalError("Engine advertised no first-turn advice") }
            if mode == "story-submit-unsupported" {
                model.draft = "先问问医生今天还有没有别的预约。"
            }
            await model.submit()
        case "story-continue-pending":
            guard model.state == .pending, model.canContinuePending else {
                fatalError("Expected a recoverable pending request, saw \(stateName(model.state))")
            }
            await model.continuePendingRequest()
        default:
            break  // story-reopen / story-recover-open are pure read modes.
        }
    }

    @MainActor
    private static func emitStoryFacts(mode: String, model: StorySessionModel) throws {
        var facts: [String: Any] = [
            "mode": mode,
            "state": stateName(model.state),
            "draft": model.draft,
            "supported_advice": model.supportedAdvice,
            "can_continue_pending": model.canContinuePending,
        ]
        if let view = model.view {
            facts["session_id"] = view.sessionId
            facts["session_status"] = view.status
            facts["turn"] = view.turn
            facts["story_revision"] = view.storyRevision
            facts["observed_store_revision"] = view.observedStoreRevision
            facts["world_time"] = view.worldTime
            facts["clues"] = view.discoveredClues.map { $0.displayName }
        }
        if let pending = model.pendingInputTurnId { facts["pending_input_turn_id"] = pending }
        if let code = model.lastServiceCode { facts["last_service_code"] = code }
        let encoded = try JSONSerialization.data(withJSONObject: facts, options: [.sortedKeys])
        print("STORY " + (String(data: encoded, encoding: .utf8) ?? "{}"))
    }

    @MainActor
    private static func waitForStory(mode: String, model: StorySessionModel, seconds: Double) async -> Bool {
        let deadline = ContinuousClock.now.advanced(by: .seconds(seconds))
        while ContinuousClock.now < deadline {
            if storyOutcome(mode: mode, model: model) { return true }
            try? await Task.sleep(for: .milliseconds(25))
        }
        return storyOutcome(mode: mode, model: model)
    }

    @MainActor
    private static func storyOutcome(mode: String, model: StorySessionModel) -> Bool {
        switch mode {
        case "story-open", "story-open-lost-ack", "story-recover-open":
            return model.state == .ready && model.view?.turn == 0
        case "story-submit", "story-submit-lost-ack", "story-reopen", "story-continue-pending":
            return model.state == .completed && model.view?.turn == 1
        case "story-submit-unsupported":
            return model.state == .failed(code: "deterministic_input_unsupported")
                && !model.draft.isEmpty && model.view?.turn == 0
        case "story-submit-interrupted":
            // The Engine died before the domain COMMIT: the App must stop in a
            // recoverable read-only state instead of inventing an outcome.
            return !model.state.isBusy && model.state != .unavailable
        default:
            return false
        }
    }

    private static func stateName(_ state: StorySessionModel.State) -> String {
        switch state {
        case .unavailable: return "unavailable"
        case .loading: return "loading"
        case .notStarted: return "not_started"
        case .opening: return "opening"
        case .ready: return "ready"
        case .submitting: return "submitting"
        case .recovering: return "recovering"
        case .pending: return "pending"
        case .completed: return "completed"
        case .failed: return "failed"
        }
    }
}
