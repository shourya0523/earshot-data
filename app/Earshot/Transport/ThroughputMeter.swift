import Foundation
import EarshotCore

/// Link quality for the status screen and the throughput test mode:
/// kbps over a 2 s window, audio packet loss from sequence gaps, and
/// latency (arrival time vs clip time, relative to the first packet).
final class ThroughputMeter {
    private var window: [(Date, Int)] = []
    private var unwrap = SeqUnwrapper()
    private var firstSeq: Int64?
    private var lastSeq: Int64 = 0
    private var received = 0
    private var firstArrival: Date?
    private var firstClip: UInt32 = 0
    private var lastReport = Date.distantPast
    private(set) var latencyMs: Double = 0
    private(set) var maxLatencyMs: Double = 0
    private let lock = NSLock()

    func record(_ p: Packet, bytes: Int) {
        lock.lock(); defer { lock.unlock() }
        let now = Date()
        window.append((now, bytes))
        window.removeAll { now.timeIntervalSince($0.0) > 2 }
        guard case .audio(let h, _) = p else { return }
        let s = unwrap.unwrap(h.seq)
        if firstSeq == nil { firstSeq = s; firstArrival = now; firstClip = h.clipMs }
        lastSeq = max(lastSeq, s); received += 1
        // relative one-way latency: how far arrival lags the clip's own clock
        let expected = firstArrival!.addingTimeInterval(Double(h.clipMs &- firstClip) / 1000)
        latencyMs = max(0, now.timeIntervalSince(expected) * 1000)
        maxLatencyMs = max(maxLatencyMs, latencyMs)
    }
    var kbps: Double {
        lock.lock(); defer { lock.unlock() }
        guard let f = window.first, let l = window.last, l.0 > f.0 else { return 0 }
        return Double(window.reduce(0) { $0 + $1.1 } * 8) / l.0.timeIntervalSince(f.0) / 1000
    }
    var lossPct: Double {
        lock.lock(); defer { lock.unlock() }
        guard let f = firstSeq else { return 0 }
        let expected = lastSeq - f + 1
        return expected > 0 ? max(0, Double(expected - Int64(received)) / Double(expected) * 100) : 0
    }
    var shouldReport: Bool {
        let n = Date(); if n.timeIntervalSince(lastReport) > 1 { lastReport = n; return true }; return false
    }
}
