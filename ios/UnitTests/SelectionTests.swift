import XCTest
import WebKit
@testable import JapaneseReader

@MainActor final class SelectionTests: XCTestCase {
    private func host(_ view: UIView) -> UIWindow {
        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene {
            window = UIWindow(windowScene: scene)
        } else { window = UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 844)) }
        let controller = UIViewController()
        window.rootViewController = controller
        view.frame = CGRect(x: 0, y: 80, width: 390, height: 500)
        controller.view.addSubview(view)
        window.makeKeyAndVisible()
        return window
    }
    func testPassageSelectionSurvivesLookupAndCanBeAdjusted() async throws {
        let model = ReaderModel()
        let view = UITextView()
        view.isEditable = false; view.isSelectable = true
        view.text = "日本語の勉強"
        let window = host(view)
        defer { window.isHidden = true }
        let first = expectation(description: "first selection searched")
        let second = expectation(description: "adjusted selection searched")
        var calls = 0
        let coordinator = SelectableJapanese.Coordinator { word in
            model.searchSelection(word)
            calls += 1
            if calls == 1 { first.fulfill() } else if calls == 2 { second.fulfill() }
        }
        view.delegate = coordinator
        XCTAssertTrue(view.becomeFirstResponder())
        view.selectedRange = NSRange(location: 0, length: 2)
        coordinator.textViewDidChangeSelection(view)
        await fulfillment(of: [first], timeout: 5)
        try await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertEqual(model.word, "日本")
        XCTAssertTrue(view.isFirstResponder)
        XCTAssertEqual(view.selectedRange, NSRange(location: 0, length: 2))
        view.selectedRange = NSRange(location: 0, length: 3)
        coordinator.textViewDidChangeSelection(view)
        await fulfillment(of: [second], timeout: 5)
        try await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertEqual(model.word, "日本語")
        XCTAssertTrue(view.isFirstResponder)
        XCTAssertEqual(view.selectedRange, NSRange(location: 0, length: 3))
    }
    func testDictionarySelectionBridgeKeepsRangeAndPage() async throws {
        let model = ReaderModel()
        model.showingEntry = true
        let first = expectation(description: "dictionary selection searched")
        let second = expectation(description: "dictionary range adjusted")
        var calls = 0
        let coordinator = DictionaryPage.Coordinator(root: model.dictionaryRoot, code: "TEST") { word in
            model.searchSelection(word)
            calls += 1
            if calls == 1 { first.fulfill() } else if calls == 2 { second.fulfill() }
        }
        let html = DictionaryPage.make(body: "<p id='passage'>日本語の勉強</p><p id='unsafe' onclick=\"document.body.dataset.unsafe='yes'\">unsafe</p>", css: "", code: "TEST")
        let view = DictionaryPage.makeWebView(html: html, coordinator: coordinator)
        let window = host(view)
        defer {
            view.configuration.userContentController.removeScriptMessageHandler(forName: "readerSelection", contentWorld: DictionaryPage.selectionWorld)
            window.isHidden = true
        }
        for _ in 0..<100 {
            if !view.isLoading && view.url != nil { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTAssertFalse(view.configuration.defaultWebpagePreferences.allowsContentJavaScript)
        let select = "const r=document.createRange(); const n=document.getElementById('passage').firstChild; r.setStart(n,0); r.setEnd(n,END); const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);"
        _ = try await view.evaluateJavaScript("(() => {" + select.replacingOccurrences(of: "END", with: "2") + "return true;})()", in: nil, in: DictionaryPage.selectionWorld)
        await fulfillment(of: [first], timeout: 5)
        try await Task.sleep(nanoseconds: 300_000_000)
        var selected = try await view.evaluateJavaScript("window.getSelection().toString()", in: nil, in: DictionaryPage.selectionWorld)
        XCTAssertEqual(selected as? String, "日本")
        XCTAssertEqual(model.word, "日本")
        XCTAssertTrue(model.showingEntry)
        _ = try await view.evaluateJavaScript("(() => {" + select.replacingOccurrences(of: "END", with: "3") + "return true;})()", in: nil, in: DictionaryPage.selectionWorld)
        await fulfillment(of: [second], timeout: 5)
        selected = try await view.evaluateJavaScript("window.getSelection().toString()", in: nil, in: DictionaryPage.selectionWorld)
        XCTAssertEqual(selected as? String, "日本語")
        XCTAssertEqual(model.word, "日本語")
        XCTAssertTrue(model.showingEntry)
        let unsafe = try await view.evaluateJavaScript("document.getElementById('unsafe').click(); document.body.dataset.unsafe || 'blocked'", in: nil, in: DictionaryPage.selectionWorld)
        XCTAssertEqual(unsafe as? String, "blocked")
    }
}
