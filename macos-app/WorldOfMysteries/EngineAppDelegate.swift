#if canImport(AppKit)
import AppKit

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

    override init() {
        self.appState = AppState()
        super.init()
    }

    init(appState: AppState) {
        self.appState = appState
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard launchTask == nil, !terminating else { return }
        let state = appState
        launchTask = Task {
            await state.startAndConnect()
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
