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

    @Test("Sandbox-length runtime roots use a compact private endpoint")
    func sandboxPathBudget() throws {
        let files = FileManager.default
        let parent = files.temporaryDirectory
        let unique = UUID().uuidString.prefix(12)
        let padding = max(0, 83 - parent.path.utf8.count - 1 - unique.utf8.count)
        let root = parent.appendingPathComponent(String(unique) + String(repeating: "x", count: padding))
        defer { try? files.removeItem(at: root) }
        // Exercise the 107-byte old endpoint that failed in the real signed GUI.
        #expect(root.appendingPathComponent("wom-12345678/engine.sock").path.utf8.count >= 104)
        let lease = try EngineRuntimeLease.create(root: root)
        defer { lease.clean() }
        #expect(lease.socketPath.utf8.count < 104)
        #expect(URL(fileURLWithPath: lease.socketPath).lastPathComponent == "s")
        let attributes = try files.attributesOfItem(atPath: lease.directory.path)
        #expect((attributes[.posixPermissions] as? NSNumber)?.intValue == 0o700)
        #expect(lease.directory.deletingLastPathComponent().path == root.path)
        lease.clean()
        #expect(!files.fileExists(atPath: lease.directory.path))
        #expect(files.fileExists(atPath: root.path))
    }

    @Test("An impossible explicit socket root stays rejected; no global fallback")
    func impossibleBudget() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString + String(repeating: "x", count: 104))
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(throws: EngineConnectionError.invalidConfiguration) {
            try EngineRuntimeLease.create(root: root)
        }
        #expect((try? FileManager.default.contentsOfDirectory(atPath: root.path)) == [])
    }

    @Test("Endpoint budget counts UTF-8 bytes rather than characters")
    func unicodeBudget() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString + String(repeating: "界", count: 30))
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(root.path.utf8.count >= 104)
        #expect(throws: EngineConnectionError.invalidConfiguration) {
            try EngineRuntimeLease.create(root: root)
        }
    }

    @Test("Story facts live in a persistent user directory, never a temporary or bundled path")
    func persistentEngineeringDataRoot() throws {
        let root = try #require(EngineLaunchConfiguration.defaultDataRoot())
        #expect(root.path.hasSuffix("/WorldofMysteries/Engineering/Golden001/Data"))
        #expect(root.path.contains("/Library/Application Support/"))
        #expect(!root.path.hasPrefix(FileManager.default.temporaryDirectory.path))
        #expect(!root.path.contains(".app/"), "用户事实不得写进 App bundle")
    }
}
