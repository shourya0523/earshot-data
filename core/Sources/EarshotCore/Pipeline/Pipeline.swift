import Foundation

/// ASR engine slot. whisper.cpp (EarshotWhisper) is the default; tests use
/// scripted transcribers.
public protocol Transcriber: AnyObject {
    var modelName: String { get }
    /// Transcribe one speech chunk (16 kHz mono float). Times are relative to
    /// the chunk start, in ms.
    func transcribe(_ pcm: [Float], prompt: String?) throws -> [ASRPiece]
}

public struct ASRPiece: Equatable, Sendable {
    public var startMs: Int64
    public var endMs: Int64
    public var text: String
    public var avgLogprob: Double?
    public init(startMs: Int64, endMs: Int64, text: String, avgLogprob: Double? = nil) {
        self.startMs = startMs; self.endMs = endMs; self.text = text; self.avgLogprob = avgLogprob
    }
}

/// Token tagger slot (EMSTagger Core ML model when present).
public struct TaggedSpan: Equatable, Sendable {
    public var label: String       // DRUG DOSE UNIT ROUTE VITAL
    public var start: Int          // clean token index (inclusive)
    public var end: Int            // inclusive
    public init(label: String, start: Int, end: Int) { self.label = label; self.start = start; self.end = end }
}
public protocol TokenTagger: AnyObject {
    var name: String { get }
    func tag(_ tokens: [String]) throws -> [TaggedSpan]
}

public struct PipelineConfig: Codable, Sendable {
    public struct ASR: Codable, Sendable {
        public var engine: String = "whisper.cpp"
        public var model: String? = nil
        public var name: String = "whisper.cpp small.en"
        public var threads: Int = 4
        public var useInitialPrompt: Bool = true
        public init() {}
        enum CodingKeys: String, CodingKey { case engine, model, name, threads, useInitialPrompt = "use_initial_prompt" }
        public init(from d: Decoder) throws {
            let c = try d.container(keyedBy: CodingKeys.self)
            engine = try c.decodeIfPresent(String.self, forKey: .engine) ?? "whisper.cpp"
            model = try c.decodeIfPresent(String.self, forKey: .model)
            name = try c.decodeIfPresent(String.self, forKey: .name) ?? "whisper.cpp small.en"
            threads = try c.decodeIfPresent(Int.self, forKey: .threads) ?? 4
            useInitialPrompt = try c.decodeIfPresent(Bool.self, forKey: .useInitialPrompt) ?? true
        }
    }
    public var callId: String = "c1"
    public var startTime: String = "2026-11-15T14:00:00-05:00"
    public var asr = ASR()
    public var tagger: String? = nil
    public var vad = VADConfig()
    public var merge = MergeConfig()
    public var piiScrub: Bool = true
    public init() {}
    enum CodingKeys: String, CodingKey { case callId = "call_id", startTime = "start_time", asr, tagger, vad, merge, piiScrub = "pii_scrub" }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        callId = try c.decodeIfPresent(String.self, forKey: .callId) ?? "c1"
        startTime = try c.decodeIfPresent(String.self, forKey: .startTime) ?? "2026-11-15T14:00:00-05:00"
        asr = try c.decodeIfPresent(ASR.self, forKey: .asr) ?? ASR()
        tagger = try c.decodeIfPresent(String.self, forKey: .tagger)
        vad = try c.decodeIfPresent(VADConfig.self, forKey: .vad) ?? VADConfig()
        merge = try c.decodeIfPresent(MergeConfig.self, forKey: .merge) ?? MergeConfig()
        piiScrub = try c.decodeIfPresent(Bool.self, forKey: .piiScrub) ?? true
    }
}

public enum PipelineInput {
    /// 16 kHz mono PCM; tap clip_ms are ms from the start of the audio.
    case pcm([Int16], taps: [TapInput])
    /// Replay packets; tap clip_ms (in packets or extra) are clip-boot ms.
    case packets([Packet], extraTaps: [TapInput])
    /// Pre-made raw transcript (skips audio + ASR). Tap clip_ms = call ms.
    case transcript(RawTranscript, taps: [TapInput])
}

public struct PipelineResult {
    public var raw: RawTranscript
    public var clean: CleanTranscript
    public var events: [EarshotEvent]
    public var docs: [RenderedDoc]
    public var timing: [String: Double]
    public var stats: [String: Int]
}

public enum PipelineError: Error, CustomStringConvertible {
    case noTranscriber, badStartTime(String)
    public var description: String {
        switch self {
        case .noTranscriber: return "audio input needs an ASR engine (build with whisper.cpp, or pass --transcript)"
        case .badStartTime(let s): return "bad start_time: \(s)"
        }
    }
}

/// Offline (batch) pipeline used by earshot-eval and tests. Same stages and
/// rendering code as the live app path.
public final class EarshotPipeline {
    public let dict: EMSDictionary
    public let config: PipelineConfig
    public let transcriber: Transcriber?
    public let tagger: TokenTagger?

    public init(dict: EMSDictionary, config: PipelineConfig, transcriber: Transcriber?, tagger: TokenTagger? = nil) {
        self.dict = dict; self.config = config; self.transcriber = transcriber; self.tagger = tagger
    }

    public func run(_ input: PipelineInput) throws -> PipelineResult {
        guard let clock = CallClock(iso: config.startTime) else { throw PipelineError.badStartTime(config.startTime) }
        var timing: [String: Double] = [:]
        var stats: [String: Int] = [:]
        func timed<T>(_ k: String, _ f: () throws -> T) rethrows -> T {
            let t0 = Date(); defer { timing[k, default: 0] += Date().timeIntervalSince(t0) }
            return try f()
        }
        var taps: [PlacedTap] = []
        var gaps: [(Int64, Int64, Int)] = []
        var raw: RawTranscript
        let asrName = transcriber?.modelName ?? config.asr.name

        switch input {
        case .transcript(let t, let tp):
            raw = t
            taps = tp.map { PlacedTap(tMs: $0.clipMs, source: $0.source, gesture: $0.gesture, clipMs: $0.clipMs) }
        case .pcm(let pcm, let tp):
            taps = tp.map { PlacedTap(tMs: $0.clipMs, source: $0.source, gesture: $0.gesture, clipMs: $0.clipMs) }
            raw = try timed("asr_total") { try transcribeAll(pcm, &timing, &stats, asrName) }
        case .packets(let packets, let extra):
            let asm = AudioAssembler(reorderDepth: Int.max)
            var pcm: [Int16] = []
            try timed("decode") {
                for p in packets { pcm += asm.push(p) }
                pcm += asm.finish()
                _ = try Optional(0) // keep closure throwing-compatible
            }
            let base = asm.firstClipMs ?? 0
            for t in asm.taps + extra {
                taps.append(PlacedTap(tMs: t.clipMs - base, source: t.source, gesture: t.gesture, clipMs: t.clipMs))
            }
            gaps = asm.gaps.map { ($0.startClipMs - base, $0.endClipMs - base, $0.missingFrames) }
            stats["frames"] = asm.framesReceived; stats["duplicates"] = asm.duplicates; stats["gaps"] = asm.gaps.count
            raw = try timed("asr_total") { try transcribeAll(pcm, &timing, &stats, asrName) }
            pcm.removeAll() // drop audio as soon as it is transcribed
        }
        raw.callId = config.callId

        // cleanup
        let cleaner = Cleanup(dict: dict)
        var cleanSegs: [CleanSegment] = []
        var corrections: [Correction] = []
        timed("cleanup") {
            for s in raw.segments {
                let (c, k) = cleaner.clean(s); cleanSegs.append(c); corrections += k
            }
        }
        // extraction
        let rules = RulesExtractor(dict: dict)
        var findings: [Finding] = []
        timed("extract_rules") { for c in cleanSegs { findings += rules.extract(c) } }
        if let tg = tagger {
            try timed("extract_tagger") { findings += try TaggerMerge(dict: dict, tagger: tg).findings(cleanSegs, existing: findings) }
        }
        // merge
        let models = ModelInfo(asr: asrName, extract: RulesExtractor.version + (tagger.map { "+" + $0.name } ?? ""))
        let merger = TapMerger(cfg: config.merge, callId: config.callId, clock: clock, models: models)
        var segTimes: [String: (Int64, Int64)] = [:]
        for s in raw.segments { segTimes[s.id] = (s.startMs, s.endMs) }
        var events = timed("merge") { merger.merge(findings: findings, segments: segTimes, taps: taps, gaps: gaps) }
        // PII scrub (quotes and field values; raw transcript stays raw)
        if config.piiScrub {
            timed("pii") {
                let pii = PIIScrubber()
                for s in raw.segments { pii.learn(s.text) }
                events = events.map(pii.scrub)
                stats["pii_tokens"] = pii.vault.count
            }
        }
        // render
        var docs: [RenderedDoc] = []
        timed("render") {
            let m = ChartModel(events: events, callId: config.callId, clock: clock)
            docs = [Renderers.soap(m), Renderers.chart(m), Renderers.imistAmbo(m), NEMSISExport.render(m, events: events, dict: dict)]
        }
        stats["segments"] = raw.segments.count; stats["events"] = events.count; stats["corrections"] = corrections.count
        stats["taps"] = taps.count
        let clean = CleanTranscript(segments: cleanSegs.map { .init(rawSpan: $0.rawSpan, text: $0.text) }, corrections: corrections)
        return PipelineResult(raw: raw, clean: clean, events: events, docs: docs, timing: timing, stats: stats)
    }

    func transcribeAll(_ pcm: [Int16], _ timing: inout [String: Double], _ stats: inout [String: Int], _ asrName: String) throws -> RawTranscript {
        guard let tr = transcriber else { throw PipelineError.noTranscriber }
        let vad = EnergyVAD(config.vad)
        var chunks: [SpeechChunk] = []
        let t0 = Date()
        // feed in 20 ms frames like the live path
        var i = 0
        while i < pcm.count {
            let j = min(pcm.count, i + 320 * 50)
            chunks += vad.push(Array(pcm[i..<j])); i = j
        }
        chunks += vad.finish()
        timing["vad"] = Date().timeIntervalSince(t0)
        stats["speech_chunks"] = chunks.count
        let prompt = config.asr.useInitialPrompt ? dict.initialPrompt() : nil
        var segs: [RawSegment] = []
        var n = 0
        for c in chunks {
            let a = Int(c.startSample), b = Int(min(Int64(pcm.count), c.endSample))
            guard b > a else { continue }
            let f = pcm[a..<b].map { Float($0) / 32768 }
            for p in try tr.transcribe(f, prompt: prompt) {
                let text = p.text.trimmingCharacters(in: .whitespacesAndNewlines)
                if text.isEmpty || ASRFilter.isHallucination(text) { continue }
                n += 1
                segs.append(RawSegment(id: "s\(n)", startMs: c.startMs + p.startMs, endMs: min(c.endMs, c.startMs + p.endMs), text: text, avgLogprob: p.avgLogprob))
            }
        }
        return RawTranscript(callId: config.callId, asrModel: asrName, initialPrompt: prompt, segments: segs)
    }
}

/// Drops well-known Whisper non-speech hallucinations.
public enum ASRFilter {
    static let junk: Set<String> = ["[blank_audio]", "[music]", "(music)", "[silence]", "you", "thank you.", "thanks for watching!",
                                    "[inaudible]", "(inaudible)", "[ sound ]", "[noise]", "(siren)", "[siren]", "."]
    public static func isHallucination(_ s: String) -> Bool {
        let l = s.lowercased().trimmingCharacters(in: .whitespaces)
        if junk.contains(l) { return true }
        if l.hasPrefix("[") && l.hasSuffix("]") { return true }
        if l.hasPrefix("(") && l.hasSuffix(")") { return true }
        return false
    }
}

/// Merges tagger spans into findings. The formulary has the final say on
/// drug names: a DRUG span with no formulary match becomes "heard, please
/// confirm", never a drug.
public struct TaggerMerge {
    let dict: EMSDictionary
    let tagger: TokenTagger
    public init(dict: EMSDictionary, tagger: TokenTagger) { self.dict = dict; self.tagger = tagger }

    public func findings(_ segs: [CleanSegment], existing: [Finding]) throws -> [Finding] {
        var out: [Finding] = []
        let covered = Set(existing.filter { $0.type == .medication || $0.fields["drug"] != nil }.flatMap { f in
            f.receipts.values.map { "\($0.rawSpan):\($0.rawRange?.first ?? -1)" }
        })
        for seg in segs where !seg.tokens.isEmpty {
            let tt = TokText(seg)
            for sp in try tagger.tag(seg.tokens.map(\.text)) where sp.label == "DRUG" {
                guard sp.start >= 0, sp.end < seg.tokens.count, sp.start <= sp.end else { continue }
                let r = sp.start...sp.end
                let key = "\(seg.rawSpan):\(seg.tokens[sp.start].rawStart)"
                if covered.contains(key) { continue }
                let phrase = seg.tokens[r].map(\.text).joined(separator: " ")
                let match = dict.aliasIndex[phrase] ?? dict.variantIndex[phrase] ?? {
                    let ds = dict.phoneticIndex[Phonetic.key(phrase.replacingOccurrences(of: " ", with: ""))] ?? []
                    return ds.count == 1 ? ds[0] : nil
                }()
                if let di = match {
                    out.append(Finding(type: .status, fields: ["kind": "drug_mention", "drug": dict.drug(di).generic, "heard_as": tt.seg.quote(sp.start, sp.end)],
                                       receipts: ["drug": tt.receipt(r)], tMs: seg.timeOf(token: sp.start), rawSpan: seg.rawSpan,
                                       quote: seg.quote(sp.start, sp.end), confidence: 0.6, flags: ["confirm"], extractor: tagger.name))
                } else {
                    out.append(Finding(type: .status, fields: ["kind": "drug_mention", "heard_as": tt.seg.quote(sp.start, sp.end), "note": "heard, please confirm — not in formulary"],
                                       receipts: ["heard_as": tt.receipt(r)], tMs: seg.timeOf(token: sp.start), rawSpan: seg.rawSpan,
                                       quote: seg.quote(sp.start, sp.end), confidence: 0.4, flags: ["confirm"], extractor: tagger.name))
                }
            }
        }
        return out
    }
}
