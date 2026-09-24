import Foundation

#if canImport(AVFoundation)
@preconcurrency import AVFoundation
#endif

public nonisolated enum PlaybackInterruption: Sendable, Equatable {
    case deviceConfigurationChanged
}

public nonisolated protocol PlaybackInterruptionSource: AnyObject, Sendable {
    func start(_ handler: @escaping @Sendable (PlaybackInterruption) -> Void)
    func stop()
}

public nonisolated final class SystemPlaybackInterruptionSource:
    PlaybackInterruptionSource, @unchecked Sendable
{
    private let lock = NSLock()
    private var observer: NSObjectProtocol?

    public init() {}

    public func start(
        _ handler: @escaping @Sendable (PlaybackInterruption) -> Void
    ) {
        lock.lock()
        defer { lock.unlock() }
        guard observer == nil else { return }
        #if canImport(AVFoundation)
        observer = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: nil,
            queue: nil
        ) { _ in
            handler(.deviceConfigurationChanged)
        }
        #endif
    }

    public func stop() {
        lock.lock()
        let token = observer
        observer = nil
        lock.unlock()
        if let token {
            NotificationCenter.default.removeObserver(token)
        }
    }

    deinit {
        stop()
    }
}
