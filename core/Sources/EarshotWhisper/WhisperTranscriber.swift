import Foundation
import EarshotCore
#if canImport(CWhisper)
import CWhisper
#else
import whisper   // iOS: whisper.xcframework module
#endif

/// whisper.cpp through its C API. Deterministic settings: greedy decoding,
/// temperature 0, no temperature fallback, fixed thread count.
public final class WhisperTranscriber: Transcriber {
    public let modelName: String
    private let ctx: OpaquePointer
    private let threads: Int32

    public init(modelPath: String, name: String? = nil, threads: Int = 4) throws {
        var cp = whisper_context_default_params()
        cp.use_gpu = false
        guard let c = whisper_init_from_file_with_params(modelPath, cp) else {
            throw NSError(domain: "earshot.whisper", code: 1, userInfo: [NSLocalizedDescriptionKey: "cannot load whisper model at \(modelPath)"])
        }
        ctx = c
        self.threads = Int32(threads)
        let base = URL(fileURLWithPath: modelPath).lastPathComponent
        modelName = name ?? "whisper.cpp \(base.replacingOccurrences(of: "ggml-", with: "").replacingOccurrences(of: ".bin", with: ""))"
    }

    deinit { whisper_free(ctx) }

    public func transcribe(_ pcm: [Float], prompt: String?) throws -> [ASRPiece] {
        // whisper needs >= 1 s of audio; pad short chunks with silence
        var audio = pcm
        if audio.count < 16000 + 1600 { audio += [Float](repeating: 0, count: 16000 + 1600 - audio.count) }
        var p = whisper_full_default_params(WHISPER_SAMPLING_GREEDY)
        p.n_threads = threads
        p.print_progress = false
        p.print_realtime = false
        p.print_timestamps = false
        p.print_special = false
        p.translate = false
        p.no_context = true
        p.single_segment = false
        p.temperature = 0
        p.temperature_inc = 0
        p.suppress_blank = true
        p.suppress_nst = true
        p.no_timestamps = false
        let rc: Int32 = "en".withCString { lang in
            p.language = lang
            if let prompt = prompt {
                return prompt.withCString { pp in
                    p.initial_prompt = pp
                    return audio.withUnsafeBufferPointer { whisper_full(ctx, p, $0.baseAddress, Int32($0.count)) }
                }
            }
            return audio.withUnsafeBufferPointer { whisper_full(ctx, p, $0.baseAddress, Int32($0.count)) }
        }
        guard rc == 0 else {
            throw NSError(domain: "earshot.whisper", code: Int(rc), userInfo: [NSLocalizedDescriptionKey: "whisper_full failed (\(rc))"])
        }
        var out: [ASRPiece] = []
        let n = whisper_full_n_segments(ctx)
        for i in 0..<n {
            let text = String(cString: whisper_full_get_segment_text(ctx, i))
            let t0 = Int64(whisper_full_get_segment_t0(ctx, i)) * 10
            let t1 = Int64(whisper_full_get_segment_t1(ctx, i)) * 10
            var lp = 0.0
            let nt = whisper_full_n_tokens(ctx, i)
            var cnt = 0
            for k in 0..<nt {
                let d = whisper_full_get_token_data(ctx, i, k)
                lp += Double(d.plog); cnt += 1
            }
            out.append(ASRPiece(startMs: t0, endMs: t1, text: text, avgLogprob: cnt > 0 ? (lp / Double(cnt) * 1000).rounded() / 1000 : nil))
        }
        return out
    }
}
