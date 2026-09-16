import Testing
import Foundation
import SwiftUI
@testable import WorldOfMysteriesCore

@Suite("Design System & UI Components Test Suite")
struct DesignSystemTests {
    
    @Test("DesignTokens Spacing grid is monotonic and strictly positive")
    func testSpacingGrid() {
        #expect(DesignTokens.Spacing.xxs == 2)
        #expect(DesignTokens.Spacing.xs == 4)
        #expect(DesignTokens.Spacing.sm == 8)
        #expect(DesignTokens.Spacing.md == 12)
        #expect(DesignTokens.Spacing.lg == 16)
        #expect(DesignTokens.Spacing.xl == 24)
        #expect(DesignTokens.Spacing.xxl == 32)
        #expect(DesignTokens.Spacing.xxxl == 48)
        
        #expect(DesignTokens.Spacing.xxs < DesignTokens.Spacing.xs)
        #expect(DesignTokens.Spacing.xs < DesignTokens.Spacing.sm)
        #expect(DesignTokens.Spacing.sm < DesignTokens.Spacing.md)
        #expect(DesignTokens.Spacing.md < DesignTokens.Spacing.lg)
        #expect(DesignTokens.Spacing.lg < DesignTokens.Spacing.xl)
    }
    
    @Test("Concentric Radii calculation follows geometric subtraction")
    func testConcentricRadii() {
        let parentRadius: CGFloat = 16
        let padding: CGFloat = 8
        let childRadius = DesignTokens.Radii.concentric(parent: parentRadius, padding: padding)
        #expect(childRadius == 8)
        
        // Edge case: padding greater than parent radius clamped to 0
        let clampedRadius = DesignTokens.Radii.concentric(parent: 12, padding: 16)
        #expect(clampedRadius == 0)
    }
    
    @Test("ListeningRingState covers all required states and prompts")
    func testListeningRingStates() {
        let allStates = ListeningRingState.allCases
        #expect(allStates.count == 6)
        
        for state in allStates {
            #expect(!state.rawValue.isEmpty)
            #expect(!state.promptText.isEmpty)
        }
        
        #expect(ListeningRingState.idle.promptText == "世界正在聆听")
        #expect(ListeningRingState.listening.promptText.contains("Advice"))
    }
    
    @Test("NavigationItem covers 8 primary experiences defined in baseline plus component gallery")
    func testNavigationItems() {
        let items = NavigationItem.allCases
        #expect(items.count == 9)
        
        let expectedTitles = ["世界", "人物", "命运", "故事书", "卡牌收藏", "世界线", "调查笔记", "组件画廊", "系统设置"]
        let actualTitles = items.map(\.localizedTitle)
        #expect(actualTitles == expectedTitles)
        
        for item in items {
            #expect(!item.systemIcon.isEmpty)
            #expect(item.id == item.rawValue)
            #expect(!item.shortcutNumber.isEmpty)
        }
        
        // 验证 NavigationSection 3 大语义分组
        let sections = NavigationSection.allCases
        #expect(sections.count == 3)
        #expect(NavigationSection.destiny.items.count == 3)
        #expect(NavigationSection.archives.items.count == 4)
        #expect(NavigationSection.system.items.count == 2)
    }
    
    @Test("DatabaseRole maps all 4 isolated databases")
    func testDatabaseRoles() {
        let canon = DatabaseRole.canon
        let world = DatabaseRole.world
        let retrieval = DatabaseRole.retrieval
        let runtime = DatabaseRole.runtime
        
        #expect(canon.rawValue == "canon.db")
        #expect(world.rawValue == "world.db")
        #expect(retrieval.rawValue == "retrieval.db")
        #expect(runtime.rawValue == "runtime.db")
        
        #expect(!canon.isRebuildable)
        #expect(!world.isRebuildable)
        #expect(retrieval.isRebuildable)
        #expect(!runtime.isRebuildable)
    }
    
    @Test("ComponentMetrics thresholds and proportions are valid")
    func testComponentMetricsAndThresholds() {
        #expect(DesignTokens.ComponentMetrics.ListeningRing.diameterDefault == 58)
        #expect(DesignTokens.ComponentMetrics.ListeningRing.pulseScaleMax > 1.0)
        
        #expect(DesignTokens.ComponentMetrics.Gauge.criticalThreshold == 0.25)
        #expect(DesignTokens.ComponentMetrics.Gauge.warningThreshold == 0.50)
        #expect(DesignTokens.ComponentMetrics.Gauge.criticalThreshold < DesignTokens.ComponentMetrics.Gauge.warningThreshold)
        
        #expect(DesignTokens.ComponentMetrics.TarotCard.aspectRatio > 1.6) // Golden ratio ~1.618
    }
    
    @Test("CardDiscoveryStage covers 5 stages of world cognition")
    func testCardDiscoveryStages() {
        let stages: [CardDiscoveryStage] = [.unknown, .silhouette, .identified, .partiallyRevealed, .established]
        #expect(stages.count == 5)
        #expect(stages.map(\.rawValue).allSatisfy { !$0.isEmpty })
    }
    
    @Test("NarrativeSpeakerRole provides consistent labels")
    func testNarrativeSpeakerRoles() {
        let narrator = NarrativeSpeakerRole.narrator
        let klein = NarrativeSpeakerRole.character("克莱恩·莫雷蒂")
        let advice = NarrativeSpeakerRole.playerAdvice
        
        #expect(narrator.displayName.contains("旁白"))
        #expect(klein.displayName == "克莱恩·莫雷蒂")
        #expect(advice.displayName.contains("Advice"))
    }
    
    @Test("Typography tokens and metrics are well-formed and non-empty")
    func testTypographyHierarchy() {
        // Assert TypographyMetrics constants are strictly positive
        #expect(DesignTokens.TypographyMetrics.narrativeLineSpacing == 6.0)
        #expect(DesignTokens.TypographyMetrics.parchmentLineSpacing == 5.0)
        #expect(DesignTokens.TypographyMetrics.displayTracking > DesignTokens.TypographyMetrics.titleTracking)
        #expect(DesignTokens.TypographyMetrics.monoTracking > 0)
        
        // Assert all Font.Mystic static font declarations instantiate without crash
        _ = Font.Mystic.gothicDisplay
        _ = Font.Mystic.displayLarge
        _ = Font.Mystic.titleLarge
        _ = Font.Mystic.titleMedium
        _ = Font.Mystic.titleSmall
        _ = Font.Mystic.narrativeSubtitle
        _ = Font.Mystic.bodyLarge
        _ = Font.Mystic.bodyMedium
        _ = Font.Mystic.caption
        _ = Font.Mystic.monoBadge
        _ = Font.Mystic.parchmentCursive
    }
    
    @Test("Color tokens cover enhanced WCAG and parchment hierarchy")
    func testColorTokensCompliance() {
        // High-contrast text hierarchy
        _ = Color.Mystic.textPrimary
        _ = Color.Mystic.textSecondary
        _ = Color.Mystic.textTertiary
        _ = Color.Mystic.textGoldAccent
        
        // Brass gold hierarchy
        _ = Color.Mystic.brassGoldPrimary
        _ = Color.Mystic.brassGoldMuted
        _ = Color.Mystic.brassGoldBorder
        
        // Parchment ink hierarchy
        _ = Color.Mystic.parchmentInk
        _ = Color.Mystic.parchmentInkSecondary
        _ = Color.Mystic.parchmentInkTertiary
        _ = Color.Mystic.parchmentWaxSeal
    }
    
    @Test("WorldlineBranchStatus covers canonical, diverged, active, and pruned")
    func testWorldlineBranchStatuses() {
        let allStatuses = WorldlineBranchStatus.allCases
        #expect(allStatuses.count == 4)
        for status in allStatuses {
            #expect(!status.rawValue.isEmpty)
            #expect(!status.iconName.isEmpty)
        }
        #expect(WorldlineBranchStatus.canonical.rawValue == "正典主轴")
        #expect(WorldlineBranchStatus.diverged.rawValue == "因果分叉")
    }
    
    @Test("PendulumState covers still, scrying, affirmative, and negative")
    func testPendulumStates() {
        let allStates = PendulumState.allCases
        #expect(allStates.count == 4)
        for state in allStates {
            #expect(!state.rawValue.isEmpty)
            #expect(!state.guidanceText.isEmpty)
        }
        #expect(PendulumState.affirmative.guidanceText.contains("肯定"))
        #expect(PendulumState.negative.guidanceText.contains("否定"))
    }
    
    @Test("Expanded UI components instantiate cleanly")
    @MainActor
    func testNewComponentInstantiations() {
        let worldlineNode = WorldlineNodeView(
            title: "测试分支",
            worldTime: "第五纪 1349年",
            status: .active,
            causeSummary: "因果测试说明"
        )
        _ = worldlineNode.body
        
        let pendulum = SpiritPendulumView(
            statement: "测试占卜语句",
            state: .affirmative
        )
        _ = pendulum.body
        
        let prayerCard = BronzeAltarPrayerCard(
            deityTitle: "不属于这个时代的愚者",
            domainName: "灰雾之上的神秘主宰",
            blessingTitle: "执掌好运的黄黑之王"
        )
        _ = prayerCard.body
        
        let starBeacon = CrimsonStarBeaconView(
            starName: "正义小姐",
            prayerPreview: "汇报情报"
        )
        _ = starBeacon.body
        
        let codexCard = CharacterCodexCard(
            characterName: "克莱恩",
            pathwayTitle: "占卜家",
            occupation: "文职",
            location: "廷根"
        )
        _ = codexCard.body
    }
}

