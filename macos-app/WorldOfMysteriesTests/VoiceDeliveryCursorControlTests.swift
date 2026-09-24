import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Voice delivery cursor IPC DTOs")
struct VoiceDeliveryCursorControlTests {
    @Test("Cursor response preserves evidence strength without inventing fully-output")
    func cursorRoundTrip() throws {
        let data = Data(#"""
        {
          "schema_version":"1.0",
          "cursor":{
            "track_id":"track-1",
            "consumer_id":"local-playback",
            "unit_id":"speech-1",
            "generation":3,
            "source_offset_frames":100,
            "total_source_frames":100,
            "evidence":"rendered_estimate",
            "stop_reason":"completed",
            "cursor_revision":2,
            "fully_output":false
          }
        }
        """#.utf8)
        let response = try JSONDecoder().decode(
            VoiceDeliveryCursorResponseDTO.self,
            from: data
        )
        let cursor = try #require(response.cursor)
        #expect(response.schemaVersion == "1.0")
        #expect(cursor.evidence == .renderedEstimate)
        #expect(cursor.stopReason == .completed)
        #expect(!cursor.fullyOutput)
        #expect(cursor.sourceOffsetFrames == cursor.totalSourceFrames)
    }

    @Test("Update request uses explicit CAS revision and nullable total/stop")
    func updateRoundTrip() throws {
        let request = VoiceDeliveryCursorUpdateDTO(
            trackId: "track-1",
            consumerId: "local-playback",
            unitId: "speech-1",
            generation: 4,
            sourceOffsetFrames: 0,
            totalSourceFrames: nil,
            evidence: .queued,
            stopReason: nil,
            expectedCursorRevision: 2
        )
        let encoded = try JSONEncoder().encode(request)
        let decoded = try JSONDecoder().decode(
            VoiceDeliveryCursorUpdateDTO.self,
            from: encoded
        )
        #expect(decoded == request)
        #expect(decoded.schemaVersion == "1.0")
        #expect(decoded.operation == "update")
        #expect(decoded.expectedCursorRevision == 2)
    }
}
