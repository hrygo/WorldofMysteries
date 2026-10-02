import SwiftUI

/// Reads a finalized session's Story Book: cover facts, chapters in committed
/// order, the ending, any unresolved threads, and the four reading-list sections
/// of PRD §20. Nothing here is regenerated.
public struct StoryBookView: View {
    private let model: StoryBookModel
    private let sessionId: String?

    public init(model: StoryBookModel, sessionId: String?) {
        self.model = model
        self.sessionId = sessionId
    }

    public var body: some View {
        // No nested ScrollView: `ContentView.workspaceScroll` already owns the
        // vertical scroll for every module page, and a second one inside it
        // collapses to a degenerate height on macOS.
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            header
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task(id: sessionId) {
            guard let sessionId, !sessionId.isEmpty else {
                model.reset()
                return
            }
            await model.load(sessionId: sessionId)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text("故事书 · Story Book")
                .font(Font.Mystic.titleLarge)
                .foregroundStyle(Color.Mystic.textGoldAccent)
            Text("已结算的一段经历，按实际发生的样子重读。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case .idle:
            placeholder("尚无可读的故事书。")
        case .loading:
            ProgressView().controlSize(.small)
        case .notFinalized:
            placeholder("这一段经历尚未落定，故事书仍在书写中。")
        case .failed(let code):
            placeholder("暂时无法读取故事书（\(code)）。")
        case .loaded(let book):
            bookBody(book)
        }
    }

    private func placeholder(_ message: String) -> some View {
        VictorianCard(style: .obsidianGlass) {
            Text(message)
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textSecondary)
        }
    }

    private func bookBody(_ book: StoryBookDTO) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            coverCard(book)
            ForEach(Array(book.chapters.enumerated()), id: \.offset) { index, chapter in
                chapterCard(index: index, chapter: chapter)
            }
            endingCard(book)
            // An empty section is not rendered. The Engine omits a row it has
            // no public label for, so an empty list means "there is nothing to
            // say here" rather than "say that there is nothing here".
            if !book.discoveredSecrets.isEmpty {
                discoveredSecretsCard(book.discoveredSecrets)
            }
            if !book.keyCharacters.isEmpty {
                keyCharactersCard(book.keyCharacters)
            }
            if !book.relationshipChanges.isEmpty {
                relationshipChangesCard(book.relationshipChanges)
            }
            if !book.worldImpacts.isEmpty {
                worldImpactsCard(book.worldImpacts)
            }
        }
    }

    private func coverCard(_ book: StoryBookDTO) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text(book.title)
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textPrimary)
                // An unnamed protagonist still occupies a slot, so it reads as
                // "someone" rather than quietly shortening the list. Same
                // wording the relationship section already uses for an
                // endpoint the Engine could not name.
                if let line = StoryBookDTO.protagonistLine(book.protagonistLabels) {
                    Text(line)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
                if let start = book.startWorldTime, let end = book.endWorldTime {
                    Text("\(start) — \(end)")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
            }
        }
    }

    private func chapterCard(index: Int, chapter: StoryBookChapterDTO) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("第 \(index + 1) 章")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                ForEach(Array(chapter.segments.enumerated()), id: \.offset) { _, segment in
                    if let speaker = segment.speaker {
                        Text("\(speaker)：\(segment.text)")
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textPrimary)
                    } else {
                        Text(segment.text)
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textSecondary)
                    }
                }
            }
        }
    }

    private func endingCard(_ book: StoryBookDTO) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("终章 · \(book.ending.type)")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                if let problem = book.ending.mainProblem {
                    Text(problem)
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
                if let threads = book.unresolvedThreads, !threads.isEmpty {
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        Text("未解之缘")
                            .font(Font.Mystic.titleSmall)
                            .foregroundStyle(Color.Mystic.textGoldAccent)
                        ForEach(threads, id: \.self) { thread in
                            Text("· \(thread)")
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.textSecondary)
                        }
                    }
                }
            }
        }
    }

    private func sectionTitle(_ text: String) -> some View {
        Text(text)
            .font(Font.Mystic.titleSmall)
            .foregroundStyle(Color.Mystic.textGoldAccent)
    }

    private func discoveredSecretsCard(_ secrets: [StoryBookDiscoveredSecretDTO]) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                sectionTitle("已发现的秘密")
                ForEach(Array(secrets.enumerated()), id: \.offset) { _, secret in
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        Text(secret.proposition)
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textPrimary)
                        // A holder the Engine could not name is shown as
                        // unknown, never as the canonical id it failed to
                        // resolve.
                        Text("· \(secret.holder ?? "持有人不明") · 确定度 \(Self.percent(secret.certainty))")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                    }
                }
            }
        }
    }

    private func keyCharactersCard(_ characters: [StoryBookKeyCharacterDTO]) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                sectionTitle("关键人物")
                ForEach(Array(characters.enumerated()), id: \.offset) { _, character in
                    Text("· \(character.label)（\(character.changeCount) 处变化）")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textPrimary)
                }
            }
        }
    }

    private func relationshipChangesCard(_ changes: [StoryBookRelationshipChangeDTO]) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                sectionTitle("重要关系变化")
                ForEach(Array(changes.enumerated()), id: \.offset) { _, change in
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        Text("\(change.from ?? "某人") → \(change.to ?? "某人")")
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textPrimary)
                        // Only the dimensions that actually moved appear, in
                        // the Engine's fixed order.
                        ForEach(Array(change.dimensions.changed.enumerated()), id: \.offset) { _, dimension in
                            Text("· \(dimension.name) \(Self.delta(dimension.delta))")
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.textSecondary)
                        }
                    }
                }
            }
        }
    }

    private func worldImpactsCard(_ impacts: [StoryBookWorldImpactDTO]) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                sectionTitle("世界影响")
                ForEach(Array(impacts.enumerated()), id: \.offset) { _, impact in
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        Text(impact.eventType)
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textPrimary)
                        Text("· \(impact.importance) · \(impact.persistence)")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                        // The Engine already dropped ids it could not resolve,
                        // so these are public labels or nothing.
                        if !impact.actors.isEmpty {
                            Text("· 行为者：\(impact.actors.joined(separator: "、"))")
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.textSecondary)
                        }
                        if !impact.targets.isEmpty {
                            Text("· 影响：\(impact.targets.joined(separator: "、"))")
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.textSecondary)
                        }
                    }
                }
            }
        }
    }

    /// A confidence the reader can compare at a glance, without implying more
    /// precision than the Engine committed.
    private static func percent(_ value: Double) -> String {
        "\(Int((value * 100).rounded()))%"
    }

    private static func delta(_ value: Double) -> String {
        let rounded = (value * 100).rounded() / 100
        return rounded > 0 ? "+\(rounded)" : "\(rounded)"
    }
}
