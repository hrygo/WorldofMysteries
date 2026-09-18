import Foundation
import Darwin

/// A sandboxed test host built from the production transport/process sources.
/// The release App is separately launched by the packaging verification script.
@main
struct EnginePackageProbe {
    static func main() async throws {
        let config = try EngineLaunchConfiguration.bundled()
        let dependency = Process()
        dependency.executableURL = config.executableURL
        dependency.arguments = ["-I", "-B", "-c", """
import agentscope,pydantic_core,openai,jsonschema,sqlite3,ssl,ctypes,json,sys,platform
from importlib.metadata import version
assert platform.python_version() == '3.14.7' and version('agentscope') == '2.0.8'
assert agentscope.__file__.startswith(sys.prefix + '/')
print(json.dumps({'passed':True,'agentscope':version('agentscope')}))
"""]
        let dependencyOutput = Pipe()
        dependency.standardOutput = dependencyOutput
        dependency.standardError = FileHandle.standardError
        try dependency.run()
        let dependencyBytes = dependencyOutput.fileHandleForReading.readDataToEndOfFile()
        dependency.waitUntilExit()
        guard dependency.terminationStatus == 0,
              let dependencyResult = try JSONSerialization.jsonObject(with: dependencyBytes) as? [String: Any],
              dependencyResult["passed"] as? Bool == true else {
            throw EngineConnectionError.invalidConfiguration
        }
        let process = EngineProcessManager(configuration: config)
        let client = EngineIPCClient()
        var elapsed: [Double] = []
        var ids: [Int32] = []
        for attempt in 0..<3 {
            let start = ContinuousClock.now
            let session = try await process.startEngine()
            ids.append(session.processIdentifier)
            try await client.connect(socketPath: session.socketPath)
            let hello = try await client.performHandshake(sessionToken: session.token)
            let health = try await client.health()
            guard hello.pythonVersion == "3.14.7", health.transportReady,
                  !session.socketPath.hasPrefix(Bundle.main.bundlePath + "/") else {
                throw EngineConnectionError.invalidConfiguration
            }
            let duration = start.duration(to: .now).components
            elapsed.append(Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15)
            if attempt == 1 { _ = kill(session.processIdentifier, SIGKILL) }
            await client.disconnect()
            await process.terminateEngine()
            guard !FileManager.default.fileExists(atPath: session.socketPath) else {
                throw EngineConnectionError.invalidConfiguration
            }
        }
        guard Set(ids).count == 3 else { throw EngineConnectionError.invalidConfiguration }
        let record: [String: Any] = ["passed": true, "launch_to_health_ms": elapsed,
            "starts": 3, "signed_sandbox_dependency_imports": true, "crash_restarted": true, "socket_outside_bundle": true,
            "source": "production Swift process manager and IPC client", "notarization": "not-tested"]
        print(String(decoding: try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]), as: UTF8.self))
    }
}
