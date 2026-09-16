import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "shield.lefthalf.filled")
                .imageScale(.large)
                .font(.system(size: 56))
                .foregroundStyle(appState.isEngineReady ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))

            VStack(spacing: 8) {
                Text("诡秘世界 (World of Mysteries)")
                    .font(.title)
                    .fontWeight(.bold)

                Text("Persistent Single-Player World Engine")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }

            HStack(spacing: 8) {
                Circle()
                    .fill(appState.isEngineReady ? Color.green : Color.orange)
                    .frame(width: 8, height: 8)

                Text(appState.isEngineReady ? "本地引擎已就绪 (Local Engine Ready)" : "正在启动并握手本地引擎...")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            if let error = appState.connectionError {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)

                Button("重试连接") {
                    Task {
                        await appState.startAndConnect()
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(48)
        .frame(minWidth: 540, minHeight: 380)
        .task {
            if !appState.isEngineReady {
                await appState.startAndConnect()
            }
        }
    }
}

#Preview {
    ContentView()
        .environment(AppState())
}

