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
            ringGlyph
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

    /// 世界聆听符号。
    ///
    /// 对齐 `docs/05_UI/Interaction_Runtime_State_v1.0.md` §10：不使用强科技感麦克风作为主视觉。
    /// 这里改用与 `WOMDividerOrnament` 同一套菱形母题的装饰语言，
    /// 状态差异由母题组合、颜色与动效共同承担，而不是换一个科技图标。
    private var ringGlyph: some View {
        ZStack {
            ListeningRingDiamondShape()
                .stroke(iconColor, lineWidth: DesignTokens.Borders.hairline)
                .frame(width: 13, height: 13)

            glyphCore
        }
        .frame(width: 20, height: 20)
    }

    @ViewBuilder
    private var glyphCore: some View {
        switch state {
        case .idle:
            Circle()
                .fill(iconColor)
                .frame(width: 4, height: 4)
        case .listening:
            ZStack {
                Circle()
                    .trim(from: 0.06, to: 0.44)
                    .stroke(iconColor, lineWidth: 1.6)
                    .frame(width: 11, height: 11)
                Circle()
                    .trim(from: 0.56, to: 0.94)
                    .stroke(iconColor, lineWidth: 1.6)
                    .frame(width: 11, height: 11)
            }
        case .interpreting:
            ZStack {
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 11, height: 1.6)
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 1.6, height: 11)
            }
        case .deciding:
            Circle()
                .trim(from: 0, to: 0.62)
                .stroke(iconColor, lineWidth: 1.8)
                .frame(width: 12, height: 12)
        case .narrating:
            VStack(spacing: 2) {
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 10, height: 1.4)
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 8, height: 1.4)
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 10, height: 1.4)
            }
        case .speaking:
            HStack(alignment: .center, spacing: 2) {
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 1.6, height: 5)
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 1.6, height: 10)
                Rectangle()
                    .fill(iconColor)
                    .frame(width: 1.6, height: 6)
            }
        }
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

/// 菱形母题轮廓。
///
/// 用显式路径来表达菱形，而不是给矩形加一个静态 45° 旋转变换：
/// 源码级守卫无法区分「静态摆放」与「持续旋转动效」，路径表达同一个母题且不留歧义。
nonisolated struct ListeningRingDiamondShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.midY))
        path.closeSubpath()
        return path
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
