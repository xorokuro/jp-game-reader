import XCTest

final class ReaderUITests: XCTestCase {
    func testReadSaveAndSearchWithoutDictionary() {
        let app = XCUIApplication()
        app.launch()
        let editor = app.textViews.firstMatch
        XCTAssertTrue(editor.waitForExistence(timeout: 10))
        editor.tap()
        editor.typeText("Japanese reading test")
        app.buttons["Read"].firstMatch.tap()
        app.buttons["Save"].tap()
        app.tabBars.buttons["Library"].tap()
        XCTAssertTrue(app.buttons["Japanese reading test"].waitForExistence(timeout: 5))
        app.terminate()
        app.launch()
        app.tabBars.buttons["Library"].tap()
        XCTAssertTrue(app.buttons["Japanese reading test"].waitForExistence(timeout: 5))
        app.tabBars.buttons["Look up"].tap()
        let search = app.textFields["Search Japanese…"]
        search.tap(); search.typeText("test\n")
        XCTAssertTrue(app.staticTexts["Add the dictionaries folder in Library first."].waitForExistence(timeout: 10))
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }
}
