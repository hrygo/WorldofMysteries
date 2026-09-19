import SwiftUI

struct PrimitivesGallerySection: View {
    @State private var lastAction = "尚未触发"
    @State private var actionCount = 0

    var body: some View {
        ComponentGallerySection(title: "10 · 通用原语组装 (Primitives Assembly)") {
            VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                HStack {
                    Text("原语行为反馈只记录在画廊本地，可随时恢复初始回执。")
                        .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                    Spacer(minLength: DesignTokens.Spacing.sm)
                    Button("重置原语回执") {
                        lastAction = "尚未触发"
                        actionCount = 0
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }

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

            LazyVGrid(
                columns: [
                    GridItem(
                        .adaptive(minimum: 96, maximum: 150),
                        spacing: DesignTokens.Spacing.sm
                    )
                ],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                ForEach(MysticTone.allCases, id: \.rawValue) { tone in
                    MysticBadge(tone.semanticLabel, tone: tone, systemIcon: "circle.fill")
                }

                MysticBadge("正典锁定", tone: .gold, variant: .panel, systemIcon: "lock.shield")
                MysticBadge(
                    "幂等可重建", tone: .teal, variant: .panel,
                    systemIcon: "arrow.triangle.2.circlepath"
                )
                MysticBadge(
                    "受阻：灵界干扰", tone: .amber, variant: .panel,
                    systemIcon: "exclamationmark.triangle"
                )
            }
        }
    }

    private var metricsAndStatus: some View {
        WOMAdaptivePair(
            trailingIdealWidth: 220,
            primaryIdealWidth: 260,
            spacing: DesignTokens.Spacing.xl
        ) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("计量条与临界阈值 (MysticMetricBar)：")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                MysticMetricBar(value: 0.88, tone: .azure)
                MysticMetricBar(value: 0.52, tone: .gold)
                MysticMetricBar(value: 0.18, tone: .teal, criticalThreshold: 0.25)
            }
        } secondary: {
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
        WOMAdaptivePair(
            trailingIdealWidth: 280,
            primaryIdealWidth: 320,
            spacing: DesignTokens.Spacing.xl
        ) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                MysticKeyValueRow(
                    key: "引擎", value: "AgentScope 2.0.8", isMonospaced: true, systemIcon: "cpu")
                MysticKeyValueRow(
                    key: "运行时", value: "Python 3.14.7", isMonospaced: true, systemIcon: "terminal")
                MysticKeyValueRow(
                    key: "当前分支", value: "main", tone: .teal, systemIcon: "arrow.triangle.branch")
            }
        } secondary: {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("操作原语 · 可触发")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)

                HStack(spacing: DesignTokens.Spacing.sm) {
                    MysticIconButton(
                        systemIcon: "arrow.triangle.2.circlepath",
                        title: "重建投影",
                        tone: .teal,
                        helpText: "画廊仅验证按钮触发反馈，不调用 retrieval.db"
                    ) { recordAction("重建投影") }

                    MysticIconButton(
                        systemIcon: "speaker.wave.2.fill",
                        title: "原声回放",
                        helpText: "画廊仅验证控件交互，不播放生产音频"
                    ) { recordAction("原声回放") }

                    MysticIconButton(
                        systemIcon: "square.and.arrow.up",
                        tone: .neutral,
                        helpText: "画廊仅验证导出按钮反馈，不生成真实证据包"
                    ) { recordAction("导出证据") }
                }

                WOMStatusBanner(
                    tone: actionCount == 0 ? .info : .success,
                    title: actionCount == 0 ? "等待交互" : "控件已响应",
                    message: "\(lastAction) · 共触发 \(actionCount) 次"
                )
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
            onAction: { recordAction("查看世界脉动") }
        )
    }

    private func recordAction(_ name: String) {
        lastAction = "\(name)（画廊本地回执）"
        actionCount += 1
    }
}
