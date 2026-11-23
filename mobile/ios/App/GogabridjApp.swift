// 고가브릿지 아이폰 앱 — 셀러 콘솔(/seller/m)을 앱 셸로 감싼다.
// 들어 있는 것: 먹색(#1a1714) 배경·밝은 상태바·safe-area · 뒤로 스와이프 · 당겨서 새로고침 · 오프라인 안내 ·
// 바깥 링크는 시스템 브라우저 · 구글/카카오/네이버 로그인은 ASWebAuthenticationSession(웹뷰 차단 회피) ·
// 로그인 세션을 공유 확장과 나눠 씀(키체인 공유) · 푸시 알림(APNs) 토큰 서버 등록 · gogabridj://open?path=… 딥링크.
import SwiftUI
import WebKit
import AuthenticationServices
import UserNotifications
import UIKit

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    static var pushToken: String?
    static var pendingPath: String?
    static var onPath: ((String) -> Void)?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { ok, _ in
            if ok { DispatchQueue.main.async { application.registerForRemoteNotifications() } }
        }
        return true
    }
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        AppDelegate.pushToken = deviceToken.map { String(format: "%02x", $0) }.joined()
        NotificationCenter.default.post(name: .kgPushToken, object: nil)
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }
    // 알림을 누르면 그 화면으로 (서버가 payload 에 "path" 를 넣는다)
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        if let p = response.notification.request.content.userInfo["path"] as? String { AppDelegate.route(p) }
        completionHandler()
    }
    static func route(_ path: String) {
        DispatchQueue.main.async { if let f = onPath { f(path) } else { pendingPath = path } }
    }
}
extension Notification.Name { static let kgPushToken = Notification.Name("kgPushToken") }

@main
struct GogabridjApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate
    var body: some Scene {
        WindowGroup {
            ShellScreen()
                .preferredColorScheme(.dark)
                .onOpenURL { url in
                    // gogabridj://open?path=/seller/m/item/123  (공유 확장·알림에서 들어옴)
                    guard url.scheme == KG.scheme else { return }
                    let p = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "path" }?.value
                    if let p = p, p.hasPrefix("/") { AppDelegate.route(p) }
                }
        }
    }
}

let kgBG = UIColor(red: 0x1a / 255.0, green: 0x17 / 255.0, blue: 0x14 / 255.0, alpha: 1)

final class ShellModel: ObservableObject {
    @Published var progress: Double = 0
    @Published var offline = false
    weak var web: WKWebView?
    func load(_ path: String) { web?.load(URLRequest(url: URL(string: path, relativeTo: KG.base)!.absoluteURL)) }
    func reload() { offline = false; if web?.url == nil { load(KG.startPath) } else { web?.reload() } }
}

struct ShellScreen: View {
    @StateObject var m = ShellModel()
    var body: some View {
        ZStack(alignment: .top) {
            Color(kgBG).ignoresSafeArea()
            WebView(m: m)
            if m.progress > 0 && m.progress < 1 {
                ProgressView(value: m.progress).progressViewStyle(.linear).tint(Color(red: 0.79, green: 0.64, blue: 0.29)).frame(height: 2)
            }
            if m.offline {
                VStack(spacing: 14) {
                    Image(systemName: "wifi.slash").font(.system(size: 44)).foregroundStyle(.secondary)
                    Text("연결할 수 없습니다").font(.title3.weight(.semibold))
                    Text("인터넷 연결을 확인한 뒤 다시 시도하세요.\n담아 둔 상품은 서버에 그대로 있습니다.").font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    Button { UIImpactFeedbackGenerator(style: .light).impactOccurred(); m.reload() } label: {
                        Text("다시 시도").font(.headline).padding(.horizontal, 22).padding(.vertical, 10)
                    }.buttonStyle(.borderedProminent).buttonBorderShape(.capsule)
                }
                .padding(28).frame(maxWidth: .infinity, maxHeight: .infinity).background(Color(kgBG))
            }
        }
    }
}

struct WebView: UIViewRepresentable {
    @ObservedObject var m: ShellModel
    func makeCoordinator() -> Coord { Coord(m) }
    func makeUIView(context: Context) -> WKWebView {
        let c = WKWebViewConfiguration()
        c.allowsInlineMediaPlayback = true
        c.websiteDataStore = .default()
        c.userContentController.add(context.coordinator, name: "kg")
        // 웹이 "앱 안"인지 알 수 있게
        c.userContentController.addUserScript(WKUserScript(source: "window.KG_APP={platform:'ios',version:'\(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") ?? "")'};document.documentElement.classList.add('kg-app');", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        c.applicationNameForUserAgent = "Version/18.6 Mobile/15E148 Safari/604.1 GogabridjApp/1"
        let w = WKWebView(frame: .zero, configuration: c)
        w.isOpaque = false; w.backgroundColor = kgBG; w.scrollView.backgroundColor = kgBG
        w.allowsBackForwardNavigationGestures = true
        w.navigationDelegate = context.coordinator; w.uiDelegate = context.coordinator
        let rc = UIRefreshControl(); rc.tintColor = .lightGray
        rc.addTarget(context.coordinator, action: #selector(Coord.pull(_:)), for: .valueChanged)
        w.scrollView.refreshControl = rc
        context.coordinator.obs = w.observe(\.estimatedProgress) { v, _ in DispatchQueue.main.async { m.progress = v.estimatedProgress } }
        m.web = w
        context.coordinator.web = w
        let mm = m
        AppDelegate.onPath = { [weak mm] p in mm?.load(p) }
        if let p = AppDelegate.pendingPath { AppDelegate.pendingPath = nil; m.load(p) } else { m.load(KG.startPath) }
        NotificationCenter.default.addObserver(context.coordinator, selector: #selector(Coord.pushTokenArrived), name: .kgPushToken, object: nil)
        return w
    }
    func updateUIView(_ w: WKWebView, context: Context) {}

    @MainActor final class Coord: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, ASWebAuthenticationPresentationContextProviding {
        let m: ShellModel; var obs: NSKeyValueObservation?; weak var web: WKWebView?
        var auth: ASWebAuthenticationSession?
        var sentPush: String?
        init(_ m: ShellModel) { self.m = m }

        @objc func pull(_ rc: UIRefreshControl) { UIImpactFeedbackGenerator(style: .medium).impactOccurred(); m.reload(); DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { rc.endRefreshing() } }
        @objc func pushTokenArrived() { sharePushToken() }

        private func ours(_ u: URL) -> Bool { guard let h = u.host else { return true }; return h == KG.host || h.hasSuffix("." + KG.host) }

        func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let u = a.request.url else { return decisionHandler(.allow) }
            let s = u.scheme?.lowercased() ?? ""
            if !["http", "https", "about", "blob", "data"].contains(s) { UIApplication.shared.open(u); return decisionHandler(.cancel) }
            // 소셜 로그인 시작 버튼 → 앱 밖 안전한 로그인 창(ASWebAuthenticationSession)
            if ours(u), let prov = Self.oauthProvider(u.path) { startOAuth(prov, next: Self.nextParam(u)); return decisionHandler(.cancel) }
            // 사용자가 눌러서 바깥 사이트로 → 시스템 브라우저
            if a.navigationType == .linkActivated && !ours(u) && a.targetFrame?.isMainFrame != false {
                UIApplication.shared.open(u); return decisionHandler(.cancel)
            }
            decisionHandler(.allow)
        }
        static func oauthProvider(_ path: String) -> String? {
            for p in ["google", "kakao", "naver"] where path.hasPrefix("/auth/\(p)/start") || path == "/auth/\(p)" || path == "/auth/\(p)/login" { return p }
            return nil
        }
        static func nextParam(_ u: URL) -> String {
            let n = URLComponents(url: u, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "next" }?.value
            return (n?.hasPrefix("/") == true) ? n! : KG.startPath
        }
        func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let u = a.request.url { if ours(u) || a.navigationType != .linkActivated { w.load(a.request) } else { UIApplication.shared.open(u) } }
            return nil
        }
        func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
            m.offline = false
            if let u = w.url, ours(u) { saveSession(); sharePushToken() }
        }
        func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { fail(e) }
        func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { fail(e) }
        private func fail(_ e: Error) { let c = (e as NSError).code; if c != NSURLErrorCancelled && c != 102 { m.offline = true } }

        // ── 로그인: 구글·카카오·네이버 ──
        // 서버 약속: /auth/<p>/start?app=1&next=… 로 시작하면 끝에 gogabridj://auth?code=<1회용> 으로 돌려준다.
        //           웹뷰가 /auth/app/exchange?code=…&next=… 를 열면 세션 쿠키를 심고 next 로 보낸다.
        func startOAuth(_ provider: String, next: String) {
            var c = URLComponents(url: KG.base.appendingPathComponent("/auth/\(provider)/start"), resolvingAgainstBaseURL: false)!
            c.queryItems = [URLQueryItem(name: "app", value: "1"), URLQueryItem(name: "next", value: next)]
            let s = ASWebAuthenticationSession(url: c.url!, callbackURLScheme: KG.scheme) { [weak self] cb, err in
                guard let self = self else { return }
                DispatchQueue.main.async {
                    guard let cb = cb, let code = URLComponents(url: cb, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "code" })?.value else { return }
                    var x = URLComponents(url: KG.base.appendingPathComponent("/auth/app/exchange"), resolvingAgainstBaseURL: false)!
                    x.queryItems = [URLQueryItem(name: "code", value: code), URLQueryItem(name: "next", value: next)]
                    self.web?.load(URLRequest(url: x.url!))
                }
            }
            s.presentationContextProvider = self
            s.prefersEphemeralWebBrowserSession = false
            auth = s
            s.start()
        }
        nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
            MainActor.assumeIsolated {
                UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }.first ?? ASPresentationAnchor()
            }
        }

        // ── 로그인 세션을 공유 확장과 나눠 쓴다 ──
        func saveSession() {
            WKWebsiteDataStore.default().httpCookieStore.getAllCookies { cookies in
                let mine = cookies.filter { $0.domain.hasSuffix(KG.host) }
                Vault.cookieHeader = mine.map { "\($0.name)=\($0.value)" }.joined(separator: "; ")
            }
            // 개인 토큰(있으면): 서버 /api/app/token 이 로그인된 세션에 토큰을 내준다. 없으면 쿠키만으로 간다.
            if Vault.token == nil {
                web?.callAsyncJavaScript("try{const r=await fetch('/api/app/token',{method:'POST',credentials:'include',headers:{'Accept':'application/json'}});if(!r.ok)return '';const j=await r.json();return j.token||''}catch(e){return ''}",
                                         arguments: [:], in: nil, in: .page) { res in
                    if case .success(let v) = res, let t = v as? String, !t.isEmpty { Vault.token = t }
                }
            }
        }
        // ── 푸시 토큰을 서버에 등록 ──
        func sharePushToken() {
            guard let t = AppDelegate.pushToken, t != sentPush, let w = web, let u = w.url, ours(u) else { return }
            #if DEBUG
            let env = "sandbox"
            #else
            let env = "production"
            #endif
            w.callAsyncJavaScript("try{const r=await fetch('/api/push/apns/register',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t,env:env,bundle:'org.kohgane.gogabridj'})});return r.ok}catch(e){return false}",
                                  arguments: ["t": t, "env": env], in: nil, in: .page) { [weak self] res in
                if case .success(let v) = res, (v as? Bool) == true { self?.sentPush = t }
            }
        }
        // 웹에서 window.webkit.messageHandlers.kg.postMessage({t:'haptic'}) / {t:'share',text,url}
        func userContentController(_ u: WKUserContentController, didReceive msg: WKScriptMessage) {
            guard let d = msg.body as? [String: Any], let t = d["t"] as? String else { return }
            if t == "haptic" { UIImpactFeedbackGenerator(style: .light).impactOccurred() }
            if t == "share" {
                var items: [Any] = []
                if let x = d["text"] as? String { items.append(x) }
                if let x = d["url"] as? String, let uu = URL(string: x) { items.append(uu) }
                guard !items.isEmpty, let root = UIApplication.shared.connectedScenes.compactMap({ ($0 as? UIWindowScene)?.keyWindow?.rootViewController }).first else { return }
                root.present(UIActivityViewController(activityItems: items, applicationActivities: nil), animated: true)
            }
        }
        // 알림창·확인창을 아이폰식으로
        func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage t: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping () -> Void) {
            alert(t, ok: completionHandler, cancel: nil)
        }
        func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage t: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            alert(t, ok: { completionHandler(true) }, cancel: { completionHandler(false) })
        }
        private func alert(_ t: String, ok: @escaping () -> Void, cancel: (() -> Void)?) {
            let a = UIAlertController(title: nil, message: t, preferredStyle: .alert)
            if let c = cancel { a.addAction(UIAlertAction(title: "취소", style: .cancel) { _ in c() }) }
            a.addAction(UIAlertAction(title: "확인", style: .default) { _ in ok() })
            var top = UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow?.rootViewController }.first
            while let p = top?.presentedViewController { top = p }
            top?.present(a, animated: true)
        }
        func webView(_ w: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(.prompt)
        }
    }
}
