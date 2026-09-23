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
    private var prebootstrapTask: Task<Void, Never>?
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

    func applicationWillFinishLaunching(_ notification: Notification) {
        guard prebootstrapTask == nil, !terminating else { return }
        let manager = appState.processManager
        // Start the bundled Engine independently of SwiftUI/MainActor rendering.
        // Product UI can be expensive to construct on cold launch; process bootstrap
        // must not wait behind that presentation work.
        prebootstrapTask = Task.detached(priority: .userInitiated) {
            _ = try? await manager.startEngine()
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard launchTask == nil, !terminating else { return }
        let state = appState
        let prebootstrap = prebootstrapTask
        launchTask = Task {
            if let prebootstrap {
                await prebootstrap.value
            }
            guard !Task.isCancelled else { return }
            await state.startAndConnect()
        }
    }

    /// Deterministic synchronization point for lifecycle verification.
    ///
    /// This does not initiate startup; it only waits for the launch task created
    /// by applicationDidFinishLaunching. Returning false proves no lifecycle
    /// bootstrap was scheduled.
    func awaitPrebootstrapCompletion() async -> Bool {
        guard let prebootstrapTask else { return false }
        await prebootstrapTask.value
        return true
    }

    func awaitLaunchCompletion() async -> Bool {
        guard let launchTask else { return false }
        await launchTask.value
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !terminating else { return .terminateLater }
        terminating = true
        prebootstrapTask?.cancel()
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
