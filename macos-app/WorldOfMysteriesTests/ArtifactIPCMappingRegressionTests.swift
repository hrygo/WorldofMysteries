import Testing

@testable import WorldOfMysteriesCore

@Suite("Artifact IPC Mapping Regressions")
struct ArtifactIPCMappingRegressionTests {
  @Test("Creeping Hunger actions remain represented by the stable IPC mapping")
  func creepingHungerMappings() {
    #expect(
      ArtifactIPCMethod.method(for: .creepingHunger, action: .graze)
        == "artifact.creeping_hunger.graze")
    #expect(
      ArtifactIPCMethod.method(for: .creepingHunger, action: .invokeSoul)
        == "artifact.creeping_hunger.invoke_soul")
  }

  @Test("Probability die model keeps CoreGraphics throw-vector defaults typechecked")
  @MainActor
  func probabilityDieThrowVectorDefault() async {
    let context = ArtifactContext(worldID: "world", worldlineID: "main", storyRevision: 1)
    let model = ProbabilityDieModel(resolver: PreviewProbabilityDieResolver())

    await model.roll(context: context, stakes: .guarded)

    #expect(model.throwVector.width == 0)
    #expect(model.throwVector.height == 0)
  }
}
