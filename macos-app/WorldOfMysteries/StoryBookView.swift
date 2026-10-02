import SwiftUI

/// Reads a finalized session's Story Book: cover facts, chapters in committed
/// order, the ending, and any unresolved threads. Nothing here is regenerated.
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
        }
    }

    private func coverCard(_ book: StoryBookDTO) -> some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text(book.title)
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textPrimary)
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
}
