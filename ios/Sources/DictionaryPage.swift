import SwiftUI
import WebKit
import UniformTypeIdentifiers

struct DictionaryPage: UIViewRepresentable {
    let html: String
    let root: URL
    let code: String
    let lookup: (String) -> Void
    static func make(body: String, css: String, code: String) -> String {
        // JavaScript is disabled in WKWebView; CSP also prevents external requests.
        let clean = body.replacingOccurrences(of: "(?is)<(script|iframe|object|embed|form|head)\\b[^>]*>.*?</\\1\\s*>", with: "", options: .regularExpression)
            .replacingOccurrences(of: "(?is)<(base|meta|link)\\b[^>]*>", with: "", options: .regularExpression)
        let safeCSS = css.replacingOccurrences(of: "(?is)</style", with: "", options: .regularExpression)
        return """
        <!doctype html><html lang="ja"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src jpread: data:; media-src jpread:; font-src jpread:; style-src 'unsafe-inline' jpread:; script-src 'none'; frame-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'">
        <style>\(safeCSS)</style><style>:root{color-scheme:light dark}body{font:19px -apple-system;line-height:1.65;padding:14px;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{max-width:100%}ddudm,ddudc,ddudt{display:block}a{color:#3987dc}audio{max-width:100%}</style></head><body>\(clean)</body></html>
        """
    }
    func makeCoordinator() -> Coordinator { Coordinator(root: root, code: code, lookup: lookup) }
    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        configuration.websiteDataStore = .nonPersistent()
        configuration.setURLSchemeHandler(context.coordinator, forURLScheme: "jpread")
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.loadHTMLString(html, baseURL: URL(string: "jpread://dictionary/"))
        return view
    }
    func updateUIView(_ view: WKWebView, context: Context) {}
    final class Coordinator: NSObject, WKURLSchemeHandler, WKNavigationDelegate {
        let root: URL
        let code: String
        let lookup: (String) -> Void
        let queue = DispatchQueue(label: "JapaneseReader.media")
        var cancelled = Set<ObjectIdentifier>()
        init(root: URL, code: String, lookup: @escaping (String) -> Void) { self.root = root; self.code = code; self.lookup = lookup }
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
                lookup(value); decisionHandler(.cancel)
            } else if action.navigationType == .other && (url.scheme == "about" || url.scheme == "jpread") { decisionHandler(.allow) }
            else { decisionHandler(.cancel) }
        }
    }
}
