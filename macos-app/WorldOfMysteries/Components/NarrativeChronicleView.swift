import SwiftUI

public enum NarrativeSpeakerRole: Sendable {
    case narrator
    case character(String)
    case playerAdvice

    public var displayName: String {
        switch self {
        case .narrator: "旁白 (Narrator)"
        case .character(let name): name
        case .playerAdvice: "你的 Advice"
        }
    }

    public var badgeColor: Color { tone.accent }

    /// 统一语义色调（与 `MysticTone` 单一事实源对齐）。
    public var tone: MysticTone {
        switch self {
        case .narrator: .neutral
        case .character: .gold
        case .playerAdvice: .azure
        }
    }

    public var iconSource: WOMIconSource {
        switch self {
        case .narrator: .asset(.codex)
        case .character: .navigation(.character)
        case .playerAdvice: .system(.voiceAdvice)
        }
    }
}

/// 沉浸式剧情字幕与历史编年史条目组件（对应原型 04 故事沉浸与 07 故事书）。
public struct NarrativeChronicleView: View {
    public let role: NarrativeSpeakerRole
    public let content: String
    public let timestamp: String
    public let isAudioPlaying: Bool
    public var onReplayAudio: (@MainActor () -> Void)?

    public init(
        role: NarrativeSpeakerRole,
        content: String,
        timestamp: String = "1349-06-28",
        isAudioPlaying: Bool = false,
        onReplayAudio: (@MainActor () -> Void)? = nil
    ) {
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.isAudioPlaying = isAudioPlaying
        self.onReplayAudio = onReplayAudio
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            header

            if content.isEmpty {
                MysticEmptyState(
                    systemIcon: "text.alignleft",
                    title: "本章回尚无已提交叙事",
                    message: "叙事只在 COMMIT 之后落库；条目为空即表示尚未产生已提交章回。",
                    tone: .neutral
                )
            } else {
                Text(content)
                    .mysticNarrativeStyle()
            }
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .womCardChrome(
            tone: .card,
            texture: .sacredSlate,
            cornerRadius: DesignTokens.Radii.md
        )
    }

    private var header: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            WOMIcon(source: role.iconSource, size: .compact)
                .foregroundStyle(role.badgeColor)

            MysticBadge(role.displayName, tone: role.tone, variant: .panel, isEmphasized: true)

            Spacer()

            Text(timestamp)
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textTertiary)

            if onReplayAudio != nil {
                Button {
                    onReplayAudio?()
                } label: {
                    HStack(spacing: DesignTokens.Spacing.xxs) {
                        WOMIcon(system: .audioReplay, size: .compact)
                        Text(isAudioPlaying ? "播放中" : "原声")
                            .font(Font.Mystic.caption)
                    }
                }
                .buttonStyle(WOMToolbarButtonStyle(.tertiary))
                .accessibilityLabel(isAudioPlaying ? "原声播放中" : "播放原声")
            }
        }
    }
}

#Preview("Narrative Chronicle") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        VStack(spacing: DesignTokens.Spacing.md) {
            NarrativeChronicleView(
                role: .narrator,
                content: "浓郁的煤气路灯光晕被浓雾撕扯得支离破碎。克莱恩从桌面上抬起头，手指下触碰到了冰凉的转轮手枪机头。"
            )
            NarrativeChronicleView(
                role: .character("克莱恩·莫雷蒂"),
                content: "“这不是梦境...那颗子弹确实穿过了我的太阳穴，为什么我还活着？”",
                isAudioPlaying: true,
                onReplayAudio: {}
            )
            NarrativeChronicleView(
                role: .playerAdvice,
                content: "“检查书桌左侧第三个抽屉，不要惊动窗外的马车。”"
            )
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 580)
    }
}
