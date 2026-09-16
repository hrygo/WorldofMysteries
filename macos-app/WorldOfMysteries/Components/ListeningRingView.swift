import SwiftUI

/// 交互状态对齐 `docs/05_UI/Interaction_Runtime_State_v1.0.md`
public enum ListeningRingState: String, Sendable, CaseIterable {
    case idle = "idle"
    case listening = "listening"
    case interpreting = "interpreting"
    case deciding = "deciding"
    case narrating = "narrating"
    case speaking = "speaking"
    
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
    public var onRingTapped: (@MainActor () -> Void)?
    
    @State private var isBreathing: Bool = false
    @State private var rotationAngle: Double = 0
    @State private var rippleScale: CGFloat = 1.0
    
    public init(
        state: ListeningRingState = .idle,
        onRingTapped: (@MainActor () -> Void)? = nil
    ) {
        self.state = state
        self.onRingTapped = onRingTapped
    }
    
    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            ZStack {
                // 外层发光与涟漪
                Circle()
                    .stroke(
                        state == .listening ? Color.Mystic.spiritualGlow : Color.Mystic.brassGoldGlow,
                        lineWidth: DesignTokens.Borders.heavy
                    )
                    .frame(width: 58, height: 58)
                    .scaleEffect(state == .listening ? rippleScale : (isBreathing ? 1.08 : 0.96))
                    .opacity(isBreathing ? 0.9 : 0.4)
                
                // 次级同心金属环
                Circle()
                    .stroke(
                        Color.Mystic.brassGoldBorder,
                        lineWidth: DesignTokens.Borders.standard
                    )
                    .frame(width: 46, height: 46)
                
                // 核心金属光圈与图标
                Circle()
                    .fill(Color.Mystic.obsidianCard)
                    .frame(width: 38, height: 38)
                    .overlay(
                        Circle()
                            .stroke(Color.Mystic.brassGoldPrimary, lineWidth: DesignTokens.Borders.chamfer)
                    )
                    .shadow(
                        color: Color.Mystic.brassGoldPrimary.opacity(0.35),
                        radius: state == .idle ? 4 : 8
                    )
                
                // 中心麦克风 / 状态图标
                Image(systemName: iconName)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(iconColor)
                    .rotationEffect(.degrees(state == .deciding ? rotationAngle : 0))
            }
            .contentShape(Circle())
            .onTapGesture {
                onRingTapped?()
            }
            
            // 语义提示文字（世界语义，不显示技术术语）
            Text(state.promptText)
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .animation(DesignTokens.Motion.smoothSpring, value: state)
        }
        .onAppear {
            startAnimations()
        }
        .onChange(of: state) { _, newState in
            handleStateChange(newState)
        }
    }
    
    private var iconName: String {
        switch state {
        case .idle, .listening:
            return "mic.fill"
        case .interpreting:
            return "sparkles"
        case .deciding:
            return "hourglass"
        case .narrating:
            return "book.closed.fill"
        case .speaking:
            return "waveform"
        }
    }
    
    private var iconColor: Color {
        switch state {
        case .idle:
            return Color.Mystic.brassGoldPrimary
        case .listening:
            return Color.Mystic.spiritualBlue
        case .interpreting:
            return Color.Mystic.spiritualGlow
        case .deciding:
            return Color.Mystic.brassGoldHover
        case .narrating, .speaking:
            return Color.Mystic.textGoldAccent
        }
    }
    
    private func startAnimations() {
        withAnimation(DesignTokens.Motion.listeningBreathing) {
            isBreathing = true
        }
    }
    
    private func handleStateChange(_ newState: ListeningRingState) {
        if newState == .listening {
            withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                rippleScale = 1.25
            }
        } else if newState == .deciding {
            withAnimation(.linear(duration: 3.0).repeatForever(autoreverses: false)) {
                rotationAngle = 360
            }
        } else {
            rippleScale = 1.0
            rotationAngle = 0
        }
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
