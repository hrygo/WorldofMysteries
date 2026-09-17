import SwiftUI

struct PrimitivesGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "10 · 通用原语组装 (Primitives Assembly)") {
            VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                toneBadges
                metricsAndStatus
                metadataAndActions
                emptyState
            }
        }
    }

    private var toneBadges: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("语义色调徽章 (MysticTone × MysticBadge)：")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)

            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingSm) {
                ForEach(MysticTone.allCases, id: \.rawValue) { tone in
                    MysticBadge(tone.semanticLabel, tone: tone, systemIcon: "circle.fill")
                }
            }

            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingSm) {
                MysticBadge("正典锁定", tone: .gold, variant: .panel, systemIcon: "lock.shield")
                MysticBadge(
                    "幂等可重建", tone: .teal, variant: .panel, systemIcon: "arrow.triangle.2.circlepath"
                )
                MysticBadge(
                    "受阻：灵界干扰", tone: .amber, variant: .panel, systemIcon: "exclamationmark.triangle"
                )
            }
        }
    }

    private var metricsAndStatus: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("计量条与临界阈值 (MysticMetricBar)：")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                MysticMetricBar(value: 0.88, tone: .azure)
                MysticMetricBar(value: 0.52, tone: .gold)
                MysticMetricBar(value: 0.18, tone: .teal, criticalThreshold: 0.25)
            }
            .frame(width: 220)

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("呼吸状态点 (MysticStatusDot)：")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                MysticStatusDot(tone: .teal, label: "引擎在线")
                MysticStatusDot(tone: .amber, isPulsing: true, label: "推演进行中")
                MysticStatusDot(tone: .crimson, label: "通路中断")
                MysticStatusDot(tone: .neutral, diameter: 6, label: "未激活")
            }
        }
    }

    private var metadataAndActions: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                MysticKeyValueRow(
                    key: "引擎", value: "AgentScope 2.0.8", isMonospaced: true, systemIcon: "cpu")
                MysticKeyValueRow(
                    key: "运行时", value: "Python 3.14.7", isMonospaced: true, systemIcon: "terminal")
                MysticKeyValueRow(
                    key: "当前分支", value: "main", tone: .teal, systemIcon: "arrow.triangle.branch")
            }
            .frame(width: 300)

            HStack(spacing: DesignTokens.Spacing.sm) {
                MysticIconButton(
                    systemIcon: "arrow.triangle.2.circlepath", title: "重建投影", tone: .teal,
                    helpText: "retrieval.db 100% 幂等重建"
                ) {}
                MysticIconButton(systemIcon: "speaker.wave.2.fill", title: "原声回放") {}
                MysticIconButton(
                    systemIcon: "square.and.arrow.up", tone: .neutral, helpText: "导出本章证据"
                ) {}
            }
        }
    }

    private var emptyState: some View {
        MysticEmptyState(
            systemIcon: "text.book.closed",
            title: "尚无已提交章回",
            message: "章回只在 COMMIT 之后进入故事书；表达层重试不会回写已提交事实。",
            tone: .gold,
            actionTitle: "查看世界脉动",
            onAction: {}
        )
    }
}
