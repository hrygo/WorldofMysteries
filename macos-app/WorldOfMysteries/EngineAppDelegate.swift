#if canImport(AppKit)
import AppKit
#if canImport(OSLog)
import OSLog
#endif

/// Owns the process-wide Engine lifecycle.
///
/// Engine startup is a process responsibility, not a side effect of any one
/// SwiftUI view appearing. Keeping the single AppState here also guarantees the
/// UI, reconnect commands, and termination barrier all address the same Engine
/// session.
@MainActor
final class EngineAppDelegate: NSObject, NSApplicationDelegate {
    let appState: AppState
    private var launchTask: Task<Void, Never>?
    private var terminating = false

    #if canImport(OSLog)
    private let logger = Logger(
        subsystem: "dev.worldofmysteries",
        category: "EngineLifecycle"
    )
    #endif

    override init() {
        self.appState = AppState()
        super.init()
    }

    init(appState: AppState) {
        self.appState = appState
        super.init()
    }

    /// Schedule Engine bootstrap at the earliest process-level AppKit lifecycle
    /// callback. Heavy SwiftUI scene construction must not be able to postpone
    /// local Engine startup until after the App has fully finished launching.
    func applicationWillFinishLaunching(_ notification: Notification) {
        scheduleEngineBootstrap()
    }

    /// Idempotent fallback for launch paths that do not deliver will-finish
    /// before this delegate is attached.
    func applicationDidFinishLaunching(_ notification: Notification) {
        scheduleEngineBootstrap()
    }

    private func scheduleEngineBootstrap() {
        guard launchTask == nil, !terminating else { return }
        #if canImport(OSLog)
        logger.notice("Engine lifecycle bootstrap scheduled")
        #endif
        let state = appState
        launchTask = Task(priority: .userInitiated) { [weak self] in
            #if canImport(OSLog)
            self?.logger.notice("Engine lifecycle bootstrap started")
            #endif
            await state.startAndConnect()
            #if canImport(OSLog)
            self?.logger.notice("Engine lifecycle bootstrap completed")
            #endif
        }
    }

    /// Deterministic synchronization point for lifecycle verification.
    ///
    /// This does not initiate startup; it only waits for the launch task created
    /// by applicationDidFinishLaunching. Returning false proves no lifecycle
    /// bootstrap was scheduled.
    func awaitLaunchCompletion() async -> Bool {
        guard let launchTask else { return false }
        await launchTask.value
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !terminating else { return .terminateLater }
        terminating = true
        launchTask?.cancel()
        let state = appState
        Task {
            await state.shutdown()
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
}
#endif
