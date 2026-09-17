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
        
        let scryingCard = CitrinePendulumScryingCard()
        _ = scryingCard.body
        #expect(ScryingResult.allCases.count == 4)
        
        let tingenCard = TingenCityDossierCard()
        _ = tingenCard.body
        #expect(TingenLocation.allCases.count == 4)
        
        let backlundCard = BacklundMetropolisCard()
        _ = backlundCard.body
        #expect(BacklundDistrict.allCases.count == 4)
        
        let gallery = ComponentGalleryView()
        _ = gallery.body
    }
    
    @Test("Unified UX Interaction tokens, Layout Insets, and Typography rhythm are positive and well-formed")
    func testInteractionAndLayoutTokens() {
        // Interaction tokens
        #expect(DesignTokens.Interaction.pressedScale < 1.0 && DesignTokens.Interaction.pressedScale > 0.9)
        #expect(DesignTokens.Interaction.pressedOpacity < 1.0 && DesignTokens.Interaction.pressedOpacity > 0.5)
        #expect(DesignTokens.Interaction.selectedBorderWidth >= 1.0)
        #expect(DesignTokens.Interaction.selectedShadowRadius > 0)
        #expect(DesignTokens.Interaction.hoverBorderOpacity > 0)
        
        // Layout insets tokens
        #expect(DesignTokens.LayoutInsets.cardPadding == 16.0)
        #expect(DesignTokens.LayoutInsets.compactCardPadding == 12.0)
        #expect(DesignTokens.LayoutInsets.rowPaddingHorizontal == 12.0)
        #expect(DesignTokens.LayoutInsets.rowPaddingVertical == 8.0)
        #expect(DesignTokens.LayoutInsets.badgePaddingHorizontal == 6.0)
        #expect(DesignTokens.LayoutInsets.badgePaddingVertical == 2.0)
        #expect(DesignTokens.LayoutInsets.panelPadding == 24.0)
        
        // Typography metrics (line spacing & tracking)
        #expect(DesignTokens.TypographyMetrics.narrativeLineSpacing > DesignTokens.TypographyMetrics.bodyLineSpacing)
        #expect(DesignTokens.TypographyMetrics.bodyLineSpacing > DesignTokens.TypographyMetrics.compactLineSpacing)
        #expect(DesignTokens.TypographyMetrics.gothicDisplayTracking >= DesignTokens.TypographyMetrics.displayTracking)
        #expect(DesignTokens.TypographyMetrics.displayTracking > DesignTokens.TypographyMetrics.titleTracking)
    }
    
    @Test("Citrine artwork geometry pins the pendant to the viewport center without letterboxing")
    func testCitrineArtworkGeometryCentering() {
        let geometry = CitrineArtworkGeometry.canonical
        let panelWidth = DesignTokens.ComponentMetrics.CitrineArtwork.panelWidth
        let viewport = CGSize(width: panelWidth, height: geometry.panelHeight(forWidth: panelWidth))
        let layout = geometry.resolveLayout(in: viewport)
        
        #expect(layout.scale > 0)
        // 视窗被原画完全覆盖：边缘无黑边缝隙
        #expect(geometry.imageSize.width * layout.scale >= viewport.width - 0.5)
        #expect(geometry.imageSize.height * layout.scale >= viewport.height - 0.5)
        
        // 黄水晶几何中心精确落在视窗正中
        let subject = CGPoint(
            x: layout.imageOrigin.x + geometry.subjectCenter.x * layout.scale,
            y: layout.imageOrigin.y + geometry.subjectCenter.y * layout.scale
        )
        #expect(abs(subject.x - viewport.width / 2) < 0.01)
        #expect(abs(subject.y - viewport.height / 2) < 0.01)
        
        // 摆动枢轴收敛于捏链点与水晶中心之间，且归一化锚点落在原画内部
        #expect(layout.swingPivot.y >= geometry.chainGrip.y - 0.01)
        #expect(layout.swingPivot.y <= geometry.subjectCenter.y)
        #expect(layout.swingAnchorUnitPoint.x > 0 && layout.swingAnchorUnitPoint.x < 1)
        #expect(layout.swingAnchorUnitPoint.y > 0 && layout.swingAnchorUnitPoint.y < 1)
        
        // 摆动条带涵盖黄水晶、且终止于红茶杯上沿之上（避免鬼影落到杯面）
        #expect(layout.swingStripFrame.contains(CGPoint(x: viewport.width / 2, y: viewport.height / 2)))
        #expect(layout.swingStripFrame.maxY < viewport.height)
        #expect(layout.swingStripFrame.height > viewport.height * 0.25)
    }
    
    @Test("Citrine artwork geometry adapts to other viewport aspects")
    func testCitrineArtworkGeometryAspectAdaptation() {
        let geometry = CitrineArtworkGeometry.canonical
        let viewports = [
            CGSize(width: 200, height: 240),
            CGSize(width: 120, height: 400),
            CGSize(width: 320, height: 200)
        ]
        
        for viewport in viewports {
            let layout = geometry.resolveLayout(in: viewport)
            #expect(geometry.imageSize.width * layout.scale >= viewport.width - 0.5)
            #expect(geometry.imageSize.height * layout.scale >= viewport.height - 0.5)
            
            let subject = CGPoint(
                x: layout.imageOrigin.x + geometry.subjectCenter.x * layout.scale,
                y: layout.imageOrigin.y + geometry.subjectCenter.y * layout.scale
            )
            #expect(abs(subject.x - viewport.width / 2) < 0.01)
            #expect(abs(subject.y - viewport.height / 2) < 0.01)
            
            #expect(layout.swingStripFrame.width > 0)
            #expect(layout.swingStripFrame.height > 0)
        }
    }
    
    @Test("Scrying prototype resolution is deterministic and stays in the presentation layer")
    func testScryingPrototypeResolution() {
        let statement = "安提哥努斯笔记仍在廷根"
        let expected: ScryingResult = statement.count % 2 == 0 ? .affirmative : .negative
        #expect(CitrinePendulumScryingCard.resolveOutcome(for: statement) == expected)
        
        // 空语句无从推演
        #expect(CitrinePendulumScryingCard.resolveOutcome(for: "   ") == .negative)
        // 涉及高位存在：无法直视
        #expect(CitrinePendulumScryingCard.resolveOutcome(for: "愚者在上") == .disturbed)
        #expect(CitrinePendulumScryingCard.resolveOutcome(for: "  灰雾之上的王座  ") == .disturbed)
        // 同一语句重复推演结果一致（确定性，可复算）
        #expect(
            CitrinePendulumScryingCard.resolveOutcome(for: statement)
                == CitrinePendulumScryingCard.resolveOutcome(for: statement)
        )
        
        // 结论定格后的停摆偏向：肯定向右、否定向左、干扰归中
        #expect(CitrinePendulumScryingCard.settledSwingAngle(for: .affirmative) > 0)
        #expect(CitrinePendulumScryingCard.settledSwingAngle(for: .negative) < 0)
        #expect(CitrinePendulumScryingCard.settledSwingAngle(for: .disturbed) == 0)
        #expect(CitrinePendulumScryingCard.settledSwingAngle(for: .inquiring) == 0)
        #expect(ScryingResult.inquiring.tone == .gold)
        #expect(ScryingResult.affirmative.tone == .teal)
        #expect(ScryingResult.negative.tone == .crimson)
        #expect(ScryingResult.disturbed.tone == .amber)
    }
    
    @Test("Mystic primitives cover the semantic tone matrix and assemble cleanly")
    @MainActor
    func testMysticPrimitives() {
        #expect(MysticTone.allCases.count == 6)
        
        for tone in MysticTone.allCases {
            #expect(!tone.semanticLabel.isEmpty)
            _ = MysticBadge("徽章", tone: tone).body
            _ = MysticStatusDot(tone: tone, isPulsing: true, label: "状态").body
            _ = MysticMetricBar(value: 0.42, tone: tone, criticalThreshold: 0.5).body
            _ = MysticKeyValueRow(key: "键", value: "值", tone: tone, isMonospaced: true).body
            _ = MysticDivider(tone: tone, label: "分隔").body
        }
        
        _ = MysticBadge("面板徽章", tone: .gold, variant: .panel, systemIcon: "lock.shield").body
        _ = MysticBadge("纯文本徽章", tone: .neutral, variant: .plain).body
        _ = MysticMetricBar(value: 0.78, tone: .amber, gradientTones: [.amber, .crimson]).body
        _ = MysticSectionHeader(title: "分区标题", caption: "副说明", count: 3).body
        _ = MysticEmptyState(
            systemIcon: "text.book.closed",
            title: "尚无内容",
            message: "说明文本",
            actionTitle: "执行",
            onAction: {}
        ).body
        _ = MysticIconButton(
            systemIcon: "arrow.triangle.2.circlepath",
            title: "重建",
            tone: .teal,
            action: {}
        ).body
    }
    
    @Test("Semantic tones are shared by canon enums instead of per-component colors")
    func testSemanticToneMappings() {
        // 地域危险等级
        #expect(BacklundDistrict.cherwood.tone == .gold)
        #expect(BacklundDistrict.bridge.tone == .amber)
        #expect(BacklundDistrict.eastEnd.tone == .crimson)
        #expect(BacklundDistrict.empress.tone == .teal)
        
        // 叙事角色
        #expect(NarrativeSpeakerRole.narrator.tone == .neutral)
        #expect(NarrativeSpeakerRole.character("克莱恩").tone == .gold)
        #expect(NarrativeSpeakerRole.playerAdvice.tone == .azure)
    }
    
    @Test("Whole component library instantiates cleanly")
    @MainActor
    func testComponentLibrarySmoke() {
        _ = ListeningRingView(state: .listening).body
        _ = SpiritualityGaugeView(title: "灵性", value: 0.5).body
        _ = TarotCardView(pathwayName: "占卜家途径", sequenceNumber: 9, sequenceTitle: "占卜家").body
        _ = CluePinboardNodeView(title: "线索", note: "说明").body
        _ = NarrativeChronicleView(role: .narrator, content: "旁白文本").body
        _ = NarrativeChronicleView(role: .narrator, content: "").body
        _ = DatabaseStatusHUDCard(role: .retrieval, isHealthy: true).body
        _ = AdviceInputField(text: .constant("建议"), targetCharacter: "克莱恩").body
        _ = CitrinePendulumArtwork(swingAngle: 6, artworkImage: nil).body
    }
}
