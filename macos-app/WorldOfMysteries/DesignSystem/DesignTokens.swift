import SwiftUI

// MARK: - DesignTokens Namespace

/// 《诡秘世界》跨端同源设计 Token 语言体系 (Single Source of Truth)
/// 严格对齐 `docs/05_UI/design_tokens.json`
public enum DesignTokens: Sendable {
    
    // MARK: - Spacing Grid (4pt / 8pt 阶梯)
    public enum Spacing: Sendable {
        public static let xxs: CGFloat = 2
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        public static let xl: CGFloat = 24
        public static let xxl: CGFloat = 32
        public static let xxxl: CGFloat = 48
    }
    
    // MARK: - Radii (同心圆角推导)
    public enum Radii: Sendable {
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        public static let xl: CGFloat = 24
        public static let full: CGFloat = 9999
        
        /// 同心圆角几何推导：R_child = max(R_parent - padding, 0)
        public static func concentric(parent: CGFloat, padding: CGFloat) -> CGFloat {
            max(parent - padding, 0)
        }
    }
    
    // MARK: - Borders
    public enum Borders: Sendable {
        public static let hairline: CGFloat = 0.5
        public static let standard: CGFloat = 1.0
        public static let chamfer: CGFloat = 1.5
        public static let heavy: CGFloat = 2.0
    }
    
    // MARK: - Motion
    public enum Motion: Sendable {
        public static let listeningPulseDuration: Double = 2.4
        public static let voiceWaveformResponse: Double = 0.12
        public static let stateTransitionDuration: Double = 0.35
        public static let pendulumSwingPeriod: Double = 3.2
        
        public static var smoothSpring: Animation {
            .spring(response: 0.35, dampingFraction: 0.82)
        }
        
        public static var listeningBreathing: Animation {
            .easeInOut(duration: listeningPulseDuration).repeatForever(autoreverses: true)
        }
    }
}

// MARK: - Color Tokens Extension

public extension Color {
    enum Mystic: Sendable {
        // Backgrounds
        public static let obsidianBase = Color(red: 13/255, green: 15/255, blue: 18/255)       // #0D0F12
        public static let obsidianElevated = Color(red: 20/255, green: 24/255, blue: 29/255)   // #14181D
        public static let obsidianCard = Color(red: 27/255, green: 32/255, blue: 38/255)       // #1B2026
        public static let obsidianGlass = Color(red: 20/255, green: 24/255, blue: 29/255).opacity(0.8)
        
        // Victorian Brass & Gold
        public static let brassGoldPrimary = Color(red: 197/255, green: 160/255, blue: 89/255) // #C5A059
        public static let brassGoldHover = Color(red: 212/255, green: 178/255, blue: 111/255) // #D4B26F
        public static let brassGoldMuted = Color(red: 140/255, green: 115/255, blue: 62/255)  // #8C733E
        public static let brassGoldBorder = Color(red: 74/255, green: 62/255, blue: 37/255)   // #4A3E25
        public static let brassGoldGlow = Color(red: 197/255, green: 160/255, blue: 89/255).opacity(0.3)
        
        // Spirituality & Void
        public static let spiritualBlue = Color(red: 74/255, green: 144/255, blue: 226/255)   // #4A90E2
        public static let spiritualGlow = Color(red: 100/255, green: 181/255, blue: 246/255).opacity(0.4)
        public static let deepVoid = Color(red: 29/255, green: 53/255, blue: 87/255)          // #1D3557
        
        // Crimson Astral & Threads
        public static let crimsonStar = Color(red: 230/255, green: 57/255, blue: 70/255)       // #E63946
        public static let crimsonThread = Color(red: 183/255, green: 28/255, blue: 28/255)    // #B71C1C
        public static let crimsonGlow = Color(red: 230/255, green: 57/255, blue: 70/255).opacity(0.4)
        
        // Parchment & Ink
        public static let parchmentBase = Color(red: 234/255, green: 219/255, blue: 182/255)   // #EADBB6
        public static let parchmentCard = Color(red: 244/255, green: 235/255, blue: 208/255)   // #F4EBD0
        public static let parchmentBorder = Color(red: 200/255, green: 178/255, blue: 130/255) // #C8B282
        public static let parchmentInk = Color(red: 43/255, green: 33/255, blue: 24/255)       // #2B2118
        
        // Text
        public static let textPrimary = Color(red: 243/255, green: 244/255, blue: 246/255)     // #F3F4F6
        public static let textSecondary = Color(red: 156/255, green: 163/255, blue: 175/255)  // #9CA3AF
        public static let textTertiary = Color(red: 107/255, green: 114/255, blue: 128/255)   // #6B7280
        public static let textGoldAccent = Color(red: 226/255, green: 196/255, blue: 133/255) // #E2C485
        
        // Status Indicators
        public static let statusOnline = Color(red: 46/255, green: 196/255, blue: 182/255)     // #2EC4B6
        public static let statusWarning = Color(red: 255/255, green: 159/255, blue: 28/255)    // #FF9F1C
        public static let statusDanger = Color(red: 231/255, green: 29/255, blue: 54/255)      // #E71D36
        public static let statusImmutable = Color(red: 72/255, green: 149/255, blue: 239/255)  // #4895EF
    }
}

// MARK: - Typography Extension

public extension Font {
    enum Mystic: Sendable {
        public static let displayLarge = Font.system(size: 28, weight: .bold, design: .default)
        public static let titleMedium = Font.system(size: 18, weight: .semibold, design: .default)
        public static let titleSmall = Font.system(size: 15, weight: .semibold, design: .default)
        public static let bodyLarge = Font.system(size: 14, weight: .regular, design: .default)
        public static let bodyMedium = Font.system(size: 13, weight: .regular, design: .default)
        public static let caption = Font.system(size: 11, weight: .medium, design: .default)
        public static let monoBadge = Font.system(size: 11, weight: .medium, design: .monospaced)
        public static let parchmentCursive = Font.system(size: 13, weight: .regular, design: .serif)
    }
}
