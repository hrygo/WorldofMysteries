import Foundation

/// Client-side draft delivery only. Calling a handler is not an Engine COMMIT receipt.
/// The Engine remains responsible for accepting Advice and resolving character decisions.
nonisolated enum AdviceDraftSubmission {
    static func payload(from draft: String, isEnabled: Bool, hasHandler: Bool) -> String? {
        guard isEnabled, hasHandler else { return nil }
        let trimmed = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    @MainActor
    @discardableResult
    static func submit(
        readDraft: () -> String,
        writeDraft: (String) -> Void,
        isEnabled: Bool,
        handler: (@MainActor (String) -> Void)?
    ) -> Bool {
        let originalDraft = readDraft()
        guard let handler,
              let advice = payload(from: originalDraft, isEnabled: isEnabled, hasHandler: true)
        else { return false }

        handler(advice)
        // A synchronous handler may replace the binding with a new draft. Do not erase it.
        if readDraft() == originalDraft {
            writeDraft("")
        }
        return true
    }
}
