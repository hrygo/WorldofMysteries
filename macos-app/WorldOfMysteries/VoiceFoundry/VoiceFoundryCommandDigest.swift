import CryptoKit
import Foundation

/// The digest a Voice Foundry command quotes about its own payload.
///
/// The engine recomputes it and refuses the command when the two disagree, so
/// these two implementations have to agree byte for byte. The engine uses
/// `json.dumps(payload, sort_keys=True)` with Python's default separators —
/// `", "` between entries and `": "` between key and value — and Foundation's
/// encoder emits neither. The canonical form is therefore written out by hand
/// and pinned against vectors produced by the engine itself.
///
/// Only the value domain the control surface accepts is supported. Anything
/// else traps rather than inventing a serialization the engine would read
/// differently, because a digest that is merely *wrong* here fails as an
/// opaque `command_digest_mismatch` at the far end of a socket.
public nonisolated enum VoiceFoundryCommandDigest {
    /// Serialize one payload the way the engine will serialize it.
    public static func canonicalJSON(_ value: AnyCodableValue) -> String {
        var out = ""
        write(value, into: &out)
        return out
    }

    /// The SHA-256 of the canonical form, lowercase hex.
    public static func digest(_ value: AnyCodableValue) -> String {
        SHA256.hash(data: Data(canonicalJSON(value).utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }

    /// The digest of an `Encodable` payload, via the same value model the
    /// envelope carries.
    public static func digest<Payload: Encodable>(_ payload: Payload) throws -> String {
        let data = try JSONEncoder().encode(payload)
        return digest(try JSONDecoder().decode(AnyCodableValue.self, from: data))
    }

    private static func write(_ value: AnyCodableValue, into out: inout String) {
        switch value {
        case .null:
            out += "null"
        case .bool(let b):
            out += b ? "true" : "false"
        case .int(let i):
            out += String(i)
        case .double:
            // The control surface accepts no floats, so a double here means a
            // payload was built wrong. Guessing at Python's repr would produce
            // a digest that mismatches for reasons nobody could see.
            preconditionFailure("Voice Foundry command payloads carry no floating-point values")
        case .string(let s):
            writeString(s, into: &out)
        case .array(let items):
            out += "["
            for (index, item) in items.enumerated() {
                if index > 0 { out += ", " }
                write(item, into: &out)
            }
            out += "]"
        case .object(let members):
            out += "{"
            // Sorted by key, byte-wise, because that is what sort_keys=True
            // does — and the digest is over this text, not over a map.
            for (index, key) in members.keys.sorted().enumerated() {
                if index > 0 { out += ", " }
                writeString(key, into: &out)
                out += ": "
                write(members[key]!, into: &out)
            }
            out += "}"
        }
    }

    /// JSON string escaping, matching `json.dumps` with its default
    /// `ensure_ascii=True`: anything outside printable ASCII becomes a `\uXXXX`
    /// escape. A review payload can legitimately carry non-ASCII text, and an
    /// escape difference here is a digest mismatch nobody would ever trace back
    /// to this function.
    private static func writeString(_ value: String, into out: inout String) {
        out += "\""
        for scalar in value.unicodeScalars {
            switch scalar {
            case "\"": out += "\\\""
            case "\\": out += "\\\\"
            case "\n": out += "\\n"
            case "\r": out += "\\r"
            case "\t": out += "\\t"
            default:
                if scalar.value < 0x20 || scalar.value > 0x7E {
                    out += String(format: "\\u%04x", scalar.value)
                } else {
                    out.unicodeScalars.append(scalar)
                }
            }
        }
        out += "\""
    }
}
