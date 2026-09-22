import Foundation
#if canImport(OSLog)
import OSLog
#endif
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// Explicit launch injection is for development/tests. Production uses bundled(),
/// never PATH, a user's Python installation, a downloaded interpreter or a shell.
public nonisolated struct EngineLaunchConfiguration: Sendable {
    public let executableURL: URL
    public let moduleDirectory: URL
    public let runtimeRoot: URL?

    public init(executableURL: URL, moduleDirectory: URL, runtimeRoot: URL? = nil) {
        self.executableURL = executableURL
        self.moduleDirectory = moduleDirectory
        self.runtimeRoot = runtimeRoot
    }

    public static func bundled(in bundle: Bundle = .main) throws -> Self {
        guard let resources = bundle.resourceURL else { throw EngineConnectionError.runtimeUnavailable }
        let root = resources.appendingPathComponent("LocalEngine", isDirectory: true)
        // Validate the small signed manifest before starting code. Whole-tree integrity
        // is enforced by package verification/code signing, not a costly launch-time hash scan.
        guard root.resolvingSymlinksInPath().standardizedFileURL.path.hasPrefix(
            bundle.bundleURL.resolvingSymlinksInPath().standardizedFileURL.path + "/") else {
            throw EngineConnectionError.runtimeUnavailable
        }
        let manifestURL = root.appendingPathComponent("runtime-manifest.json")
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: manifestURL.path),
              let size = attributes[.size] as? NSNumber, size.intValue <= 8 * 1024 * 1024,
              let data = try? Data(contentsOf: manifestURL), data.count <= 8 * 1024 * 1024,
              let manifest = try? JSONDecoder().decode(BundledRuntimeManifest.self, from: data),
              manifest.formatVersion == 1, manifest.pythonVersion == "3.14.7",
              manifest.architecture == "arm64", manifest.gilEnabled,
              manifest.protocolVersion == "1.0", manifest.agentscopeVersion == "2.0.8" else {
            throw EngineConnectionError.runtimeUnavailable
        }
        let resolvedRoot = root.resolvingSymlinksInPath().standardizedFileURL.path + "/"
        for relative in ["bin/python3", "engine/infrastructure/ipc_server.py", "runtime-manifest.json"] {
            guard root.appendingPathComponent(relative).resolvingSymlinksInPath()
                .standardizedFileURL.path.hasPrefix(resolvedRoot) else {
                throw EngineConnectionError.runtimeUnavailable
            }
        }
        let configuration = Self(executableURL: root.appendingPathComponent("bin/python3"),
                                 moduleDirectory: root.appendingPathComponent("engine", isDirectory: true))
        try configuration.validate()
        return configuration
    }

    func validate() throws {
        let files = FileManager.default
        guard executableURL.isFileURL, moduleDirectory.isFileURL,
              files.isExecutableFile(atPath: executableURL.path),
              files.fileExists(atPath: moduleDirectory.appendingPathComponent("infrastructure/ipc_server.py").path) else {
            throw EngineConnectionError.runtimeUnavailable
        }
    }
}

/// Packaging metadata is not a new wire protocol or proof of distribution approval.
private nonisolated struct BundledRuntimeManifest: Decodable {
    let formatVersion: Int
    let pythonVersion: String
    let architecture: String
    let gilEnabled: Bool
    let protocolVersion: String
    let agentscopeVersion: String
    enum CodingKeys: String, CodingKey {
        case formatVersion = "format_version", pythonVersion = "python_version"
        case architecture, gilEnabled = "gil_enabled", protocolVersion = "protocol_version"
        case agentscopeVersion = "agentscope_version"
    }
}

/// Memory-only credential. Diagnostic descriptions deliberately redact it.
public nonisolated struct EngineLaunchSession: Sendable, CustomStringConvertible, CustomDebugStringConvertible {
    public let identifier: UUID
    public let processIdentifier: Int32
    public let socketPath: String
    let token: String
    public var description: String { "EngineLaunchSession(credential: redacted)" }
    public var debugDescription: String { description }
}

nonisolated struct EngineRuntimeLease: Sendable {
    let directory: URL
    let device: UInt64
    let inode: UInt64
    // Endpoint names are private launch metadata, not persisted world identifiers.
    // A compact name leaves room for sandbox container prefixes in Darwin sun_path.
    static let socketName = "s"
    var socketPath: String { directory.appendingPathComponent(Self.socketName).path }

    /// Fixed stage identifiers and numeric diagnostics only: never log runtime paths,
    /// payloads, environment variables or launch credentials.
    private static func rejected(_ stage: String, code: Int32 = 0) -> EngineConnectionError {
        #if canImport(OSLog)
        Logger(subsystem: "dev.worldofmysteries", category: "EngineRuntime")
            .error("Runtime setup rejected at \(stage, privacy: .public); code \(code)")
        #endif
        return .invalidConfiguration
    }

    static func create(root explicitRoot: URL?) throws -> Self {
        let files = FileManager.default
        let support = files.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
            .appendingPathComponent("WorldofMysteries/Runtime", isDirectory: true)
        let component = "wom-" + UUID().uuidString.prefix(8)
        func endpointBytes(in root: URL) -> Int {
            root.appendingPathComponent(component, isDirectory: true)
                .appendingPathComponent(Self.socketName).path.utf8.count
        }
        var root = explicitRoot ?? support ?? files.temporaryDirectory
        // Account for the actual UTF-8 endpoint, not an estimated path suffix.
        // Only ephemeral sockets fall back to the app's own temporary directory;
        // never redirect user data or escape to a shared/global /tmp namespace.
        if explicitRoot == nil, endpointBytes(in: root) >= 104 { root = files.temporaryDirectory }
        guard root.isFileURL else { throw rejected("non-file-root") }
        do { try files.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700]) }
        catch { throw rejected("create-runtime-root", code: Int32(truncatingIfNeeded: (error as NSError).code)) }
        let directory = root.appendingPathComponent(component, isDirectory: true)
        let socketBytes = endpointBytes(in: root)
        guard socketBytes < 104 else { throw rejected("socket-path-budget", code: Int32(socketBytes)) }
        guard mkdir(directory.path, 0o700) == 0 else { throw rejected("create-private-directory", code: errno) }
        var info = stat()
        guard lstat(directory.path, &info) == 0 else { throw rejected("inspect-private-directory", code: errno) }
        guard (info.st_mode & 0o170000) == 0o040000, info.st_uid == getuid(),
              (info.st_mode & 0o077) == 0 else { throw rejected("private-directory-identity") }
        return Self(directory: directory, device: UInt64(info.st_dev), inode: UInt64(info.st_ino))
    }

    /// Called only after the owned child has exited. Never recursively delete data;
    /// a replaced directory, active lock or unknown extra file is left untouched.
    func clean() {
        var info = stat()
        guard lstat(directory.path, &info) == 0, UInt64(info.st_dev) == device,
              UInt64(info.st_ino) == inode, (info.st_mode & 0o170000) == 0o040000 else { return }
        let lockPath = socketPath + ".lock"
        let lock = open(lockPath, O_RDWR | O_NOFOLLOW | O_CLOEXEC)
        if lock >= 0 {
            defer { _ = close(lock) }
            guard flock(lock, LOCK_EX | LOCK_NB) == 0 else { return }
            var socketInfo = stat()
            if lstat(socketPath, &socketInfo) == 0, (socketInfo.st_mode & 0o170000) == 0o140000,
               socketInfo.st_uid == getuid() { _ = unlink(socketPath) }
            _ = unlink(lockPath)
        }
        _ = rmdir(directory.path)
    }
}

/// Owns one child process, launch token and private runtime lease. Concurrent starts
/// coalesce; stop waits for a bounded graceful exit before SIGKILL. No login daemon.
public actor EngineProcessManager {
    #if canImport(OSLog)
    private static let logger = Logger(
        subsystem: "dev.worldofmysteries",
        category: "EngineProcess"
    )
    #endif

    private let configuration: EngineLaunchConfiguration?
    private var process: Process?
    private var session: EngineLaunchSession?
    private var lease: EngineRuntimeLease?
    private var starting: Task<EngineLaunchSession, any Error>?
    private var stopping: Task<Void, Never>?
    private var startIdentity = UUID()
    private var stopIdentity = UUID()
    public private(set) var lastExitStatus: Int32?
    public var isRunning: Bool { process?.isRunning == true }
    public var runningProcessIdentifier: Int32? { isRunning ? process?.processIdentifier : nil }
    public nonisolated var isScaffoldOnly: Bool { false }

    public init(configuration: EngineLaunchConfiguration? = nil) { self.configuration = configuration }

    @discardableResult
    public func startEngine() async throws -> EngineLaunchSession {
        if let stopping { await stopping.value }
        try Task.checkCancellation()
        if let starting { return try await starting.value }
        if let session, isRunning { return session }
        lease?.clean()
        lease = nil
        process = nil
        session = nil
        let identity = UUID()
        startIdentity = identity
        let task = Task { try await launch() }
        starting = task
        do {
            let result = try await withTaskCancellationHandler { try await task.value } onCancel: { task.cancel() }
            if startIdentity == identity { starting = nil }
            return result
        } catch {
            if startIdentity == identity { starting = nil }
            throw error
        }
    }

    private func launch() async throws -> EngineLaunchSession {
        try Task.checkCancellation()
        #if canImport(OSLog)
        Self.logger.notice("Engine launch resolving runtime")
        #endif
        let config: EngineLaunchConfiguration
        do {
            config = try configuration ?? EngineLaunchConfiguration.bundled()
            try config.validate()
        } catch {
            #if canImport(OSLog)
            Self.logger.error("Engine launch runtime validation failed")
            #endif
            throw error
        }
        #if canImport(OSLog)
        Self.logger.notice("Engine launch runtime validated")
        #endif
        let runtime: EngineRuntimeLease
        do {
            runtime = try EngineRuntimeLease.create(root: config.runtimeRoot)
        } catch {
            #if canImport(OSLog)
            Self.logger.error("Engine launch runtime lease failed")
            #endif
            throw error
        }
        lease = runtime
        #if canImport(OSLog)
        Self.logger.notice("Engine launch runtime lease ready")
        #endif
        let credential = (0..<32).map { _ in String(format: "%02x", UInt8.random(in: .min ... .max)) }.joined()
        let child = Process()
        let input = Pipe()
        // Fill and close the small pipe while its parent-owned reader is still open.
        // This cannot SIGPIPE if the child fails to launch or exits immediately.
        do {
            try input.fileHandleForWriting.write(contentsOf: Data(credential.utf8))
            try input.fileHandleForWriting.close()
            child.executableURL = config.executableURL
            child.currentDirectoryURL = config.moduleDirectory
            child.arguments = ["-E", "-s", "-B", "-X", "utf8", "-m", "infrastructure.ipc_server", "--socket", runtime.socketPath,
                               "--token-fd", "0", "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
            child.environment = ProcessInfo.processInfo.environment.filter {
                !$0.key.hasPrefix("PYTHON") && !$0.key.hasPrefix("DYLD_") && !$0.key.hasPrefix("LD_") && $0.key != "VIRTUAL_ENV"
            }
            child.standardInput = input
            child.standardOutput = FileHandle.nullDevice
            child.standardError = FileHandle.nullDevice
            #if canImport(OSLog)
            Self.logger.notice("Engine child process launch requested")
            #endif
            try child.run()
            #if canImport(OSLog)
            Self.logger.notice("Engine child process started")
            #endif
            try input.fileHandleForReading.close()
        } catch {
            #if canImport(OSLog)
            Self.logger.error("Engine child process launch failed")
            #endif
            try? input.fileHandleForReading.close()
            try? input.fileHandleForWriting.close()
            if child.isRunning { await Self.stopProcess(child) }
            runtime.clean()
            lease = nil
            throw EngineConnectionError.launchFailed
        }
        process = child
        lastExitStatus = nil
        let launch = EngineLaunchSession(identifier: UUID(), processIdentifier: child.processIdentifier,
                                          socketPath: runtime.socketPath, token: credential)
        session = launch
        do {
            let deadline = ContinuousClock.now.advanced(by: .seconds(5))
            while ContinuousClock.now < deadline {
                try Task.checkCancellation()
                guard child.isRunning else {
                    #if canImport(OSLog)
                    Self.logger.error(
                        "Engine child exited before socket; status \(child.terminationStatus, privacy: .public)"
                    )
                    #endif
                    throw EngineConnectionError.launchFailed
                }
                var info = stat()
                if lstat(runtime.socketPath, &info) == 0, (info.st_mode & 0o170000) == 0o140000 {
                    #if canImport(OSLog)
                    Self.logger.notice("Engine IPC socket became ready")
                    #endif
                    return launch
                }
                try await Task.sleep(for: .milliseconds(20))
            }
            #if canImport(OSLog)
            Self.logger.error("Engine IPC socket readiness timed out")
            #endif
            throw EngineConnectionError.timedOut
        } catch {
            await Self.stopProcess(child)
            lastExitStatus = child.terminationStatus
            runtime.clean()
            process = nil; session = nil; lease = nil
            throw error
        }
    }

    public func terminateEngine() async {
        #if canImport(OSLog)
        Self.logger.notice("Engine termination requested")
        #endif
        if let stopping { await stopping.value; return }
        let identity = UUID()
        stopIdentity = identity
        let startup = starting
        startup?.cancel()
        let task = Task {
            _ = await startup?.result
            if let child = process {
                #if canImport(OSLog)
                Self.logger.notice("Engine termination stopping active child")
                #endif
                await Self.stopProcess(child)
                lastExitStatus = child.terminationStatus
            }
            lease?.clean()
            process = nil; session = nil; lease = nil
        }
        stopping = task
        await task.value
        if stopIdentity == identity { stopping = nil }
    }

    private nonisolated static func stopProcess(_ child: Process) async {
        // Cleanup must complete even when the startup caller has been cancelled.
        await Task.detached {
            guard child.isRunning else { return }
            #if canImport(OSLog)
            Self.logger.notice("Engine child graceful termination requested")
            #endif
            child.terminate()
            let deadline = ContinuousClock.now.advanced(by: .seconds(2))
            while child.isRunning, ContinuousClock.now < deadline { try? await Task.sleep(for: .milliseconds(20)) }
            if child.isRunning {
                #if canImport(OSLog)
                Self.logger.error("Engine child termination escalated to SIGKILL")
                #endif
                _ = kill(child.processIdentifier, SIGKILL)
            }
            // Foundation reaps the child; this wait runs on a detached cleanup task,
            // after bounded termination, never on the UI actor.
            while child.isRunning { try? await Task.sleep(for: .milliseconds(10)) }
        }.value
    }
}
