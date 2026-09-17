import SwiftUI

/// 灵摆占卜推演状态。
public enum ScryingResult: String, Sendable, CaseIterable {
    case inquiring = "静候灵启"
    case affirmative = "启示：肯定 (Yes)"
    case negative = "启示：否定 (No)"
    case disturbed = "受阻：灵界干扰"

    public var accentColor: Color { tone.accent }

    /// 统一语义色调映射（与 `MysticTone` 单一事实源对齐）。
    public var tone: MysticTone {
        switch self {
        case .inquiring: .gold
        case .affirmative: .teal
        case .negative: .crimson
        case .disturbed: .amber
        }
    }

    public var guidanceText: String {
        switch self {
        case .inquiring: "手肘抵桌，持链悬垂，闭目默念七遍语句……"
        case .affirmative: "灵摆呈顺时针规律旋转 · 灵界回馈为真"
        case .negative: "灵摆呈逆时针剧烈旋转 · 灵界回馈为假"
        case .disturbed: "灵摆杂乱无章震颤 · 涉及高位存在，无法直视"
        }
    }
}

/// 黄水晶吊坠 · 灵摆占卜仪轨卡片。
///
/// 本卡片为表达层原型：推演结论仅用于界面演示，绝不写入领域事实（不变量 5、9）。
public struct CitrinePendulumScryingCard: View {
    public let defaultStatement: String
    public var onScryingTriggered: (@MainActor (String) -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var statement: String
    @State private var state: ScryingResult = .inquiring
    @State private var swingAngle: Double = 0
    @State private var isScrying = false

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
                    WOMDividerOrnament(opacity: 0.5)
                    ritualProtocol
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .background(
            WOMPanelBackground(
                tone: .ritual,
                cornerRadius: DesignTokens.Radii.lg,
                texture: .foolVeil,
                textureOpacity: 0.045
            )
        )
        .onChange(of: reduceMotion) { _, newValue in
            if newValue {
                swingAngle = 0
            }
        }
    }

    // MARK: - 标题行

    private var header: some View {
        HStack(alignment: .center, spacing: DesignTokens.Spacing.sm) {
            WOMIcon(.divination, size: .standard)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)

            Text("黄水晶吊坠 · 灵摆占卜法")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)

            Spacer(minLength: DesignTokens.Spacing.sm)

            HStack(spacing: DesignTokens.Spacing.xs) {
                WOMIcon(.spirituality, size: .compact)
                Text("灵性消耗 -5%")
            }
            .font(Font.Mystic.monoBadge)
            .foregroundStyle(Color.Mystic.spiritualBlue)
            .accessibilityElement(children: .combine)
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
        .shadow(
            color: Color.Mystic.brassGoldPrimary.opacity(isScrying ? 0.25 : 0.12),
            radius: 10
        )
    }

    // MARK: - 状态判读

    private var statePanel: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                MysticStatusDot(tone: state.tone, isPulsing: isScrying && !reduceMotion, label: state.rawValue)

                Spacer(minLength: DesignTokens.Spacing.sm)

                HStack(spacing: DesignTokens.Spacing.xs) {
                    WOMIcon(
                        status: isScrying ? .active : .success,
                        size: .compact
                    )
                    Text(isScrying ? "推演中" : "已定格")
                }
                .font(Font.Mystic.caption)
                .foregroundStyle(isScrying ? Color.Mystic.brassGoldPrimary : Color.Mystic.textSecondary)
            }

            Text(state.guidanceText)
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
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
                        WOMPanelBackground(
                            tone: .card,
                            cornerRadius: DesignTokens.Radii.sm,
                            texture: .sacredSlate,
                            textureOpacity: 0.02
                        )
                    )
                    .onSubmit { triggerScrying() }

                Button {
                    triggerScrying()
                } label: {
                    HStack(spacing: DesignTokens.Spacing.xs) {
                        if isScrying {
                            WOMIcon(status: .active, size: .standard)
                        } else {
                            WOMIcon(.divination, size: .standard)
                        }
                        Text(isScrying ? "推演中" : "执链占卜")
                            .font(Font.Mystic.bodyMedium)
                            .fontWeight(.semibold)
                    }
                }
                .buttonStyle(WOMButtonStyle(.ritual))
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

        if reduceMotion {
            swingAngle = 0
        } else {
            withAnimation(
                .easeInOut(duration: DesignTokens.Motion.pendulumSwingInterval)
                    .repeatForever(autoreverses: true)
            ) {
                swingAngle = DesignTokens.Motion.pendulumSwingMaxDegrees
            }
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
            let outcome = Self.resolveOutcome(for: statement)
            withAnimation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring) {
                state = outcome
                swingAngle = reduceMotion ? 0 : Self.settledSwingAngle(for: outcome)
            }
            isScrying = false
            onScryingTriggered?(statement)
        }
    }

    /// 结论定格后的停摆偏向（顺时针为真 / 逆时针为假 / 干扰归中）。
    nonisolated static func settledSwingAngle(for outcome: ScryingResult) -> Double {
        switch outcome {
        case .affirmative: DesignTokens.Motion.pendulumSwingMaxDegrees
        case .negative: -DesignTokens.Motion.pendulumSwingMaxDegrees
        case .inquiring, .disturbed: 0
        }
    }

    /// 原型推演规则（纯函数，便于单测）。
    nonisolated public static func resolveOutcome(for statement: String) -> ScryingResult {
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
