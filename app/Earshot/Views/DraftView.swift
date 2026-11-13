import SwiftUI
import EarshotCore

/// The four outputs as tabs. Tap any line to see its receipt(s).
struct DraftView: View {
    @Environment(AppModel.self) var model
    @State private var tab = 0
    @State private var receipt: EarshotEvent?
    @State private var shareURLs: [URL] = []
    @State private var sharing = false
    @State private var confirmSign = false
    var body: some View {
        NavigationStack {
            let docs = model.session?.render() ?? []
            VStack(spacing: 0) {
                Picker("Output", selection: $tab) {
                    Text("SOAP").tag(0); Text("CHART").tag(1); Text("IMIST-AMBO").tag(2); Text("NEMSIS XML").tag(3)
                }.pickerStyle(.segmented).padding()
                if docs.count == 4 {
                    let d = docs[tab]
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(Array(d.text.split(separator: "\n", omittingEmptySubsequences: false).enumerated()), id: \.offset) { i, line in
                                let ids = d.receipts[i] ?? []
                                Text(String(line))
                                    .font(tab == 3 ? .caption.monospaced() : .body)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.vertical, 2)
                                    .background(ids.isEmpty ? Color.clear : Color.accentColor.opacity(0.06))
                                    .onTapGesture { if let id = ids.first { receipt = model.events.first { $0.id == id } } }
                            }
                        }.padding(.horizontal)
                    }
                } else {
                    ContentUnavailableView("No call yet", systemImage: "doc.text", description: Text("Start a call on the Connect tab."))
                }
            }
            .navigationTitle("Draft")
            .toolbar {
                Button("Export", systemImage: "square.and.arrow.up") { shareURLs = model.exportFiles(); sharing = !shareURLs.isEmpty }
                Button("Review & sign") { confirmSign = true }.disabled(model.session == nil)
            }
            .sheet(item: $receipt) { ReceiptView(event: $0, clock: model.session?.clock) }
            .sheet(isPresented: $sharing) {
                ShareSheet(items: shareURLs) { activity in model.recordShare(shareURLs, to: activity ?? "share sheet") }
            }
            .confirmationDialog("Sign this draft?", isPresented: $confirmSign) {
                Button("I reviewed it — sign and wipe", role: .destructive) { model.sign() }
            } message: {
                Text("Export first. Signing wipes the timeline and transcript from this iPad.")
            }
        }
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [URL]
    let completed: (String?) -> Void
    func makeUIViewController(context: Context) -> UIActivityViewController {
        let vc = UIActivityViewController(activityItems: items, applicationActivities: nil)
        vc.completionWithItemsHandler = { type, done, _, _ in if done { completed(type?.rawValue) } }
        return vc
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
