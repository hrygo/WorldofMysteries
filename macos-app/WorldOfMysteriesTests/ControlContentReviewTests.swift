import Testing
@testable import WorldOfMysteriesCore

@Suite("Control Content Review")
struct ControlContentReviewTests {
    @Test(arguments: ["", " ", "\t\n", "\u{3000}", "\u{00A0}"])
    func blankContentIsNotActionable(_ value: String) {
        #expect(WOMControlText.nonEmpty(value) == nil)
        let feedback = WOMFeedbackPresentation(
            title: value, message: value, fallbackTitle: "暂无内容",
            actionTitle: value, hasAction: true
        )
        #expect(feedback.title == "暂无内容")
        #expect(feedback.message == nil)
        #expect(feedback.actionTitle == nil)
        #expect(feedback.accessibilitySummary == "暂无内容")
    }

    @Test("first usable duplicate wins without reordering values")
    func duplicateIdentityResolution() {
        let raw = [
            WOMSegmentedOption(value: 2, title: "   "),
            WOMSegmentedOption(value: 1, title: " 世界 ", systemImage: " globe "),
            WOMSegmentedOption(value: 2, title: "档案"),
            WOMSegmentedOption(value: 1, title: "重复世界"),
            WOMSegmentedOption(value: 3, title: "章回", systemImage: " "),
        ]
        let result = WOMSegmentedPresentation(options: raw, selection: 2)
        #expect(result.options.map(\.value) == [1, 2, 3])
        #expect(result.options.map(\.title) == ["世界", "档案", "章回"])
        #expect(result.options[0].systemImage == "globe")
        #expect(result.options[2].systemImage == nil)
        #expect(raw[0].title == "   ")
        #expect(raw.count == 5)
    }

    @Test("equal labels with distinct values remain distinct choices")
    func labelsAreNotIdentity() {
        let result = WOMSegmentedPresentation(options: [
            WOMSegmentedOption(value: "a", title: "同名"),
            WOMSegmentedOption(value: "b", title: "同名"),
        ], selection: "b")
        #expect(result.options.map(\.id) == ["a", "b"])
        #expect(result.hasAvailableSelection)
    }

    @Test("empty or entirely unlabeled options retain the caller's selected value")
    func emptyOptionsDoNotSelectAnotherValue() {
        for options: [WOMSegmentedOption<Int>] in [[], [.init(value: 1, title: " ")]] {
            let result = WOMSegmentedPresentation(options: options, selection: 42)
            #expect(result.isEmpty)
            #expect(!result.hasAvailableSelection)
            #expect(result.selection == 42)
            #expect(result.displayedSelectionTitle == "暂无可用选项")
        }
    }

    @Test("missing selection is not relabeled as the first available option")
    func unavailableSelectionIsExplicit() {
        let result = WOMSegmentedPresentation(
            options: [.init(value: "world", title: "世界")], selection: "archive"
        )
        #expect(!result.isEmpty)
        #expect(!result.hasAvailableSelection)
        #expect(result.selection == "archive")
        #expect(result.displayedSelectionTitle == "当前选项不可用")
    }

    @Test("removal and restoration preserve the original choice")
    func selectionRecovery() {
        let all: [WOMSegmentedOption<String>] = [
            .init(value: "world", title: "世界"), .init(value: "archive", title: "档案"),
        ]
        let missing = WOMSegmentedPresentation(options: Array(all.prefix(1)), selection: "archive")
        let restored = WOMSegmentedPresentation(options: all, selection: missing.selection)
        #expect(restored.hasAvailableSelection)
        #expect(restored.selection == "archive")
        #expect(restored.displayedSelectionTitle == "档案")
    }

    @Test("an explicit nil value is a valid optional selection, not an empty list")
    func optionalSelectionIdentity() {
        let options: [WOMSegmentedOption<String?>] = [
            .init(value: nil, title: "全部"), .init(value: "world", title: "世界"),
        ]
        let all = WOMSegmentedPresentation(options: options, selection: nil)
        #expect(all.hasAvailableSelection)
        #expect(all.displayedSelectionTitle == "全部")
        let missing = WOMSegmentedPresentation(options: Array(options.suffix(1)), selection: nil)
        #expect(!missing.hasAvailableSelection)
        #expect(missing.selection == nil)
    }

    @Test("value labels update without changing the selection identity")
    func metadataRefresh() {
        let result = WOMSegmentedPresentation(
            options: [.init(value: 7, title: "  Updated label  ")], selection: 7
        )
        #expect(result.selection == 7)
        #expect(result.displayedSelectionTitle == "Updated label")
    }

    @Test("action requires both a usable label and a handler")
    func feedbackActionBoundary() {
        let noHandler = WOMFeedbackPresentation(
            title: "失败", message: nil, fallbackTitle: "状态",
            actionTitle: "重试", hasAction: false
        )
        let noLabel = WOMFeedbackPresentation(
            title: "失败", message: nil, fallbackTitle: "状态", hasAction: true
        )
        let valid = WOMFeedbackPresentation(
            title: "失败", message: nil, fallbackTitle: "状态",
            actionTitle: "  重试  ", hasAction: true
        )
        #expect(noHandler.actionTitle == nil)
        #expect(noLabel.actionTitle == nil)
        #expect(valid.actionTitle == "重试")
    }

    @Test("accessibility summary retains message and strips only surrounding whitespace")
    func completeAccessibleDescription() {
        let result = WOMFeedbackPresentation(
            title: "  正在准备  ", message: "\n等待本地服务响应\n第二行说明\n", fallbackTitle: "状态"
        )
        #expect(result.accessibilitySummary == "正在准备，等待本地服务响应\n第二行说明")
    }

    @Test("missing message does not introduce punctuation or a blank label")
    func optionalMessageAndFallback() {
        #expect(WOMControlText.nonEmpty(nil) == nil)
        let result = WOMFeedbackPresentation(title: " ", message: nil, fallbackTitle: "\n")
        #expect(result.title == "状态信息")
        #expect(result.accessibilitySummary == "状态信息")
    }
}
