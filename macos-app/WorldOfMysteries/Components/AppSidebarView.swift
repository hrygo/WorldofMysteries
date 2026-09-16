import SwiftUI

/// 8 栏一级体验定义对齐 `docs/05_UI/UI_交互基线_v1.0.md`
public enum NavigationItem: String, CaseIterable, Identifiable, Sendable {
    case world = "World"
    case character = "Character"
    case fate = "Fate"
    case storyBook = "Story Book"
    case cards = "Cards"
    case worldline = "Worldline"
    case notes = "Notes"
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
        case .settings: return "gearshape"
        }
    }
}

/// 8 栏沉浸式维多利亚暗金侧边栏
public struct AppSidebarView: View {
    @Binding public var selection: NavigationItem
    
    public init(selection: Binding<NavigationItem>) {
        self._selection = selection
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            // 顶部 macOS 交通灯与品牌留白
            HStack(spacing: DesignTokens.Spacing.sm) {
                Image(systemName: "eye.circle.fill")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                
                Text("诡秘世界")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)
                
                Spacer()
            }
            .padding(.horizontal, DesignTokens.Spacing.lg)
            .padding(.top, DesignTokens.Spacing.xl)
            .padding(.bottom, DesignTokens.Spacing.md)
            
            // 8 项导航列表
            VStack(spacing: DesignTokens.Spacing.xxs) {
                ForEach(NavigationItem.allCases.filter { $0 != .settings }) { item in
                    sidebarRow(for: item)
                }
            }
            
            Spacer()
            
            // 底部常驻分割线与设置
            Divider()
                .background(Color.Mystic.brassGoldBorder.opacity(0.4))
                .padding(.horizontal, DesignTokens.Spacing.lg)
            
            sidebarRow(for: .settings)
                .padding(.bottom, DesignTokens.Spacing.lg)
        }
        .frame(width: 200)
        .background(Color.Mystic.obsidianElevated)
        .overlay(
            Rectangle()
                .frame(width: DesignTokens.Borders.standard)
                .foregroundStyle(Color.Mystic.brassGoldBorder.opacity(0.3)),
            alignment: .trailing
        )
    }
    
    @ViewBuilder
    private func sidebarRow(for item: NavigationItem) -> some View {
        let isSelected = selection == item
        
        Button {
            withAnimation(DesignTokens.Motion.smoothSpring) {
                selection = item
            }
        } label: {
            HStack(spacing: DesignTokens.Spacing.md) {
                Image(systemName: item.systemIcon)
                    .font(.system(size: 14, weight: isSelected ? .semibold : .regular))
                    .frame(width: 20)
                    .foregroundStyle(isSelected ? Color.Mystic.brassGoldPrimary : Color.Mystic.textSecondary)
                
                Text(item.localizedTitle)
                    .font(Font.Mystic.bodyMedium)
                    .fontWeight(isSelected ? .semibold : .regular)
                    .foregroundStyle(isSelected ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
                
                Spacer()
                
                if isSelected {
                    Circle()
                        .fill(Color.Mystic.brassGoldPrimary)
                        .frame(width: 4, height: 4)
                        .shadow(color: Color.Mystic.brassGoldPrimary, radius: 4)
                }
            }
            .padding(.horizontal, DesignTokens.Spacing.md)
            .padding(.vertical, DesignTokens.Spacing.sm)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                    .fill(isSelected ? Color.Mystic.obsidianCard : Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                            .stroke(
                                isSelected ? Color.Mystic.brassGoldBorder : Color.clear,
                                lineWidth: DesignTokens.Borders.hairline
                            )
                    )
            )
        }
        .buttonStyle(.plain)
        .padding(.horizontal, DesignTokens.Spacing.sm)
    }
}

#Preview("App Sidebar") {
    AppSidebarView(selection: .constant(.fate))
        .frame(height: 600)
}
