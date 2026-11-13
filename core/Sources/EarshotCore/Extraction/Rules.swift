import Foundation

/// A pre-event extracted from one clean segment. Turned into `EarshotEvent`s
/// by the tap merger (which assigns IDs, times and sources).
public struct Finding: Equatable, Sendable {
    public var type: EventType
    public var fields: [String: String]
    public var receipts: [String: FieldReceipt]
    public var tMs: Int64
    public var rawSpan: String
    public var quote: String
    public var confidence: Double
    public var flags: [String]
    public var extractor: String
}

/// Regex helper over a clean segment's joined token text.
struct TokText {
    let seg: CleanSegment
    let text: String
    var starts: [Int] = []
    var ends: [Int] = []
    init(_ seg: CleanSegment) {
        self.seg = seg
        // Clause punctuation becomes " ;" and sentence ends " |" so patterns
        // using \s+ between words never run across a boundary.
        var s = ""
        for (i, t) in seg.tokens.enumerated() {
            if i > 0 { s += " " }
            starts.append(s.count); s += t.text; ends.append(s.count)
            if let p = t.punct { s += ".?!".contains(p) ? " |" : " ;" }
        }
        text = s
    }
    /// Token index range covering character range [a, b).
    func tokens(_ r: NSRange) -> ClosedRange<Int>? {
        guard r.location != NSNotFound, !seg.tokens.isEmpty else { return nil }
        let a = r.location, b = r.location + r.length
        guard let f = ends.firstIndex(where: { $0 > a }), let l = starts.lastIndex(where: { $0 < b }), f <= l else { return nil }
        return f...l
    }
    func receipt(_ r: ClosedRange<Int>, inferred: String? = nil) -> FieldReceipt {
        FieldReceipt(rawSpan: seg.rawSpan, quote: seg.quote(r.lowerBound, r.upperBound),
                     rawRange: [seg.tokens[r.lowerBound].rawStart, seg.tokens[r.upperBound].rawEnd], inferred: inferred)
    }
    func sub(_ r: NSRange) -> String { (text as NSString).substring(with: r) }
}

final class Rx {
    let re: NSRegularExpression
    init(_ p: String) { re = try! NSRegularExpression(pattern: p, options: [.caseInsensitive]) }
    func all(_ s: String) -> [NSTextCheckingResult] { re.matches(in: s, range: NSRange(location: 0, length: (s as NSString).length)) }
}

public final class RulesExtractor {
    public static let version = "rules-v1"
    let dict: EMSDictionary
    public init(dict: EMSDictionary) {
        self.dict = dict
        var p: [String: (String, String)] = [:]
        var s: [String: (String, String)] = [:]
        for t in dict.terms.terms {
            let k = Text.normalizePhrase(t.term)
            switch t.category {
            case "procedure" where !RulesExtractor.ambiguousProcedures.contains(k): p[k] = (t.expansion, t.term)
            case "status": s[k] = (t.term, "condition")   // keep the medic's own word, never a definition
            case "symptom": s[k] = (t.expansion, "symptom")
            case "history": if k.count >= 3 && !["meds", "hx"].contains(k) { s[k] = (t.expansion, "history") }
            default: break
            }
        }
        // extra procedure phrasings not in the term list
        for (k, v) in [("started an iv", "intravenous access"), ("got an iv", "intravenous access"), ("iv in", "intravenous access"),
                       ("line in", "intravenous access"), ("got a line", "intravenous access"), ("shock delivered", "defibrillation"),
                       ("shocking", "defibrillation"), ("delivered a shock", "defibrillation"), ("starting compressions", "chest compressions"),
                       ("start compressions", "chest compressions"), ("12 lead", "12-lead ECG"), ("pads on", "defibrillation pads applied"),
                       ("on the monitor", "cardiac monitoring"), ("tube is in", "endotracheal intubation"), ("igel", "i-gel supraglottic airway"),
                       ("c collar", "cervical collar"), ("on cpap", "continuous positive airway pressure")] {
            p[k] = (v, k)
        }
        procLex = p; statusLex = s
        maxProcTokens = (p.keys.map { $0.split(separator: " ").count } + [1]).max()!
        maxStatusTokens = (s.keys.map { $0.split(separator: " ").count } + [1]).max()!
    }

    static let ambiguousProcedures: Set<String> = ["shock", "suction", "splint", "cpr", "tq", "pacing", "bagging"]
    let procLex: [String: (String, String)]
    let statusLex: [String: (String, String)]
    let maxProcTokens: Int
    let maxStatusTokens: Int

    static let adminVerbs: Set<String> = ["gave", "given", "give", "giving", "administered", "administer", "administering", "pushed",
                                          "pushing", "push", "hung", "hanging", "started", "starting", "got", "spray", "sprayed",
                                          "dose", "repeat", "repeated", "another", "drew", "drawing", "ivp", "titrating", "bolus"]
    static let homeMedCues: Set<String> = ["takes", "taking", "prescribed", "home", "history", "uses", "regular", "daily", "prescription"]
    static let ptaCues: Set<String> = ["took", "before"]
    static let negCues: Set<String> = ["no", "not", "didn't", "don't", "held", "withheld", "hold", "holding", "refused", "declined",
                                       "without", "never", "denies", "deny", "negative", "won't", "didnt", "dont", "contraindicated"]

    public func extract(_ seg: CleanSegment) -> [Finding] {
        guard !seg.tokens.isEmpty else { return [] }
        let tt = TokText(seg)
        var out: [Finding] = []
        var used = Set<Int>()   // token indices consumed by vitals (so numbers aren't reused as doses)
        if let v = vitals(tt, &used) { out.append(v) }
        out += medications(tt, used: used)
        out += procedures(tt)
        out += statuses(tt)
        out += patientInfo(tt)
        out += dispatch(tt)
        out += transport(tt)
        return out.sorted { ($0.tMs, $0.type.rawValue) < ($1.tMs, $1.type.rawValue) }
    }

    // MARK: vitals

    struct VitalRule { let fields: [String]; let rx: Rx; let ranges: [ClosedRange<Double>]; let conf: Double }
    static let N = #"(?:is |of |was |at |now |about |around |reading |reads )?"#
    static let vitalRules: [VitalRule] = [
        VitalRule(fields: ["bp_systolic", "bp_diastolic"], rx: Rx(#"\b(?:bp|blood pressure|pressure|bps)\s+"# + N + #"(\d{2,3})/(\d{2,3})\b"#), ranges: [40...300, 20...200], conf: 0.92),
        VitalRule(fields: ["bp_systolic"], rx: Rx(#"\b(?:bp|blood pressure|pressure)\s+"# + N + #"(\d{2,3})\s+(?:by\s+)?palp"#), ranges: [40...300], conf: 0.88),
        VitalRule(fields: ["bp_systolic", "bp_diastolic"], rx: Rx(#"(?<![\w/])(\d{2,3})/(\d{2,3})(?![\w/])"#), ranges: [60...260, 30...160], conf: 0.7),
        VitalRule(fields: ["heart_rate"], rx: Rx(#"\b(?:hr|heart rate|pulse|pulse rate|pulses|heart rates|rate)\s+"# + N + #"(\d{2,3})\b"#), ranges: [20...260], conf: 0.9),
        VitalRule(fields: ["heart_rate"], rx: Rx(#"\b(?:tachy|tachycardic|brady|bradycardic|sinus tach|sinus brady|sinus|afib|tachycardia|bradycardia)\s+(?:at|in the|of)\s+(?:about\s+)?(\d{2,3})s?\b"#), ranges: [20...260], conf: 0.85),
        VitalRule(fields: ["resp_rate"], rx: Rx(#"\b(?:rr|resps|resp|respirations|respiratory rate|resp rate|breathing|breathing at|respiration)\s+"# + #"(?:are |is |of |at |about |around )?(\d{1,2})\b"#), ranges: [2...70], conf: 0.88),
        VitalRule(fields: ["spo2"], rx: Rx(#"\b(?:spo2|sats|sat|o2 sat|o2 sats|pulse ox|satting|sating|saturation|saturating|sats are|o2 saturation)\s+"# + N + #"(\d{2,3})\b(?!\s*(?:lpm|l|liters))"#), ranges: [40...100], conf: 0.9),
        VitalRule(fields: ["spo2"], rx: Rx(#"\b(\d{2,3})\s*(?:%)\s+(?:on\s+)?(?:room air|ra|\d+\s*lpm|nrb|nc|non rebreather|nasal cannula)"#), ranges: [40...100], conf: 0.85),
        VitalRule(fields: ["glucose"], rx: Rx(#"\b(?:bgl|cbg|glucose|sugar|blood sugar|blood glucose|d stick|dextro|accucheck|accu check|sugars)\s+"# + N + #"(\d{2,3}|high|hi|low|lo)\b"#), ranges: [10...700], conf: 0.88),
        VitalRule(fields: ["gcs"], rx: Rx(#"\bgcs\s+(?:is |of |was |a |at )?(\d{1,2})\b"#), ranges: [3...15], conf: 0.92),
        VitalRule(fields: ["etco2"], rx: Rx(#"\b(?:etco2|end tidal|capno|capnography|end tidal co2)\s+"# + N + #"(\d{1,3})\b"#), ranges: [0...150], conf: 0.88),
        VitalRule(fields: ["temp"], rx: Rx(#"\b(?:temp|temperature)\s+"# + N + #"(\d{2,3}(?:\.\d)?)\b"#), ranges: [25...110], conf: 0.85),
        VitalRule(fields: ["pain"], rx: Rx(#"\bpain\s+(?:is |of |at |score |scale |level )*(?:a |an )?(\d{1,2})(?:\s+out of\s+10|/10)?\b"#), ranges: [0...10], conf: 0.85),
        VitalRule(fields: ["pain"], rx: Rx(#"\b(\d{1,2})\s+out of\s+10\b"#), ranges: [0...10], conf: 0.75),
    ]
    static let aoRx = Rx(#"\ba&ox([1-4])\b"#)
    static let perrlRx = Rx(#"\b(perrla?|pupils equal(?: round)?(?: and)? reactive)\b"#)
    static let rhythmRx = Rx(#"\b(normal sinus rhythm|nsr|sinus rhythm|sinus tach(?:ycardia)?|sinus brady(?:cardia)?|afib(?: with rvr)?|atrial fibrillation|vfib|v fib|vtach|v tach|svt|pea|asystole|st elevation|stemi)\b"#)
    static let o2onRx = Rx(#"\bon\s+(room air|ra|\d+\s*(?:lpm|l)(?:\s+(?:nrb|nc|non rebreather|nasal cannula|via nrb|via nc))?|nrb|non rebreather|nasal cannula|cpap)\b"#)

    func vitals(_ tt: TokText, _ used: inout Set<Int>) -> Finding? {
        var fields: [String: String] = [:]
        var rec: [String: FieldReceipt] = [:]
        var firstTok = Int.max
        var allToks: [ClosedRange<Int>] = []
        var conf = 1.0
        for rule in RulesExtractor.vitalRules {
            for m in rule.rx.all(tt.text) {
                guard let tr = tt.tokens(m.range) else { continue }
                if tr.contains(where: { used.contains($0) }) { continue }
                var vals: [String] = []
                var ok = true
                for (gi, f) in rule.fields.enumerated() {
                    let v = tt.sub(m.range(at: gi + 1))
                    if fields[f] != nil { ok = false; break }      // first mention wins within a segment
                    if let d = Double(v), !rule.ranges[gi].contains(d) { ok = false; break }
                    vals.append(v)
                }
                if rule.fields.count == 2, let s = Double(vals.first ?? ""), let d = Double(vals.last ?? ""), s <= d { ok = false }
                guard ok, vals.count == rule.fields.count else { continue }
                for (gi, f) in rule.fields.enumerated() {
                    fields[f] = vals[gi]; rec[f] = tt.receipt(tr)
                }
                if rule.fields == ["bp_systolic"] { fields["bp_method"] = "palpation"; rec["bp_method"] = tt.receipt(tr) }
                for k in tr { used.insert(k) }
                firstTok = min(firstTok, tr.lowerBound); allToks.append(tr); conf = min(conf, rule.conf)
            }
        }
        func simple(_ rx: Rx, _ field: String, _ map: (String) -> String) {
            for m in rx.all(tt.text) where fields[field] == nil {
                guard let tr = tt.tokens(m.range) else { continue }
                fields[field] = map(tt.sub(m.range(at: 1))); rec[field] = tt.receipt(tr)
                firstTok = min(firstTok, tr.lowerBound); allToks.append(tr); conf = min(conf, 0.9)
            }
        }
        simple(RulesExtractor.aoRx, "mental_status") { "A&Ox\($0)" }
        simple(RulesExtractor.perrlRx, "pupils") { _ in "PERRL" }
        simple(RulesExtractor.rhythmRx, "ecg") { $0.uppercased() == $0 ? $0 : $0.lowercased() }
        if !fields.isEmpty { simple(RulesExtractor.o2onRx, "o2_on") { $0 } }
        guard !fields.isEmpty else { return nil }
        let lo = allToks.map(\.lowerBound).min()!, hi = allToks.map(\.upperBound).max()!
        return Finding(type: .vitals, fields: fields, receipts: rec, tMs: tt.seg.timeOf(token: firstTok), rawSpan: tt.seg.rawSpan,
                       quote: tt.seg.quote(lo, hi), confidence: conf, flags: [], extractor: RulesExtractor.version)
    }

    // MARK: medications

    struct DrugHit { let drug: Int; let range: ClosedRange<Int>; let conf: Double; let how: String }

    func drugHits(_ tt: TokText) -> [DrugHit] {
        let toks = tt.seg.tokens
        var hits: [DrugHit] = []
        var i = 0
        while i < toks.count {
            var found: DrugHit? = nil
            for n in stride(from: min(dict.maxAliasTokens, toks.count - i), through: 1, by: -1) {
                let phrase = toks[i..<(i + n)].map(\.text).joined(separator: " ")
                if let di = dict.aliasIndex[phrase] {
                    let rule = toks[i].rule
                    let conf = rule == "formulary:asr_variant" ? 0.75 : rule == "formulary:fuzzy" ? 0.65 : 0.9
                    if dict.contextRequired.contains(phrase) && !hasMedContext(toks, i, i + n - 1) { break }
                    found = DrugHit(drug: di, range: i...(i + n - 1), conf: conf, how: rule ?? "alias")
                    break
                }
            }
            if found == nil, toks[i].text.count >= 5, toks[i].text.allSatisfy({ $0.isLetter }), dict.termIndex[toks[i].text] == nil,
               hasMedContext(toks, i, i) {
                let key = Phonetic.key(toks[i].text)
                if let ds = dict.phoneticIndex[key], ds.count == 1 {
                    found = DrugHit(drug: ds[0], range: i...i, conf: 0.55, how: "phonetic")
                } else if key.count >= 4 {
                    // near-phonetic: keys within edit distance 1 (e.g. "Safranib" SFRNB ~ Zofran SFRN). Always "please confirm".
                    var cands = Set<Int>()
                    for (k, ds) in dict.phoneticIndex where abs(k.count - key.count) <= 1 && k.count >= 4 && Text.levenshtein(k, key) <= 1 {
                        cands.formUnion(ds)
                    }
                    if cands.count == 1 { found = DrugHit(drug: cands.first!, range: i...i, conf: 0.45, how: "phonetic~") }
                }
            }
            if let f = found { hits.append(f); i = f.range.upperBound + 1 } else { i += 1 }
        }
        return hits
    }

    func isNumber(_ s: String) -> Bool { Double(s) != nil }

    func hasMedContext(_ toks: [CleanToken], _ a: Int, _ b: Int) -> Bool {
        let lo = max(0, a - 5), hi = min(toks.count - 1, b + 5)
        for k in lo...hi where k < a || k > b {
            let t = toks[k].text
            if isNumber(t) || dict.unitIndex[t] != nil || RulesExtractor.adminVerbs.contains(t) || ["po", "sl", "iv", "io", "im", "sq", "neb", "mg", "mcg"].contains(t) { return true }
        }
        return false
    }

    func medications(_ tt: TokText, used: Set<Int>) -> [Finding] {
        let toks = tt.seg.tokens
        let hits = drugHits(tt)
        var out: [Finding] = []
        for (hi, h) in hits.enumerated() {
            let d = dict.drug(h.drug)
            let prevEnd = hi > 0 ? hits[hi - 1].range.upperBound + 1 : 0
            let nextStart = hi + 1 < hits.count ? hits[hi + 1].range.lowerBound - 1 : toks.count - 1
            let lo = max(prevEnd, h.range.lowerBound - 5), hiW = min(nextStart, h.range.upperBound + 7)
            var fields: [String: String] = ["drug": d.generic]
            var rec: [String: FieldReceipt] = ["drug": tt.receipt(h.range)]
            var flags: [String] = []
            var span = h.range
            if h.conf < 0.7 { flags.append("confirm") }
            if Text.normalizePhrase(d.generic) != toks[h.range.lowerBound].text || h.range.count > 1 {
                fields["drug_as_heard"] = tt.seg.quote(h.range.lowerBound, h.range.upperBound)
            }
            // context words before the drug
            let before = toks[max(0, h.range.lowerBound - 4)..<h.range.lowerBound].map(\.text)
            let negated = before.suffix(3).contains { RulesExtractor.negCues.contains($0) }
            let allergy = before.contains { $0.hasPrefix("allerg") }
            let homeMed = before.contains { RulesExtractor.homeMedCues.contains($0) } || before.suffix(2) == ["is", "on"] || before.suffix(2) == ["she's", "on"] || before.suffix(2) == ["he's", "on"]
            let pta = before.contains { RulesExtractor.ptaCues.contains($0) }
            // dose: number (+ unit) after the drug, or "<n> <unit> of <drug>" / "<n> of <drug>" before it
            var amount: (String, ClosedRange<Int>)? = nil
            var unit: (String, ClosedRange<Int>)? = nil
            var k = h.range.upperBound + 1
            while k <= hiW {
                if !used.contains(k), isNumber(toks[k].text) {
                    amount = (toks[k].text, k...k)
                    if k + 1 <= hiW, let u = unitOf(toks[k + 1].text) { unit = (u, (k + 1)...(k + 1)) }
                    break
                }
                k += 1
            }
            if amount == nil {
                var j = h.range.lowerBound - 1
                if j >= lo && toks[j].text == "of" { j -= 1 }
                if j >= lo, let u = unitOf(toks[j].text), j - 1 >= lo, isNumber(toks[j - 1].text), !used.contains(j - 1) {
                    amount = (toks[j - 1].text, (j - 1)...(j - 1)); unit = (u, j...j)
                } else if j >= lo, isNumber(toks[j].text), !used.contains(j), toks[h.range.lowerBound - 1].text == "of" {
                    amount = (toks[j].text, j...j)
                }
            }
            if let a = amount {
                fields["dose"] = a.0; rec["dose"] = tt.receipt(a.1); span = min(span.lowerBound, a.1.lowerBound)...max(span.upperBound, a.1.upperBound)
                if let u = unit {
                    fields["unit"] = u.0; rec["unit"] = tt.receipt(u.1); span = min(span.lowerBound, u.1.lowerBound)...max(span.upperBound, u.1.upperBound)
                } else {
                    let units = Set(d.typical_doses.filter { $0.amount == a.0 }.map(\.unit))
                    if units.count == 1, let u = units.first {
                        fields["unit"] = u
                        rec["unit"] = FieldReceipt(rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(a.1.lowerBound, a.1.upperBound), rawRange: nil,
                                                   inferred: "unit not spoken; \(a.0) \(u) is the protocol dose for \(d.generic)")
                        flags.append("inferred")
                    }
                }
                if let u = fields["unit"], u.hasSuffix("/kg") || u.hasSuffix("/min") || u.hasSuffix("/hr") { /* rate/weight dose stays as heard */ }
            }
            // route
            if let (r, rr) = route(toks, lo, hiW, drug: d) {
                fields["route"] = r; rec["route"] = tt.receipt(rr); span = min(span.lowerBound, rr.lowerBound)...max(span.upperBound, rr.upperBound)
            }
            let admin = toks[lo...hiW].contains { RulesExtractor.adminVerbs.contains($0.text) }
            var type = EventType.medication
            if allergy {
                type = .status; fields = ["kind": "allergy", "allergy": d.generic]; rec = ["allergy": rec["drug"]!]
            } else if negated {
                type = .status; fields["kind"] = "med_not_given"
            } else if homeMed && amount == nil {
                type = .status; fields["kind"] = "home_med"
            } else if pta {
                type = .status; fields["kind"] = "prior_to_arrival_med"
            } else if amount == nil && !admin {
                type = .status; fields["kind"] = "drug_mention"; flags.append("confirm")
            }
            if d.high_alert && type == .medication && !flags.contains("confirm") && fields["dose"] == nil { flags.append("confirm") }
            out.append(Finding(type: type, fields: fields, receipts: rec, tMs: tt.seg.timeOf(token: h.range.lowerBound), rawSpan: tt.seg.rawSpan,
                               quote: tt.seg.quote(span.lowerBound, span.upperBound), confidence: h.conf, flags: Array(Set(flags)).sorted(),
                               extractor: RulesExtractor.version + (h.how == "alias" ? "" : ":" + h.how)))
        }
        return out
    }

    func unitOf(_ t: String) -> String? {
        if dict.formulary.units[t] != nil { return t }
        if let u = dict.unitIndex[t], !["l", "u", "in"].contains(t) { return u }
        return nil
    }

    static let routeWords: [String: String] = ["chewed": "PO", "chew": "PO", "chewable": "PO", "swallow": "PO", "push": "IV", "pushed": "IV",
                                               "ivp": "IV", "drip": "IV", "spray": "IN", "atomized": "IN", "nostril": "IN", "nose": "IN",
                                               "thigh": "IM", "deltoid": "IM", "tongue": "SL", "neb": "NEB", "nebulizer": "NEB", "patch": "TD"]
    func route(_ toks: [CleanToken], _ lo: Int, _ hi: Int, drug: Drug) -> (String, ClosedRange<Int>)? {
        guard lo <= hi else { return nil }
        for k in lo...hi {
            for n in stride(from: min(4, hi - k + 1), through: 1, by: -1) {
                let phrase = toks[k..<(k + n)].map(\.text).joined(separator: " ")
                if phrase == "in" || phrase == "et" { continue }  // too ambiguous alone
                if let r = dict.routeIndex[phrase] ?? (n == 1 ? RulesExtractor.routeWords[phrase] : nil) {
                    if r == "IV" && (phrase == "push" || phrase == "pushed") && !drug.routes.contains("IV") { continue }
                    return (r, k...(k + n - 1))
                }
            }
        }
        return nil
    }

    // MARK: procedures

    static let ivRx = Rx(#"\b(\d{2})\s*(?:gauge|g)\b(?:\s+(?:iv|in the|in))?(?:\s+(?:the\s+)?(left|right|l|r))?\s*(ac|antecubital|hand|forearm|wrist|ej|external jugular|arm)?"#)
    static let joulesRx = Rx(#"\b(?:shock(?:ed|ing)?|defib(?:rillated)?|cardioverted|cardiovert)\s+(?:at\s+)?(\d{2,3})\s*(?:joules|j)\b"#)

    func procedures(_ tt: TokText) -> [Finding] {
        let toks = tt.seg.tokens
        var out: [Finding] = []
        var taken = Set<Int>()
        for m in RulesExtractor.ivRx.all(tt.text) {
            guard let tr = tt.tokens(m.range) else { continue }
            var f: [String: String] = ["procedure": "IV access", "gauge": tt.sub(m.range(at: 1))]
            if m.range(at: 2).location != NSNotFound || m.range(at: 3).location != NSNotFound {
                let side = m.range(at: 2).location != NSNotFound ? tt.sub(m.range(at: 2)) : ""
                let site = m.range(at: 3).location != NSNotFound ? tt.sub(m.range(at: 3)) : ""
                f["site"] = [side, site].filter { !$0.isEmpty }.joined(separator: " ").uppercased().replacingOccurrences(of: "LEFT", with: "left").replacingOccurrences(of: "RIGHT", with: "right")
            }
            var rec: [String: FieldReceipt] = [:]
            for k in f.keys { rec[k] = tt.receipt(tr) }
            for k in tr { taken.insert(k) }
            out.append(Finding(type: .procedure, fields: f, receipts: rec, tMs: tt.seg.timeOf(token: tr.lowerBound), rawSpan: tt.seg.rawSpan,
                               quote: tt.seg.quote(tr.lowerBound, tr.upperBound), confidence: 0.88, flags: [], extractor: RulesExtractor.version))
        }
        for m in RulesExtractor.joulesRx.all(tt.text) {
            guard let tr = tt.tokens(m.range) else { continue }
            for k in tr { taken.insert(k) }
            let f = ["procedure": "defibrillation", "energy_j": tt.sub(m.range(at: 1))]
            out.append(Finding(type: .procedure, fields: f, receipts: ["procedure": tt.receipt(tr), "energy_j": tt.receipt(tr)],
                               tMs: tt.seg.timeOf(token: tr.lowerBound), rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(tr.lowerBound, tr.upperBound),
                               confidence: 0.88, flags: [], extractor: RulesExtractor.version))
        }
        var i = 0
        var seen = Set<String>()
        while i < toks.count {
            var adv = 1
            if !taken.contains(i) {
                for n in stride(from: min(maxProcTokens, toks.count - i), through: 1, by: -1) {
                    let phrase = toks[i..<(i + n)].map(\.text).joined(separator: " ")
                    if let (canon, _) = procLex[phrase] {
                        let before = toks[max(0, i - 3)..<i].map(\.text)
                        let neg = before.contains { RulesExtractor.negCues.contains($0) }
                        if !seen.contains(canon) {
                            seen.insert(canon)
                            let tr = i...(i + n - 1)
                            var f = ["procedure": canon]
                            if neg { f["kind"] = "not_done" }
                            out.append(Finding(type: neg ? .status : .procedure, fields: f, receipts: ["procedure": tt.receipt(tr)],
                                               tMs: tt.seg.timeOf(token: i), rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(i, i + n - 1),
                                               confidence: 0.85, flags: [], extractor: RulesExtractor.version))
                        }
                        adv = n; break
                    }
                }
            }
            i += adv
        }
        return out
    }

    // MARK: status (condition, symptoms, history)

    func statuses(_ tt: TokText) -> [Finding] {
        let toks = tt.seg.tokens
        var out: [Finding] = []
        var i = 0
        var seen = Set<String>()
        while i < toks.count {
            var adv = 1
            for n in stride(from: min(maxStatusTokens, toks.count - i), through: 1, by: -1) {
                let phrase = toks[i..<(i + n)].map(\.text).joined(separator: " ")
                guard let (exp, kind) = statusLex[phrase] else { continue }
                // "code" / "stable" etc. are common words; require them not to be part of a bigger phrase handled elsewhere
                if phrase == "code" && i + 1 < toks.count && ["3", "2", "1", "blue", "status"].contains(toks[i + 1].text) { break }
                if phrase == "stable" && i > 0 && ["hemodynamically"].contains(toks[i - 1].text) == false && i + 1 < toks.count && toks[i + 1].text == "angina" { break }
                let before = toks[max(0, i - 3)..<i].map(\.text)
                let neg = before.contains { RulesExtractor.negCues.contains($0) } || (before.last == "longer")
                let key = kind + ":" + exp + (neg ? ":neg" : "")
                if !seen.contains(key) {
                    seen.insert(key)
                    let tr = (neg ? max(0, i - min(3, before.count)) : i)...(i + n - 1)
                    var f: [String: String] = ["kind": kind, kind == "condition" ? "condition" : kind: exp]
                    if neg { f["negated"] = "true" }
                    let key2 = kind == "condition" ? "condition" : kind
                    out.append(Finding(type: .status, fields: f, receipts: [key2: tt.receipt(tr)], tMs: tt.seg.timeOf(token: i),
                                       rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(tr.lowerBound, tr.upperBound), confidence: 0.8, flags: [],
                                       extractor: RulesExtractor.version))
                }
                adv = n; break
            }
            i += adv
        }
        return out
    }

    // MARK: patient info

    static let ageRx = Rx(#"\b(\d{1,3})\s*(?:year|yr|years|yrs)\s*old\b(?:\s+(male|female|man|woman|boy|girl|gentleman|lady))?"#)
    static let ageShortRx = Rx(#"\b(\d{1,3})\s*(yom|yof|yo m|yo f|y o m|y o f)\b"#)
    static let sexRx = Rx(#"\b(male|female)\s+(?:patient|pt)\b"#)
    static let weightRx = Rx(#"\b(?:weighs|weight|weighing|weight is|weight of)?\s*(about|around|approximately|approx|maybe|roughly|like|estimated|probably)?\s*(\d{2,3})\s*(kg|kilos|kilograms|kilo|pounds|lbs|lb)\b"#)
    static let allergyRx = Rx(#"\b(?:allergic to|allergies to|allergy to|allergies are|allergies include|allergic|allergies)\s+([a-z]+(?:\s+(?:and\s+)?[a-z]+){0,3}?)(?=\s+[|;]|\s+(?:she|he|they|takes|and no|no)\b|\s*$)"#)
    static let nkdaRx = Rx(#"\b(nkda|nka|no known drug allergies|no known allergies|no allergies)\b"#)
    static let historyRx = Rx(#"\b(?:history of|hx of|pmh of|past medical history of|past history of|pmh)\s+([a-z0-9]+(?:\s+(?:and\s+)?[a-z0-9]+){0,4}?)(?=\s+[|;]|\s+(?:she|he|they|takes|allergic|no)\b|\s*$)"#)

    func patientInfo(_ tt: TokText) -> [Finding] {
        var out: [Finding] = []
        func add(_ f: [String: String], _ key: String, _ tr: ClosedRange<Int>, _ conf: Double, flags: [String] = []) {
            out.append(Finding(type: .status, fields: f, receipts: [key: tt.receipt(tr)], tMs: tt.seg.timeOf(token: tr.lowerBound),
                               rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(tr.lowerBound, tr.upperBound), confidence: conf, flags: flags,
                               extractor: RulesExtractor.version))
        }
        for m in RulesExtractor.ageRx.all(tt.text) {
            guard let tr = tt.tokens(m.range), let age = Int(tt.sub(m.range(at: 1))), age <= 120 else { continue }
            var f = ["kind": "patient", "age": String(age)]
            if m.range(at: 2).location != NSNotFound { f["sex"] = sexWord(tt.sub(m.range(at: 2))) }
            out.append(Finding(type: .status, fields: f, receipts: Dictionary(uniqueKeysWithValues: f.keys.filter { $0 != "kind" }.map { ($0, tt.receipt(tr)) }),
                               tMs: tt.seg.timeOf(token: tr.lowerBound), rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(tr.lowerBound, tr.upperBound),
                               confidence: 0.9, flags: [], extractor: RulesExtractor.version))
        }
        for m in RulesExtractor.ageShortRx.all(tt.text) {
            guard let tr = tt.tokens(m.range), let age = Int(tt.sub(m.range(at: 1))), age <= 120 else { continue }
            let f = ["kind": "patient", "age": String(age), "sex": tt.sub(m.range(at: 2)).hasSuffix("m") ? "male" : "female"]
            out.append(Finding(type: .status, fields: f, receipts: ["age": tt.receipt(tr), "sex": tt.receipt(tr)], tMs: tt.seg.timeOf(token: tr.lowerBound),
                               rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(tr.lowerBound, tr.upperBound), confidence: 0.85, flags: [], extractor: RulesExtractor.version))
        }
        for m in RulesExtractor.sexRx.all(tt.text) {
            guard let tr = tt.tokens(m.range) else { continue }
            add(["kind": "patient", "sex": tt.sub(m.range(at: 1)).lowercased()], "sex", tr, 0.85)
        }
        for m in RulesExtractor.weightRx.all(tt.text) {
            guard let tr = tt.tokens(m.range), let w = Double(tt.sub(m.range(at: 2))) else { continue }
            let u = tt.sub(m.range(at: 3)).lowercased()
            let kg = u.hasPrefix("k") ? w : (w * 0.4536).rounded()
            guard (2...350).contains(kg) else { continue }
            var f = ["kind": "patient", "weight_kg": String(Int(kg))]
            if !u.hasPrefix("k") { f["weight_as_heard"] = "\(Int(w)) lb" }
            if m.range(at: 1).location != NSNotFound { f["weight_estimated"] = "true" }
            add(f, "weight_kg", tr, 0.85)
        }
        for m in RulesExtractor.nkdaRx.all(tt.text) {
            guard let tr = tt.tokens(m.range) else { continue }
            add(["kind": "allergy", "allergy": "NKDA"], "allergy", tr, 0.9)
        }
        for m in RulesExtractor.allergyRx.all(tt.text) {
            guard let tr = tt.tokens(m.range) else { continue }
            let what = tt.sub(m.range(at: 1))
            if dict.aliasIndex[what] != nil { continue } // drug allergy handled by medication pass
            if ["to", "no", "none"].contains(what) { continue }
            add(["kind": "allergy", "allergy": what], "allergy", tr, 0.75, flags: ["confirm"])
        }
        for m in RulesExtractor.historyRx.all(tt.text) {
            guard let tr = tt.tokens(m.range) else { continue }
            add(["kind": "history", "history": tt.sub(m.range(at: 1))], "history", tr, 0.75)
        }
        return out
    }

    func sexWord(_ s: String) -> String {
        ["male", "man", "boy", "gentleman"].contains(s.lowercased()) ? "male" : "female"
    }

    // MARK: dispatch vs found

    static let W = #"[^\s|;]+"#
    static let phrase = #"("# + W + #"(?:\s+"# + W + #"){0,4}?)"#
    static let stop = #"(?=\s+[|;]|\s+(?:but|and|turned|turns|it|which|so|now|when|then|patient|pt|she|he|they|with|for)\b|\s*$)"#
    static let dispatchRx = Rx(#"\b(?:dispatched for|dispatched to|dispatched as|called for|call came in as|came in as|came in for|dispatch said|dispatch says|toned out for|sent for|we got called for|got called for|call was for)\s+(?:an?\s+|the\s+)?"# + phrase + stop)
    static let foundRx = Rx(#"\b(?:turned out to be|turns out to be|turns out it's|turned out it was|it's actually|it is actually|is actually|was actually|actually an?|found to be|looks more like|more like an?)\s+(?:an?\s+|the\s+)?"# + phrase + stop)
    static let ccRx = Rx(#"\b(?:complaining of|complains of|c/o|chief complaint is|chief complaint of|chief complaint|cc is|presenting with|presents with)\s+"# + phrase + stop)

    func dispatch(_ tt: TokText) -> [Finding] {
        var out: [Finding] = []
        for (rx, field, conf) in [(RulesExtractor.dispatchRx, "dispatch_reason", 0.85), (RulesExtractor.foundRx, "found", 0.75), (RulesExtractor.ccRx, "chief_complaint", 0.8)] {
            for m in rx.all(tt.text) {
                guard let tr = tt.tokens(m.range), let vr = tt.tokens(m.range(at: 1)) else { continue }
                let val = tt.seg.quote(vr.lowerBound, vr.upperBound).trimmingCharacters(in: CharacterSet(charactersIn: " ,.;"))
                out.append(Finding(type: .dispatch, fields: [field: val], receipts: [field: tt.receipt(tr)], tMs: tt.seg.timeOf(token: tr.lowerBound),
                                   rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(tr.lowerBound, tr.upperBound), confidence: conf, flags: [],
                                   extractor: RulesExtractor.version))
            }
        }
        return out
    }

    // MARK: transport

    static let destRx = Rx(#"\b(?:transporting to|transport to|transporting him to|transporting her to|headed to|heading to|en route to|going to|taking (?:him|her|them|the patient|pt) to|we're going to|we are going to|transporting)\s+(?:the\s+)?"# + phrase + #"(?=\s+[|;]|\s+(?:eta|with|priority|code|lights|and|now|in|for)\b|\s*$)"#)
    static let modeRx = Rx(#"\b(lights and sirens|code 3|code three|emergent|non emergent|non-emergent|code 2|code two|no lights)\b"#)
    static let alertRx = Rx(#"\b(stemi alert|stroke alert|trauma alert|sepsis alert|cath lab|trauma team|code stroke|code stemi)\b"#)
    static let etaRx = Rx(#"\beta\s+(?:is\s+|of\s+|about\s+|in\s+)*(\d{1,3})\s*(?:minutes|minute|mins|min)\b"#)
    static let arrivedRx = Rx(#"\b(?:we're at|we are at|arrived at|arriving at|pulling into|pulling in to|we're here at)\s+(?:the\s+)?"# + phrase + #"(?=\s+[|;]|\s+(?:now|and|with)\b|\s*$)"#)

    func transport(_ tt: TokText) -> [Finding] {
        var fields: [String: String] = [:]
        var rec: [String: FieldReceipt] = [:]
        var trs: [ClosedRange<Int>] = []
        func grab(_ rx: Rx, _ field: String, group: Int = 1, clean: Bool = false, _ map: (String) -> String = { $0 }) {
            for m in rx.all(tt.text) where fields[field] == nil {
                guard let tr = tt.tokens(m.range) else { continue }
                let r = m.range(at: group)
                guard r.location != NSNotFound, let vr = tt.tokens(r) else { continue }
                let v = clean ? tt.sub(r) : tt.seg.quote(vr.lowerBound, vr.upperBound)
                fields[field] = map(v.trimmingCharacters(in: CharacterSet(charactersIn: " ,.;")))
                rec[field] = tt.receipt(tr); trs.append(tr)
            }
        }
        grab(RulesExtractor.destRx, "destination")
        grab(RulesExtractor.modeRx, "mode") { $0.lowercased() }
        grab(RulesExtractor.alertRx, "alert") { $0.lowercased() }
        grab(RulesExtractor.etaRx, "eta_min", clean: true)
        var out: [Finding] = []
        if !fields.isEmpty {
            let lo = trs.map(\.lowerBound).min()!, hi = trs.map(\.upperBound).max()!
            out.append(Finding(type: .transport, fields: fields, receipts: rec, tMs: tt.seg.timeOf(token: lo), rawSpan: tt.seg.rawSpan,
                               quote: tt.seg.quote(lo, hi), confidence: 0.8, flags: [], extractor: RulesExtractor.version))
        }
        for m in RulesExtractor.arrivedRx.all(tt.text) {
            guard let tr = tt.tokens(m.range) else { continue }
            var f = ["kind": "arrived_heard"]
            if m.range(at: 1).location != NSNotFound, m.range(at: 1).length > 0, let vr = tt.tokens(m.range(at: 1)) {
                f["destination"] = tt.seg.quote(vr.lowerBound, vr.upperBound).trimmingCharacters(in: CharacterSet(charactersIn: " ,.;"))
            }
            out.append(Finding(type: .transport, fields: f, receipts: ["kind": tt.receipt(tr)], tMs: tt.seg.timeOf(token: tr.lowerBound),
                               rawSpan: tt.seg.rawSpan, quote: tt.seg.quote(tr.lowerBound, tr.upperBound), confidence: 0.6, flags: ["confirm"],
                               extractor: RulesExtractor.version))
        }
        return out
    }
}
