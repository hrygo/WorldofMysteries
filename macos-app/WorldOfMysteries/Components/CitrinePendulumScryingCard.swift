import SwiftUI

/// 灵摆占卜推演状态
public enum ScryingResult: String, Sendable, CaseIterable {
    case inquiring = "静候灵启"
    case affirmative = "启示：肯定 (Yes)"
    case negative = "启示：否定 (No)"
    case disturbed = "受阻：灵界干扰"
    
    public var accentColor: Color {
        tone.accent
    }
    
    /// 统一语义色调映射（与 `MysticTone` 单一事实源对齐）
    public var tone: MysticTone {
        switch self {
        case .inquiring: return .gold
        case .affirmative: return .teal
        case .negative: return .crimson
        case .disturbed: return .amber
        }
    }
    
    public var guidanceText: String {
        switch self {
        case .inquiring:
            return "手肘抵桌，持链悬垂，闭目默念七遍语句……"
        case .affirmative:
            return "灵摆呈顺时针规律旋转 · 灵界回馈为真"
        case .negative:
            return "灵摆呈逆时针剧烈旋转 · 灵界回馈为假"
        case .disturbed:
            return "灵摆杂乱无章震颤 · 涉及高位存在，无法直视"
        }
    }
}

/// 黄水晶吊坠 · 灵摆占卜仪轨卡片
///
/// 以正典「克莱恩执链占卜」原画构成竖向占卜视窗（黄水晶锚定视窗正中、摆动枢轴为手指捏链点），
/// 右侧为状态判读、占卜语句输入与仪轨说明。
///
/// - 本卡片为表达层原型：推演结论仅用于界面演示，绝不写入领域事实（不变量 5、9）。
public struct CitrinePendulumScryingCard: View {
    public let defaultStatement: String
    public var onScryingTriggered: (@MainActor (String) -> Void)?
    
    @State private var statement: String
    @State private var state: ScryingResult = .inquiring
    @State private var swingAngle: Double = 0
    @State private var isScrying: Bool = false
    
    public init(
        defaultStatement: String = "《安提哥努斯家族笔记》仍遗留在廷根市内。",
        onScryingTriggered: (@MainActor (String) -> Void)? = nil
    ) {
        self.defaultStatement = defaultStatement
        self._statement = State(initialValue: defaultStatement)
        self.onScryingTriggered = onScryingTriggered
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
            header
            
            HStack(alignment: .top, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                artworkPanel
                
                VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
                    statePanel
                    statementPanel
                    MysticDivider(tone: .gold)
                    ritualProtocol
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .background(
            Color.Mystic.obsidianElevated
                .overlay(
                    LinearGradient(
                        colors: [Color.Mystic.brassGoldMuted.opacity(0.05), Color.clear],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
        )
    }
    
    // MARK: - 标题行
    
    private var header: some View {
        HStack(alignment: .center, spacing: DesignTokens.Spacing.sm) {
            Image(systemName: "sparkles")
                .font(.system(size: 14))
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            
            Text("黄水晶吊坠 · 灵摆占卜法")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
            
            Spacer(minLength: DesignTokens.Spacing.sm)
            
            MysticBadge("灵性消耗 -5%", tone: .azure, systemIcon: "bolt.fill")
        }
    }
    
    // MARK: - 原画视窗
    
    private var artworkPanel: some View {
        let artwork = CitrineArtworkGeometry.canonical
        let width = DesignTokens.ComponentMetrics.CitrineArtwork.panelWidth
        
        return CitrinePendulumArtwork(
            swingAngle: swingAngle,
            glowIntensity: isScrying ? 0.22 : 0.38
        )
        .frame(width: width, height: artwork.panelHeight(forWidth: width))
        .shadow(color: Color.Mystic.brassGoldPrimary.opacity(isScrying ? 0.25 : 0.12), radius: 10)
    }
    
    // MARK: - 状态判读
    
    private var statePanel: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                MysticStatusDot(tone: state.tone, isPulsing: isScrying, label: state.rawValue)
                
                Spacer(minLength: DesignTokens.Spacing.sm)
                
                MysticBadge(
                    isScrying ? "推演中" : "已定格",
                    tone: isScrying ? .amber : .neutral,
                    systemIcon: isScrying ? "hourglass" : "seal"
                )
            }
            
            Text(state.guidanceText)
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
    
    // MARK: - 占卜语句与执链按钮
    
    private var statementPanel: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text("默念占卜语句（七遍）：")
                .mysticCaptionStyle(color: Color.Mystic.brassGoldMuted)
            
            HStack(spacing: DesignTokens.Spacing.sm) {
                TextField("输入占卜语句…", text: $statement)
                    .textFieldStyle(.plain)
                    .font(Font.Mystic.parchmentCursive)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .padding(.horizontal, DesignTokens.Spacing.md)
                    .padding(.vertical, DesignTokens.Spacing.sm)
                    .background(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                            .fill(Color.Mystic.obsidianCard)
                            .overlay(
                                RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                                    .stroke(Color.Mystic.brassGoldBorder.opacity(0.5), lineWidth: DesignTokens.Borders.standard)
                            )
                    )
                    .onSubmit { triggerScrying() }
                
                Button {
                    triggerScrying()
                } label: {
                    HStack(spacing: DesignTokens.Spacing.xs) {
                        Image(systemName: isScrying ? "waveform.path.ecg" : "waveform.path")
                        Text(isScrying ? "推演中" : "执链占卜")
                    }
                    .font(Font.Mystic.bodyMedium)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.Mystic.obsidianBase)
                    .padding(.horizontal, DesignTokens.Spacing.md)
                    .padding(.vertical, DesignTokens.Spacing.sm)
                    .background(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                            .fill(isScrying ? Color.Mystic.brassGoldMuted : Color.Mystic.brassGoldPrimary)
                    )
                    .shadow(color: Color.Mystic.brassGoldPrimary.opacity(0.4), radius: 6)
                }
                .mysticPressable()
                .disabled(isScrying)
                .help("手肘抵桌，持链悬垂，默念语句七遍后执链占卜")
            }
        }
    }
    
    // MARK: - 仪轨说明
    
    private var ritualProtocol: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            MysticKeyValueRow(
                key: "仪轨",
                value: "持链悬垂 · 默念七遍",
                systemIcon: "hand.raised"
            )
            MysticKeyValueRow(
                key: "判读",
                value: "顺时针为真 · 逆时针为假",
                systemIcon: "arrow.trianglehead.clockwise"
            )
            MysticKeyValueRow(
                key: "记录",
                value: "仅呈现启示 · 事实由引擎提交",
                tone: .gold,
                systemIcon: "checkmark.seal"
            )
        }
    }
    
    // MARK: - 原型推演
    
    private func triggerScrying() {
        guard !isScrying else { return }
        isScrying = true
        state = .inquiring
        
        // 悬垂灵摆自捏链点往返摇晃
        withAnimation(
            .easeInOut(duration: DesignTokens.Motion.pendulumSwingInterval)
                .repeatForever(autoreverses: true)
        ) {
            swingAngle = DesignTokens.Motion.pendulumSwingMaxDegrees
        }
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
            let outcome = Self.resolveOutcome(for: statement)
            withAnimation(DesignTokens.Motion.smoothSpring) {
                state = outcome
                swingAngle = Self.settledSwingAngle(for: outcome)
            }
            isScrying = false
            onScryingTriggered?(statement)
        }
    }
    
    /// 结论定格后的停摆偏向（顺时针为真 / 逆时针为假 / 干扰归中）
    static func settledSwingAngle(for outcome: ScryingResult) -> Double {
        switch outcome {
        case .affirmative: return DesignTokens.Motion.pendulumSwingMaxDegrees
        case .negative: return -DesignTokens.Motion.pendulumSwingMaxDegrees
        case .inquiring, .disturbed: return 0
        }
    }
    
    /// 原型推演规则（纯函数，便于单测）：
    /// 涉及高位存在的语句无法直视 → 受阻；其余按语句字数奇偶给出肯定/否定。
    /// 真实占卜结论由引擎 Outcome Resolver 在 COMMIT 边界裁定，本函数不产生任何领域事实。
    public static func resolveOutcome(for statement: String) -> ScryingResult {
        let trimmed = statement.trimmingCharacters(in: .whitespacesAndNewlines)
        let unreachableKeywords = ["愚者", "灰雾", "造物主", "隐匿贤者", "永暗之河", "真神"]
        if unreachableKeywords.contains(where: { trimmed.contains($0) }) {
            return .disturbed
        }
        if trimmed.isEmpty {
            return .negative
        }
        return trimmed.count % 2 == 0 ? .affirmative : .negative
    }
}

#Preview("Citrine Pendulum Scrying Card") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        CitrinePendulumScryingCard()
            .frame(width: 580)
            .padding()
    }
}
