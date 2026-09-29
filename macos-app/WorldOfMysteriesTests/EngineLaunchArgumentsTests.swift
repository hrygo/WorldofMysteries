import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Engine launch arguments")
struct EngineLaunchArgumentsTests {
    private func arguments(
        durablePostCommit: Bool = true,
        dataRoot: String? = "/tmp/wom-data",
        voiceId: String? = "voice-1"
    ) -> [String] {
        EngineLaunchConfiguration.engineArguments(
            socketPath: "/tmp/wom-ws/s",
            parentProcessIdentifier: 4242,
            dataRoot: dataRoot,
            voiceId: voiceId,
            durablePostCommit: durablePostCommit
        )
    }

    @Test("The production launch opts into durable post-COMMIT work")
    func durableOptIn() {
        let args = arguments()
        #expect(args.contains("--durable-post-commit"))
    }

    @Test("Durable opt-in survives an absent data root and voice binding")
    func durableOptInWithoutOptionalFlags() {
        let args = arguments(dataRoot: nil, voiceId: nil)
        #expect(args.contains("--durable-post-commit"))
        #expect(!args.contains("--data-root"))
        #expect(!args.contains("--voice-id"))
    }

    @Test("Opting out is explicit and never silent")
    func durableOptOut() {
        #expect(!arguments(durablePostCommit: false).contains("--durable-post-commit"))
    }

    @Test("The transport identity and entrypoint are unchanged by the opt-in")
    func transportIdentityPreserved() {
        let args = arguments()
        #expect(args.first == "-E")
        #expect(args.contains("-m"))
        #expect(args.contains("infrastructure.ipc_server"))
        #expect(args.contains("--socket"))
        #expect(args.contains("--token-fd"))
        #expect(args.contains("4242"))
    }

    @Test("A configuration built for production requests durable post-COMMIT work")
    func configurationDefaultsToDurable() {
        let configuration = EngineLaunchConfiguration(
            executableURL: URL(fileURLWithPath: "/tmp/wom/python3"),
            moduleDirectory: URL(fileURLWithPath: "/tmp/wom/engine", isDirectory: true)
        )
        #expect(configuration.durablePostCommit)
        #expect(
            EngineLaunchConfiguration(
                executableURL: URL(fileURLWithPath: "/tmp/wom/python3"),
                moduleDirectory: URL(fileURLWithPath: "/tmp/wom/engine", isDirectory: true),
                durablePostCommit: false
            ).durablePostCommit == false
        )
    }
}
