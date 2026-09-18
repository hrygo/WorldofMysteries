import SwiftUI

/// Presentation of the runtime state supplied by the caller; this enum does not advance a turn.
public nonisolated enum ListeningRingState: String, Sendable, CaseIterable {
    case idle, listening, interpreting, deciding, narrating, speaking

    public var iconSource: WOMIconSource {
        switch self {
        case .idle, .listening: .system(.voiceAdvice)
        case .interpreting: .status(.active)
        case .deciding: .asset(.character)
        case .narrating: .asset(.codex)
        case .speaking: .system(.audioReplay)
        }
    }

    /// No default speaker identity: the runtime may be performing any known character.
    public var promptText: String { promptText(speakerName: nil) }

    public func promptText(speakerName: String?) -> String {
        switch self {
        case .idle: return "等待你的声音"
        case .listening: return "正在倾听你的建议…"
        case .interpreting: return "正在理解你的建议…"
        case .deciding: return "人物正在权衡动机…"
        case .narrating: return "叙事展开中…"
        case .speaking:
            let name = speakerName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return name.isEmpty ? "人物正在回应…" : "\(name)正在回应…"
        }
    }
}

/// Deterministic visual projection, not a second runtime state machine or audio simulator.
nonisolated struct ListeningRingPresentation: Sendable {
    let state: ListeningRingState
    let audioLevel: Double
    let reduceMotion: Bool
    let isEnabled: Bool
    let appearsActive: Bool

    private var motionAllowed: Bool { !reduceMotion && isEnabled && appearsActive }
    private var measuredAudio: Double? {
        guard state == .listening || state == .speaking else { return nil }
        return WOMMetricReading(audioLevel).fraction
    }

    var shouldBreathe: Bool {
        motionAllowed && state == .listening && (measuredAudio ?? 0) <= 0
    }

    func scale(at phase: Double) -> CGFloat {
        guard motionAllowed else { return 1 }
        if let level = measuredAudio, level > 0 {
            return 1 + CGFloat(level) * DesignTokens.ComponentMetrics.ListeningRing.audioScaleGain
        }
        guard shouldBreathe else { return 1 }
        let fraction = WOMMetricReading(phase).geometryFraction
        let low = DesignTokens.ComponentMetrics.ListeningRing.breathingScaleMin
        let high = DesignTokens.ComponentMetrics.ListeningRing.breathingScaleMax
        return low + CGFloat(fraction) * (high - low)
    }

    func opacity(at phase: Double) -> Double {
        let low = DesignTokens.ComponentMetrics.ListeningRing.breathingOpacityMin
        let high = DesignTokens.ComponentMetrics.ListeningRing.breathingOpacityMax
        guard state != .idle else { return low }
        guard shouldBreathe else {
            return DesignTokens.ComponentMetrics.ListeningRing.reducedMotionOpacity
        }
        return low + WOMMetricReading(phase).geometryFraction * (high - low)
    }
}

/// Global voice-interaction ring. Listening breathes; character deliberation stays quiet.
public struct ListeningRingView: View {
    public let state: ListeningRingState
    public let audioLevel: Double
    public let speakerName: String?
    public var onRingTapped: (@MainActor () -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.controlActiveState) private var controlActiveState
    @FocusState private var isRingFocused: Bool

    public init(
        state: ListeningRingState = .idle,
        audioLevel: Double = 0.0,
        speakerName: String? = nil,
        onRingTapped: (@MainActor () -> Void)? = nil
    ) {
        self.state = state
        self.audioLevel = audioLevel
        self.speakerName = speakerName
        self.onRingTapped = onRingTapped
    }

    private var presentation: ListeningRingPresentation {
        ListeningRingPresentation(
            state: state, audioLevel: audioLevel, reduceMotion: reduceMotion,
            isEnabled: isEnabled, appearsActive: controlActiveState != .inactive
        )
    }

    private var promptText: String { state.promptText(speakerName: speakerName) }

    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            interactiveRing
            Text(promptText)
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityHidden(onRingTapped != nil)
        }
    }

    @ViewBuilder
    private var interactiveRing: some View {
        if let onRingTapped {
            Button(action: onRingTapped) { ringVisual }
                .buttonStyle(MysticPressableButtonStyle())
                .focused($isRingFocused)
                .accessibilityLabel(promptText)
                .accessibilityHint("激活语音交互")
        } else {
            ringVisual.accessibilityHidden(true)
        }
    }

    @ViewBuilder
    private var outerRing: some View {
        if presentation.shouldBreathe {
            // The animator exists only while listening; leaving this branch removes the loop.
            // No repeat-forever state survives into deciding or an inactive window.
            outerRingShape.phaseAnimator([0.0, 1.0]) { ring, phase in
                ring.scaleEffect(presentation.scale(at: phase))
                    .opacity(presentation.opacity(at: phase))
            } animation: { _ in
                .easeInOut(duration: DesignTokens.Motion.listeningPulseDuration / 2)
            }
        } else {
            outerRingShape
                .scaleEffect(presentation.scale(at: 0))
                .opacity(presentation.opacity(at: 0))
        }
    }

    private var outerRingShape: some View {
        Circle()
            .stroke(
                state == .listening ? Color.Mystic.spiritualGlow : Color.Mystic.brassGoldGlow,
                lineWidth: DesignTokens.Borders.heavy
            )
            .frame(
                width: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault,
                height: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault
            )
    }

    private var ringVisual: some View {
        ZStack {
            outerRing
            Circle()
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
                .frame(
                    width: DesignTokens.ComponentMetrics.ListeningRing.middleRingDiameter,
                    height: DesignTokens.ComponentMetrics.ListeningRing.middleRingDiameter
                )
            Circle()
                .fill(Color.Mystic.obsidianCard)
                .frame(
                    width: DesignTokens.ComponentMetrics.ListeningRing.innerCircleDiameter,
                    height: DesignTokens.ComponentMetrics.ListeningRing.innerCircleDiameter
                )
                .overlay {
                    Circle().stroke(Color.Mystic.brassGoldPrimary, lineWidth: DesignTokens.Borders.chamfer)
                }
                .shadow(
                    color: Color.Mystic.brassGoldPrimary.opacity(reduceMotion ? 0.2 : 0.35),
                    radius: reduceMotion
                        ? DesignTokens.ComponentMetrics.ListeningRing.reducedMotionShadowRadius
                        : DesignTokens.ComponentMetrics.ListeningRing.idleShadowRadius
                )
            WOMIcon(source: state.iconSource, size: .compact)
                .foregroundStyle(iconColor)
            Circle()
                .stroke(Color.Mystic.textGoldAccent, lineWidth: DesignTokens.Accessibility.focusRingWidth)
                .frame(
                    width: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault
                        + DesignTokens.Accessibility.focusRingOffset * 2,
                    height: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault
                        + DesignTokens.Accessibility.focusRingOffset * 2
                )
                .opacity(isRingFocused && isEnabled ? 1 : 0)
        }
        .contentShape(Circle())
    }

    private var iconColor: Color {
        switch state {
        case .idle: Color.Mystic.brassGoldPrimary
        case .listening, .interpreting: Color.Mystic.spiritualBlue
        case .deciding: Color.Mystic.brassGoldHover
        case .narrating, .speaking: Color.Mystic.textGoldAccent
        }
    }
}

#Preview("Listening Ring States") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        HStack(spacing: DesignTokens.Spacing.xl) {
            ForEach(ListeningRingState.allCases, id: \.rawValue) { state in
                ListeningRingView(state: state)
            }
        }
    }
    .frame(width: 720, height: 160)
}
