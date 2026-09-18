import Foundation

/// Presentation of a normalized measurement supplied by the caller, never a domain calculation.
/// Non-finite input is unavailable, not a fabricated zero, full reserve or danger verdict.
nonisolated struct WOMMetricReading: Equatable, Sendable {
    let fraction: Double?

    init(_ value: Double) {
        fraction = value.isFinite ? min(max(value, 0), 1) : nil
    }

    var geometryFraction: Double { fraction ?? 0 }

    var percentText: String {
        guard let fraction else { return "读数不可用" }
        return "\(Int(fraction * 100))%"
    }

    func isBelow(_ threshold: Double?) -> Bool {
        guard let fraction, let threshold, threshold.isFinite,
              (0...1).contains(threshold)
        else { return false }
        return fraction < threshold
    }
}
