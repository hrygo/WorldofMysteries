import SwiftUI

public enum DatabaseRole: String, Sendable, CaseIterable, Identifiable {
    case canon = "canon.db"
    case world = "world.db"
    case retrieval = "retrieval.db"
    case runtime = "runtime.db"

    public var id: String { rawValue }
    
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

/// 四库探针状态。
///
/// 界面不允许在没有任何探针数据时显示「健康 + 体积」——那会让用户以为系统已经接入了数据内核。
/// 未接入时一律表达为 `notProbed`，并显式说明原因。
public enum DatabaseProbeStatus: Sendable, Equatable {
    case notProbed
    case measured(sizeText: String, isHealthy: Bool)

    public var isProbed: Bool {
        if case .measured = self { return true }
        return false
    }
}

/// 四库物理隔离健康状态卡片
public struct DatabaseStatusHUDCard: View {
    public let role: DatabaseRole
    public let status: DatabaseProbeStatus
    public var onRebuildTapped: (@MainActor () -> Void)?
    
    public init(
        role: DatabaseRole,
        status: DatabaseProbeStatus = .notProbed,
        onRebuildTapped: (@MainActor () -> Void)? = nil
    ) {
        self.role = role
        self.status = status
        self.onRebuildTapped = onRebuildTapped
    }

    private var isHealthy: Bool {
        if case .measured(_, let isHealthy) = status { return isHealthy }
        return false
    }

    private var statusTone: MysticTone {
        switch status {
        case .notProbed: .neutral
        case .measured(_, let isHealthy): isHealthy ? .teal : .crimson
        }
    }

    private var sizeText: String {
        if case .measured(let sizeText, _) = status { return sizeText }
        return "—"
    }
    
    public var body: some View {
        VictorianCard(style: .obsidianGlass, cornerRadius: DesignTokens.Radii.md) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                HStack {
                    MysticStatusDot(tone: statusTone, isPulsing: status.isProbed && !isHealthy)
                    
                    Text(role.rawValue)
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.textGoldAccent)
                    
                    Spacer(minLength: DesignTokens.Spacing.sm)

                    if role.isRebuildable, status.isProbed, let onRebuildTapped {
                        MysticIconButton(
                            systemIcon: .refresh,
                            tone: .teal,
                            helpText: "retrieval.db 为异步投影，删除后可 100% 幂等重建",
                            action: onRebuildTapped
                        )
                    }
                    
                    Text(sizeText)
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.textTertiary)
                }
                
                Text(role.roleDescription)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                if !status.isProbed {
                    Text("尚未接入 Local Engine 探针，容量与健康度暂不可知。")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textTertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

#Preview("Database HUD Cards") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        VStack(spacing: DesignTokens.Spacing.md) {
            DatabaseStatusHUDCard(role: .canon)
            DatabaseStatusHUDCard(role: .world)
            DatabaseStatusHUDCard(role: .retrieval)
            DatabaseStatusHUDCard(role: .runtime)
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 360)
    }
}
