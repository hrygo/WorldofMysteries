import AppKit
import Foundation
import SwiftUI
import Testing
@testable import WorldOfMysteriesCore

@Suite("Control State Review")
struct ControlStateReviewTests {
    @Test("Actual button palette remains readable across composited interaction states")
    @MainActor
    func compositedButtonStates() throws {
        let surfaces: [Color] = [.Mystic.obsidianBase, .Mystic.obsidianElevated, .Mystic.obsidianCard, .Mystic.deepVoid]
        var checked = 0
        var enabledMinimum = Double.infinity
        var disabledMinimum = Double.infinity
        for variant in WOMButtonVariant.allCases {
            for enabled in [false, true] {
                for hovered in [false, true] {
                    for pressed in [false, true] {
                        for active in [false, true] {
                            for increased in [false, true] {
                                let palette = WOMButtonPalette(
                                    variant: variant, isEnabled: enabled, isHovered: hovered,
                                    isPressed: pressed, appearsActive: active, increasedContrast: increased
                                )
                                let foreground = try RGBA(palette.foreground)
                                let background = try RGBA(palette.background)
                                for surface in surfaces {
                                    let underlay = try RGBA(surface)
                                    let fill = background.over(underlay)
                                    let ink = foreground.over(fill)
                                    let actualFill = fill.withOpacity(palette.opacity).over(underlay)
                                    let actualInk = ink.withOpacity(palette.opacity).over(underlay)
                                    let ratio = contrast(actualInk, actualFill)
                                    // Disabled controls are exempt from WCAG's text minimum. This
                                    // is our stronger product target: unavailable commands stay legible.
                                    #expect(ratio >= 4.5, "\(variant), enabled=\(enabled), hover=\(hovered), pressed=\(pressed), active=\(active): \(ratio):1")
                                    if enabled { enabledMinimum = min(enabledMinimum, ratio) }
                                    else { disabledMinimum = min(disabledMinimum, ratio) }
                                    checked += 1
                                }
                            }
                        }
                    }
                }
            }
        }
        #expect(checked == 640)
        print("BUTTON_CONTRAST_REVIEW cases=\(checked) enabledMin=\(enabledMinimum) disabledMin=\(disabledMinimum)")
    }

    @Test("Disabled palette ignores hover, press and inactive-window state")
    @MainActor
    func disabledPaletteIsStable() throws {
        for variant in WOMButtonVariant.allCases {
            let resting = WOMButtonPalette(variant: variant, isEnabled: false, isHovered: false,
                isPressed: false, appearsActive: true, increasedContrast: false)
            let staleEvents = WOMButtonPalette(variant: variant, isEnabled: false, isHovered: true,
                isPressed: true, appearsActive: false, increasedContrast: false)
            #expect(try RGBA(resting.foreground) == RGBA(staleEvents.foreground))
            #expect(try RGBA(resting.background) == RGBA(staleEvents.background))
            #expect(resting.opacity == 1 && staleEvents.opacity == 1)
            #expect(try RGBA(resting.foreground) == RGBA(Color.Mystic.textSecondary))
            #expect(try RGBA(resting.background) == RGBA(Color.Mystic.obsidianCard))
        }
    }

    @Test("Disabled high-contrast mode increases label visibility without reviving an action")
    @MainActor
    func disabledHighContrast() throws {
        let palette = WOMButtonPalette(variant: .primary, isEnabled: false, isHovered: true,
            isPressed: true, appearsActive: true, increasedContrast: true)
        #expect(try RGBA(palette.foreground) == RGBA(Color.Mystic.textPrimary))
        #expect(try RGBA(palette.background) == RGBA(Color.Mystic.obsidianCard))
    }

    @Test("All button densities consume the tested palette and clear disabled hover state")
    func paletteWiring() throws {
        let source = try String(contentsOf: appRoot.appendingPathComponent("DesignSystem/WOMButtonStyles.swift"), encoding: .utf8)
        #expect(source.contains(".foregroundStyle(palette.foreground)"))
        #expect(source.contains(".background(shape.fill(palette.background))"))
        #expect(source.contains(".opacity(palette.opacity)"))
        #expect(source.contains("isHovered = isEnabled && hovering"))
        #expect(source.contains(".onChange(of: isEnabled)"))
        #expect(!source.contains(".opacity(isEnabled ? pressedOpacity : 0.48)"))
    }

    @Test("Every typed system and status symbol exists on the target macOS runtime")
    @MainActor
    func symbolsExist() {
        let names = Set(WOMSystemIcon.allCases.map(\.rawValue))
            .union(WOMStatusIcon.allCases.map(\.rawValue))
        for name in names.sorted() {
            #expect(NSImage(systemSymbolName: name, accessibilityDescription: nil) != nil,
                    "Missing native symbol: \(name)")
        }
    }

    private var appRoot: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries")
    }

    private struct RGBA: Equatable {
        let r: Double, g: Double, b: Double, a: Double

        @MainActor
        init(_ color: Color) throws {
            let resolved = try #require(NSColor(color).usingColorSpace(.sRGB))
            r = resolved.redComponent; g = resolved.greenComponent
            b = resolved.blueComponent; a = resolved.alphaComponent
        }

        init(r: Double, g: Double, b: Double, a: Double) {
            self.r = r; self.g = g; self.b = b; self.a = a
        }

        func withOpacity(_ alpha: Double) -> Self { Self(r: r, g: g, b: b, a: a * alpha) }
        func over(_ other: Self) -> Self {
            // Test backdrops and every composited intermediate are opaque.
            Self(r: r * a + other.r * (1 - a), g: g * a + other.g * (1 - a),
                 b: b * a + other.b * (1 - a), a: 1)
        }
        var luminance: Double {
            func linear(_ v: Double) -> Double {
                v <= 0.04045 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4)
            }
            return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
        }
    }

    private func contrast(_ lhs: RGBA, _ rhs: RGBA) -> Double {
        (max(lhs.luminance, rhs.luminance) + 0.05) / (min(lhs.luminance, rhs.luminance) + 0.05)
    }
}
