import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Bundled runtime selection")
struct BundledRuntimeTests {
    private func withBundle(_ change: (URL) throws -> Void, check: (Bundle) throws -> Void) throws {
        let base = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: base) }
        let app = base.appendingPathComponent("诡秘 空格.app")
        let contents = app.appendingPathComponent("Contents")
        let root = contents.appendingPathComponent("Resources/LocalEngine")
        try FileManager.default.createDirectory(at: root.appendingPathComponent("bin"), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: root.appendingPathComponent("engine/infrastructure"), withIntermediateDirectories: true)
        let plist = ["CFBundleIdentifier":"dev.worldofmysteries.runtime-test", "CFBundlePackageType":"APPL", "CFBundleExecutable":"Test"]
        try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
            .write(to: contents.appendingPathComponent("Info.plist"))
        let executable = root.appendingPathComponent("bin/python3")
        try Data("test fixture: never executed".utf8).write(to: executable)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)
        try Data().write(to: root.appendingPathComponent("engine/infrastructure/ipc_server.py"))
        let manifest: [String: Any] = ["format_version":1, "python_version":"3.14.7", "architecture":"arm64",
             "gil_enabled":true, "agentscope_version":"2.0.8", "protocol_version":"1.0"]
        try JSONSerialization.data(withJSONObject:manifest).write(to:root.appendingPathComponent("runtime-manifest.json"))
        try change(root)
        let bundle = try #require(Bundle(url: app))
        try check(bundle)
    }

    @Test("A complete compatible manifest resolves inside a relocated bundle")
    func valid() throws {
        try withBundle({ _ in }) { bundle in
            let config = try EngineLaunchConfiguration.bundled(in: bundle)
            #expect(config.executableURL.path.hasPrefix(bundle.bundlePath + "/"))
        }
    }

    @Test("Missing or malformed manifest never falls back to system Python", arguments: ["", "{}", "[]", "{\"gil_enabled\":false}"])
    func malformed(_ text: String) throws {
        try withBundle({ root in
            try Data(text.utf8).write(to: root.appendingPathComponent("runtime-manifest.json"))
        }) { bundle in
            #expect(throws: EngineConnectionError.runtimeUnavailable) { try EngineLaunchConfiguration.bundled(in: bundle) }
        }
    }

    @Test("An interpreter link cannot escape its application")
    func escapedInterpreter() throws {
        try withBundle({ root in
            let python = root.appendingPathComponent("bin/python3")
            try FileManager.default.removeItem(at: python)
            try FileManager.default.createSymbolicLink(atPath: python.path, withDestinationPath: "/usr/bin/true")
        }) { bundle in
            #expect(throws: EngineConnectionError.runtimeUnavailable) { try EngineLaunchConfiguration.bundled(in: bundle) }
        }
    }

    @Test("Runtime architecture and version mismatches are rejected", arguments: ["architecture", "python_version", "agentscope_version", "protocol_version"])
    func incompatible(_ field: String) throws {
        try withBundle({ root in
            let file = root.appendingPathComponent("runtime-manifest.json")
            var data = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String:Any])
            data[field] = "incompatible"
            try JSONSerialization.data(withJSONObject: data).write(to: file)
        }) { bundle in
            #expect(throws: EngineConnectionError.runtimeUnavailable) { try EngineLaunchConfiguration.bundled(in: bundle) }
        }
    }
}
