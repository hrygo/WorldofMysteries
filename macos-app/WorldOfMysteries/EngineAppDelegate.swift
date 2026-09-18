#if canImport(AppKit)
import AppKit

/// Native termination barrier, rather than fire-and-forget cleanup after termination.
/// Forced App exit is separately handled by the Engine's parent-death watchdog.
@MainActor
final class EngineAppDelegate: NSObject, NSApplicationDelegate {
    weak var appState: AppState?
    private var terminating = false

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let appState else { return .terminateNow }
        guard !terminating else { return .terminateLater }
        terminating = true
        Task {
            await appState.shutdown()
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
}
#endif
