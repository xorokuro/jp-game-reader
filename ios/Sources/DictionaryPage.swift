import SwiftUI
import WebKit
import UniformTypeIdentifiers

struct DictionaryPage: UIViewRepresentable {
    let html: String
    let root: URL
    let code: String
    var paperRGB: Int? = nil
    var followLink: ((String) -> Void)? = nil
    let lookup: (String) -> Void
    static func audioLinks(_ source: String) -> String {
        guard let pattern = try? NSRegularExpression(pattern: "(?is)<a\\b[^>]*href=[\"']sound://([^\"']+)[\"'][^>]*>.*?</a>") else { return source }
        var result = source
        for match in pattern.matches(in: source, range: NSRange(source.startIndex..., in: source)).reversed() {
            guard let range = Range(match.range, in: result), let nameRange = Range(match.range(at: 1), in: source) else { continue }
            let name = String(source[nameRange]).replacingOccurrences(of: "\\", with: "/").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? ""
            result.replaceSubrange(range, with: "<audio controls preload=\"none\" src=\"jpread://dictionary/\(encoded)\"></audio>")
        }
        return result
    }
    static func make(body: String, css: String, code: String) -> String {
        // Dictionary-authored JavaScript is disabled; only our isolated selection observer runs.
        // CSP continues to prevent external requests and page scripts.
        let clean = body.replacingOccurrences(of: "(?is)<(script|iframe|object|embed|form|head)\\b[^>]*>.*?</\\1\\s*>", with: "", options: .regularExpression)
            .replacingOccurrences(of: "(?is)<(base|meta|link)\\b[^>]*>", with: "", options: .regularExpression)
        let safeCSS = css.replacingOccurrences(of: "(?is)</style", with: "", options: .regularExpression)
        let rendered = audioLinks(clean)
        return """
        <!doctype html><html lang="ja"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src jpread: data:; media-src jpread:; font-src jpread:; style-src 'unsafe-inline' jpread:; script-src 'none'; frame-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'">
        <style>\(safeCSS)</style><style>:root{color-scheme:light dark}body{font:19px -apple-system;line-height:1.65;padding:14px;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{max-width:100%}ddudm,ddudc,ddudt{display:block}a{color:#3987dc}audio{max-width:100%}body,body *{-webkit-user-select:text;user-select:text}::selection{background:#93c5fd;color:#111}</style></head><body>\(rendered)</body></html>
        """
    }
    static let selectionWorld = WKContentWorld.world(name: "JapaneseReaderSelection")
    static let selectionScript = """
    (() => {
        let pending, previous = "";
        document.addEventListener("selectionchange", () => {
            clearTimeout(pending);
            const text = window.getSelection()?.toString().trim() || "";
            if (!text || Array.from(text).length > 40) { previous = ""; window.webkit.messageHandlers.readerSelection.postMessage(""); return; }
            pending = setTimeout(() => {
                const current = window.getSelection()?.toString().trim() || "";
                if (current !== text || current === previous) return;
                previous = current;
                window.webkit.messageHandlers.readerSelection.postMessage(current);
            }, 400);
        });
    })();
    """
    func makeCoordinator() -> Coordinator { Coordinator(root: root, code: code, followLink: followLink, lookup: lookup) }
    static func makeWebView(html: String, coordinator: Coordinator) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        configuration.websiteDataStore = .nonPersistent()
        configuration.setURLSchemeHandler(coordinator, forURLScheme: "jpread")
        configuration.userContentController.add(coordinator, contentWorld: selectionWorld, name: "readerSelection")
        configuration.userContentController.addUserScript(WKUserScript(source: selectionScript, injectionTime: .atDocumentEnd, forMainFrameOnly: true, in: selectionWorld))
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.accessibilityIdentifier = "dictionaryEntryPage"
        view.navigationDelegate = coordinator
        view.loadHTMLString(html, baseURL: URL(string: "jpread://dictionary/"))
        return view
    }
    func makeUIView(context: Context) -> WKWebView { Self.makeWebView(html: html, coordinator: context.coordinator) }
    // Search results update the surrounding SwiftUI view. Never reload the document
    // here: that would discard the native selection handles and scroll position.
    func updateUIView(_ view: WKWebView, context: Context) {
        context.coordinator.lookup = lookup
        context.coordinator.followLink = followLink
        view.backgroundColor = paperRGB.map { UIColor(Palette.color($0)) } ?? .systemBackground
        view.scrollView.backgroundColor = view.backgroundColor
        context.coordinator.paperRGB = paperRGB
        context.coordinator.applyPaper(view)
    }
    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        view.configuration.userContentController.removeScriptMessageHandler(forName: "readerSelection", contentWorld: selectionWorld)
        view.stopLoading()
    }
    final class Coordinator: NSObject, WKURLSchemeHandler, WKNavigationDelegate, WKScriptMessageHandler {
        let root: URL
        let code: String
        var lookup: (String) -> Void
        var followLink: ((String) -> Void)?
        var paperRGB: Int?
        func applyPaper(_ view: WKWebView) {
            let css: String
            if let rgb = paperRGB {
                let hex = String(format: "#%06X", rgb & 0xFFFFFF)
                let ink = Palette.luminance(Palette.channels(rgb)) < 0.179 ? "#ffffff" : "#000000"
                css = "html,body{background:\(hex)!important;color:\(ink)!important}body *{background-color:transparent!important;color:inherit!important}a{text-decoration:underline!important}"
            } else { css = "" }
            let script = "(() => {let s=document.getElementById('reader-palette');if(!s){s=document.createElement('style');s.id='reader-palette';document.head.appendChild(s);}s.textContent='\(css)';})()"
            view.evaluateJavaScript(script, in: nil, in: DictionaryPage.selectionWorld, completionHandler: nil)
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { applyPaper(webView) }
        let queue = DispatchQueue(label: "JapaneseReader.media")
        var cancelled = Set<ObjectIdentifier>()
        init(root: URL, code: String, followLink: ((String) -> Void)? = nil, lookup: @escaping (String) -> Void) { self.root = root; self.code = code; self.lookup = lookup; self.followLink = followLink }
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "readerSelection", message.frameInfo.isMainFrame,
                  let text = message.body as? String else { return }
            let word = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard word.count <= 40 else { return }
            lookup(word)
        }
        func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask) {
            let id = ObjectIdentifier(urlSchemeTask)
            cancelled.remove(id)
            let url = urlSchemeTask.request.url!
            queue.async {
                let result = Result { try DictionaryStore(root: self.root).media(code: self.code, name: url.path) }
                DispatchQueue.main.async {
                    guard !self.cancelled.contains(id) else { self.cancelled.remove(id); return }
                    switch result {
                    case .success(let data):
                        let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
                        urlSchemeTask.didReceive(URLResponse(url: url, mimeType: mime, expectedContentLength: data.count, textEncodingName: nil))
                        urlSchemeTask.didReceive(data); urlSchemeTask.didFinish()
                    case .failure(let error): urlSchemeTask.didFailWithError(error)
                    }
                }
            }
        }
        func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) { cancelled.insert(ObjectIdentifier(urlSchemeTask)) }
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { decisionHandler(.cancel); return }
            if url.scheme == "entry" {
                let value = String(url.absoluteString.dropFirst("entry://".count)).components(separatedBy: "#")[0].removingPercentEncoding ?? ""
                (followLink ?? lookup)(value); decisionHandler(.cancel)
            } else if action.navigationType == .other && (url.scheme == "about" || url.scheme == "jpread") { decisionHandler(.allow) }
            else { decisionHandler(.cancel) }
        }
    }
}
