import Foundation

/// In-memory PCM ring buffer (16 kHz mono Int16). Never touches disk.
public final class PCMRingBuffer {
    private var buf: [Int16]
    private var start = 0         // index of oldest sample in buf
    private var count = 0
    /// Absolute sample index of the oldest held sample.
    public private(set) var baseSample: Int64 = 0
    public init(capacitySeconds: Int = 60) {
        buf = [Int16](repeating: 0, count: capacitySeconds * Wire.sampleRate)
    }
    public var capacity: Int { buf.count }
    public var endSample: Int64 { baseSample + Int64(count) }

    public func append(_ pcm: [Int16]) {
        for x in pcm {
            if count == buf.count { start = (start + 1) % buf.count; count -= 1; baseSample += 1 }
            buf[(start + count) % buf.count] = x
            count += 1
        }
    }
    /// Copy samples [from, to) (absolute indices). Clamped to what is held.
    public func read(from: Int64, to: Int64) -> [Int16] {
        let a = max(from, baseSample), b = min(to, endSample)
        guard b > a else { return [] }
        var out = [Int16](); out.reserveCapacity(Int(b - a))
        for k in a..<b { out.append(buf[(start + Int(k - baseSample)) % buf.count]) }
        return out
    }
    /// Drop everything before `sample` (free audio once transcribed).
    public func discard(before sample: Int64) {
        let n = Int(min(max(0, sample - baseSample), Int64(count)))
        for k in 0..<n { buf[(start + k) % buf.count] = 0 }
        start = (start + n) % buf.count; count -= n; baseSample += Int64(n)
    }
    /// Zero and drop everything (stop / sign).
    public func wipe() {
        for i in buf.indices { buf[i] = 0 }
        baseSample = endSample; start = 0; count = 0
    }
}

/// A finished speech segment, in samples relative to call start.
public struct SpeechChunk: Equatable, Sendable {
    public var startSample: Int64
    public var endSample: Int64
    public var startMs: Int64 { startSample * 1000 / Int64(Wire.sampleRate) }
    public var endMs: Int64 { endSample * 1000 / Int64(Wire.sampleRate) }
}

public struct VADConfig: Codable, Equatable, Sendable {
    public var frameMs: Int = 20
    public var startRatio: Double = 3.0       // speech if rms > floor * ratio
    public var minRMS: Double = 250           // absolute floor (Int16 units)
    public var hangoverMs: Int = 500
    public var minSpeechMs: Int = 250
    public var maxSegmentMs: Int = 15000
    public var preRollMs: Int = 200
    public init() {}
}

/// Energy-based VAD with an adaptive noise floor. Streaming: feed PCM, get
/// finished chunks. Deterministic for a given input.
public final class EnergyVAD {
    public let cfg: VADConfig
    private var floor: Double = 200
    private var inSpeech = false
    private var segStart: Int64 = 0
    private var lastVoice: Int64 = 0
    private var voicedMs = 0
    private var pos: Int64 = 0
    private var carry: [Int16] = []
    public init(_ cfg: VADConfig = VADConfig()) { self.cfg = cfg }

    var frameLen: Int { cfg.frameMs * Wire.sampleRate / 1000 }

    public func push(_ pcm: [Int16]) -> [SpeechChunk] {
        var out: [SpeechChunk] = []
        carry.append(contentsOf: pcm)
        var i = 0
        let fl = frameLen
        while i + fl <= carry.count {
            var acc = 0.0
            for k in i..<(i + fl) { let v = Double(carry[k]); acc += v * v }
            let rms = (acc / Double(fl)).squareRoot()
            let frameStart = pos
            pos += Int64(fl)
            let voiced = rms > max(cfg.minRMS, floor * cfg.startRatio)
            if !voiced {
                // adapt floor slowly toward quiet frames
                floor = floor * 0.95 + rms * 0.05
            }
            if voiced {
                if !inSpeech {
                    inSpeech = true
                    segStart = max(0, frameStart - Int64(cfg.preRollMs * Wire.sampleRate / 1000))
                    voicedMs = 0
                }
                lastVoice = pos
                voicedMs += cfg.frameMs
            }
            if inSpeech {
                let silentMs = Int((pos - lastVoice) * 1000 / Int64(Wire.sampleRate))
                let lenMs = Int((pos - segStart) * 1000 / Int64(Wire.sampleRate))
                if silentMs >= cfg.hangoverMs || lenMs >= cfg.maxSegmentMs {
                    if voicedMs >= cfg.minSpeechMs {
                        out.append(SpeechChunk(startSample: segStart, endSample: lenMs >= cfg.maxSegmentMs ? pos : min(pos, lastVoice + Int64(cfg.hangoverMs / 2 * Wire.sampleRate / 1000))))
                    }
                    inSpeech = false
                }
            }
            i += fl
        }
        carry.removeFirst(i)
        return out
    }

    public func finish() -> [SpeechChunk] {
        defer { inSpeech = false }
        if inSpeech && voicedMs >= cfg.minSpeechMs { return [SpeechChunk(startSample: segStart, endSample: pos)] }
        return []
    }
}

/// WAV reader for eval input (16-bit PCM; resamples/downmixes if needed).
public enum WAVReader {
    public enum Err: Error { case notWav, unsupported(String) }
    public static func read(_ url: URL) throws -> [Int16] {
        let d = [UInt8](try Data(contentsOf: url))
        guard d.count > 44, String(bytes: d[0..<4], encoding: .ascii) == "RIFF", String(bytes: d[8..<12], encoding: .ascii) == "WAVE" else { throw Err.notWav }
        var off = 12
        var channels = 1, rate = 16000, bits = 16, fmt = 1
        var pcm: [Int16] = []
        while off + 8 <= d.count {
            let id = String(bytes: d[off..<(off + 4)], encoding: .ascii) ?? ""
            let size = Int(d.readLE(UInt32.self, at: off + 4))
            let body = off + 8
            if id == "fmt " {
                fmt = Int(d.readLE(UInt16.self, at: body))
                channels = Int(d.readLE(UInt16.self, at: body + 2))
                rate = Int(d.readLE(UInt32.self, at: body + 4))
                bits = Int(d.readLE(UInt16.self, at: body + 14))
            } else if id == "data" {
                let end = min(d.count, body + size)
                if fmt == 1 && bits == 16 {
                    var i = body
                    while i + 2 * channels <= end {
                        var acc = 0
                        for c in 0..<channels { acc += Int(Int16(bitPattern: d.readLE(UInt16.self, at: i + 2 * c))) }
                        pcm.append(Int16(acc / channels)); i += 2 * channels
                    }
                } else if fmt == 3 && bits == 32 {
                    var i = body
                    while i + 4 * channels <= end {
                        var acc: Float = 0
                        for c in 0..<channels { acc += Float(bitPattern: d.readLE(UInt32.self, at: i + 4 * c)) }
                        pcm.append(Int16(max(-1, min(1, acc / Float(channels))) * 32767)); i += 4 * channels
                    }
                } else { throw Err.unsupported("fmt=\(fmt) bits=\(bits)") }
            }
            off = body + size + (size & 1)
        }
        if rate != Wire.sampleRate { pcm = resample(pcm, from: rate, to: Wire.sampleRate) }
        return pcm
    }

    /// Linear resampler (good enough for speech -> 16 kHz).
    public static func resample(_ x: [Int16], from: Int, to: Int) -> [Int16] {
        guard from != to, !x.isEmpty else { return x }
        let n = Int(Int64(x.count) * Int64(to) / Int64(from))
        var out = [Int16](repeating: 0, count: n)
        let r = Double(from) / Double(to)
        for i in 0..<n {
            let p = Double(i) * r
            let j = Int(p), f = p - Double(j)
            let a = Double(x[min(j, x.count - 1)]), b = Double(x[min(j + 1, x.count - 1)])
            out[i] = Int16(a + (b - a) * f)
        }
        return out
    }

    /// WAV bytes in memory (tests only; Earshot never writes audio to disk).
    public static func encode(_ pcm: [Int16], rate: Int = 16000) -> [UInt8] {
        var o: [UInt8] = Array("RIFF".utf8)
        o.appendLE(UInt32(36 + pcm.count * 2)); o += Array("WAVEfmt ".utf8)
        o.appendLE(UInt32(16)); o.appendLE(UInt16(1)); o.appendLE(UInt16(1)); o.appendLE(UInt32(rate))
        o.appendLE(UInt32(rate * 2)); o.appendLE(UInt16(2)); o.appendLE(UInt16(16))
        o += Array("data".utf8); o.appendLE(UInt32(pcm.count * 2))
        for s in pcm { o.appendLE(s) }
        return o
    }
}
