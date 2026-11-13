import Foundation
import SwiftUI
import Observation
import EarshotCore

enum TransportKind: String, CaseIterable, Identifiable {
    case replay = "Replay (demo)"
    case ble = "Bluetooth LE"
    case wifi = "Wi-Fi (clip hotspot)"
    var id: String { rawValue }
}

enum ModelSlot: String, CaseIterable, Identifiable {
    case stock = "Stock"
    case fineTuned = "Fine-tuned"
    var id: String { rawValue }
}

/// App state. A thin layer over EarshotCore.LiveSession.
@Observable
final class AppModel {
    // dictionary + config
    let dict: EMSDictionary
    var config = PipelineConfig()

    // settings
    var transport: TransportKind = {
        #if targetEnvironment(simulator)
        return .replay
        #else
        return .ble
        #endif
    }()
    var asrSlot: ModelSlot = .stock
    var useTagger = false
    var useFoundationModels = true
    var replaySpeed: Double = 1
    var destinationName = "Mass General ED"
    var destinationLat = 42.3628
    var destinationLon = -71.0692

    // live state
    var session: LiveSession?
    var source: PacketSource?
    var clipState: ClipState = .off
    var link = LinkStatus(connected: false, transport: "none")
    var events: [EarshotEvent] = []
    var callStart = Date()
    var signed = false
    var statusMessage = ""
    let ledger = Ledger()
    let store = CallStore()
    let geofence = Geofence()

    init() {
        let f = Bundle.main.url(forResource: "formulary", withExtension: "json")!.deletingLastPathComponent()
        dict = try! EMSDictionary(directory: f)
        geofence.onEnter = { [weak self] in self?.markArrival(method: "geofence") }
    }

    // MARK: derived

    var chart: ChartModel? { session?.chartModel() }
    var arrival: EarshotEvent? { events.first { $0.type == .arrival } }
    var handoff: EarshotEvent? { events.first { $0.type == .handoff } }
    var unlabeledTaps: [EarshotEvent] { events.filter(\.isUnlabeledTap) }
    var confirmItems: [EarshotEvent] { events.filter(\.needsConfirm) }
    var lastVitals: EarshotEvent? { events.last { $0.type == .vitals } }

    /// Vitals due: every 5 min by default, 10 if the crew said "stable", 3 if "unstable".
    var vitalsIntervalMin: Int {
        let cond = events.last { $0.type == .status && $0.fields["kind"] == "condition" }?.fields["condition"] ?? ""
        if ["unstable", "crashing", "decompensating", "deteriorating", "worsening"].contains(cond) { return 3 }
        if cond == "stable" { return 10 }
        return 5
    }

    // MARK: models

    func makeTranscriber() -> Transcriber? {
        let names = asrSlot == .fineTuned ? ["whisper-ems-small.en-q5", "ggml-small.en"] : ["ggml-small.en", "ggml-tiny.en"]
        for n in names {
            if let url = ModelLocator.find(n, ext: "bin") {
                if let t = try? WhisperTranscriber(modelPath: url.path, threads: ProcessInfo.processInfo.activeProcessorCount > 4 ? 4 : 2) {
                    if n != names[0] { statusMessage = "\(names[0]) not found; using \(n)" }
                    return t
                }
            }
        }
        statusMessage = "No whisper model found. Run app/scripts/fetch_deps.sh, or copy ggml-small.en.bin into the app's Documents folder."
        return nil
    }

    func makeTagger() -> TokenTagger? {
        guard useTagger, let url = ModelLocator.find("EMSTagger", ext: "mlpackage") else { return nil }
        return try? CoreMLTagger(modelPath: url.path)
    }

    // MARK: call lifecycle

    func startCall() {
        stopCall()
        signed = false
        callStart = Date()
        let tz = TimeZone.current.secondsFromGMT()
        let s = LiveSession(dict: dict, config: config, callId: "c\(Int(callStart.timeIntervalSince1970))",
                            startEpochMs: Int64(callStart.timeIntervalSince1970 * 1000), tzOffsetSeconds: tz,
                            transcriber: makeTranscriber(), tagger: makeTagger())
        s.onEvents = { [weak self] ev in
            guard let self else { return }
            self.events = ev
            self.store.save(ev, callId: s.callId)
        }
        s.onState = { [weak self] st in self?.clipState = st }
        let src: PacketSource
        switch transport {
        case .replay:
            guard let url = Bundle.main.url(forResource: "demo_call", withExtension: "replay"),
                  let r = try? ReplayPacketSource(url: url, speed: replaySpeed) else {
                statusMessage = "demo_call.replay missing from the app bundle"; return
            }
            src = r
        case .ble: src = BLEPacketSource()
        case .wifi: src = WiFiPacketSource()
        }
        src.onPacket = { [weak s] p in s?.handle(p) }
        src.onStatus = { [weak self] st in DispatchQueue.main.async { self?.link = st } }
        s.source = src
        session = s; source = src
        src.start()
        // clock sync: tell the clip our epoch so tap times map to wall time
        src.send(.clock(PacketHeader(type: .clock, seq: 0, clipMs: 0), epochMs: UInt64(Date().timeIntervalSince1970 * 1000)))
        geofence.start(lat: destinationLat, lon: destinationLon, radius: 150)
    }

    func stopCall() {
        source?.send(.state(PacketHeader(type: .state, seq: 0, clipMs: 0), StatePayload(state: .off)))
        source?.stop()
        geofence.stop()
    }

    func markArrival(method: String = "button") {
        guard arrival == nil else { return }
        session?.tabletTap(gesture: "arrival")
    }

    /// The nurse's accept on the handoff card: eTimes.12, stops wall time.
    func nurseAccept() {
        guard handoff == nil else { return }
        session?.tabletTap(gesture: "handoff")
    }

    func manualMark() { session?.tabletTap(gesture: "mark") }

    func label(tap: EarshotEvent, type: EventType, fields: [String: String]) {
        session?.medicEntry(type: type, fields: fields, forTapId: tap.id, at: tap.tMs)
    }

    /// Medic reviewed and signed. Exports stay with the medic; store is wiped.
    func sign() {
        signed = true
        stopCall()
        if let s = session { store.wipe(callId: s.callId); s.wipe() }
        events = []
    }

    // MARK: export

    func exportFiles() -> [URL] {
        guard let s = session else { return [] }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("earshot-\(s.callId)")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var urls: [URL] = []
        for d in s.render() {
            let u = dir.appendingPathComponent(d.name)
            try? d.text.write(to: u, atomically: true, encoding: .utf8); urls.append(u)
        }
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        let u = dir.appendingPathComponent("events.json")
        try? enc.encode(s.events).write(to: u); urls.append(u)
        return urls
    }

    func recordShare(_ urls: [URL], to destination: String) {
        for u in urls {
            let size = (try? FileManager.default.attributesOfItem(atPath: u.path)[.size] as? Int) ?? 0
            ledger.record(what: u.lastPathComponent, destination: destination, bytes: size ?? 0)
        }
    }
}

enum ModelLocator {
    /// Looks in Documents/ (drop-in via Finder/Files), then the app bundle.
    /// Exact name first, then any file starting with `name` (e.g. the data agent's
    /// "whisper-ems-small.en-r16-q5.bin" fills the "whisper-ems-small.en-q5" slot).
    static func find(_ name: String, ext: String) -> URL? {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let bases = [docs, docs.appendingPathComponent("models"), Bundle.main.resourceURL?.appendingPathComponent("Models")].compactMap { $0 }
        for base in bases {
            let u = base.appendingPathComponent("\(name).\(ext)")
            if FileManager.default.fileExists(atPath: u.path) { return u }
        }
        if let u = Bundle.main.url(forResource: name, withExtension: ext) { return u }
        let prefix = name.replacingOccurrences(of: "-q5", with: "")
        for base in bases {
            let files = (try? FileManager.default.contentsOfDirectory(atPath: base.path)) ?? []
            if let f = files.sorted().first(where: { $0.hasPrefix(prefix) && $0.hasSuffix(".\(ext)") }) { return base.appendingPathComponent(f) }
        }
        return nil
    }
}
