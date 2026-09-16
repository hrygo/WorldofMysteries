import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "shield.lefthalf.filled")
                .imageScale(.large)
                .font(.system(size: 48))
                .foregroundStyle(.tint)
            Text("诡秘世界 (World of Mysteries)")
                .font(.title)
                .fontWeight(.bold)
            Text(appState.isEngineReady ? "本地引擎已就绪" : "等待本地引擎握手...")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(40)
        .frame(minWidth: 500, minHeight: 350)
    }
}

#Preview {
    ContentView()
        .environment(AppState())
}
