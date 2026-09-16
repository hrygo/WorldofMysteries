import Testing
import Foundation
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
    
    @Test("NavigationItem covers 8 primary experiences defined in baseline")
    func testNavigationItems() {
        let items = NavigationItem.allCases
        #expect(items.count == 8)
        
        let expectedTitles = ["世界", "人物", "命运", "故事书", "卡牌收藏", "世界线", "调查笔记", "系统设置"]
        let actualTitles = items.map(\.localizedTitle)
        #expect(actualTitles == expectedTitles)
        
        for item in items {
            #expect(!item.systemIcon.isEmpty)
            #expect(item.id == item.rawValue)
        }
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
}

