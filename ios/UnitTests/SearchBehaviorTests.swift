import XCTest
import SQLite3
@testable import JapaneseReader

@MainActor final class SearchBehaviorTests: XCTestCase {
    private func fixture() throws -> (ReaderModel, URL, String) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let dictionaries = root.appendingPathComponent("dictionaries")
        try FileManager.default.createDirectory(at: dictionaries, withIntermediateDirectories: true)
        try Data().write(to: dictionaries.appendingPathComponent("test.mdx"))
        var db: OpaquePointer?
        XCTAssertEqual(sqlite3_open(dictionaries.appendingPathComponent("mdict-index.sqlite3").path, &db), SQLITE_OK)
        defer { sqlite3_close(db) }
        let sql = """
        CREATE TABLE dictionaries(code TEXT,name TEXT,root TEXT,css TEXT);
        CREATE TABLE files(id INTEGER,code TEXT,path TEXT,kind TEXT,size INTEGER,encoding TEXT);
        CREATE TABLE records(id INTEGER,file INTEGER,word TEXT,norm TEXT,start INTEGER,end INTEGER);
        CREATE TABLE blocks(file INTEGER,start INTEGER,end INTEGER,offset INTEGER,size INTEGER);
        INSERT INTO dictionaries VALUES('TEST','Test dictionary','.','');
        INSERT INTO files VALUES(1,'TEST','test.mdx','.mdx',0,'utf-8');
        INSERT INTO records VALUES(1,1,'原因','原因',0,0);
        INSERT INTO records VALUES(2,1,'原因論','原因論',0,0);
        """
        XCTAssertEqual(sqlite3_exec(db, sql, nil, nil, nil), SQLITE_OK)
        let suite = "SearchBehaviorTests." + UUID().uuidString
        let model = ReaderModel(documents: root, preferences: UserDefaults(suiteName: suite)!)
        return (model, root, suite)
    }
    private func settle(_ model: ReaderModel) async throws {
        // A serial queue barrier delivers completion after all queued lookups.
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            model.queue.async { DispatchQueue.main.async { continuation.resume() } }
        }
    }
    func testIndependentDefaultsPersistenceAndManualSearch() async throws {
        let (model, root, suite) = try fixture()
        defer { try? FileManager.default.removeItem(at: root); UserDefaults.standard.removePersistentDomain(forName: suite) }
        try await settle(model)
        XCTAssertTrue(model.readerAutoSearch)
        XCTAssertTrue(model.dictionaryAutoSearch)
        model.readerAutoSearch = false
        model.select("原", inDictionary: false)
        XCTAssertEqual(model.readerSelection, "原")
        XCTAssertFalse(model.showingLookup)
        XCTAssertTrue(model.dictionaryAutoSearch)
        model.searchSelected(inDictionary: false)
        try await settle(model)
        XCTAssertTrue(model.showingLookup)
        XCTAssertEqual(model.hits.map(\.word), ["原因", "原因論"])
        model.closeLookup()
        model.select("原因", inDictionary: true)
        try await settle(model)
        XCTAssertTrue(model.showingLookup)
        XCTAssertFalse(model.showingEntry)
        model.closeLookup()
        model.dictionaryAutoSearch = false
        model.readerAutoSearch = true
        model.select("原因", inDictionary: true)
        XCTAssertFalse(model.showingLookup)
        model.select("原因", inDictionary: false)
        try await settle(model)
        XCTAssertTrue(model.showingLookup)
        let restored = ReaderModel(documents: root, preferences: UserDefaults(suiteName: suite)!)
        try await settle(restored)
        XCTAssertTrue(restored.readerAutoSearch)
        XCTAssertFalse(restored.dictionaryAutoSearch)
    }
    func testNoMatchAndCancelledSearchDoNotNavigate() async throws {
        let (model, root, suite) = try fixture()
        defer { try? FileManager.default.removeItem(at: root); UserDefaults.standard.removePersistentDomain(forName: suite) }
        try await settle(model)
        model.select("not found", inDictionary: false)
        try await settle(model)
        XCTAssertFalse(model.showingLookup)
        XCTAssertTrue(model.hits.isEmpty)
        model.select("原因", inDictionary: false)
        model.closeLookup()
        try await settle(model)
        XCTAssertFalse(model.showingLookup)
        model.select("原因", inDictionary: false)
        model.readerAutoSearch = false
        try await settle(model)
        XCTAssertFalse(model.showingLookup)
    }
}
