import Foundation
import Dispatch
import Synchronization
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// One nonblocking socket lifetime. All mutable resources are protected by Mutex;
/// I/O callbacks run on one private queue. No unchecked Sendable or cooperative-pool
/// blocking reads. A timeout/cancellation closes this lifetime: mutations are NEVER replayed.
nonisolated final class EngineSocketTransport: Sendable {
    private struct Pending {
        let trace: String
        let nonce: UUID
        let continuation: CheckedContinuation<IPCEnvelope, any Error>
    }
    private struct State {
        var fd: Int32 = -1
        var closed = false
        var connected = false
        var connecting: CheckedContinuation<Void, any Error>?
        var readSource: (any DispatchSourceRead)?
        var writeSource: (any DispatchSourceWrite)?
        var writeSuspended = false
        var incoming = [UInt8]()
        var outgoing = Data()
        var pending = [String: Pending]()
        var frameGeneration: UInt64 = 0
        var sequences = [String: Int]()
    }
    private let state = Mutex(State())
    private let queue = DispatchQueue(label: "worldofmysteries.ipc.io", qos: .userInitiated)
    let events: AsyncThrowingStream<IPCEnvelope, any Error>
    let failures: AsyncStream<EngineConnectionError>
    private let failureSink: AsyncStream<EngineConnectionError>.Continuation
    private let eventSink: AsyncThrowingStream<IPCEnvelope, any Error>.Continuation
    private static let maximumPending = 32
    private static let maximumQueuedBytes = 4 * IPCFrameCodec.maximumBytes

    init() {
        let channel = AsyncThrowingStream<IPCEnvelope, any Error>.makeStream(bufferingPolicy: .bufferingOldest(128))
        events = channel.stream
        eventSink = channel.continuation
        let closed = AsyncStream<EngineConnectionError>.makeStream(bufferingPolicy: .bufferingNewest(1))
        failures = closed.stream
        failureSink = closed.continuation
    }

    var isConnected: Bool { state.withLock { $0.connected && !$0.closed } }

    func connect(path: String, timeout: TimeInterval) async throws {
        try Task.checkCancellation()
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, any Error>) in
                queue.async {
                    self.state.withLock { s in
                        guard !s.closed, s.fd < 0 else {
                            continuation.resume(throwing: EngineConnectionError.notConnected); return
                        }
                        s.connecting = continuation
                        do {
                            try self.open(path: path, state: &s)
                            self.queue.asyncAfter(deadline: .now() + timeout) { [weak self] in
                                self?.state.withLock { s in
                                    if s.connecting != nil { self?.fail(&s, error: .timedOut) }
                                }
                            }
                        } catch { self.fail(&s, error: .connectionFailed) }
                    }
                }
            }
        } onCancel: { self.cancel() }
        try Task.checkCancellation()
    }

    func request(_ envelope: IPCEnvelope, timeout: TimeInterval) async throws -> IPCEnvelope {
        try Task.checkCancellation()
        guard envelope.kind == "request", let id = envelope.requestId else {
            throw EngineConnectionError.invalidFrame
        }
        let frame = try IPCFrameCodec.encode(envelope)
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async {
                    self.state.withLock { s in
                        guard s.connected, !s.closed else {
                            continuation.resume(throwing: EngineConnectionError.notConnected); return
                        }
                        guard s.pending[id] == nil else {
                            continuation.resume(throwing: EngineConnectionError.correlationMismatch); return
                        }
                        guard s.pending.count < Self.maximumPending,
                              s.outgoing.count + frame.count <= Self.maximumQueuedBytes else {
                            continuation.resume(throwing: EngineConnectionError.capacityExceeded); return
                        }
                        let nonce = UUID()
                        s.pending[id] = Pending(trace: envelope.traceId, nonce: nonce, continuation: continuation)
                        s.outgoing.append(frame)
                        if s.writeSuspended {
                            s.writeSuspended = false
                            s.writeSource?.resume()
                        }
                        self.flush(&s)
                        self.queue.asyncAfter(deadline: .now() + timeout) { [weak self] in
                            self?.state.withLock { s in
                                if s.pending[id]?.nonce == nonce { self?.fail(&s, error: .timedOut) }
                            }
                        }
                    }
                }
            }
        } onCancel: { self.cancel() }
    }

    func close() async {
        await withCheckedContinuation { continuation in
            queue.async {
                self.state.withLock { self.fail(&$0, error: .disconnected) }
                continuation.resume()
            }
        }
    }

    private func cancel() {
        queue.async { self.state.withLock { self.fail(&$0, error: .disconnected) } }
    }

    private func open(path: String, state s: inout State) throws {
        var address = sockaddr_un()
        let name = Array(path.utf8)
        guard !name.isEmpty, !name.contains(0), name.count < MemoryLayout.size(ofValue: address.sun_path) else {
            throw EngineConnectionError.invalidConfiguration
        }
        var info = stat()
        guard lstat(path, &info) == 0, (info.st_mode & 0o170000) == 0o140000,
              info.st_uid == getuid(), (info.st_mode & 0o077) == 0 else {
            throw EngineConnectionError.connectionFailed
        }
        address.sun_family = sa_family_t(AF_UNIX)
        #if canImport(Darwin)
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        #else
        let fd = Glibc.socket(AF_UNIX, Int32(SOCK_STREAM.rawValue), 0)
        #endif
        guard fd >= 0 else { throw EngineConnectionError.connectionFailed }
        s.fd = fd
        guard fcntl(fd, F_SETFL, O_NONBLOCK) == 0, fcntl(fd, F_SETFD, FD_CLOEXEC) == 0 else {
            throw EngineConnectionError.connectionFailed
        }
        #if canImport(Darwin)
        var noSignal: Int32 = 1
        guard setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, socklen_t(MemoryLayout<Int32>.size)) == 0 else {
            throw EngineConnectionError.connectionFailed
        }
        #endif
        withUnsafeMutableBytes(of: &address.sun_path) { $0.copyBytes(from: name) }
        let result = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                #if canImport(Darwin)
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
                #else
                Glibc.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
                #endif
            }
        }
        guard result == 0 || errno == EINPROGRESS else { throw EngineConnectionError.connectionFailed }
        let read = DispatchSource.makeReadSource(fileDescriptor: fd, queue: queue)
        let write = DispatchSource.makeWriteSource(fileDescriptor: fd, queue: queue)
        read.setEventHandler { [weak self] in self?.readAvailable() }
        write.setEventHandler { [weak self] in self?.writeAvailable() }
        // Both callbacks share this queue, and fail() invalidates state.fd before
        // cancelling either source. Only this cancel handler closes the descriptor.
        read.setCancelHandler { systemClose(fd) }
        s.readSource = read
        s.writeSource = write
        read.activate()
        write.activate()
        if result == 0 { finishConnection(&s) }
    }

    private func finishConnection(_ s: inout State) {
        s.connected = true
        let continuation = s.connecting
        s.connecting = nil
        continuation?.resume()
        flush(&s)
    }

    private func writeAvailable() {
        state.withLock { s in
            guard !s.closed else { return }
            if !s.connected {
                var error: Int32 = 0
                var size = socklen_t(MemoryLayout<Int32>.size)
                guard getsockopt(s.fd, SOL_SOCKET, SO_ERROR, &error, &size) == 0, error == 0 else {
                    fail(&s, error: .connectionFailed); return
                }
                finishConnection(&s)
            } else { flush(&s) }
        }
    }

    private func flush(_ s: inout State) {
        guard s.connected, !s.closed else { return }
        while !s.outgoing.isEmpty {
            let count = s.outgoing.withUnsafeBytes { bytes in
                #if canImport(Darwin)
                Darwin.send(s.fd, bytes.baseAddress!, bytes.count, 0)
                #else
                Glibc.send(s.fd, bytes.baseAddress!, bytes.count, Int32(MSG_NOSIGNAL))
                #endif
            }
            if count > 0 { s.outgoing.removeFirst(count) }
            else if count < 0, errno == EINTR { continue }
            else if count < 0, errno == EAGAIN || errno == EWOULDBLOCK { return }
            else { fail(&s, error: .disconnected); return }
        }
        if !s.writeSuspended {
            s.writeSuspended = true
            s.writeSource?.suspend()
        }
    }

    private func readAvailable() {
        state.withLock { s in
            guard s.connected, !s.closed else { return }
            var chunk = [UInt8](repeating: 0, count: 65_536)
            // Keep one callback bounded so cancellation and other connections progress.
            for _ in 0..<16 {
                let count = recv(s.fd, &chunk, chunk.count, 0)
                if count == 0 { fail(&s, error: .disconnected); return }
                if count < 0 {
                    if errno == EINTR { continue }
                    if errno == EAGAIN || errno == EWOULDBLOCK { return }
                    fail(&s, error: .disconnected); return
                }
                let wasEmpty = s.incoming.isEmpty
                s.incoming.append(contentsOf: chunk.prefix(count))
                if wasEmpty { startFrameDeadline(&s) }
                do {
                    while s.incoming.count >= 4 {
                        let size = s.incoming.prefix(4).reduce(0) { ($0 << 8) | Int($1) }
                        guard size > 0, size <= IPCFrameCodec.maximumBytes else { throw EngineConnectionError.invalidFrame }
                        guard s.incoming.count >= size + 4 else { break }
                        let message = try IPCFrameCodec.decode(Data(s.incoming[4..<(size + 4)]))
                        s.incoming.removeFirst(size + 4)
                        s.frameGeneration &+= 1
                        if !s.incoming.isEmpty { startFrameDeadline(&s) }
                        if message.kind == "event", let stream = message.streamId, let sequence = message.sequence {
                            guard s.sequences[stream].map({ sequence > $0 }) ?? true,
                                  s.sequences[stream] != nil || s.sequences.count < 16 else { throw EngineConnectionError.invalidFrame }
                            s.sequences[stream] = sequence
                            if case .dropped = eventSink.yield(message) { throw EngineConnectionError.capacityExceeded }
                        } else {
                            guard message.kind == "response", let id = message.requestId,
                                  let pending = s.pending[id], pending.trace == message.traceId else {
                                throw EngineConnectionError.correlationMismatch
                            }
                            s.pending.removeValue(forKey: id)
                            pending.continuation.resume(returning: message)
                        }
                    }
                } catch {
                    fail(&s, error: (error as? EngineConnectionError) ?? .invalidFrame); return
                }
            }
        }
    }

    private func startFrameDeadline(_ s: inout State) {
        s.frameGeneration &+= 1
        let generation = s.frameGeneration
        queue.asyncAfter(deadline: .now() + 5) { [weak self] in
            self?.state.withLock { s in
                if !s.incoming.isEmpty, s.frameGeneration == generation { self?.fail(&s, error: .timedOut) }
            }
        }
    }

    private func fail(_ s: inout State, error: EngineConnectionError) {
        guard !s.closed else { return }
        s.closed = true
        s.connected = false
        s.connecting?.resume(throwing: error)
        s.connecting = nil
        for pending in s.pending.values { pending.continuation.resume(throwing: error) }
        s.pending.removeAll()
        s.incoming.removeAll()
        s.outgoing.removeAll()
        if s.writeSuspended { s.writeSource?.resume(); s.writeSuspended = false }
        s.writeSource?.cancel()
        if let read = s.readSource { read.cancel() }
        else if s.fd >= 0 { systemClose(s.fd) }
        s.fd = -1
        s.readSource = nil
        s.writeSource = nil
        eventSink.finish(throwing: error)
        failureSink.yield(error)
        failureSink.finish()
    }

    deinit {
        state.withLock { s in
            if s.writeSuspended { s.writeSource?.resume() }
            s.writeSource?.cancel()
            if let read = s.readSource { read.cancel() }
            else if s.fd >= 0 { systemClose(s.fd) }
        }
        eventSink.finish()
        failureSink.finish()
    }
}

private nonisolated func systemClose(_ fd: Int32) {
    #if canImport(Darwin)
    _ = Darwin.close(fd)
    #else
    _ = Glibc.close(fd)
    #endif
}
