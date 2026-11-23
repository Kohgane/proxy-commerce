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
    @Published var toast: String?
    @Published var askClip = false
    @Published var showGuide = !UserDefaults.standard.bool(forKey: "guide_taobao_v1")
    weak var web: WKWebView?
    private var clipCC = 0
    private var flushing = false
    func load(_ path: String) { web?.load(URLRequest(url: URL(string: path, relativeTo: KG.base)!.absoluteURL)) }
    func reload() { offline = false; if web?.url == nil { load(KG.startPath) } else { web?.reload() } }
    func flash(_ t: String) {
        toast = t
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.6) { [weak self] in if self?.toast == t { self?.toast = nil } }
    }
    func onActive() { flushOutbox(); checkClipboard() }

    // 공유 확장이 연결 못 해 보관해 둔 것 → 지금 다시 보낸다
    func flushOutbox() {
        let items = Outbox.all()
        guard !items.isEmpty, !flushing, Vault.loggedIn else { return }
        flushing = true
        var left: [ShareItem] = []; var sent = 0
        let g = DispatchGroup(); let lock = NSLock()
        for it in items {
            g.enter()
            Collect.post(it) { r in
                lock.lock()
                switch r {
                case .ok: sent += 1
                case .fail: break
                default: left.append(it)
                }
                lock.unlock(); g.leave()
            }
        }
        g.notify(queue: .main) { [weak self] in
            guard let self = self else { return }
            Outbox.save(left); self.flushing = false
            if sent > 0 { self.flash("보관해 둔 \(sent)개를 보냈어요 ✓"); self.load("/seller/collect") }
        }
    }

    // 클립보드에 상품 링크가 있으면 「이 상품 담을까요?」 (먼저 내용은 안 읽고 링크인지만 본다)
    func checkClipboard() {
        guard !showGuide, !askClip, Vault.loggedIn else { return }
        let pb = UIPasteboard.general
        let cc = pb.changeCount
        guard cc != UserDefaults.standard.integer(forKey: "clip_cc") else { return }
        pb.detectPatterns(for: [.probableWebURL]) { [weak self] res in
            guard case .success(let found) = res, found.contains(.probableWebURL) else { return }
            DispatchQueue.main.async { self?.clipCC = cc; self?.askClip = true }
        }
    }
    func skipClip() { UserDefaults.standard.set(clipCC, forKey: "clip_cc") }
    func takeClip() {
        UserDefaults.standard.set(clipCC, forKey: "clip_cc")
        let pb = UIPasteboard.general
        let s = pb.string ?? pb.url?.absoluteString ?? ""
        guard !s.isEmpty else { return }
        let it = ShareItem(text: s, url: "", title: "", ts: Date().timeIntervalSince1970)
        Collect.post(it) { [weak self] r in
            DispatchQueue.main.async {
                guard let self = self else { return }
                switch r {
                case .ok(let d, let u):
                    self.flash("담았어요 ✓")
                    self.load(Collect.itemPath(d, u) ?? "/seller/collect")
                case .offline:
                    Outbox.add(it); self.flash("담아 뒀어요, 연결되면 보낼게요")
                case .auth:
                    self.flash("먼저 로그인해 주세요")
                case .fail(let c):
                    self.flash("담지 못했어요 (\(c))")
                }
            }
        }
    }
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
            if let t = m.toast {
                VStack {
                    Spacer()
                    Text(t).font(.subheadline.weight(.semibold)).foregroundStyle(Color(red: 0.96, green: 0.94, blue: 0.89))
                        .padding(.horizontal, 18).padding(.vertical, 12)
                        .background(Capsule().fill(Color(red: 0.13, green: 0.12, blue: 0.11)).overlay(Capsule().stroke(Color(red: 0.79, green: 0.64, blue: 0.29).opacity(0.6), lineWidth: 1)))
                        .shadow(color: .black.opacity(0.4), radius: 12, y: 6)
                        .padding(.bottom, 40)
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .allowsHitTesting(false)
            }
        }
        .animation(.spring(duration: 0.35), value: m.toast)
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in m.onActive() }
        .alert("이 상품 담을까요?", isPresented: $m.askClip) {
            Button("담기") { m.takeClip() }
            Button("아니요", role: .cancel) { m.skipClip() }
        } message: {
            Text("복사해 둔 링크를 고가브릿지 수집함에 넣습니다.")
        }
        .fullScreenCover(isPresented: $m.showGuide) {
            TaobaoGuide {
                UserDefaults.standard.set(true, forKey: "guide_taobao_v1")
                m.showGuide = false
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { m.onActive() }
            }
        }
    }
}

// 첫 실행 한 장: 타오바오는 자체 공유창에서 「更多」를 눌러야 아이폰 공유 목록이 나온다
struct TaobaoGuide: View {
    var done: () -> Void
    let gold = Color(red: 0.79, green: 0.64, blue: 0.29)
    let ink = Color(red: 0.10, green: 0.09, blue: 0.08)
    var body: some View {
        ZStack {
            Color(kgBG).ignoresSafeArea()
            VStack(alignment: .leading, spacing: 22) {
                Text("타오바오에서 담는 법").font(.title2.weight(.bold)).foregroundStyle(.white)
                Text("한 번만 보시면 됩니다.").font(.subheadline).foregroundStyle(.secondary)
                step(1, "상품 화면에서 공유(分享) 버튼")
                phone {
                    HStack(spacing: 14) {
                        ForEach(["微信", "QQ", "微博", "复制链接"], id: \.self) { t in chip(t, hi: false) }
                        chip("更多", hi: true)
                    }
                }
                step(2, "타오바오 공유창 맨 끝 「更多」")
                phone {
                    HStack(spacing: 14) {
                        appIcon("메시지", Color.green, hi: false)
                        appIcon("메일", Color.blue, hi: false)
                        appIcon("고가브릿지", gold, hi: true)
                        appIcon("메모", Color.yellow, hi: false)
                    }
                }
                step(3, "아이폰 공유 목록에서 「고가브릿지」 → 1초면 담깁니다")
                Text("팁: 아이폰 공유 목록 끝 「더 보기 → 편집」에서 고가브릿지를 즐겨찾기에 넣으면 맨 앞에 나옵니다.")
                    .font(.footnote).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Button(action: done) {
                    Text("알겠어요").font(.headline).frame(maxWidth: .infinity).padding(.vertical, 14)
                        .background(Capsule().fill(gold)).foregroundStyle(ink)
                }
            }
            .padding(24)
        }
        .preferredColorScheme(.dark)
    }
    func step(_ n: Int, _ t: String) -> some View {
        HStack(spacing: 10) {
            Text("\(n)").font(.subheadline.weight(.bold)).foregroundStyle(ink).frame(width: 26, height: 26).background(Circle().fill(gold))
            Text(t).font(.body.weight(.semibold)).foregroundStyle(.white)
        }
    }
    func phone<C: View>(@ViewBuilder _ c: () -> C) -> some View {
        c().padding(.vertical, 16).padding(.horizontal, 12).frame(maxWidth: .infinity)
            .background(RoundedRectangle(cornerRadius: 18).fill(Color.white.opacity(0.06)).overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.white.opacity(0.08))))
    }
    func chip(_ t: String, hi: Bool) -> some View {
        VStack(spacing: 6) {
            Circle().fill(hi ? Color.orange : Color.white.opacity(0.18)).frame(width: 40, height: 40)
                .overlay(Image(systemName: hi ? "ellipsis" : "circle.fill").font(.system(size: hi ? 18 : 6, weight: .bold)).foregroundStyle(.white))
                .overlay(Circle().stroke(gold, lineWidth: hi ? 3 : 0).padding(-5))
            Text(t).font(.caption2).foregroundStyle(hi ? gold : .secondary)
        }
    }
    func appIcon(_ t: String, _ c: Color, hi: Bool) -> some View {
        VStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 12).fill(c.opacity(hi ? 1 : 0.55)).frame(width: 48, height: 48)
                .overlay(Text(hi ? "고" : "").font(.title3.weight(.heavy)).foregroundStyle(ink))
                .overlay(RoundedRectangle(cornerRadius: 15).stroke(gold, lineWidth: hi ? 3 : 0).padding(-5))
            Text(t).font(.caption2).foregroundStyle(hi ? gold : .secondary)
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
