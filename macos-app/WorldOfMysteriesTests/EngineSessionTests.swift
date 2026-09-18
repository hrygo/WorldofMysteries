import Foundation
import Testing
@testable import WorldOfMysteriesCore

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
