import SwiftUI

/// 交互状态对齐 `docs/05_UI/Interaction_Runtime_State_v1.0.md`
public enum ListeningRingState: String, Sendable, CaseIterable {
    case idle = "idle"
    case listening = "listening"
    case interpreting = "interpreting"
    case deciding = "deciding"
    case narrating = "narrating"
    case speaking = "speaking"

    public var iconSource: WOMIconSource {
        switch self {
        case .idle, .listening: .system(.voiceAdvice)
        case .interpreting: .status(.active)
        case .deciding: .status(.cooldown)
        case .narrating: .asset(.codex)
        case .speaking: .system(.audioReplay)
        }
    }

    public var promptText: String {
        switch self {
        case .idle: return "世界正在聆听"
        case .listening: return "正在倾听 Advice..."
        case .interpreting: return "正在感知非凡因果..."
        case .deciding: return "人物正在权衡动机..."
        case .narrating: return "叙事展开中..."
        case .speaking: return "克莱恩正在回应..."
        }
    }
}

/// 全局常驻声纹交互环（双同心圆金属光圈）
public struct ListeningRingView: View {
    public let state: ListeningRingState
    public let audioLevel: Double
    public var onRingTapped: (@MainActor () -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @FocusState private var isRingFocused: Bool
    @State private var isBreathing: Bool = false
    @State private var rotationAngle: Double = 0
    @State private var rippleScale: CGFloat = 1.0

    public init(
        state: ListeningRingState = .idle,
        audioLevel: Double = 0.0,
        onRingTapped: (@MainActor () -> Void)? = nil
    ) {
        self.state = state
        self.audioLevel = min(max(audioLevel, 0.0), 1.0)
        self.onRingTapped = onRingTapped
    }

    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            interactiveRing

            Text(state.promptText)
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .animation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring, value: state)
                .accessibilityHidden(onRingTapped != nil)
        }
        .onAppear {
            startAnimations()
            handleStateChange(state)
        }
        .onChange(of: state) { _, newState in
            handleStateChange(newState)
        }
        .onChange(of: reduceMotion) { _, newValue in
            if newValue {
                resetMotionState()
            } else {
                startAnimations()
                handleStateChange(state)
            }
        }
    }

    @ViewBuilder
    private var interactiveRing: some View {
        if let onRingTapped {
            Button(action: onRingTapped) {
                ringVisual
            }
            .buttonStyle(MysticPressableButtonStyle())
            .focused($isRingFocused)
            .accessibilityLabel(state.promptText)
            .accessibilityHint("激活以切换语音 Advice 交互状态")
        } else {
            ringVisual
                .accessibilityHidden(true)
        }
    }

    private var ringVisual: some View {
        ZStack {
            Circle()
                .stroke(
                    state == .listening ? Color.Mystic.spiritualGlow : Color.Mystic.brassGoldGlow,
                    lineWidth: DesignTokens.Borders.heavy
                )
                .frame(
                    width: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault,
                    height: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault
                )
                .scaleEffect(resolvedRingScale)
                .opacity(
                    reduceMotion
                        ? DesignTokens.ComponentMetrics.ListeningRing.reducedMotionOpacity
                        : (
                            isBreathing
                                ? DesignTokens.ComponentMetrics.ListeningRing.breathingOpacityMax
                                : DesignTokens.ComponentMetrics.ListeningRing.breathingOpacityMin
                        )
                )

            Circle()
                .stroke(
                    Color.Mystic.brassGoldBorder,
                    lineWidth: DesignTokens.Borders.standard
                )
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
                .overlay(
                    Circle()
                        .stroke(Color.Mystic.brassGoldPrimary, lineWidth: DesignTokens.Borders.chamfer)
                )
                .shadow(
                    color: Color.Mystic.brassGoldPrimary.opacity(reduceMotion ? 0.2 : 0.35),
                    radius: reduceMotion
                        ? DesignTokens.ComponentMetrics.ListeningRing.reducedMotionShadowRadius
                        : (
                            state == .idle
                                ? DesignTokens.ComponentMetrics.ListeningRing.idleShadowRadius
                                : DesignTokens.ComponentMetrics.ListeningRing.activeShadowRadius
                        )
                )

            WOMIcon(source: state.iconSource, size: .compact)
                .foregroundStyle(iconColor)
                .rotationEffect(.degrees(reduceMotion ? 0 : (state == .deciding ? rotationAngle : 0)))

            Circle()
                .stroke(
                    Color.Mystic.textGoldAccent,
                    lineWidth: DesignTokens.Accessibility.focusRingWidth
                )
                .frame(
                    width: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault
                        + DesignTokens.Accessibility.focusRingOffset * 2,
                    height: DesignTokens.ComponentMetrics.ListeningRing.diameterDefault
                        + DesignTokens.Accessibility.focusRingOffset * 2
                )
                .opacity(isRingFocused ? 1 : 0)
        }
        .contentShape(Circle())
    }

    private var resolvedRingScale: CGFloat {
        if reduceMotion { return 1 }
        if (state == .listening || state == .speaking) && audioLevel > 0 {
            return 1.0 + CGFloat(audioLevel) * DesignTokens.ComponentMetrics.ListeningRing.audioScaleGain
        }
        return state == .listening
            ? rippleScale
            : (
                isBreathing
                    ? DesignTokens.ComponentMetrics.ListeningRing.breathingScaleMax
                    : DesignTokens.ComponentMetrics.ListeningRing.breathingScaleMin
            )
    }

    private var iconColor: Color {
        switch state {
        case .idle:
            return Color.Mystic.brassGoldPrimary
        case .listening, .interpreting:
            return Color.Mystic.spiritualBlue
        case .deciding:
            return Color.Mystic.brassGoldHover
        case .narrating, .speaking:
            return Color.Mystic.textGoldAccent
        }
    }

    private func startAnimations() {
        guard !reduceMotion else {
            resetMotionState()
            return
        }
        withAnimation(DesignTokens.Motion.listeningBreathing) {
            isBreathing = true
        }
    }

    private func handleStateChange(_ newState: ListeningRingState) {
        guard !reduceMotion else {
            resetMotionState()
            return
        }

        if newState == .listening {
            withAnimation(
                .easeInOut(duration: DesignTokens.Motion.listeningRippleDuration)
                    .repeatForever(autoreverses: true)
            ) {
                rippleScale = DesignTokens.ComponentMetrics.ListeningRing.pulseScaleMax
            }
        } else if newState == .deciding {
            withAnimation(
                .linear(duration: DesignTokens.Motion.listeningDecisionRotationDuration)
                    .repeatForever(autoreverses: false)
            ) {
                rotationAngle = DesignTokens.ComponentMetrics.ListeningRing.fullRotationDegrees
            }
        } else {
            rippleScale = 1.0
            rotationAngle = 0
        }
    }

    private func resetMotionState() {
        isBreathing = false
        rippleScale = 1.0
        rotationAngle = 0
    }
}

#Preview("Listening Ring States") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        HStack(spacing: DesignTokens.Spacing.xl) {
            ListeningRingView(state: .idle)
            ListeningRingView(state: .listening)
            ListeningRingView(state: .interpreting)
            ListeningRingView(state: .deciding)
            ListeningRingView(state: .speaking)
        }
    }
    .frame(width: 600, height: 160)
}
