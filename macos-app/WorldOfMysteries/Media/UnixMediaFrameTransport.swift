import Dispatch
import Foundation
import Synchronization

#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public nonisolated enum MediaSocketTransportFailure: Error, Sendable, Equatable, LocalizedError {
    case invalidConfiguration
    case connectionFailed
    case notConnected
    case timedOut
    case disconnected
    case capacityExceeded
    case invalidFrame

    public var errorDescription: String? {
        "The local media transport could not maintain a valid bounded stream."
    }
}

public nonisolated protocol MediaFrameTransport: Sendable {
    func connect(path: String, timeout: TimeInterval) async throws
    func send(_ frame: MediaFrame) async throws
    func frameStream() -> AsyncThrowingStream<MediaFrame, any Error>
    func close() async
}

/// One bounded AF_UNIX media-channel lifetime.
///
/// This deliberately mirrors the control transport's filesystem/peer boundary,
/// but parses the independent Engine Media framing contract instead of IPC JSON.
/// No ticket, PCM, socket path or private payload is emitted to diagnostics.
public nonisolated final class UnixMediaFrameTransport: MediaFrameTransport, Sendable {
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
        var pendingSends: [CheckedContinuation<Void, any Error>] = []
        var frameGeneration: UInt64 = 0
    }

    private let state = Mutex(State())
    private let queue = DispatchQueue(label: "worldofmysteries.media.io", qos: .userInitiated)
    private let frames: AsyncThrowingStream<MediaFrame, any Error>
    private let frameSink: AsyncThrowingStream<MediaFrame, any Error>.Continuation

    private static let maximumQueuedBytes = 2 * MediaFrameCodec.maximumPayloadBytes
    private static let maximumBufferedBytes =
        2 * (8 + MediaFrameCodec.maximumHeaderBytes + MediaFrameCodec.maximumPayloadBytes)

    public init() {
        let channel = AsyncThrowingStream<MediaFrame, any Error>.makeStream(
            bufferingPolicy: .bufferingOldest(32)
        )
        frames = channel.stream
        frameSink = channel.continuation
    }

    public func frameStream() -> AsyncThrowingStream<MediaFrame, any Error> {
        frames
    }

    public func connect(path: String, timeout: TimeInterval = 5) async throws {
        guard timeout.isFinite, timeout > 0 else {
            throw MediaSocketTransportFailure.invalidConfiguration
        }
        try Task.checkCancellation()
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, any Error>) in
                queue.async {
                    self.state.withLock { state in
                        guard !state.closed, state.fd < 0 else {
                            continuation.resume(throwing: MediaSocketTransportFailure.notConnected)
                            return
                        }
                        state.connecting = continuation
                        do {
                            try self.open(path: path, state: &state)
                            self.queue.asyncAfter(deadline: .now() + timeout) { [weak self] in
                                self?.state.withLock { state in
                                    if state.connecting != nil {
                                        self?.fail(&state, error: .timedOut)
                                    }
                                }
                            }
                        } catch let failure as MediaSocketTransportFailure {
                            self.fail(&state, error: failure)
                        } catch {
                            self.fail(&state, error: .connectionFailed)
                        }
                    }
                }
            }
        } onCancel: {
            self.cancel()
        }
        try Task.checkCancellation()
    }

    public func send(_ frame: MediaFrame) async throws {
        let encoded: Data
        do {
            encoded = try MediaFrameCodec.encode(frame)
        } catch {
            throw MediaSocketTransportFailure.invalidFrame
        }

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, any Error>) in
            queue.async {
                self.state.withLock { state in
                    guard state.connected, !state.closed else {
                        continuation.resume(throwing: MediaSocketTransportFailure.notConnected)
                        return
                    }
                    guard state.outgoing.count + encoded.count <= Self.maximumQueuedBytes else {
                        continuation.resume(throwing: MediaSocketTransportFailure.capacityExceeded)
                        return
                    }
                    state.outgoing.append(encoded)
                    state.pendingSends.append(continuation)
                    if state.writeSuspended {
                        state.writeSuspended = false
                        state.writeSource?.resume()
                    }
                    // send() is a delivery barrier, not merely an enqueue call:
                    // Stop relies on CANCEL being flushed before close() tears
                    // down the socket.
                    self.flush(&state)
                }
            }
        }
    }

    public func close() async {
        await withCheckedContinuation { continuation in
            queue.async {
                self.state.withLock { self.fail(&$0, error: .disconnected) }
                continuation.resume()
            }
        }
    }

    private func cancel() {
        queue.async {
            self.state.withLock { self.fail(&$0, error: .disconnected) }
        }
    }

    private func open(path: String, state: inout State) throws {
        var address = sockaddr_un()
        let name = Array(path.utf8)
        guard !name.isEmpty,
              !name.contains(0),
              name.count < MemoryLayout.size(ofValue: address.sun_path)
        else {
            throw MediaSocketTransportFailure.invalidConfiguration
        }

        var info = stat()
        guard lstat(path, &info) == 0,
              (info.st_mode & 0o170000) == 0o140000,
              info.st_uid == getuid(),
              (info.st_mode & 0o077) == 0
        else {
            throw MediaSocketTransportFailure.connectionFailed
        }

        address.sun_family = sa_family_t(AF_UNIX)
        #if canImport(Darwin)
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        #else
        let fd = Glibc.socket(AF_UNIX, Int32(SOCK_STREAM.rawValue), 0)
        #endif
        guard fd >= 0 else { throw MediaSocketTransportFailure.connectionFailed }
        state.fd = fd

        guard fcntl(fd, F_SETFL, O_NONBLOCK) == 0,
              fcntl(fd, F_SETFD, FD_CLOEXEC) == 0
        else {
            throw MediaSocketTransportFailure.connectionFailed
        }
        #if canImport(Darwin)
        var noSignal: Int32 = 1
        guard setsockopt(
            fd,
            SOL_SOCKET,
            SO_NOSIGPIPE,
            &noSignal,
            socklen_t(MemoryLayout<Int32>.size)
        ) == 0 else {
            throw MediaSocketTransportFailure.connectionFailed
        }
        #endif

        withUnsafeMutableBytes(of: &address.sun_path) { raw in
            raw.copyBytes(from: name)
        }
        let result = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                #if canImport(Darwin)
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
                #else
                Glibc.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
                #endif
            }
        }
        guard result == 0 || errno == EINPROGRESS else {
            throw MediaSocketTransportFailure.connectionFailed
        }

        let read = DispatchSource.makeReadSource(fileDescriptor: fd, queue: queue)
        let write = DispatchSource.makeWriteSource(fileDescriptor: fd, queue: queue)
        read.setEventHandler { [weak self] in self?.readAvailable() }
        write.setEventHandler { [weak self] in self?.writeAvailable() }
        read.setCancelHandler { closeMediaFD(fd) }
        state.readSource = read
        state.writeSource = write
        read.activate()
        write.activate()
        if result == 0 {
            finishConnection(&state)
        }
    }

    private func finishConnection(_ state: inout State) {
        state.connected = true
        let continuation = state.connecting
        state.connecting = nil
        continuation?.resume()
        flush(&state)
    }

    private func writeAvailable() {
        state.withLock { state in
            guard !state.closed else { return }
            if !state.connected {
                var error: Int32 = 0
                var size = socklen_t(MemoryLayout<Int32>.size)
                guard getsockopt(state.fd, SOL_SOCKET, SO_ERROR, &error, &size) == 0,
                      error == 0
                else {
                    fail(&state, error: .connectionFailed)
                    return
                }
                finishConnection(&state)
            } else {
                flush(&state)
            }
        }
    }

    private func flush(_ state: inout State) {
        guard state.connected, !state.closed else { return }
        while !state.outgoing.isEmpty {
            let count = state.outgoing.withUnsafeBytes { bytes in
                #if canImport(Darwin)
                Darwin.send(state.fd, bytes.baseAddress!, bytes.count, 0)
                #else
                Glibc.send(state.fd, bytes.baseAddress!, bytes.count, Int32(MSG_NOSIGNAL))
                #endif
            }
            if count > 0 {
                state.outgoing.removeFirst(count)
            } else if count < 0, errno == EINTR {
                continue
            } else if count < 0, errno == EAGAIN || errno == EWOULDBLOCK {
                return
            } else {
                fail(&state, error: .disconnected)
                return
            }
        }
        let completed = state.pendingSends
        state.pendingSends.removeAll(keepingCapacity: true)
        for continuation in completed {
            continuation.resume()
        }
        if !state.writeSuspended {
            state.writeSuspended = true
            state.writeSource?.suspend()
        }
    }

    private func readAvailable() {
        state.withLock { state in
            guard state.connected, !state.closed else { return }
            var chunk = [UInt8](repeating: 0, count: 65_536)

            for _ in 0..<16 {
                let count = recv(state.fd, &chunk, chunk.count, 0)
                if count == 0 {
                    fail(&state, error: .disconnected)
                    return
                }
                if count < 0 {
                    if errno == EINTR { continue }
                    if errno == EAGAIN || errno == EWOULDBLOCK { return }
                    fail(&state, error: .disconnected)
                    return
                }
                guard state.incoming.count + count <= Self.maximumBufferedBytes else {
                    fail(&state, error: .capacityExceeded)
                    return
                }

                let wasEmpty = state.incoming.isEmpty
                state.incoming.append(contentsOf: chunk.prefix(count))
                if wasEmpty {
                    startFrameDeadline(&state)
                }

                do {
                    try drainFrames(&state)
                } catch let failure as MediaSocketTransportFailure {
                    fail(&state, error: failure)
                    return
                } catch {
                    fail(&state, error: .invalidFrame)
                    return
                }
            }
        }
    }

    private func drainFrames(_ state: inout State) throws {
        while state.incoming.count >= 8 {
            let headerLength = readUInt32(state.incoming[0..<4])
            let payloadLength = readUInt32(state.incoming[4..<8])
            guard (2...MediaFrameCodec.maximumHeaderBytes).contains(headerLength),
                  payloadLength <= MediaFrameCodec.maximumPayloadBytes
            else {
                throw MediaSocketTransportFailure.invalidFrame
            }
            let total = 8 + headerLength + payloadLength
            guard total <= Self.maximumBufferedBytes else {
                throw MediaSocketTransportFailure.capacityExceeded
            }
            guard state.incoming.count >= total else { break }

            let frameData = Data(state.incoming[0..<total])
            let frame: MediaFrame
            do {
                frame = try MediaFrameCodec.decode(frameData)
            } catch {
                throw MediaSocketTransportFailure.invalidFrame
            }
            state.incoming.removeFirst(total)
            state.frameGeneration &+= 1
            if !state.incoming.isEmpty {
                startFrameDeadline(&state)
            }
            if case .dropped = frameSink.yield(frame) {
                throw MediaSocketTransportFailure.capacityExceeded
            }
        }
    }

    private func startFrameDeadline(_ state: inout State) {
        state.frameGeneration &+= 1
        let generation = state.frameGeneration
        queue.asyncAfter(deadline: .now() + 5) { [weak self] in
            self?.state.withLock { state in
                if !state.incoming.isEmpty, state.frameGeneration == generation {
                    self?.fail(&state, error: .timedOut)
                }
            }
        }
    }

    private func fail(_ state: inout State, error: MediaSocketTransportFailure) {
        guard !state.closed else { return }
        state.closed = true
        state.connected = false
        state.connecting?.resume(throwing: error)
        state.connecting = nil
        let pendingSends = state.pendingSends
        state.pendingSends.removeAll()
        for continuation in pendingSends {
            continuation.resume(throwing: error)
        }
        state.incoming.removeAll()
        state.outgoing.removeAll()
        if state.writeSuspended {
            state.writeSource?.resume()
            state.writeSuspended = false
        }
        state.writeSource?.cancel()
        if let read = state.readSource {
            read.cancel()
        } else if state.fd >= 0 {
            closeMediaFD(state.fd)
        }
        state.fd = -1
        state.readSource = nil
        state.writeSource = nil
        frameSink.finish(throwing: error)
    }

    deinit {
        state.withLock { state in
            let pendingSends = state.pendingSends
            state.pendingSends.removeAll()
            for continuation in pendingSends {
                continuation.resume(throwing: MediaSocketTransportFailure.disconnected)
            }
            if state.writeSuspended {
                state.writeSource?.resume()
            }
            state.writeSource?.cancel()
            if let read = state.readSource {
                read.cancel()
            } else if state.fd >= 0 {
                closeMediaFD(state.fd)
            }
        }
        frameSink.finish()
    }

    private func readUInt32(_ bytes: ArraySlice<UInt8>) -> Int {
        bytes.reduce(0) { ($0 << 8) | Int($1) }
    }
}

private nonisolated func closeMediaFD(_ fd: Int32) {
    #if canImport(Darwin)
    _ = Darwin.close(fd)
    #else
    _ = Glibc.close(fd)
    #endif
}
