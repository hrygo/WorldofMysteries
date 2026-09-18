import Foundation

/// Presentation text is normalized without modifying the caller's model or action.
nonisolated enum WOMControlText {
    static func nonEmpty(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

/// Typed option used by `WOMAdaptiveSegmentedPicker`.
/// The value remains caller-owned; this metadata never persists a selection.
public nonisolated struct WOMSegmentedOption<Value: Hashable>: Identifiable {
    public let value: Value
    public let title: String
    public let systemImage: String?

    public init(value: Value, title: String, systemImage: String? = nil) {
        self.value = value
        self.title = title
        self.systemImage = systemImage
    }

    public var id: Value { value }
}

/// A read-only snapshot for native Picker rendering, including temporarily missing selections.
/// First usable occurrence wins for duplicate values; unlabeled choices are not actionable.
nonisolated struct WOMSegmentedPresentation<Value: Hashable> {
    let options: [WOMSegmentedOption<Value>]
    let selection: Value

    init(options: [WOMSegmentedOption<Value>], selection: Value) {
        var seen = Set<Value>()
        self.options = options.compactMap { option in
            guard let title = WOMControlText.nonEmpty(option.title),
                  seen.insert(option.value).inserted else { return nil }
            return WOMSegmentedOption(
                value: option.value,
                title: title,
                systemImage: WOMControlText.nonEmpty(option.systemImage)
            )
        }
        self.selection = selection
    }

    var hasAvailableSelection: Bool {
        options.contains { $0.value == selection }
    }

    var isEmpty: Bool { options.isEmpty }

    var placeholderTitle: String {
        isEmpty ? "暂无可用选项" : "当前选项不可用"
    }

    var displayedSelectionTitle: String {
        options.first { $0.value == selection }?.title ?? placeholderTitle
    }
}

/// Shared label/message/action policy for loading, empty-state and banner primitives.
/// A handler alone must never create an unlabeled action; a title alone is not an action.
nonisolated struct WOMFeedbackPresentation {
    let title: String
    let message: String?
    let actionTitle: String?

    init(
        title: String,
        message: String?,
        fallbackTitle: String,
        actionTitle: String? = nil,
        hasAction: Bool = false
    ) {
        self.title = WOMControlText.nonEmpty(title)
            ?? WOMControlText.nonEmpty(fallbackTitle) ?? "状态信息"
        self.message = WOMControlText.nonEmpty(message)
        self.actionTitle = hasAction ? WOMControlText.nonEmpty(actionTitle) : nil
    }

    var accessibilitySummary: String {
        [title, message].compactMap { $0 }.joined(separator: "，")
    }
}
