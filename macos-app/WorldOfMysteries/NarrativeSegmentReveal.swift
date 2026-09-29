import Foundation
import Observation

/// Reveals one committed turn's narrative a segment at a time.
///
/// This is presentation, not streaming, and the difference matters. The Engine
/// publishes a turn's narrative atomically: `narrative_segments` is empty until
/// `narrative_state` is `ready`, and complete when it is. Nothing here invents a
/// segment the Engine never sent, and the reveal always ends on exactly the
/// snapshot it started from — a reader can never end up looking at a version of
/// the turn that was never committed.
///
/// Published narrative blocks are append-only under the post-COMMIT SQL
/// authorizer, so a longer snapshot continues the reveal rather than restarting
/// it, and a new turn starts over.
@MainActor
@Observable
public final class NarrativeSegmentReveal {
    /// Roughly a reading beat. Short enough that a two-segment turn reads as one
    /// continuous paragraph, long enough that a five-segment turn does not
    /// appear all at once.
    public static let defaultCadence = Duration.milliseconds(420)

    @ObservationIgnored private let cadence: Duration
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var turnId: String?
    @ObservationIgnored private var segmentCount = 0

    /// How many of the authoritative segments are currently on screen. Never
    /// larger than the snapshot, never smaller than the previous count for the
    /// same turn.
    public private(set) var visibleCount = 0
    /// True while segments are still being revealed for this turn.
    public private(set) var isRevealing = false

    public init(cadence: Duration = NarrativeSegmentReveal.defaultCadence) {
        self.cadence = cadence
    }

    /// The prefix of the authoritative snapshot the reader may see.
    public func visible<Segment>(
        from segments: [Segment],
        turnId: String
    ) -> [Segment] {
        guard self.turnId == turnId else { return [] }
        return Array(segments.prefix(visibleCount))
    }

    /// Advance the reveal toward the authoritative snapshot.
    ///
    /// The first segment of a turn appears with the text itself; the rest follow
    /// on the cadence. Calling this repeatedly with the same turn is the normal
    /// case — the App re-reads the projection until the work settles.
    public func present<Segment>(turnId: String, segments: [Segment]) {
        if self.turnId != turnId {
            stop()
            self.turnId = turnId
        }
        let total = segments.count
        guard total > 0 else {
            visibleCount = 0
            return
        }
        // Defensive: a snapshot can only grow for one turn, so a count that
        // exceeds it means the reader was moved to a shorter projection.
        if visibleCount > total {
            visibleCount = total
        }
        if visibleCount == 0 {
            visibleCount = 1
        }
        guard visibleCount < total else {
            stop()
            return
        }
        isRevealing = true
        task?.cancel()
        task = Task { [weak self] in
            guard let self else { return }
            while self.visibleCount < total {
                do {
                    try await Task.sleep(for: self.cadence)
                } catch {
                    return
                }
                guard self.turnId == turnId else { return }
                self.visibleCount = min(total, self.visibleCount + 1)
            }
            self.stop()
        }
    }

    /// Forget the current turn. The next `present` starts from its first
    /// segment again.
    public func reset() {
        stop()
        turnId = nil
        visibleCount = 0
    }

    private func stop() {
        task?.cancel()
        task = nil
        isRevealing = false
    }
}
