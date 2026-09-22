import Foundation
import Testing
#if canImport(AppKit)
import AppKit
#endif
@testable import WorldOfMysteriesCore

private final class EngineBootstrapRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var eventsStorage: [String] = []

    func record(_ event: String) {
        lock.lock()
        eventsStorage.append(event)
        lock.unlock()
    }

    func snapshot() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return eventsStorage
    }
}

private actor StubEngineProcessManager: EngineProcessManaging {
    private let recorder: EngineBootstrapRecorder

    init(recorder: EngineBootstrapRecorder) {
        self.recorder = recorder
    }

    func startEngine() async throws -> EngineLaunchSession {
        recorder.record("start")
        return EngineLaunchSession(
            identifier: UUID(),
            processIdentifier: 4242,
            socketPath: "/nonexistent/wom/prewarmed.sock",
            token: String(repeating: "a", count: 64)
        )
    }

    func terminateEngine() async {
        recorder.record("terminate")
    }
}

private func blockCurrentThread(for interval: TimeInterval) {
    Thread.sleep(forTimeInterval: interval)
}

@Suite("Local Engine session boundaries")
struct EngineSessionTests {
    @Test("A successful envelope without a valid handshake is not authentication")
    func handshakeValidation() throws {
        #expect(throws: EngineConnectionError.authenticationFailed) { try EngineHandshake(payload: [:]) }
        let hello: [String: AnyCodableValue] = [
            "engine_version": .string("0.1"), "engine_build": .string("test"),
            "python_version": .string("3.14.7"), "protocol_version": .string("1.0"),
            "capabilities": .array([.string("system.health")])
        ]
        #expect(try EngineHandshake(payload: hello).capabilities == ["system.health"])
        var duplicate = hello
        duplicate["capabilities"] = .array([.string("system.health"), .string("system.health")])
        #expect(throws: EngineConnectionError.authenticationFailed) { try EngineHandshake(payload: duplicate) }
    }

    @Test("Health is typed and transport is not world/model/voice readiness")
    func healthValidation() throws {
        let values: [String: AnyCodableValue] = ["transport_ready": .bool(true), "world_ready": .bool(false), "model_ready": .bool(false), "voice_ready": .bool(false)]
        let health = try EngineHealth(payload: values)
        #expect(health.transportReady && !health.worldReady && !health.modelReady && !health.voiceReady)
        var invalid = values
        invalid["world_ready"] = .string("true")
        #expect(throws: EngineConnectionError.invalidFrame) { try EngineHealth(payload: invalid) }
        #expect(!EngineConnectionState.transportReady.isReady)
        #expect(!EngineConnectionState.unavailable.isReady)
    }

    @Test("Handshake capability remains the authority for media.open")
    func mediaCapabilityGate() async {
        let client = EngineIPCClient(requestTimeout: 0.1)
        do {
            _ = try await client.openMedia(
                direction: .engineToApp,
                generation: 1,
                format: MediaFormat(sampleRate: 24000)
            )
            Issue.record("Media opened without an authenticated control connection")
        } catch {
            #expect(error as? EngineConnectionError == .notConnected)
        }
    }

    @Test("Production connection cannot succeed without a socket")
    func noEcho() async {
        let client = EngineIPCClient(requestTimeout: 0.1)
        #expect(!client.isScaffoldOnly)
        do {
            try await client.connect(socketPath: "/nonexistent/wom/engine.sock")
            Issue.record("A nonexistent socket was accepted")
        } catch { }
        #expect(await !client.isConnected)
        await client.disconnect()
    }

    @Test("Missing runtime and concurrent reconnects cannot fabricate readiness")
    @MainActor
    func missingRuntime() async {
        let config = EngineLaunchConfiguration(executableURL: URL(fileURLWithPath: "/nonexistent/wom/python3"),
                                               moduleDirectory: URL(fileURLWithPath: "/nonexistent/wom/engine"))
        let manager = EngineProcessManager(configuration: config)
        let app = AppState(processManager: manager)
        async let first: Void = app.startAndConnect()
        async let second: Void = app.startAndConnect()
        _ = await (first, second)
        #expect(app.connectionState == .unavailable)
        #expect(!app.isEngineReady && app.isShowingDemoData)
        #expect(app.engineHealth == nil && app.engineHandshake == nil)
        #expect(await !manager.isRunning)
        await app.shutdown()
        #expect(app.connectionState == .idle)
        #expect(app.connectionError == nil)
    }
}


#if canImport(AppKit)
extension EngineSessionTests {
    @Test("App delegate prewarms Engine while MainActor is blocked")
    @MainActor
    func appDelegatePrewarmsOffMainActor() async {
        let recorder = EngineBootstrapRecorder()
        let manager = StubEngineProcessManager(recorder: recorder)
        let state = AppState(processManager: manager)
        let delegate = EngineAppDelegate(appState: state)

        delegate.applicationDidFinishLaunching(
            Notification(name: NSApplication.didFinishLaunchingNotification)
        )

        // Simulate expensive initial SwiftUI/AppKit work. A MainActor-inherited
        // bootstrap task cannot run during this interval; the detached process
        // prewarm must still reach the process-manager actor.
        blockCurrentThread(for: 0.2)
        #expect(recorder.snapshot() == ["start"])

        #expect(await delegate.awaitLaunchCompletion())
        let events = recorder.snapshot()
        #expect(events.prefix(2) == ["start", "start"])
        #expect(events.last == "terminate")
        await state.shutdown()
    }

    @Test("Prewarmed process is not terminated before connection reuse")
    @MainActor
    func prewarmIsReusedBeforeFailureCleanup() async {
        let recorder = EngineBootstrapRecorder()
        let manager = StubEngineProcessManager(recorder: recorder)
        let state = AppState(processManager: manager)

        await state.prewarmEngineProcess()
        await state.startAndConnect()

        let events = recorder.snapshot()
        #expect(events.prefix(2) == ["start", "start"])
        #expect(events.dropFirst(2).first == "terminate")
        await state.shutdown()
    }

    @Test("Process lifecycle owns Engine bootstrap instead of a SwiftUI view")
    @MainActor
    func appDelegateOwnsBootstrap() async throws {
        let config = EngineLaunchConfiguration(
            executableURL: URL(fileURLWithPath: "/nonexistent/wom/python3"),
            moduleDirectory: URL(fileURLWithPath: "/nonexistent/wom/engine")
        )
        let state = AppState(processManager: EngineProcessManager(configuration: config))
        let delegate = EngineAppDelegate(appState: state)

        delegate.applicationDidFinishLaunching(
            Notification(name: NSApplication.didFinishLaunchingNotification)
        )

        #expect(await delegate.awaitLaunchCompletion())
        #expect(state.connectionState == .unavailable)
        await state.shutdown()
        #expect(state.connectionState == .idle)
    }

    @Test("ContentView no longer owns process bootstrap")
    func viewSourceDoesNotStartEngine() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let source = try String(
            contentsOf: root.appendingPathComponent("WorldOfMysteries/ContentView.swift"),
            encoding: .utf8
        )
        #expect(!source.contains("await appState.startAndConnect()"))
    }
}
#endif
