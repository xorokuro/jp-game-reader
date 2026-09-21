import SwiftUI
import UniformTypeIdentifiers
import Translation

struct SavedText: Identifiable, Codable {
    var id = UUID()
    var text: String
    var note = ""
    var date = Date()
}

@MainActor final class ReaderModel: ObservableObject {
    @Published var text = ""
    @Published var word = ""
    @Published var hits: [DictionaryHit] = []
    @Published var status = ""
    @Published var dictionaries: [String] = []
    @Published var busy = false
    @Published var saved: [SavedText] = []
    @Published var entryHTML = ""
    @Published var entryCode = ""
    @Published var showingEntry = false
    private var searchGeneration = 0
    private var libraryWritable = true
    let queue = DispatchQueue(label: "JapaneseReader.dictionary", qos: .userInitiated)
    let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    var dictionaryRoot: URL { documents.appendingPathComponent("dictionaries", isDirectory: true) }
    var libraryURL: URL { documents.appendingPathComponent("reading-library.json") }
    init() {
        do {
            try FileManager.default.createDirectory(at: documents, withIntermediateDirectories: true)
            let help = documents.appendingPathComponent("ABOUT THIS FOLDER.txt")
            if !FileManager.default.fileExists(atPath: help.path) {
                try "Japanese Reader\n\nMove the supplied dictionaries folder here, keeping mdict-index.sqlite3 and sources inside it. Then open Library and tap Refresh dictionaries.\n\nSaved passages and notes are in reading-library.json. Copy that file for backup before uninstalling the app.\n".write(to: help, atomically: true, encoding: .utf8)
            }
        } catch { status = "Could not prepare the Files folder: \(error.localizedDescription)" }
        if let bytes = try? Data(contentsOf: libraryURL) {
            do { saved = try JSONDecoder().decode([SavedText].self, from: bytes) }
            catch { libraryWritable = false; status = "The saved library could not be read. Its file has been preserved." }
        }
        reload()
    }
    func reload() {
        let root = dictionaryRoot
        queue.async {
            let result = Result { try DictionaryStore(root: root).catalog().compactMap { $0["name"] } }
            DispatchQueue.main.async {
                switch result {
                case .success(let names): self.dictionaries = names
                case .failure: self.dictionaries = []
                }
            }
        }
    }
    func search() {
        searchGeneration += 1
        let generation = searchGeneration, query = word, root = dictionaryRoot
        guard !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { hits = []; return }
        busy = true
        queue.async {
            let result = Result { try DictionaryStore(root: root).search(query) }
            DispatchQueue.main.async {
                guard generation == self.searchGeneration else { return }
                self.busy = false
                switch result {
                case .success(let hits): self.hits = hits; self.status = hits.isEmpty ? "No match. Try the dictionary form of the word." : ""
                case .failure(let error): self.hits = []; self.status = error.localizedDescription
                }
            }
        }
    }
    func open(_ hit: DictionaryHit) {
        let root = dictionaryRoot
        busy = true
        queue.async {
            let result = Result { () -> String in
                let store = try DictionaryStore(root: root)
                return DictionaryPage.make(body: try store.entry(hit), css: try store.stylesheet(code: hit.code), code: hit.code)
            }
            DispatchQueue.main.async {
                self.busy = false
                switch result {
                case .success(let html): self.entryHTML = html; self.entryCode = hit.code; self.showingEntry = true
                case .failure(let error): self.status = error.localizedDescription
                }
            }
        }
    }
    func persist() {
        guard libraryWritable else { status = "The saved library file needs repair before saving new passages. Copy reading-library.json from Files for safekeeping."; return }
        do { try JSONEncoder().encode(saved).write(to: libraryURL, options: .atomic) }
        catch { status = "Could not save: \(error.localizedDescription)" }
    }
    func save() {
        guard libraryWritable else { persist(); return }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard !saved.contains(where: { $0.text == text }) else { status = "Already in your library."; return }
        saved.insert(SavedText(text: text), at: 0); persist(); status = "Saved to your library."
    }
    func prompt() -> String {
        "Help me study this Japanese passage. Translate into natural English and Traditional Chinese, explain grammar and vocabulary, give readings, and preserve the original Japanese. Do not invent missing context.\n\n\(text)" + (word.isEmpty ? "" : "\n\nFocus on this selected word in context: \(word)")
    }
    func importFolder(_ source: URL) {
        guard !busy else { return }
        busy = true; status = "Copying dictionaries. Keep this app open until it finishes."
        UIApplication.shared.isIdleTimerDisabled = true
        let destination = dictionaryRoot
        queue.async {
            let scoped = source.startAccessingSecurityScopedResource()
            defer { if scoped { source.stopAccessingSecurityScopedResource() } }
            let fm = FileManager.default
            let staging = destination.deletingLastPathComponent().appendingPathComponent("dictionary-import-" + UUID().uuidString)
            let result = Result { () -> Void in
                guard source.standardizedFileURL != destination.standardizedFileURL else { return }
                guard !fm.fileExists(atPath: destination.path) else { throw ReaderError("A dictionaries folder already exists. Use Files to move it out before replacing it; your existing dictionaries have been kept.") }
                let store = try DictionaryStore(root: source)
                guard !(try store.catalog()).isEmpty else { throw ReaderError("This folder contains no indexed dictionaries.") }
                try store.validateFiles()
                try fm.copyItem(at: source, to: staging)
                try DictionaryStore(root: staging).validateFiles()
                try fm.moveItem(at: staging, to: destination)
            }
            try? fm.removeItem(at: staging)
            DispatchQueue.main.async {
                self.busy = false; UIApplication.shared.isIdleTimerDisabled = false
                switch result {
                case .success: self.status = "Dictionaries are on this iPhone. You can read offline."; self.reload()
                case .failure(let error): self.status = error.localizedDescription
                }
            }
        }
    }
}

@main struct JapaneseReaderApp: App {
    @StateObject private var model = ReaderModel()
    var body: some Scene { WindowGroup { ReaderHome().environmentObject(model).tint(Color(red: 0.12, green: 0.48, blue: 0.45)) } }
}

struct ReaderHome: View {
    @EnvironmentObject var model: ReaderModel
    @State private var importing = false
    @State private var translation = false
    @State private var selectedTab = 0
    @State private var editing = true
    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Paste a passage. Select a word to look it up.").font(.subheadline).foregroundStyle(.secondary)
                    Picker("Reading mode", selection: $editing) {
                        Text("Paste / edit").tag(true); Text("Read / select words").tag(false)
                    }.pickerStyle(.segmented)
                    if editing {
                        TextEditor(text: $model.text).font(.system(size: 21)).accessibilityIdentifier("passageEditor").overlay(RoundedRectangle(cornerRadius: 12).stroke(.secondary.opacity(0.3)))
                    } else {
                        SelectableJapanese(text: model.text) { word in
                            model.word = word; model.search()
                        }
                    }
                    HStack {
                        Button("Read") { editing = false; UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }.buttonStyle(.borderedProminent).accessibilityIdentifier("openPassage")
                        Button("Save") { model.save() }.buttonStyle(.bordered)
                        Button("Translate") { translation = true }.buttonStyle(.bordered).disabled(model.text.isEmpty)
                            .translationPresentation(isPresented: $translation, text: model.text)
                    }
                    Button { UIPasteboard.general.string = model.prompt(); model.status = "Learning prompt copied. Paste it into your preferred AI app." } label: { Label("Copy learning prompt", systemImage: "doc.on.doc") }
                    lookup.frame(maxHeight: 240)
                    if !model.status.isEmpty { Text(model.status).font(.footnote).foregroundStyle(.secondary) }
                }.padding().navigationTitle("Japanese Reader")
            }.tabItem { Label("Read", systemImage: "book") }.tag(0)
            NavigationStack {
                VStack { lookup; if !model.status.isEmpty { Text(model.status).font(.footnote).padding() } }
                    .navigationTitle("Dictionary")
            }.tabItem { Label("Look up", systemImage: "magnifyingglass") }.tag(1)
            NavigationStack {
                List {
                    Section("Offline dictionaries · \(model.dictionaries.count)") {
                        Text("Move the supplied dictionaries folder into On My iPhone → Japanese Reader using Files, then tap Refresh. Or import the folder below.").font(.subheadline)
                        Button("Import dictionaries folder") { importing = true }.disabled(model.busy)
                        Button("Refresh dictionaries") { model.reload() }
                        ForEach(model.dictionaries, id: \.self) { Text($0).font(.footnote) }
                    }
                    Section("Saved passages") {
                        ForEach($model.saved) { $item in
                            VStack(alignment: .leading) {
                                Button { model.text = item.text; selectedTab = 0; editing = false } label: { Text(item.text).lineLimit(3).foregroundStyle(.primary) }
                                TextField("Study note", text: $item.note, axis: .vertical).onChange(of: item.note) { model.persist() }
                            }
                        }
                    }
                    Section("Keep a backup") {
                        Text("Your passages and notes are in reading-library.json in Files → On My iPhone → Japanese Reader. Copy this file before uninstalling. Dictionary files can also be copied from here.").font(.footnote)
                    }
                    Section("Translation") {
                        Text("Translate opens Apple's translation panel. Apple may ask you to download languages. Argos and LM Studio from the Windows app are not included in this iPhone edition. Copy learning prompt works with any AI app you choose.").font(.footnote)
                    }
                    if model.busy { ProgressView("Working…") }
                    if !model.status.isEmpty { Text(model.status).font(.footnote) }
                }.navigationTitle("Library & setup")
            }.tabItem { Label("Library", systemImage: "books.vertical") }.tag(2)
        }
        .onChange(of: selectedTab) { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.folder]) { result in
            switch result {
            case .success(let folder): model.importFolder(folder)
            case .failure(let error): model.status = error.localizedDescription
            }
        }
        .sheet(isPresented: $model.showingEntry) {
            NavigationStack {
                DictionaryPage(html: model.entryHTML, root: model.dictionaryRoot, code: model.entryCode) { word in
                    model.showingEntry = false; model.word = word; model.search()
                }.navigationTitle("Dictionary entry").navigationBarTitleDisplayMode(.inline)
                    .toolbar { Button("Done") { model.showingEntry = false } }
            }
        }
    }
    private var lookup: some View {
        VStack {
            HStack {
                TextField("Search Japanese…", text: $model.word).textInputAutocapitalization(.never).autocorrectionDisabled().onSubmit { model.search() }
                Button { model.search() } label: { Image(systemName: "magnifyingglass") }.accessibilityLabel("Search dictionaries")
                if model.busy { ProgressView() }
            }.padding(10).background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
            List(model.hits) { hit in
                Button { model.open(hit) } label: {
                    VStack(alignment: .leading) { Text(hit.word).font(.headline); Text(hit.dictionary).font(.caption).foregroundStyle(.secondary) }
                }
            }.listStyle(.plain)
        }.padding(.horizontal, 4)
    }
}

struct SelectableJapanese: UIViewRepresentable {
    let text: String
    let selected: (String) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(selected) }
    func makeUIView(context: Context) -> UITextView {
        let view = UITextView(); view.isEditable = false; view.isSelectable = true
        view.font = .systemFont(ofSize: 23); view.backgroundColor = .clear; view.delegate = context.coordinator
        return view
    }
    func updateUIView(_ view: UITextView, context: Context) { if view.text != text { view.text = text } }
    final class Coordinator: NSObject, UITextViewDelegate {
        let selected: (String) -> Void
        var pending: DispatchWorkItem?
        init(_ selected: @escaping (String) -> Void) { self.selected = selected }
        func textViewDidChangeSelection(_ textView: UITextView) {
            pending?.cancel()
            guard let range = textView.selectedTextRange, let word = textView.text(in: range), !word.isEmpty, word.count <= 40 else { return }
            let action = DispatchWorkItem { self.selected(word) }
            pending = action; DispatchQueue.main.asyncAfter(deadline: .now() + 0.4, execute: action)
        }
    }
}
