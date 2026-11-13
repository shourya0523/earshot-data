import SwiftUI
import EarshotCore

struct SettingsView: View {
    @Environment(AppModel.self) var model
    var body: some View {
        @Bindable var m = model
        NavigationStack {
            Form {
                Section {
                    Picker("Speech model", selection: $m.asrSlot) {
                        ForEach(ModelSlot.allCases) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.segmented)
                    LabeledContent("Stock", value: ModelLocator.find("ggml-small.en", ext: "bin") != nil ? "ggml-small.en.bin ✓" : "missing")
                    LabeledContent("Fine-tuned", value: ModelLocator.find("whisper-ems-small.en-q5", ext: "bin") != nil ? "whisper-ems-small.en-q5.bin ✓" : "not installed (stock is used)")
                    Toggle("Drug tagger (EMSTagger)", isOn: $m.useTagger)
                        .disabled(ModelLocator.find("EMSTagger", ext: "mlpackage") == nil)
                    Toggle("Apple Intelligence tap suggestions", isOn: $m.useFoundationModels)
                        .disabled(!FoundationModelsLabeler.isAvailable)
                } header: { Text("Models (A/B)") } footer: {
                    Text("Changes apply to the next call. Drop model files into the app's Documents folder (Files app) or the models folder in Xcode.")
                }
                Section("Destination (arrival geofence)") {
                    TextField("Name", text: $m.destinationName)
                    TextField("Latitude", value: $m.destinationLat, format: .number)
                    TextField("Longitude", value: $m.destinationLon, format: .number)
                }
                Section("About") {
                    LabeledContent("Extractor", value: RulesExtractor.version)
                    LabeledContent("Dictionary", value: model.dict.version)
                    Text("Earshot documents only. It never diagnoses or advises, and nothing is filed until the medic signs.").font(.footnote)
                }
            }
            .navigationTitle("Settings")
        }
    }
}
