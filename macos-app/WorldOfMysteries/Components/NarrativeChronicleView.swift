import SwiftUI

public enum NarrativeSpeakerRole: Sendable {
    case narrator
    case character(String)
    case playerAdvice
    
    public var displayName: String {
        switch self {
        case .narrator: return "旁白 (Narrator)"
        case .character(let name): return name
        case .playerAdvice: return "你的 Advice"
        }
    }
    
    public var badgeColor: Color {
        switch self {
        case .narrator: return Color.Mystic.textTertiary
        case .character: return Color.Mystic.brassGoldPrimary
        case .playerAdvice: return Color.Mystic.spiritualBlue
        }
    }
}

/// 沉浸式剧情字幕与历史编年史条目组件（对应原型 04 故事沉浸与 07 故事书）
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
        VictorianCard(style: .obsidianGlass, cornerRadius: DesignTokens.Radii.md) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                // 头部说话人标签与时间戳
                HStack(spacing: DesignTokens.Spacing.sm) {
                    Text(role.displayName)
                        .font(Font.Mystic.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(role.badgeColor)
                        .padding(.horizontal, DesignTokens.Spacing.sm)
                        .padding(.vertical, DesignTokens.Spacing.xxs)
                        .background(role.badgeColor.opacity(0.15))
                        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.xs))
                    
                    Spacer()
                    
                    Text(timestamp)
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.textTertiary)
                    
                    if onReplayAudio != nil {
                        Button {
                            onReplayAudio?()
                        } label: {
                            HStack(spacing: DesignTokens.Spacing.xxs) {
                                Image(systemName: isAudioPlaying ? "waveform" : "speaker.wave.2.fill")
                                    .font(.system(size: 11))
                                    .symbolEffect(.variableColor.iterative, isActive: isAudioPlaying)
                                Text(isAudioPlaying ? "播放中" : "原声")
                                    .font(Font.Mystic.caption)
                            }
                            .foregroundStyle(Color.Mystic.brassGoldHover)
                            .padding(.horizontal, DesignTokens.Spacing.xs)
                        }
                        .buttonStyle(.plain)
                    }
                }
                
                // 核心叙事正文
                Text(content)
                    .font(Font.Mystic.narrativeSubtitle)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .lineSpacing(6)
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
