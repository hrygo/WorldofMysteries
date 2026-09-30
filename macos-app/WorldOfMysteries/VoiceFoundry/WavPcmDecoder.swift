import Foundation

/// Turns a provider WAV into the raw PCM the playback actor already speaks.
///
/// The playback path is fixed at 24 kHz mono PCM16 — that is what
/// `AVAudioEnginePCMPlaybackBackend` runs, and it is what SpeechRail renders.
/// Anything else is refused rather than resampled or reinterpreted: silently
/// playing a 16 kHz file at 24 kHz produces audio that plays perfectly and is
/// audibly wrong, which is the one outcome a voice review must never produce.
public nonisolated enum WavPcmDecoder {
    public static let expectedSampleRate = 24_000
    public static let expectedChannels = 1
    public static let expectedBitsPerSample = 16

    public struct Pcm: Equatable {
        public let samples: Data
        public let frameCount: Int
        public let sampleRate: Int
        public let channels: Int
    }

    public static func decode(_ data: Data) throws -> Pcm {
        let bytes = [UInt8](data)
        guard bytes.count >= 12,
              bytes[0] == 0x52, bytes[1] == 0x49, bytes[2] == 0x46, bytes[3] == 0x46,
              bytes[8] == 0x57, bytes[9] == 0x41, bytes[10] == 0x56, bytes[11] == 0x45
        else {
            throw VoiceFoundryClientError.audioNotPlayable
        }

        var format: (channels: Int, sampleRate: Int, bits: Int)?
        var payload: Range<Int>?
        var cursor = 12
        // Chunks are word-aligned: an odd-sized one carries a pad byte the
        // next chunk's offset does not include. Walking with that rule is what
        // keeps a LIST or fact chunk from shifting the data chunk's start.
        while cursor + 8 <= bytes.count {
            let id = String(bytes: bytes[cursor ..< cursor + 4], encoding: .ascii) ?? ""
            let size = Int(readUInt32(bytes, cursor + 4))
            let body = cursor + 8
            guard body + size <= bytes.count else { break }
            switch id {
            case "fmt " where size >= 16:
                format = (
                    channels: Int(readUInt16(bytes, body + 2)),
                    sampleRate: Int(readUInt32(bytes, body + 4)),
                    bits: Int(readUInt16(bytes, body + 14))
                )
            case "data":
                payload = body ..< (body + size)
            default:
                break
            }
            cursor = body + size + (size % 2)
        }

        guard let format, let payload,
              format.channels == expectedChannels,
              format.bits == expectedBitsPerSample,
              format.sampleRate == expectedSampleRate
        else {
            throw VoiceFoundryClientError.audioNotPlayable
        }
        // A trailing half-frame is a truncated file, not a shorter one.
        let length = payload.upperBound - payload.lowerBound
        guard length % (expectedChannels * expectedBitsPerSample / 8) == 0 else {
            throw VoiceFoundryClientError.audioNotPlayable
        }
        return Pcm(
            samples: data.subdata(in: payload),
            frameCount: length / (expectedChannels * expectedBitsPerSample / 8),
            sampleRate: format.sampleRate,
            channels: format.channels
        )
    }

    private static func readUInt16(_ bytes: [UInt8], _ offset: Int) -> UInt16 {
        (UInt16(bytes[offset]) | UInt16(bytes[offset + 1]) << 8)
    }

    private static func readUInt32(_ bytes: [UInt8], _ offset: Int) -> UInt32 {
        UInt32(bytes[offset])
            | UInt32(bytes[offset + 1]) << 8
            | UInt32(bytes[offset + 2]) << 16
            | UInt32(bytes[offset + 3]) << 24
    }
}
