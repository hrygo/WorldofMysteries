import Testing
import Foundation
import SwiftUI
import AppKit
@testable import WorldOfMysteriesCore

// 临时离屏渲染探针：仅用于人工核对视觉构图，核对完成后移除。
@Suite("Render Probe")
struct RenderProbe {
    @Test("Render citrine artwork and scrying card to PNG")
    @MainActor
    func renderProbe() throws {
        guard let image = NSImage(contentsOfFile: "/tmp/probe_art.jpg") else {
            Issue.record("probe artwork missing")
            return
        }
        
        try render(
            CitrinePendulumArtwork(swingAngle: 0, artworkImage: image).frame(width: 156, height: 310),
            to: "/tmp/probe_0.png",
            size: CGSize(width: 156, height: 310)
        )
        try render(
            CitrinePendulumArtwork(swingAngle: 6, artworkImage: image).frame(width: 156, height: 310),
            to: "/tmp/probe_pos.png",
            size: CGSize(width: 156, height: 310)
        )
        try render(
            CitrinePendulumArtwork(swingAngle: -6, artworkImage: image).frame(width: 156, height: 310),
            to: "/tmp/probe_neg.png",
            size: CGSize(width: 156, height: 310)
        )
        try render(
            CitrinePendulumScryingCard().frame(width: 580).padding(DesignTokens.Spacing.lg),
            to: "/tmp/probe_card.png",
            size: CGSize(width: 612, height: 420)
        )
    }
    
    @MainActor
    private func render(_ view: some View, to path: String, size: CGSize) throws {
        let renderer = ImageRenderer(
            content: view
                .frame(width: size.width, height: size.height, alignment: .top)
                .background(Color.Mystic.obsidianBase)
        )
        renderer.scale = 2
        guard let cgImage = renderer.cgImage else {
            Issue.record("render failed for \(path)")
            return
        }
        let rep = NSBitmapImageRep(cgImage: cgImage)
        guard let data = rep.representation(using: .png, properties: [:]) else {
            Issue.record("encode failed for \(path)")
            return
        }
        try data.write(to: URL(fileURLWithPath: path))
    }
}
