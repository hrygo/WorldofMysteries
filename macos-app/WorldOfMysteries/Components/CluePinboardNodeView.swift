import SwiftUI

/// 侦探卷宗线索节点卡片（对应原型 09 调查笔记）
public struct CluePinboardNodeView: View {
    public let title: String
    public let note: String
    public let dateText: String
    public let hasCrimsonThread: Bool
    public var onNodeTapped: (@MainActor () -> Void)?
    
    public init(
        title: String,
        note: String,
        dateText: String = "6月28日 晨",
        hasCrimsonThread: Bool = true,
        onNodeTapped: (@MainActor () -> Void)? = nil
    ) {
        self.title = title
        self.note = note
        self.dateText = dateText
        self.hasCrimsonThread = hasCrimsonThread
        self.onNodeTapped = onNodeTapped
    }
    
    public var body: some View {
        Button {
            onNodeTapped?()
        } label: {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                // 顶部黄铜图钉与红线指示
                HStack {
                    Circle()
                        .fill(Color.Mystic.brassGoldPrimary)
                        .frame(width: 10, height: 10)
                        .overlay(Circle().stroke(Color.black.opacity(0.4), lineWidth: 1))
                        .shadow(color: Color.black.opacity(0.3), radius: 2, y: 1)
                    
                    Spacer()
                    
                    if hasCrimsonThread {
                        HStack(spacing: 2) {
                            Circle()
                                .fill(Color.Mystic.crimsonStar)
                                .frame(width: 4, height: 4)
                            Text("密修会关联线")
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.crimsonThread)
                        }
                    }
                }
                
                // 线索标题
                Text(title)
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.parchmentInk)
                
                // 钢笔草写便签
                Text(note)
                    .font(Font.Mystic.parchmentCursive)
                    .foregroundStyle(Color.Mystic.parchmentInk)
                    .lineLimit(3)
                    .lineSpacing(3)
                
                HStack {
                    Spacer()
                    Text(dateText)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.parchmentInk.opacity(0.6))
                }
            }
            .padding(DesignTokens.Spacing.md)
            .frame(width: 220)
            .background(Color.Mystic.parchmentCard)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.xs))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.xs)
                    .stroke(Color.Mystic.parchmentBorder, lineWidth: DesignTokens.Borders.standard)
            )
            .shadow(color: Color.black.opacity(0.2), radius: 6, y: 3)
        }
        .buttonStyle(.plain)
    }
}

#Preview("Clue Pinboard Nodes") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        HStack(spacing: DesignTokens.Spacing.lg) {
            CluePinboardNodeView(
                title: "自杀的手枪",
                note: "转轮手枪内缺少一颗子弹。弹壳掉落在书桌右侧红木脚垫旁。"
            )
            CluePinboardNodeView(
                title: "安提哥努斯笔记",
                note: "分明记得昨天还在韦尔奇书架第三格，翻遍房间未见踪影。"
            )
        }
        .padding(DesignTokens.Spacing.xl)
    }
}
