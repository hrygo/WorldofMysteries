import Foundation
import Testing
@testable import WorldOfMysteriesCore

// MARK: - Fixtures

/// A canonical WAV: 24 kHz mono PCM16, which is what SpeechRail renders and
/// the only shape the playback actor accepts.
private func makeWav(
    pcm: Data,
    sampleRate: Int = 24_000,
    channels: Int = 1,
    bitsPerSample: Int = 16
) -> Data {
    let blockAlign = channels * bitsPerSample / 8
    var out = Data("RIFF".utf8)
    out.append(uint32: UInt32(36 + pcm.count))
    out.append(Data("WAVEfmt ".utf8))
    out.append(uint32: 16)
    out.append(uint16: 1)  // PCM
    out.append(uint16: UInt16(channels))
    out.append(uint32: UInt32(sampleRate))
    out.append(uint32: UInt32(sampleRate * blockAlign))
    out.append(uint16: UInt16(blockAlign))
    out.append(uint16: UInt16(bitsPerSample))
    out.append(Data("data".utf8))
    out.append(uint32: UInt32(pcm.count))
    out.append(pcm)
    return out
}

private extension Data {
    mutating func append(uint16 value: UInt16) {
        append(contentsOf: [UInt8(value & 0xFF), UInt8(value >> 8)])
    }

    mutating func append(uint32 value: UInt32) {
        append(contentsOf: [
            UInt8(value & 0xFF),
            UInt8((value >> 8) & 0xFF),
            UInt8((value >> 16) & 0xFF),
            UInt8((value >> 24) & 0xFF),
        ])
    }
}

// MARK: - Payload digest

@Suite("Voice Foundry command digests")
struct VoiceFoundryCommandDigestTests {
    /// These four digests were produced by the engine's own
    /// `infrastructure/voice_foundry_control.py::_digest`, which is
    /// `sha256(json.dumps(payload, sort_keys=True))` with Python's default
    /// separators. Foundation's encoder emits neither `", "` nor `": "`, so a
    /// client that used it would compute a different digest for every command
    /// and every refusal would arrive as an opaque `command_digest_mismatch`.
    @Test(
        "the canonical form reproduces the digests the engine computes",
        arguments: [
            (
                "{\"candidate_id\": \"vf-task-1:candidate:0\", "
                    + "\"preview_audio_digest\": \"\(String(repeating: "9", count: 64))\"}",
                "b11fb1385b13abc09fdca97a679db8b1cac578901ba6adff45bb4d5f08c92320"
            ),
            (
                """
                {"human_review": {"identity": "pass", "naturalness": "pass", \
                "reference_audio_digest": "\(String(repeating: "9", count: 64))", \
                "validation_audio_digest": "\(String(repeating: "d", count: 64))", \
                "validation_id": "vv_eeeeeeeeeeeeeeeeeeeeeeee"}}
                """,
                "19507f8bce1defcb8017b17224f52829864ff87554153ce0a8aee30388498dff"
            ),
            ("{}", "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
            (
                "{\"reason_code\": \"operator_abandoned\"}",
                "6f7e7386fe371c0c5da34dbff872778704c2fbae98351cf111fcd0c081d18038"
            ),
        ]
    )
    func matchesTheEngine(canonical: String, digest: String) {
        #expect(VoiceFoundryCommandDigest.canonicalJSON(parse(canonical)) == canonical)
        #expect(VoiceFoundryCommandDigest.digest(parse(canonical)) == digest)
    }

    @Test("a review payload digests as the engine will serialize it")
    func reviewPayload() throws {
        let payload = VoiceFoundryReviewPayloadDTO(
            humanReview: VoiceFoundryHumanReviewDTO(
                validationId: "vv_eeeeeeeeeeeeeeeeeeeeeeee",
                referenceAudioDigest: String(repeating: "9", count: 64),
                validationAudioDigest: String(repeating: "d", count: 64),
                identity: "pass",
                naturalness: "pass"
            )
        )
        let command = try VoiceFoundryCommandDTO(
            commandId: "cmd-review",
            taskId: "task-1",
            expectedTaskRevision: 7,
            action: "review",
            payload: payload
        )
        #expect(
            command.payloadDigest
                == "19507f8bce1defcb8017b17224f52829864ff87554153ce0a8aee30388498dff"
        )
    }

    /// A review text can legitimately be non-ASCII. `json.dumps` escapes
    /// anything outside printable ASCII, and an unescaped character here would
    /// change the digest without changing anything a reader could see.
    @Test("non-ASCII text is escaped the way Python escapes it")
    func nonASCII() {
        let value = AnyCodableValue.object([
            "text": .string("格尔golde"),
        ])
        #expect(
            VoiceFoundryCommandDigest.canonicalJSON(value)
                == "{\"text\": \"\\u683c\\u5c14golde\"}"
        )
    }

    private func parse(_ json: String) -> AnyCodableValue {
        .object(
            try! JSONDecoder().decode(
                [String: AnyCodableValue].self,
                from: Data(json.replacingOccurrences(of: "\n", with: "").utf8)
            )
        )
    }
}

// MARK: - WAV decoding

@Suite("WAV decoding for audition playback")
struct WavPcmDecoderTests {
    @Test("a canonical asset yields the samples and their frame count")
    func decodes() throws {
        let pcm = Data([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
        let decoded = try WavPcmDecoder.decode(makeWav(pcm: pcm))
        #expect(decoded.samples == pcm)
        #expect(decoded.frameCount == 4)
        #expect(decoded.sampleRate == 24_000)
        #expect(decoded.channels == 1)
    }

    /// The playback actor runs at 24 kHz. Replaying a 16 kHz file at 24 kHz
    /// produces audio that plays cleanly and is audibly wrong — which is the
    /// one outcome a voice review must never produce.
    @Test("audio at another sample rate is refused, not resampled")
    func refusesOtherSampleRates() {
        #expect(throws: VoiceFoundryClientError.audioNotPlayable) {
            try WavPcmDecoder.decode(
                makeWav(pcm: Data(repeating: 0, count: 64), sampleRate: 16_000)
            )
        }
    }

    @Test("something that is not a RIFF/WAVE file is refused")
    func refusesNonWav() {
        #expect(throws: VoiceFoundryClientError.audioNotPlayable) {
            try WavPcmDecoder.decode(Data("not audio at all".utf8))
        }
    }

    /// A trailing half-frame is a truncated file, not a shorter one. Handing
    /// the fragment to the audio unit would click instead of playing.
    @Test("a truncated final frame is refused")
    func refusesTruncated() {
        #expect(throws: VoiceFoundryClientError.audioNotPlayable) {
            try WavPcmDecoder.decode(makeWav(pcm: Data([0x01, 0x02, 0x03])))
        }
    }

    /// Chunks are word-aligned: an odd-sized chunk carries a pad byte the next
    /// chunk's offset excludes. Ignoring that shifts the data chunk and the
    /// listener hears static.
    @Test("an odd-sized chunk before the data does not shift it")
    func skipsOddSizedChunks() throws {
        let pcm = Data(repeating: 0x2A, count: 32)
        var wav = makeWav(pcm: pcm)
        // Splice a three-byte LIST chunk — plus the pad byte an odd-sized chunk
        // must carry — in front of the data chunk.
        let list = Data("LIST".utf8)
            + Data([0x03, 0x00, 0x00, 0x00])
            + Data([0x41, 0x42, 0x43, 0x00])
        let insertion = wav.startIndex + 36
        wav.insert(contentsOf: list, at: insertion)
        // Fix the RIFF size the splice invalidated.
        let total = UInt32(wav.count - 8)
        wav.replaceSubrange((wav.startIndex + 4)..<(wav.startIndex + 8), with: [
            UInt8(total & 0xFF),
            UInt8((total >> 8) & 0xFF),
            UInt8((total >> 16) & 0xFF),
            UInt8((total >> 24) & 0xFF),
        ])
        #expect(try WavPcmDecoder.decode(wav).samples == pcm)
    }
}

// MARK: - Asset payload

@Suite("Voice Foundry asset payloads")
struct VoiceFoundryAssetResponseTests {
    private func response(base64: String, bytes: Int) -> VoiceFoundryAssetResponseDTO {
        VoiceFoundryAssetResponseDTO(
            schemaVersion: "1.0",
            taskId: "task-1",
            candidateId: "task-1:candidate:0",
            kind: .validation,
            candidateRevision: "vr_" + String(repeating: "c", count: 32),
            validationId: "vv_" + String(repeating: "e", count: 24),
            audioDigest: "9" + String(repeating: "0", count: 63),
            audioBytes: bytes,
            audioBase64: base64
        )
    }

    @Test("the audio decodes to exactly what the engine said it sent")
    func decodes() throws {
        let audio = Data("RIFF----WAVEfake".utf8)
        let decoded = try response(
            base64: audio.base64EncodedString(),
            bytes: audio.count
        ).decodedAudio()
        #expect(decoded == audio)
    }

    /// `audioBytes` is the engine's claim about its own answer. If the decoded
    /// payload disagrees, the answer is not the asset it describes and nothing
    /// downstream may treat it as one.
    @Test("a payload that is not what the engine reported is refused")
    func refusesMismatch() {
        #expect(throws: VoiceFoundryClientError.assetPayloadMismatch) {
            try response(base64: Data("short".utf8).base64EncodedString(), bytes: 999)
                .decodedAudio()
        }
    }

    @Test("a task with several candidates offers nothing to audition")
    func ambiguousTaskHasNoCandidate() {
        let task = VoiceFoundryTaskDTO(
            schemaVersion: "1.0",
            taskId: "task-1",
            requestId: "req-1",
            requestDigest: String(repeating: "a", count: 64),
            scope: VoiceFoundryScopeDTO(
                ownerId: "owner",
                worldId: "world",
                worldlineId: "line",
                presentationIdentity: "narrator",
                phase: "narration",
                locale: "zh-CN"
            ),
            stage: "awaiting_review",
            taskRevision: 3,
            cancelRequested: false,
            operationStatus: "confirmed",
            requiredActions: ["listen_reference", "listen_validation", "review"],
            reasonCode: nil,
            candidates: []
        )
        #expect(task.auditionedCandidate == nil)
    }
}
