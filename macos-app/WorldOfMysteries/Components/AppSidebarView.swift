import SwiftUI

/// 导航分组定义（命运动态、神秘卷宗、系统治理）
public enum NavigationSection: String, CaseIterable, Identifiable, Sendable {
    case destiny = "命运动态"
    case archives = "神秘卷宗"
    case system = "系统工坊"

    public var id: String { rawValue }

    public var items: [NavigationItem] {
        switch self {
        case .destiny: [.world, .character, .fate]
        case .archives: [.storyBook, .cards, .worldline, .notes]
        case .system: [.gallery, .settings]
        }
    }
}

/// 9 栏一级体验定义对齐 `docs/05_UI/UI_交互基线_v1.0.md` 与全新组件画廊。
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
        case .world: "世界"
        case .character: "人物"
        case .fate: "命运"
        case .storyBook: "故事书"
        case .cards: "卡牌收藏"
        case .worldline: "世界线"
        case .notes: "调查笔记"
        case .gallery: "组件画廊"
        case .settings: "系统设置"
        }
    }

    /// Typed visual-system source used by the production Sidebar.
    public var iconSource: WOMIconSource {
        switch self {
        case .world: .asset(.world)
        case .character: .navigation(.character)
        case .fate: .navigation(.fate)
        case .storyBook: .asset(.codex)
        case .cards: .asset(.card)
        case .worldline: .navigation(.worldline)
        case .notes: .navigation(.notes)
        case .gallery: .system(.gallery)
        case .settings: .system(.settings)
        }
    }

    /// Compatibility mapping retained until all call sites migrate to `iconSource`.
    public var systemIcon: String {
        switch self {
        case .world: "globe.europe.africa.fill"
        case .character: "person.text.rectangle"
        case .fate: "sparkles"
        case .storyBook: "book.closed"
        case .cards: "square.stack.3d.up"
        case .worldline: "point.topleft.down.to.point.bottomright.curvepath"
        case .notes: "text.badge.magnifyingglass"
        case .gallery: "square.grid.2x2"
        case .settings: "gearshape"
        }
    }

    public var shortcutNumber: String {
        switch self {
        case .world: "1"
        case .character: "2"
        case .fate: "3"
        case .storyBook: "4"
        case .cards: "5"
        case .worldline: "6"
        case .notes: "7"
        case .gallery: "8"
        case .settings: "9"
        }
    }
}

/// 高保真维多利亚暗金侧边栏菜单组件（支持折叠/展开、徽标系统、快捷键提示与灵性微状态卡片）。
public struct AppSidebarView: View {
    @Binding public var selection: NavigationItem
    @Binding public var isCollapsed: Bool
    public var badgeCounts: [NavigationItem: Int]

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hoveredItem: NavigationItem?

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
            headerSection

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
            footerStatusCard
        }
        .frame(width: isCollapsed ? 68 : 224)
        .background(
            WOMPanelBackground(
                tone: .panel,
                cornerRadius: 0,
                texture: .sacredSlate,
                textureOpacity: 0.025
            )
        )
        .overlay(
            Rectangle()
                .frame(width: DesignTokens.Borders.standard)
                .foregroundStyle(Color.Mystic.brassGoldBorder.opacity(0.35)),
            alignment: .trailing
        )
        .animation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring, value: isCollapsed)
    }

    // MARK: - Header

    @ViewBuilder
    private var headerSection: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            WOMIcon(
                .seal,
                size: .prominent,
                accessibilityLabel: isCollapsed ? "诡秘世界" : nil
            )
            .foregroundStyle(
                LinearGradient(
                    colors: [Color.Mystic.brassGoldPrimary, Color.Mystic.brassGoldHover],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .shadow(color: Color.Mystic.brassGoldPrimary.opacity(0.32), radius: 5)

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

            Button {
                withAnimation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring) {
                    isCollapsed.toggle()
                }
            } label: {
                WOMIcon(
                    system: isCollapsed ? .sidebarExpand : .sidebarCollapse,
                    size: .compact
                )
                .foregroundStyle(Color.Mystic.textSecondary)
            }
            .buttonStyle(WOMToolbarButtonStyle())
            .accessibilityLabel(isCollapsed ? "展开侧边栏" : "折叠侧边栏")
            .help(isCollapsed ? "展开侧边栏 (⌥⌘S)" : "折叠侧边栏 (⌥⌘S)")
        }
        .padding(.horizontal, isCollapsed ? DesignTokens.Spacing.sm : DesignTokens.Spacing.md)
        .padding(.top, DesignTokens.Spacing.lg)
        .padding(.bottom, DesignTokens.Spacing.md)

        WOMDividerOrnament(opacity: 0.42)
            .padding(.horizontal, DesignTokens.Spacing.sm)
    }

    // MARK: - Section Block

    @ViewBuilder
    private func sectionBlock(_ section: NavigationSection) -> some View {
        VStack(alignment: isCollapsed ? .center : .leading, spacing: DesignTokens.Spacing.xxs) {
            if !isCollapsed {
                Text(section.rawValue)
                    .womSectionHeaderStyle()
                    .foregroundStyle(Color.Mystic.textTertiary)
                    .padding(.horizontal, DesignTokens.Spacing.md)
                    .padding(.top, DesignTokens.Spacing.xs)
                    .padding(.bottom, 2)
            } else {
                Circle()
                    .fill(Color.Mystic.brassGoldBorder.opacity(0.35))
                    .frame(width: 3, height: 3)
                    .padding(.vertical, 4)
                    .accessibilityHidden(true)
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
            withAnimation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring) {
                selection = item
            }
        } label: {
            HStack(spacing: DesignTokens.Spacing.md) {
                if !isCollapsed {
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(isSelected ? Color.Mystic.brassGoldPrimary : Color.clear)
                        .frame(width: 3, height: 16)
                        .shadow(
                            color: isSelected ? Color.Mystic.brassGoldPrimary.opacity(0.55) : .clear,
                            radius: 4
                        )
                }

                ZStack(alignment: .topTrailing) {
                    WOMIcon(source: item.iconSource, size: .standard)
                        .foregroundStyle(
                            isSelected
                                ? Color.Mystic.brassGoldPrimary
                                : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
                        )
                        .frame(width: 20, height: 20)

                    if isCollapsed && count > 0 {
                        Circle()
                            .fill(Color.Mystic.crimsonStar)
                            .frame(width: 6, height: 6)
                            .offset(x: 4, y: -2)
                            .shadow(color: Color.Mystic.crimsonGlow, radius: 3)
                            .accessibilityHidden(true)
                    }
                }

                if !isCollapsed {
                    Text(item.localizedTitle)
                        .font(Font.Mystic.bodyMedium)
                        .fontWeight(isSelected ? .semibold : .regular)
                        .foregroundStyle(
                            isSelected
                                ? Color.Mystic.textPrimary
                                : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
                        )

                    Spacer()

                    if count > 0 {
                        Text("\(count)")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundStyle(Color.white)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Capsule().fill(Color.Mystic.crimsonStar.opacity(0.84)))
                            .shadow(color: Color.Mystic.crimsonGlow, radius: 3)
                    }

                    Text("⌘\(item.shortcutNumber)")
                        .font(.system(size: 10, weight: .regular, design: .monospaced))
                        .foregroundStyle(
                            isSelected
                                ? Color.Mystic.brassGoldMuted
                                : Color.Mystic.textTertiary.opacity(0.6)
                        )
                }
            }
            .padding(.horizontal, isCollapsed ? 12 : DesignTokens.Spacing.sm)
            .padding(.vertical, DesignTokens.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: isCollapsed ? .center : .leading)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.sm, style: .continuous)
                    .fill(
                        isSelected
                            ? Color.Mystic.obsidianCard
                            : (isHovered ? Color.Mystic.obsidianCard.opacity(0.55) : Color.clear)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm, style: .continuous)
                            .stroke(
                                isSelected
                                    ? Color.Mystic.brassGoldBorder.opacity(0.72)
                                    : (isHovered ? Color.Mystic.brassGoldBorder.opacity(0.28) : Color.clear),
                                lineWidth: DesignTokens.Borders.hairline
                            )
                    )
            )
        }
        .buttonStyle(MysticPressableButtonStyle(scale: 0.99, pressedOpacity: 0.92))
        .onHover { hovering in
            hoveredItem = hovering ? item : nil
        }
        .accessibilityLabel(item.localizedTitle)
        .accessibilityValue(count > 0 ? "\(count) 个未处理项目" : "")
        .help("\(item.localizedTitle) (⌘\(item.shortcutNumber))")
    }

    // MARK: - Footer Status Card

    @ViewBuilder
    private var footerStatusCard: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            WOMDividerOrnament(opacity: 0.34)
                .padding(.horizontal, DesignTokens.Spacing.sm)

            if !isCollapsed {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: DesignTokens.Spacing.sm) {
                        portrait

                        VStack(alignment: .leading, spacing: 1) {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(Color.Mystic.statusOnline)
                                    .frame(width: 5, height: 5)
                                    .shadow(color: Color.Mystic.statusOnline.opacity(0.72), radius: 2)
                                    .accessibilityHidden(true)

                                Text("克莱恩 · 占卜家")
                                    .font(Font.Mystic.caption)
                                    .fontWeight(.medium)
                                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                            }
                        }

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

                    spiritualityMeter
                }
                .padding(.horizontal, DesignTokens.Spacing.md)
                .padding(.vertical, DesignTokens.Spacing.sm)
                .background(
                    WOMPanelBackground(
                        tone: .card,
                        cornerRadius: DesignTokens.Radii.sm,
                        texture: .velvet,
                        textureOpacity: 0.035
                    )
                )
                .padding(.horizontal, DesignTokens.Spacing.sm)
                .padding(.bottom, DesignTokens.Spacing.md)
            } else {
                collapsedPortrait
            }
        }
    }

    private var portrait: some View {
        ZStack {
            Circle()
                .fill(Color.Mystic.obsidianCard)
                .frame(width: 26, height: 26)

            if NSImage(named: "PortraitKlein") != nil {
                Image("PortraitKlein")
                    .resizable()
                    .scaledToFill()
                    .frame(width: 26, height: 26)
                    .clipShape(Circle())
            } else {
                Image(systemName: "person.circle.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
            }

            Circle()
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: 1)
                .frame(width: 26, height: 26)
        }
        .accessibilityLabel("克莱恩·莫雷蒂")
    }

    private var spiritualityMeter: some View {
        VStack(spacing: 3) {
            HStack(spacing: DesignTokens.Spacing.xs) {
                WOMIcon(.spirituality, size: .compact)
                    .foregroundStyle(Color.Mystic.spiritualBlue)

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
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("灵性储备")
        .accessibilityValue("85%")
    }

    private var collapsedPortrait: some View {
        ZStack {
            if NSImage(named: "PortraitKlein") != nil {
                Image("PortraitKlein")
                    .resizable()
                    .scaledToFill()
                    .frame(width: 22, height: 22)
                    .clipShape(Circle())
            }

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
                .offset(x: 10, y: -10)
        }
        .padding(.vertical, DesignTokens.Spacing.sm)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("克莱恩·莫雷蒂，占卜家序列 9，灵性 85%")
        .help("克莱恩·莫雷蒂 (占卜家 Seq 9 · 灵性 85%)")
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
