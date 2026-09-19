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
