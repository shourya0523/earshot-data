import Foundation
import EarshotCore
#if canImport(FoundationModels)
import FoundationModels
#endif

/// Optional Apple Foundation Models layer. It may only (a) suggest a label
/// for an unlabeled tap and (b) write narrative prose. Every suggestion must
/// cite a raw span id that exists in the transcript, or it is discarded.
/// Suggestions are shown to the medic as "suggested"; they never become
/// events until the medic accepts them (then they are medic-entered).
struct TapLabelSuggestion: Equatable {
    var tapId: String
    var type: String
    var text: String
    var rawSpan: String
    var quote: String
}

enum FoundationModelsLabeler {
    static var isAvailable: Bool {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) { return SystemLanguageModel.default.isAvailable }
        #endif
        return false
    }

    static func suggest(tap: EarshotEvent, context: [RawSegment]) async -> TapLabelSuggestion? {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *), SystemLanguageModel.default.isAvailable, !context.isEmpty {
            let session = LanguageModelSession(instructions: """
            You label moments an EMT marked on a timeline. Use ONLY the transcript lines given. \
            If no line says what happened, answer with span_id "none". Never diagnose. Never invent numbers.
            """)
            let lines = context.map { "[\($0.id)] \($0.text)" }.joined(separator: "\n")
            let prompt = "Marked at t=\(tap.tMs / 1000)s. Transcript:\n\(lines)\nWhat was marked?"
            guard let r = try? await session.respond(to: prompt, generating: GenLabel.self) else { return nil }
            let g = r.content
            // citation check: the span must exist and the quote must be inside it
            guard let seg = context.first(where: { $0.id == g.span_id }), !g.quote.isEmpty,
                  seg.text.lowercased().contains(g.quote.lowercased()) else { return nil }
            return TapLabelSuggestion(tapId: tap.id, type: g.type, text: g.label, rawSpan: seg.id, quote: g.quote)
        }
        #endif
        return nil
    }
}

#if canImport(FoundationModels)
@available(iOS 26.0, *)
@Generable
struct GenLabel {
    @Guide(description: "Transcript span id that says what happened, e.g. s12, or none")
    var span_id: String
    @Guide(description: "Exact words copied from that span")
    var quote: String
    @Guide(description: "One of: vitals, medication, procedure, status")
    var type: String
    @Guide(description: "Short label, e.g. 'aspirin 324 PO'")
    var label: String
}
#endif
