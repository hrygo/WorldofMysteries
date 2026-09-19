import SwiftUI

/// Canon 特殊物品玩法组件独立分组，便于重型 Artifact 预览按需懒加载。
struct ComponentGalleryArtifactGroup: View {
    var body: some View {
        ComponentGallerySection(title: "13 · 特殊物品玩法组件 (Canon Artifact Gameplay)") {
            ArtifactShowcaseView()
        }
    }
}
