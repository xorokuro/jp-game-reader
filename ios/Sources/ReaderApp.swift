import SwiftUI
import UniformTypeIdentifiers
import Translation

struct SavedText: Identifiable, Codable {
    var id = UUID()
    var text: String
    var note = ""
    var date = Date()
}

struct InstalledDictionary: Identifiable {
    let id: String
    let code: String
    let name: String
    let root: URL
}

@MainActor final class ReaderModel: ObservableObject {
    @Published var text = ""
    @Published var word = ""
    @Published var hits: [DictionaryHit] = []
    @Published var status = ""
    @Published var dictionaries: [InstalledDictionary] = []
    @Published var disabledDictionaries = Set(UserDefaults.standard.stringArray(forKey: "disabledDictionaries") ?? [])
    var dictionaryOrder = UserDefaults.standard.stringArray(forKey: "dictionaryOrder") ?? []
    @Published var entryRoot: URL?
    @Published var busy = false
    @Published var saved: [SavedText] = []
    @Published var autoSave = UserDefaults.standard.bool(forKey: "savePassagesOnRead") {
        didSet { UserDefaults.standard.set(autoSave, forKey: "savePassagesOnRead") }
    }
    @Published private(set) var recentlyDeleted: [SavedText] = []
    @Published var entryHTML = ""
    @Published var entryID = UUID()
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
        let extras = documents.appendingPathComponent("Dictionary Packs", isDirectory: true)
        queue.async {
            let roots = [root] + ((try? FileManager.default.contentsOfDirectory(at: extras, includingPropertiesForKeys: nil)) ?? []).sorted { $0.path < $1.path }
            let items = roots.flatMap { folder -> [InstalledDictionary] in
                guard let catalog = try? DictionaryStore(root: folder).catalog() else { return [] }
                return catalog.compactMap { row in
                    guard let code = row["code"], let name = row["name"] else { return nil }
                    let id = (folder == root ? "base" : folder.lastPathComponent) + ":" + code
                    return InstalledDictionary(id: id, code: code, name: name, root: folder)
                }
            }
            DispatchQueue.main.async {
                let order = self.dictionaryOrder
                self.dictionaries = items.sorted { (order.firstIndex(of: $0.id) ?? Int.max) < (order.firstIndex(of: $1.id) ?? Int.max) }
            }
        }
    }
    func enableDictionary(_ id: String, enabled: Bool) {
        if enabled { disabledDictionaries.remove(id) } else { disabledDictionaries.insert(id) }
        UserDefaults.standard.set(Array(disabledDictionaries), forKey: "disabledDictionaries")
        searchGeneration += 1; hits = []; busy = false
    }
    func moveDictionaries(from: IndexSet, to: Int) {
        dictionaries.move(fromOffsets: from, toOffset: to)
        dictionaryOrder = dictionaries.map(\.id)
        UserDefaults.standard.set(dictionaryOrder, forKey: "dictionaryOrder")
        searchGeneration += 1; hits = []; busy = false
    }
    func searchSelection(_ selected: String) {
        word = selected
        search(dismissKeyboard: false)
    }
    func search(dismissKeyboard: Bool = true) {
        if dismissKeyboard { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
        searchGeneration += 1
        let generation = searchGeneration, query = word
        let selected = dictionaries.filter { !disabledDictionaries.contains($0.id) }
        guard !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { hits = []; return }
        busy = true
        queue.async {
            let result = Result { () -> [DictionaryHit] in
                guard !selected.isEmpty else { throw ReaderError("Enable a dictionary in Library first, or add the dictionaries folder.") }
                return try selected.flatMap { try DictionaryStore(root: $0.root).search(query, codes: [$0.code]) }
            }
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
        let root = hit.root
        busy = true
        queue.async {
            let result = Result { () -> String in
                let store = try DictionaryStore(root: root)
                return DictionaryPage.make(body: try store.entry(hit), css: try store.stylesheet(code: hit.code), code: hit.code)
            }
            DispatchQueue.main.async {
                self.busy = false
                switch result {
                case .success(let html): self.entryHTML = html; self.entryCode = hit.code; self.entryRoot = root; self.entryID = UUID(); self.showingEntry = true
                case .failure(let error): self.status = error.localizedDescription
                }
            }
        }
    }
    @discardableResult private func store(_ passages: [SavedText]) -> Bool {
        guard libraryWritable else { status = "The saved library file needs repair before saving new passages. Copy reading-library.json from Files for safekeeping."; return false }
        do {
            try JSONEncoder().encode(passages).write(to: libraryURL, options: .atomic)
            saved = passages
            return true
        } catch { status = "Could not update your library: \(error.localizedDescription)"; return false }
    }
    func save() {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard !saved.contains(where: { $0.text == text }) else { status = "Already in your library."; return }
        if store([SavedText(text: text)] + saved) { status = "Saved to your library." }
    }
    func readPassage() {
        if autoSave { save() }
        else { status = "Auto-save is off. Tap Save if you want to keep this passage." }
    }
    func updateNote(id: UUID, note: String) {
        var next = saved
        guard let index = next.firstIndex(where: { $0.id == id }) else { return }
        next[index].note = note
        store(next)
    }
    func delete(ids: Set<UUID>) {
        let removed = saved.filter { ids.contains($0.id) }
        guard !removed.isEmpty else { return }
        if store(saved.filter { !ids.contains($0.id) }) {
            recentlyDeleted = removed
            status = "Deleted \(removed.count) saved passage(s). Undo is available below."
        }
    }
    func undoDelete() {
        let existing = Set(saved.map(\.id))
        let restored = recentlyDeleted.filter { !existing.contains($0.id) }
        if store((saved + restored).sorted { $0.date > $1.date }) {
            recentlyDeleted = []; status = "Deleted passages restored."
        }
    }
    func prompt() -> String {
        "Help me study this Japanese passage. Translate into natural English and Traditional Chinese, explain grammar and vocabulary, give readings, and preserve the original Japanese. Do not invent missing context.\n\n\(text)" + (word.isEmpty ? "" : "\n\nFocus on this selected word in context: \(word)")
    }
    func importFolder(_ source: URL) {
        guard !busy else { return }
        busy = true; status = "Copying dictionaries. Keep this app open until it finishes."
        UIApplication.shared.isIdleTimerDisabled = true
        let destination = FileManager.default.fileExists(atPath: dictionaryRoot.path)
            ? documents.appendingPathComponent("Dictionary Packs", isDirectory: true).appendingPathComponent(UUID().uuidString, isDirectory: true)
            : dictionaryRoot
        queue.async {
            let scoped = source.startAccessingSecurityScopedResource()
            defer { if scoped { source.stopAccessingSecurityScopedResource() } }
            let fm = FileManager.default
            let staging = self.documents.appendingPathComponent("dictionary-import-" + UUID().uuidString)
            let result = Result { () -> Void in
                guard source.standardizedFileURL != destination.standardizedFileURL else { return }
                guard !fm.fileExists(atPath: destination.path) else { throw ReaderError("A dictionaries folder already exists. Use Files to move it out before replacing it; your existing dictionaries have been kept.") }
                let store = try DictionaryStore(root: source)
                guard !(try store.catalog()).isEmpty else { throw ReaderError("This folder contains no indexed dictionaries.") }
                try store.validateFiles()
                try fm.copyItem(at: source, to: staging)
                try DictionaryStore(root: staging).validateFiles()
                try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
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
    @State private var librarySearch = ""
    @State private var deleteAll = false
    @FocusState private var passageFocused: Bool
    @Environment(\.colorScheme) private var colorScheme
    @AppStorage("paletteAccent") private var accentRGB = 0x1F7A73
    @AppStorage("palettePaper") private var paperRGB = 0xFFFFFF
    @AppStorage("customReadingPaper") private var customPaper = false
    private var paper: Color { customPaper ? Palette.color(paperRGB) : Color(uiColor: .systemBackground) }
    private var ink: Color { customPaper ? Palette.ink(paperRGB) : .primary }
    private var accent: Color { Palette.accessibleAccent(accentRGB, dark: colorScheme == .dark) }
    private func colorBinding(_ value: Binding<Int>) -> Binding<Color> {
        Binding(get: { Palette.color(value.wrappedValue) }, set: { value.wrappedValue = Palette.rgb($0) })
    }
    private func read() {
        passageFocused = false
        model.readPassage(); editing = false
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }
    private var filteredPassages: [SavedText] {
        guard !librarySearch.isEmpty else { return model.saved }
        return model.saved.filter { $0.text.localizedCaseInsensitiveContains(librarySearch) || $0.note.localizedCaseInsensitiveContains(librarySearch) }
    }
    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        PasteButton(payloadType: String.self) { strings in
                            guard !strings.isEmpty else { return }
                            model.text = strings.joined(separator: "\n")
                            model.status = ""
                            editing = true
                            passageFocused = false
                            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                        }.buttonStyle(.borderedProminent).tint(Palette.color(accentRGB)).foregroundStyle(Palette.ink(accentRGB)).accessibilityIdentifier("pastePassage")
                        Text("Paste Japanese from another app").font(.caption).foregroundStyle(.secondary)
                    }
                    Text("Paste a passage. Select a word to look it up.").font(.subheadline).foregroundStyle(.secondary)
                    Toggle("Auto-save passages", isOn: $model.autoSave).accessibilityIdentifier("autoSavePassages")
                    Text(model.autoSave ? "Saved when you tap Read. Your choice is remembered." : "Off: pasted text stays temporary unless you tap Save.").font(.caption).foregroundStyle(.secondary)
                    Picker("Reading mode", selection: $editing) {
                        Text("Paste / edit").tag(true); Text("Read / select words").tag(false)
                    }.pickerStyle(.segmented)
                    if editing {
                        TextEditor(text: $model.text).scrollContentBackground(.hidden).foregroundStyle(ink).background(paper).font(.system(size: 21)).focused($passageFocused).frame(height: 220).accessibilityIdentifier("passageEditor").overlay(RoundedRectangle(cornerRadius: 12).stroke(.secondary.opacity(0.3)))
                    } else {
                        SelectableJapanese(text: model.text, ink: UIColor(ink), paper: UIColor(paper)) { word in
                            model.searchSelection(word)
                        }.frame(height: 280)
                    }
                    HStack {
                        if !passageFocused { Button("Read") { read() }.buttonStyle(.borderedProminent).tint(Palette.color(accentRGB)).foregroundStyle(Palette.ink(accentRGB)).accessibilityIdentifier("openPassage") }
                        Button("Save") { model.save() }.buttonStyle(.bordered)
                        Button("Translate") { translation = true }.buttonStyle(.bordered).disabled(model.text.isEmpty)
                            .translationPresentation(isPresented: $translation, text: model.text)
                    }
                    Button { UIPasteboard.general.string = model.prompt(); model.status = "Learning prompt copied. Paste it into your preferred AI app." } label: { Label("Copy learning prompt", systemImage: "doc.on.doc") }
                    lookup.frame(height: model.hits.isEmpty ? 56 : 240)
                    if !model.status.isEmpty { Text(model.status).font(.footnote).foregroundStyle(.secondary) }
                }.padding()
                }.scrollDismissesKeyboard(.interactively)
                .navigationTitle("Japanese Reader").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItemGroup(placement: .keyboard) {
                        if passageFocused { Button("Read") { read() }.accessibilityIdentifier("openPassage") }
                        Spacer()
                        Button("Done") {
                            passageFocused = false
                            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                        }.accessibilityIdentifier("dismissKeyboard")
                    }
                }
            }.tabItem { Label("Read", systemImage: "book") }.tag(0)
            NavigationStack {
                VStack { lookup; if !model.status.isEmpty { Text(model.status).font(.footnote).padding() } }
                    .navigationTitle("Dictionary")
            }.tabItem { Label("Look up", systemImage: "magnifyingglass") }.tag(1)
            NavigationStack {
                List {
                    Section("Saved passages · \(model.saved.count)") {
                        if model.saved.isEmpty {
                            Text("No saved passages. Use Save, or turn on Auto-save and tap Read.").foregroundStyle(.secondary).accessibilityIdentifier("emptyLibrary")
                        } else if filteredPassages.isEmpty {
                            Text("No passages match your search.").foregroundStyle(.secondary)
                        }
                        ForEach(filteredPassages) { item in
                            VStack(alignment: .leading, spacing: 6) {
                                Button { model.text = item.text; selectedTab = 0; editing = false } label: { Text(item.text).lineLimit(3).foregroundStyle(.primary) }
                                Text(item.date, style: .date).font(.caption).foregroundStyle(.secondary)
                                TextField("Study note", text: Binding(get: { model.saved.first(where: { $0.id == item.id })?.note ?? "" }, set: { model.updateNote(id: item.id, note: $0) }), axis: .vertical)
                            }
                        }.onDelete { offsets in
                            let ids = Set(offsets.map { filteredPassages[$0].id })
                            model.delete(ids: ids)
                        }
                        if !model.recentlyDeleted.isEmpty { Button("Undo delete") { model.undoDelete() } }
                        if !model.saved.isEmpty {
                            ShareLink(item: model.libraryURL) { Label("Export saved texts", systemImage: "square.and.arrow.up") }
                            Button("Delete all saved passages", role: .destructive) { deleteAll = true }
                        }
                    }
                    Section("Offline dictionaries · \(model.dictionaries.count)") {
                        Text("Move the supplied dictionaries folder into On My iPhone → Japanese Reader using Files, then tap Refresh. Or import the folder below.").font(.subheadline)
                        Button("Add dictionary pack") { importing = true }.disabled(model.busy)
                        Button("Refresh dictionaries") { model.reload() }
                        Text("Switch dictionaries on or off. Tap Edit, then drag the handles to set lookup order. Add another prepared pack without downloading your existing dictionaries again.").font(.caption)
                        HStack {
                            Button("Enable all") { for item in model.dictionaries { model.enableDictionary(item.id, enabled: true) } }
                            Button("Disable all") { for item in model.dictionaries { model.enableDictionary(item.id, enabled: false) } }
                        }
                        ForEach(model.dictionaries) { item in
                            Toggle(item.name, isOn: Binding(get: { !model.disabledDictionaries.contains(item.id) }, set: { model.enableDictionary(item.id, enabled: $0) })).font(.footnote)
                        }.onMove { model.moveDictionaries(from: $0, to: $1) }
                    }
                    Section("Colors & contrast") {
                        ColorPicker("Accent color", selection: colorBinding($accentRGB), supportsOpacity: false).accessibilityIdentifier("accentColor")
                        Toggle("Custom reading background", isOn: $customPaper).accessibilityIdentifier("customPaper")
                        if customPaper {
                            ColorPicker("Reading background", selection: colorBinding($paperRGB), supportsOpacity: false)
                        }
                        Text("日本語 · Reading preview").font(.title3).foregroundStyle(ink).padding().frame(maxWidth: .infinity).background(paper, in: RoundedRectangle(cornerRadius: 10))
                        Text("Text automatically switches between black and white for contrast. Links adjust for light and dark mode. Colors are remembered.").font(.caption)
                        Button("Reset colors") { accentRGB = 0x1F7A73; paperRGB = 0xFFFFFF; customPaper = false }
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
                    .searchable(text: $librarySearch, prompt: "Find saved text or notes")
                    .toolbar { EditButton() }
                    .confirmationDialog("Delete all \(model.saved.count) saved passages and their notes?", isPresented: $deleteAll, titleVisibility: .visible) {
                        Button("Delete all", role: .destructive) { model.delete(ids: Set(model.saved.map(\.id))) }
                        Button("Cancel", role: .cancel) {}
                    }
            }.tabItem { Label("Library", systemImage: "books.vertical") }.tag(2)
        }
        .tint(accent)
        .onChange(of: selectedTab) { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.folder]) { result in
            switch result {
            case .success(let folder): model.importFolder(folder)
            case .failure(let error): model.status = error.localizedDescription
            }
        }
        .sheet(isPresented: $model.showingEntry) {
            NavigationStack {
                VStack(spacing: 0) {
                    DictionaryPage(html: model.entryHTML, root: model.entryRoot ?? model.dictionaryRoot, code: model.entryCode) { word in
                        model.searchSelection(word)
                    }.id(model.entryID)
                    Divider()
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(model.word.isEmpty ? "Select text above to look it up" : "Looking up: " + model.word).font(.subheadline).lineLimit(2).accessibilityIdentifier("entryLookupWord")
                            Spacer()
                            if model.busy { ProgressView() }
                        }.padding(.horizontal)
                        List(model.hits, id: \.identity) { hit in
                            Button { model.open(hit) } label: {
                                VStack(alignment: .leading) { Text(hit.word); Text(hit.dictionary).font(.caption).foregroundStyle(.secondary) }
                            }
                        }.listStyle(.plain)
                        if !model.status.isEmpty { Text(model.status).font(.caption).foregroundStyle(.secondary).padding(.horizontal).lineLimit(2) }
                    }.frame(height: 200).padding(.vertical, 8)
                }.navigationTitle("Dictionary entry").navigationBarTitleDisplayMode(.inline)
                    .toolbar { Button("Done") { model.showingEntry = false } }
            }.presentationDetents([.large])
        }
    }
    private var lookup: some View {
        VStack {
            HStack {
                TextField("Search Japanese…", text: $model.word).textInputAutocapitalization(.never).autocorrectionDisabled().submitLabel(.search).onSubmit { model.search() }
                Button { model.search() } label: { Image(systemName: "magnifyingglass") }.accessibilityLabel("Search dictionaries")
                if model.busy { ProgressView() }
            }.padding(10).background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
            List(model.hits, id: \.identity) { hit in
                Button { model.open(hit) } label: {
                    VStack(alignment: .leading) { Text(hit.word).font(.headline); Text(hit.dictionary).font(.caption).foregroundStyle(.secondary) }
                }
            }.listStyle(.plain)
        }.padding(.horizontal, 4)
    }
}

struct SelectableJapanese: UIViewRepresentable {
    let text: String
    var ink: UIColor = .label
    var paper: UIColor = .systemBackground
    let selected: (String) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(selected) }
    func makeUIView(context: Context) -> UITextView {
        let view = UITextView(); view.isEditable = false; view.isSelectable = true
        view.accessibilityIdentifier = "selectablePassage"
        view.font = .systemFont(ofSize: 23); view.backgroundColor = .clear; view.delegate = context.coordinator
        return view
    }
    func updateUIView(_ view: UITextView, context: Context) {
        if view.text != text { view.text = text }
        if view.textColor != ink { view.textColor = ink }
        if view.backgroundColor != paper { view.backgroundColor = paper }
    }
    final class Coordinator: NSObject, UITextViewDelegate {
        let selected: (String) -> Void
        var pending: DispatchWorkItem?
        init(_ selected: @escaping (String) -> Void) { self.selected = selected }
        func textViewDidChangeSelection(_ textView: UITextView) {
            pending?.cancel()
            guard let range = textView.selectedTextRange, let word = textView.text(in: range), !word.isEmpty, word.count <= 40 else { return }
            let selectedRange = textView.selectedRange
            let action = DispatchWorkItem { [weak textView, weak self] in
                guard let textView, textView.selectedRange == selectedRange else { return }
                self?.selected(word)
            }
            pending = action; DispatchQueue.main.asyncAfter(deadline: .now() + 0.4, execute: action)
        }
    }
}
