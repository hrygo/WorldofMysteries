import SwiftUI

public struct ArtifactAmbientField: View {
  let tone: MysticTone
  let intensity: Double
  let particleCount: Int
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  public init(tone: MysticTone, intensity: Double = 0.7, particleCount: Int = 18) {
    self.tone = tone
    self.intensity = min(max(intensity, 0), 1)
    self.particleCount = max(0, particleCount)
  }

  public var body: some View {
    TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 24.0)) { timeline in
      Canvas { context, size in
        let t = timeline.date.timeIntervalSinceReferenceDate
        let center = CGPoint(x: size.width / 2, y: size.height * 0.46)
        let radius = max(size.width, size.height) * 0.48
        for index in 0..<particleCount {
          let seed = Double(index + 1)
          let angle = seed * 1.731 + t * (0.045 + seed.truncatingRemainder(dividingBy: 5) * 0.008)
          let radial = 0.18 + seed.truncatingRemainder(dividingBy: 11) / 16
          let point = CGPoint(
            x: center.x + cos(angle) * radius * radial,
            y: center.y + sin(angle * 0.91) * radius * radial * 0.72)
          let r = 0.8 + seed.truncatingRemainder(dividingBy: 4) * 0.45
          context.opacity = (0.06 + 0.20 * intensity) * (0.72 + sin(t * 0.9 + seed) * 0.28)
          context.fill(
            Path(ellipseIn: CGRect(x: point.x - r, y: point.y - r, width: r * 2, height: r * 2)),
            with: .color(tone.accent))
        }
      }
    }
    .allowsHitTesting(false)
    .accessibilityHidden(true)
  }
}

public struct ArtifactPulseRing: View {
  let tone: MysticTone
  let active: Bool
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  public init(tone: MysticTone, active: Bool = true) {
    self.tone = tone
    self.active = active
  }

  public var body: some View {
    TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 30.0)) { timeline in
      let pulse =
        active && !reduceMotion
        ? (sin(timeline.date.timeIntervalSinceReferenceDate * 2.1) + 1) * 0.5 : 0.35
      Circle()
        .stroke(
          tone.accent.opacity(0.28 + pulse * 0.42), lineWidth: DesignTokens.Borders.standard + pulse
        )
        .scaleEffect(0.92 + pulse * 0.045)
    }
    .allowsHitTesting(false).accessibilityHidden(true)
  }
}

public struct ArtifactTypewriterText: View {
  let text: String
  let font: Font
  let intervalSeconds: Double
  @State private var count = 0
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  public init(_ text: String, font: Font = Font.Mystic.bodyMedium, intervalSeconds: Double = 0.02) {
    self.text = text
    self.font = font
    self.intervalSeconds = intervalSeconds
  }

  public var body: some View {
    Text(String(text.prefix(count)))
      .font(font).foregroundStyle(Color.Mystic.textPrimary).textSelection(.enabled)
      .task(id: text) {
        count = reduceMotion ? text.count : 0
        guard !reduceMotion, !text.isEmpty else { return }
        for index in 1...text.count {
          guard !Task.isCancelled else { return }
          count = index
          if index < text.count { try? await Task.sleep(for: .seconds(intervalSeconds)) }
        }
      }
  }
}

public struct ArtifactMirrorSurface: View {
  let active: Bool
  let warning: Bool
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  public init(active: Bool, warning: Bool = false) {
    self.active = active
    self.warning = warning
  }

  public var body: some View {
    TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 30.0)) { timeline in
      Canvas { context, size in
        let tone: MysticTone = warning ? .crimson : .azure
        let t = timeline.date.timeIntervalSinceReferenceDate
        let c = CGPoint(x: size.width / 2, y: size.height / 2)
        let s = min(size.width, size.height)
        let base = Path(
          ellipseIn: CGRect(x: c.x - s * 0.39, y: c.y - s * 0.45, width: s * 0.78, height: s * 0.9))
        context.opacity = 0.34
        context.fill(base, with: .color(Color.Mystic.abyssVoid))
        context.stroke(
          base, with: .color(tone.accent.opacity(0.55)), lineWidth: DesignTokens.Borders.standard)
        for i in 0..<4 {
          let phase =
            active && !reduceMotion
            ? (t * 0.24 + Double(i) * 0.2).truncatingRemainder(dividingBy: 1) : Double(i) / 4
          let scale = 0.46 + phase * 0.54
          let rect = CGRect(
            x: c.x - s * 0.32 * scale, y: c.y - s * 0.37 * scale, width: s * 0.64 * scale,
            height: s * 0.74 * scale)
          context.opacity = 0.24 * (1 - phase)
          context.stroke(
            Path(ellipseIn: rect), with: .color(tone.accent),
            lineWidth: DesignTokens.Borders.hairline)
        }
      }
    }.accessibilityHidden(true)
  }
}

public struct ArtifactPortalSurface: View {
  let active: Bool
  let tone: MysticTone
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  public init(active: Bool, tone: MysticTone = .azure) {
    self.active = active
    self.tone = tone
  }

  public var body: some View {
    TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 30.0)) { timeline in
      let rotation = active && !reduceMotion ? timeline.date.timeIntervalSinceReferenceDate * 18 : 0
      ZStack {
        Circle().stroke(tone.accent.opacity(0.16), lineWidth: DesignTokens.Spacing.lg)
        Circle().trim(from: 0.08, to: 0.92)
          .stroke(
            tone.accent.opacity(0.72),
            style: StrokeStyle(lineWidth: DesignTokens.Borders.heavy, lineCap: .round)
          )
          .rotationEffect(.degrees(rotation))
        Circle().fill(
          RadialGradient(
            colors: [tone.accent.opacity(active ? 0.15 : 0.05), Color.Mystic.abyssVoid],
            center: .center, startRadius: 4, endRadius: 100)
        )
        .padding(DesignTokens.Spacing.xl)
      }
    }.accessibilityHidden(true)
  }
}

public struct ArtifactReticleSurface: View {
  let locked: Bool
  let confidence: Double
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  public init(locked: Bool, confidence: Double) {
    self.locked = locked
    self.confidence = min(max(confidence, 0), 1)
  }

  public var body: some View {
    TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 30.0)) { timeline in
      let pulse =
        locked && !reduceMotion
        ? (sin(timeline.date.timeIntervalSinceReferenceDate * 4.2) + 1) * 0.5 : 0.2
      ZStack {
        Circle().stroke(
          Color.Mystic.statusDanger.opacity(0.25), lineWidth: DesignTokens.Borders.hairline)
        Circle().trim(from: 0, to: confidence).stroke(
          Color.Mystic.statusDanger,
          style: StrokeStyle(lineWidth: DesignTokens.Borders.heavy, lineCap: .round)
        ).rotationEffect(.degrees(-90))
        Rectangle().fill(Color.Mystic.statusDanger.opacity(0.35)).frame(
          width: DesignTokens.Borders.hairline, height: 160)
        Rectangle().fill(Color.Mystic.statusDanger.opacity(0.35)).frame(
          width: 160, height: DesignTokens.Borders.hairline)
        Circle().stroke(
          Color.Mystic.statusDanger.opacity(0.65), lineWidth: DesignTokens.Borders.standard
        ).frame(width: 52 + pulse * 10, height: 52 + pulse * 10)
      }
    }.accessibilityHidden(true)
  }
}
