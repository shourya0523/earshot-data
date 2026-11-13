import Foundation

/// A tap placed on the call timeline (call-relative ms).
public struct PlacedTap: Equatable, Sendable {
    public var tMs: Int64
    public var source: String
    public var gesture: String
    public var clipMs: Int64
    public init(tMs: Int64, source: String, gesture: String, clipMs: Int64) {
        self.tMs = tMs; self.source = source; self.gesture = gesture; self.clipMs = clipMs
    }
}

public struct MergeConfig: Codable, Equatable, Sendable {
    public var windowMs: Int64 = 3000        // ± window for labeling a tap
    public var extendedMs: Int64 = 10000     // forward extension when nothing in ± window
    public init() {}
}

/// Turns findings + taps + gaps into the final, ordered event list.
/// Rules (docs/ARCHITECTURE.md#taps):
///  * a tap's time is the event time, even if speech about it comes later;
///  * a tap is labeled by the nearest labelable finding whose speech segment
///    overlaps ±3 s, else (tap, tap+10 s]; one finding labels at most one tap;
///  * two taps are never merged with each other; unlabeled taps stay;
///  * findings that no tap claims become `heard` events.
public struct TapMerger {
    public var cfg: MergeConfig
    public var callId: String
    public var clock: CallClock
    public var models: ModelInfo
    public init(cfg: MergeConfig = MergeConfig(), callId: String, clock: CallClock, models: ModelInfo) {
        self.cfg = cfg; self.callId = callId; self.clock = clock; self.models = models
    }

    static let labelable: Set<EventType> = [.vitals, .medication, .procedure, .status]
    static let labelableStatusKinds: Set<String> = ["condition", "symptom", "drug_mention", "med_not_given", "not_done", "prior_to_arrival_med"]
    static let typePriority: [EventType: Int] = [.medication: 0, .procedure: 1, .vitals: 2, .status: 3]

    func isLabelable(_ f: Finding) -> Bool {
        guard TapMerger.labelable.contains(f.type) else { return false }
        if f.type == .status { return TapMerger.labelableStatusKinds.contains(f.fields["kind"] ?? "") }
        return true
    }

    public func merge(findings: [Finding], segments: [String: (Int64, Int64)], taps: [PlacedTap], gaps: [(Int64, Int64, Int)],
                      extra: [EarshotEvent] = []) -> [EarshotEvent] {
        var out: [EarshotEvent] = []
        var claimed = Set<Int>()
        let sortedTaps = taps.sorted { ($0.tMs, $0.source) < ($1.tMs, $1.source) }
        func dist(_ f: Finding, _ t: Int64) -> Int64 {
            let (s, e) = segments[f.rawSpan] ?? (f.tMs, f.tMs)
            if t >= s && t <= e { return 0 }
            return t < s ? s - t : t - e
        }
        var arrivalFromTablet = extra.contains { $0.type == .arrival }
        for tap in sortedTaps {
            switch tap.gesture {
            case "yes", "no":
                out.append(make(.consent, tap.tMs, ["consent": tap.gesture == "yes" ? "yes" : "no (refused, nothing recorded)"],
                                .tap, nil, nil, 1.0, tap: tap))
                continue
            case "arrival":
                out.append(make(.arrival, tap.tMs, ["method": "tap", "nemsis": "eTimes.11"], .tablet, nil, nil, 1.0, tap: tap))
                arrivalFromTablet = true
                continue
            case "handoff":
                out.append(make(.handoff, tap.tMs, ["method": "nurse accept", "nemsis": "eTimes.12"], .tablet, nil, nil, 1.0, tap: tap))
                continue
            case "start", "stop":
                continue
            default: break
            }
            // mark: find nearest labelable finding
            var best: (Int, Int64, Int)? = nil
            for (i, f) in findings.enumerated() where !claimed.contains(i) && isLabelable(f) {
                let d = dist(f, tap.tMs)
                let inWindow = d <= cfg.windowMs
                let inExtended = !inWindow && (segments[f.rawSpan]?.0 ?? f.tMs) > tap.tMs && d <= cfg.extendedMs
                guard inWindow || inExtended else { continue }
                // in-window candidates always beat extended ones
                let score = inWindow ? d : cfg.windowMs + d
                let pri = TapMerger.typePriority[f.type] ?? 9
                if best == nil || score < best!.1 || (score == best!.1 && pri < best!.2) { best = (i, score, pri) }
            }
            if let (i, _, _) = best {
                claimed.insert(i)
                let f = findings[i]
                var e = make(f.type, tap.tMs, f.fields, .tapHeard, f.quote, f.rawSpan, f.confidence, tap: tap, receipts: f.receipts,
                             flags: f.flags, extractor: f.extractor)
                e.fields["heard_at"] = clock.clock(f.tMs)
                out.append(e)
            } else {
                out.append(make(.tap, tap.tMs, ["label": "no label"], .tap, nil, nil, 1.0, tap: tap, flags: ["unlabeled"]))
            }
        }
        var arrivalHeardUsed = arrivalFromTablet
        for (i, f) in findings.enumerated() where !claimed.contains(i) {
            if f.type == .transport && f.fields["kind"] == "arrived_heard" && !arrivalHeardUsed {
                arrivalHeardUsed = true
                var flds = ["method": "heard", "nemsis": "eTimes.11"]
                if let d = f.fields["destination"] { flds["destination"] = d }
                out.append(make(.arrival, f.tMs, flds, .heard, f.quote, f.rawSpan, f.confidence, receipts: f.receipts, flags: ["confirm"], extractor: f.extractor))
                continue
            }
            out.append(make(f.type, f.tMs, f.fields, .heard, f.quote, f.rawSpan, f.confidence, receipts: f.receipts, flags: f.flags, extractor: f.extractor))
        }
        for g in gaps {
            out.append(make(.audioGap, g.0, ["duration_ms": String(g.1 - g.0), "missing_frames": String(g.2)], .tablet, nil, nil, 1.0))
        }
        out.append(contentsOf: extra)
        // deterministic order + ids
        let order: [EventType: Int] = Dictionary(uniqueKeysWithValues: EventType.allCases.enumerated().map { ($1, $0) })
        out.sort { a, b in
            if a.tMs != b.tMs { return a.tMs < b.tMs }
            if a.type != b.type { return order[a.type]! < order[b.type]! }
            return (a.rawSpan ?? "", a.quote ?? "", a.fields.description) < (b.rawSpan ?? "", b.quote ?? "", b.fields.description)
        }
        for k in out.indices { out[k].id = "e\(k + 1)" }
        return out
    }

    func make(_ type: EventType, _ t: Int64, _ fields: [String: String], _ source: EventSource, _ quote: String?, _ span: String?,
              _ conf: Double, tap: PlacedTap? = nil, receipts: [String: FieldReceipt]? = nil, flags: [String] = [],
              extractor: String? = nil) -> EarshotEvent {
        EarshotEvent(id: "", callId: callId, time: clock.iso(t), tMs: t, type: type, fields: fields, source: source, quote: quote,
                     rawSpan: span, confidence: conf,
                     models: ModelInfo(asr: span == nil ? "none" : models.asr, extract: extractor ?? (span == nil ? "none" : models.extract)),
                     receipts: (receipts?.isEmpty ?? true) ? nil : receipts, flags: flags.isEmpty ? nil : flags,
                     tapSource: tap?.source, tapClipMs: tap?.clipMs)
    }
}
