import SwiftUI

/// Canon 神器展览独立分组，便于重型 Artifact 预览按需懒加载。
struct ComponentGalleryArtifactGroup: View {
    var body: some View {
        ComponentGallerySection(title: "13 · 神器展览 (Artifact Vault)") {
            ArtifactShowcaseView()
        }
    }
}
