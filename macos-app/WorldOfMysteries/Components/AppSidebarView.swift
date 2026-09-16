import SwiftUI

/// 导航分组定义（命运动态、神秘卷宗、系统治理）
public enum NavigationSection: String, CaseIterable, Identifiable, Sendable {
    case destiny = "命运动态"
    case archives = "神秘卷宗"
    case system = "系统工坊"
    
    public var id: String { rawValue }
    
    public var items: [NavigationItem] {
        switch self {
        case .destiny:
            return [.world, .character, .fate]
        case .archives:
            return [.storyBook, .cards, .worldline, .notes]
        case .system:
            return [.gallery, .settings]
        }
    }
}

/// 9 栏一级体验定义对齐 `docs/05_UI/UI_交互基线_v1.0.md` 与全新组件画廊
public enum NavigationItem: String, CaseIterable, Identifiable, Sendable {
    case world = "World"
    case character = "Character"
    case fate = "Fate"
    case storyBook = "Story Book"
    case cards = "Cards"
    case worldline = "Worldline"
    case notes = "Notes"
    case gallery = "Gallery"
    case settings = "Settings"
    
    public var id: String { rawValue }
    
    public var localizedTitle: String {
        switch self {
        case .world: return "世界"
        case .character: return "人物"
        case .fate: return "命运"
        case .storyBook: return "故事书"
        case .cards: return "卡牌收藏"
        case .worldline: return "世界线"
        case .notes: return "调查笔记"
        case .gallery: return "组件画廊"
        case .settings: return "系统设置"
        }
    }
    
    public var systemIcon: String {
        switch self {
        case .world: return "globe.europe.africa.fill"
        case .character: return "person.text.rectangle"
        case .fate: return "sparkles"
        case .storyBook: return "book.closed"
        case .cards: return "square.stack.3d.up"
        case .worldline: return "point.topleft.down.to.point.bottomright.curvepath"
        case .notes: return "text.badge.magnifyingglass"
        case .gallery: return "square.grid.2x2"
        case .settings: return "gearshape"
        }
    }
    
    public var shortcutNumber: String {
        switch self {
        case .world: return "1"
        case .character: return "2"
        case .fate: return "3"
        case .storyBook: return "4"
        case .cards: return "5"
        case .worldline: return "6"
        case .notes: return "7"
        case .gallery: return "8"
        case .settings: return "9"
        }
    }
}

/// 高保真维多利亚暗金侧边栏菜单组件（支持折叠/展开、徽标系统、快捷键提示与灵性微状态卡片）
public struct AppSidebarView: View {
    @Binding public var selection: NavigationItem
    @Binding public var isCollapsed: Bool
    public var badgeCounts: [NavigationItem: Int]
    
    @State private var hoveredItem: NavigationItem? = nil
    
    public init(
        selection: Binding<NavigationItem>,
        isCollapsed: Binding<Bool> = .constant(false),
        badgeCounts: [NavigationItem: Int] = [.fate: 2, .worldline: 1]
    ) {
        self._selection = selection
        self._isCollapsed = isCollapsed
        self.badgeCounts = badgeCounts
    }
    
    public var body: some View {
        VStack(alignment: isCollapsed ? .center : .leading, spacing: 0) {
            // 1. 顶部 Header 与折叠开关
            headerSection
            
            // 2. 分组导航列表
            ScrollView(.vertical, showsIndicators: false) {
                VStack(alignment: isCollapsed ? .center : .leading, spacing: DesignTokens.Spacing.md) {
                    ForEach(NavigationSection.allCases) { section in
                        sectionBlock(section)
                    }
                }
                .padding(.vertical, DesignTokens.Spacing.sm)
                .padding(.horizontal, isCollapsed ? DesignTokens.Spacing.xs : DesignTokens.Spacing.sm)
            }
            
            Spacer(minLength: DesignTokens.Spacing.sm)
            
            // 3. 底部灵性状态与纪元微卡片
            footerStatusCard
        }
        .frame(width: isCollapsed ? 68 : 224)
        .background(
            Color.Mystic.obsidianElevated
                .overlay(
                    LinearGradient(
                        colors: [
                            Color.Mystic.brassGoldMuted.opacity(0.04),
                            Color.clear
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .overlay(
            Rectangle()
                .frame(width: DesignTokens.Borders.standard)
                .foregroundStyle(Color.Mystic.brassGoldBorder.opacity(0.35)),
            alignment: .trailing
        )
        .animation(DesignTokens.Motion.smoothSpring, value: isCollapsed)
    }
    
    // MARK: - Header
    @ViewBuilder
    private var headerSection: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            // 全知之眼徽标
            Image(systemName: "eye.circle.fill")
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.Mystic.brassGoldPrimary, Color.Mystic.brassGoldHover],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .shadow(color: Color.Mystic.brassGoldPrimary.opacity(0.4), radius: 6)
            
            if !isCollapsed {
                VStack(alignment: .leading, spacing: 1) {
                    Text("诡秘世界")
                        .font(Font.Mystic.titleSmall)
                        .fontWeight(.bold)
                        .foregroundStyle(Color.Mystic.textPrimary)
                    
                    Text("World of Mysteries")
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(Color.Mystic.brassGoldMuted)
                }
                
                Spacer()
            }
            
            // 折叠/展开切换按钮
            Button {
                withAnimation(DesignTokens.Motion.smoothSpring) {
                    isCollapsed.toggle()
                }
            } label: {
                Image(systemName: isCollapsed ? "sidebar.right" : "sidebar.left")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Color.Mystic.textTertiary)
                    .padding(6)
                    .background(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.xs)
                            .fill(Color.Mystic.obsidianCard.opacity(0.6))
                    )
            }
            .buttonStyle(.plain)
            .help(isCollapsed ? "展开侧边栏 (⌥⌘S)" : "折叠侧边栏 (⌥⌘S)")
        }
        .padding(.horizontal, isCollapsed ? DesignTokens.Spacing.sm : DesignTokens.Spacing.md)
        .padding(.top, DesignTokens.Spacing.lg)
        .padding(.bottom, DesignTokens.Spacing.md)
        
        Divider()
            .background(Color.Mystic.brassGoldBorder.opacity(0.3))
    }
    
    // MARK: - Section Block
    @ViewBuilder
    private func sectionBlock(_ section: NavigationSection) -> some View {
        VStack(alignment: isCollapsed ? .center : .leading, spacing: DesignTokens.Spacing.xxs) {
            if !isCollapsed {
                Text(section.rawValue)
                    .font(Font.Mystic.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(Color.Mystic.textTertiary)
                    .padding(.horizontal, DesignTokens.Spacing.md)
                    .padding(.top, DesignTokens.Spacing.xs)
                    .padding(.bottom, 2)
            } else {
                // 折叠模式下的轻微隔离
                Circle()
                    .fill(Color.Mystic.brassGoldBorder.opacity(0.3))
                    .frame(width: 3, height: 3)
                    .padding(.vertical, 4)
            }
            
            ForEach(section.items) { item in
                sidebarRow(for: item)
            }
        }
    }
    
    // MARK: - Row
    @ViewBuilder
    private func sidebarRow(for item: NavigationItem) -> some View {
        let isSelected = selection == item
        let isHovered = hoveredItem == item
        let count = badgeCounts[item] ?? 0
        
        Button {
            withAnimation(DesignTokens.Motion.smoothSpring) {
                selection = item
            }
        } label: {
            HStack(spacing: DesignTokens.Spacing.md) {
                // 选中态左侧暗金竖指示条 (仅在展开模式显示)
                if !isCollapsed {
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(isSelected ? Color.Mystic.brassGoldPrimary : Color.clear)
                        .frame(width: 3, height: 16)
                        .shadow(color: isSelected ? Color.Mystic.brassGoldPrimary.opacity(0.6) : .clear, radius: 4)
                }
                
                // 图标
                ZStack(alignment: .topTrailing) {
                    Image(systemName: item.systemIcon)
                        .font(.system(size: 15, weight: isSelected ? .semibold : .regular))
                        .foregroundStyle(
                            isSelected
                                ? Color.Mystic.brassGoldPrimary
                                : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
                        )
                        .frame(width: 20, height: 20)
                    
                    // 折叠模式下的 Badge 红点
                    if isCollapsed && count > 0 {
                        Circle()
                            .fill(Color.Mystic.crimsonGlow)
                            .frame(width: 6, height: 6)
                            .offset(x: 4, y: -2)
                            .shadow(color: Color.Mystic.crimsonGlow.opacity(0.8), radius: 3)
                    }
                }
                
                // 展开模式下的文字、Badge 与快捷键
                if !isCollapsed {
                    Text(item.localizedTitle)
                        .font(Font.Mystic.bodyMedium)
                        .fontWeight(isSelected ? .semibold : .regular)
                        .foregroundStyle(isSelected ? Color.Mystic.textPrimary : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textSecondary))
                    
                    Spacer()
                    
                    // Badge 计数胶囊
                    if count > 0 {
                        Text("\(count)")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundStyle(Color.white)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(
                                Capsule()
                                    .fill(Color.Mystic.crimsonGlow.opacity(0.9))
                            )
                            .shadow(color: Color.Mystic.crimsonGlow.opacity(0.5), radius: 4)
                    }
                    
                    // 快捷键提示
                    Text("⌘\(item.shortcutNumber)")
                        .font(.system(size: 10, weight: .regular, design: .monospaced))
                        .foregroundStyle(isSelected ? Color.Mystic.brassGoldMuted : Color.Mystic.textTertiary.opacity(0.6))
                }
            }
            .padding(.horizontal, isCollapsed ? 12 : DesignTokens.Spacing.sm)
            .padding(.vertical, DesignTokens.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: isCollapsed ? .center : .leading)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                    .fill(
                        isSelected
                            ? Color.Mystic.obsidianCard
                            : (isHovered ? Color.Mystic.obsidianCard.opacity(0.5) : Color.clear)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                            .stroke(
                                isSelected ? Color.Mystic.brassGoldBorder.opacity(0.7) : (isHovered ? Color.Mystic.brassGoldBorder.opacity(0.25) : Color.clear),
                                lineWidth: DesignTokens.Borders.hairline
                            )
                    )
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            hoveredItem = hovering ? item : nil
        }
        .help("\(item.localizedTitle) (⌘\(item.shortcutNumber))")
    }
    
    // MARK: - Footer Status Card
    @ViewBuilder
    private var footerStatusCard: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            Divider()
                .background(Color.Mystic.brassGoldBorder.opacity(0.25))
            
            if !isCollapsed {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Circle()
                            .fill(Color.Mystic.statusOnline)
                            .frame(width: 6, height: 6)
                            .shadow(color: Color.Mystic.statusOnline.opacity(0.8), radius: 3)
                        
                        Text("克莱恩 · 占卜家")
                            .font(Font.Mystic.caption)
                            .fontWeight(.medium)
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)
                        
                        Spacer()
                        
                        Text("Seq 9")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(Color.Mystic.parchmentInkSecondary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.Mystic.parchmentCard)
                            )
                    }
                    
                    // 灵性与理智微进度条
                    VStack(spacing: 3) {
                        HStack {
                            Text("灵性储备")
                                .font(.system(size: 9))
                                .foregroundStyle(Color.Mystic.textTertiary)
                            Spacer()
                            Text("85%")
                                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                                .foregroundStyle(Color.Mystic.textSecondary)
                        }
                        
                        GeometryReader { proxy in
                            ZStack(alignment: .leading) {
                                Capsule()
                                    .fill(Color.Mystic.obsidianCard)
                                Capsule()
                                    .fill(
                                        LinearGradient(
                                            colors: [Color.Mystic.spiritualBlue, Color.Mystic.spiritualGlow],
                                            startPoint: .leading,
                                            endPoint: .trailing
                                        )
                                    )
                                    .frame(width: proxy.size.width * 0.85)
                            }
                        }
                        .frame(height: 3)
                    }
                }
                .padding(.horizontal, DesignTokens.Spacing.md)
                .padding(.vertical, DesignTokens.Spacing.sm)
                .background(
                    RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                        .fill(Color.Mystic.obsidianBase.opacity(0.6))
                        .overlay(
                            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                                .stroke(Color.Mystic.brassGoldBorder.opacity(0.2), lineWidth: 1)
                        )
                )
                .padding(.horizontal, DesignTokens.Spacing.sm)
                .padding(.bottom, DesignTokens.Spacing.md)
            } else {
                // 折叠模式下的微型灵性圆点指示
                ZStack {
                    Circle()
                        .stroke(Color.Mystic.brassGoldBorder.opacity(0.3), lineWidth: 2)
                        .frame(width: 28, height: 28)
                    
                    Circle()
                        .trim(from: 0, to: 0.85)
                        .stroke(Color.Mystic.spiritualBlue, lineWidth: 2)
                        .frame(width: 28, height: 28)
                        .rotationEffect(.degrees(-90))
                    
                    Circle()
                        .fill(Color.Mystic.statusOnline)
                        .frame(width: 6, height: 6)
                }
                .padding(.vertical, DesignTokens.Spacing.sm)
                .help("克莱恩·莫雷蒂 (灵性 85% · 引擎就绪)")
            }
        }
    }
}

#Preview("App Sidebar - Expanded") {
    AppSidebarView(selection: .constant(.fate), isCollapsed: .constant(false))
        .frame(height: 680)
}

#Preview("App Sidebar - Collapsed") {
    AppSidebarView(selection: .constant(.fate), isCollapsed: .constant(true))
        .frame(height: 680)
}
