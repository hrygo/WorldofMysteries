import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("World Interaction Boundaries")
struct WorldInteractionBoundaryTests {
    @Test("Advice readiness requires a nonempty draft, an enabled control and a handler")
    func adviceReadiness() {
        #expect(AdviceDraftSubmission.payload(from: "  保持警惕\n", isEnabled: true, hasHandler: true) == "保持警惕")
        #expect(AdviceDraftSubmission.payload(from: "保持警惕", isEnabled: false, hasHandler: true) == nil)
        #expect(AdviceDraftSubmission.payload(from: "保持警惕", isEnabled: true, hasHandler: false) == nil)
        #expect(AdviceDraftSubmission.payload(from: " \t\n ", isEnabled: true, hasHandler: true) == nil)
    }

    @Test("Missing Advice handler never consumes a draft")
    @MainActor
    func missingHandlerPreservesDraft() {
        var draft = "  留在灯光下，不要进入巷子。\n"
        let original = draft
        var writes = 0
        let delivered = AdviceDraftSubmission.submit(
            readDraft: { draft },
            writeDraft: { draft = $0; writes += 1 },
            isEnabled: true,
            handler: nil
        )
        #expect(!delivered)
        #expect(draft == original)
        #expect(writes == 0)
    }

    @Test("Disabled Advice refuses keyboard-path delivery as well as pointer delivery")
    @MainActor
    func disabledHandlerDoesNotRun() {
        var draft = "不要独自调查。"
        var deliveries: [String] = []
        let delivered = AdviceDraftSubmission.submit(
            readDraft: { draft },
            writeDraft: { draft = $0 },
            isEnabled: false,
            handler: { deliveries.append($0) }
        )
        #expect(!delivered)
        #expect(deliveries.isEmpty)
        #expect(draft == "不要独自调查。")
    }

    @Test("Whitespace-only Advice is not delivered or silently discarded")
    @MainActor
    func whitespaceDraftPreserved() {
        var draft = " \t\n "
        var deliveries = 0
        let delivered1 = AdviceDraftSubmission.submit(
            readDraft: { draft },
            writeDraft: { draft = $0 },
            isEnabled: true,
            handler: { _ in deliveries += 1 }
        )
        #expect(!delivered1)
        #expect(draft == " \t\n ")
        #expect(deliveries == 0)
    }

    @Test("Available Advice delivers one trimmed message and clears only that draft")
    @MainActor
    func adviceDelivery() {
        var draft = "  请先观察。\n"
        var deliveries: [String] = []
        let delivered3 = AdviceDraftSubmission.submit(
            readDraft: { draft },
            writeDraft: { draft = $0 },
            isEnabled: true,
            handler: { deliveries.append($0) }
        )
        #expect(delivered3)
        #expect(deliveries == ["请先观察。"])
        #expect(draft.isEmpty)
        let delivered2 = AdviceDraftSubmission.submit(
            readDraft: { draft },
            writeDraft: { draft = $0 },
            isEnabled: true,
            handler: { deliveries.append($0) }
        )
        #expect(!delivered2)
        #expect(deliveries.count == 1)
    }

    @Test("A handler's replacement draft survives delivery cleanup")
    @MainActor
    func replacementDraftPreserved() {
        var draft = "先观察门口。"
        var deliveries: [String] = []
        let delivered4 = AdviceDraftSubmission.submit(
            readDraft: { draft },
            writeDraft: { draft = $0 },
            isEnabled: true,
            handler: { advice in
                deliveries.append(advice)
                draft = "再留意窗边。"
            }
        )
        #expect(delivered4)
        #expect(deliveries == ["先观察门口。"])
        #expect(draft == "再留意窗边。")
    }

    @Test("Unknown and fragment cards reveal nothing through copy or identity styling", arguments: [
        CardDiscoveryStage.unknown, .silhouette,
    ])
    func concealedIdentity(stage: CardDiscoveryStage) {
        let first = CardDiscoveryPresentation(
            stage: stage, pathwayName: "SECRET_PATHWAY_A", sequenceNumber: 7, sequenceTitle: "SECRET_TITLE_A"
        )
        let second = CardDiscoveryPresentation(
            stage: stage, pathwayName: "SECRET_PATHWAY_B", sequenceNumber: 0, sequenceTitle: "SECRET_TITLE_B"
        )
        // Noninterference: different hidden identities must produce the same exposed projection.
        #expect(first == second)
        #expect(!first.revealsIdentity)
        #expect(first.sequenceLabel == "Seq.?")
        for copy in [first.pathwayLabel, first.sequenceLabel, first.title, first.accessibilityLabel, first.stageText] {
            #expect(!copy.contains("SECRET_"))
        }
    }

    @Test("Identification reveals only the identity supplied by the caller", arguments: [
        CardDiscoveryStage.identified, .partiallyRevealed, .established,
    ])
    func revealedIdentity(stage: CardDiscoveryStage) {
        let projection = CardDiscoveryPresentation(
            stage: stage, pathwayName: "已确认途径", sequenceNumber: 4, sequenceTitle: "已确认序列"
        )
        #expect(projection.revealsIdentity)
        #expect(projection.pathwayLabel == "已确认途径")
        #expect(projection.sequenceLabel == "Seq.4")
        #expect(projection.title == "已确认序列")
        #expect(projection.accessibilityLabel == "已确认途径，序列 4 已确认序列")
    }

    @Test("Discovery progress never claims that the player changed Canon")
    func establishedBiographyIsNotCanonMutation() {
        let projection = CardDiscoveryPresentation(
            stage: .established, pathwayName: "已确认途径", sequenceNumber: 9, sequenceTitle: "已确认序列"
        )
        #expect(projection.stageText == "生平已建立")
        #expect(!projection.stageText.contains("正典已确立"))
    }

    @Test("Switching to an undiscovered world context removes previously exposed identity")
    func concealAfterContextChange() {
        var stage: CardDiscoveryStage = .established
        func projection() -> CardDiscoveryPresentation {
            CardDiscoveryPresentation(
                stage: stage, pathwayName: "SECRET_PATHWAY", sequenceNumber: 3, sequenceTitle: "SECRET_TITLE"
            )
        }
        #expect(projection().revealsIdentity)
        stage = .unknown
        #expect(!projection().revealsIdentity)
        #expect(projection().title == "未知卡牌")
        #expect(!projection().accessibilityLabel.contains("SECRET_"))
    }
}
