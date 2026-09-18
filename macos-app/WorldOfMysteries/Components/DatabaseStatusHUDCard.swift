import SwiftUI

public enum DatabaseRole: String, Sendable {
    case canon = "canon.db"
    case world = "world.db"
    case retrieval = "retrieval.db"
    case runtime = "runtime.db"
    
    public var roleDescription: String {
        switch self {
        case .canon: return "正典历史底座 · 只读锁死"
        case .world: return "用户现实世界 · WAL 强事务"
        case .retrieval: return "异步知识投影 · 可幂等重建"
        case .runtime: return "易失会话与记忆 · 临时隔离"
        }
    }
    
    public var isRebuildable: Bool {
        self == .retrieval
    }
}

/// 四库物理隔离健康状态卡片
public struct DatabaseStatusHUDCard: View {
    public let role: DatabaseRole
    public let isHealthy: Bool
    public let sizeText: String
    public var onRebuildTapped: (@MainActor () -> Void)?
    
    public init(
        role: DatabaseRole,
        isHealthy: Bool = true,
        sizeText: String = "24.5 MB",
        onRebuildTapped: (@MainActor () -> Void)? = nil
    ) {
        self.role = role
        self.isHealthy = isHealthy
        self.sizeText = sizeText
        self.onRebuildTapped = onRebuildTapped
    }
    
    public var body: some View {
        VictorianCard(style: .obsidianGlass, cornerRadius: DesignTokens.Radii.md) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                HStack {
                    MysticStatusDot(tone: isHealthy ? .teal : .crimson, isPulsing: !isHealthy)
                    
                    Text(role.rawValue)
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.textGoldAccent)
                    
                    Spacer()
                    
                    Text(sizeText)
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.textTertiary)
                }
                
                Text(role.roleDescription)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                
                if role.isRebuildable {
                    MysticIconButton(
                        systemIcon: .refresh,
                        title: "100% 幂等重建索引",
                        tone: .teal,
                        helpText: "retrieval.db 为异步投影，删除后可 100% 幂等重建",
                        action: { onRebuildTapped?() }
                    )
                    .disabled(onRebuildTapped == nil)
                    .padding(.top, DesignTokens.Spacing.xxs)
                }
            }
        }
    }
}

#Preview("Database HUD Cards") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        VStack(spacing: DesignTokens.Spacing.md) {
            DatabaseStatusHUDCard(role: .canon, isHealthy: true, sizeText: "38.2 MB")
            DatabaseStatusHUDCard(role: .world, isHealthy: true, sizeText: "14.6 MB")
            DatabaseStatusHUDCard(role: .retrieval, isHealthy: true, sizeText: "52.1 MB")
            DatabaseStatusHUDCard(role: .runtime, isHealthy: true, sizeText: "4.8 MB")
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 360)
    }
}
