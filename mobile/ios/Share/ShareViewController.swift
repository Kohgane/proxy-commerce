// 공유 → 고가브릿지. 타오바오 复制链接 글·사파리 주소·쿠팡 링크를 그대로 서버(/seller/collect/share)에 넘긴다.
// 해석은 서버가 한다. 로그인은 본앱이 키체인 공유 그룹에 남긴 세션(쿠키/개인 토큰)을 쓴다.
import UIKit
import UniformTypeIdentifiers

final class ShareViewController: UIViewController {
    private let card = UIView(), thumb = UIImageView(), titleL = UILabel(), subL = UILabel(), spin = UIActivityIndicatorView(style: .medium)
    private let openB = UIButton(type: .system), closeB = UIButton(type: .system)
    private var openPath = "/seller/collect"

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor.black.withAlphaComponent(0.35)
        layout()
        guard Vault.loggedIn else { return show("고가브릿지 앱에서 먼저 로그인해 주세요", sub: "로그인한 뒤 다시 공유하면 바로 담깁니다.", ok: false) }
        collect { [weak self] text, url, title in self?.send(text: text, url: url, title: title) }
    }

    private func layout() {
        card.backgroundColor = UIColor(red: 0x1a / 255.0, green: 0x17 / 255.0, blue: 0x14 / 255.0, alpha: 1)
        card.layer.cornerRadius = 18; card.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(card)
        thumb.contentMode = .scaleAspectFill; thumb.clipsToBounds = true; thumb.layer.cornerRadius = 10
        thumb.backgroundColor = UIColor(white: 1, alpha: 0.06); thumb.translatesAutoresizingMaskIntoConstraints = false
        titleL.font = .systemFont(ofSize: 17, weight: .semibold); titleL.textColor = UIColor(red: 0.96, green: 0.94, blue: 0.89, alpha: 1); titleL.numberOfLines = 2
        titleL.text = "담는 중…"
        subL.font = .systemFont(ofSize: 13); subL.textColor = UIColor(white: 1, alpha: 0.55); subL.numberOfLines = 2
        openB.setTitle("앱에서 보기", for: .normal); openB.titleLabel?.font = .systemFont(ofSize: 16, weight: .bold)
        openB.tintColor = UIColor(red: 0.79, green: 0.64, blue: 0.29, alpha: 1); openB.isHidden = true
        openB.addTarget(self, action: #selector(openApp), for: .touchUpInside)
        closeB.setTitle("닫기", for: .normal); closeB.tintColor = UIColor(white: 1, alpha: 0.7)
        closeB.addTarget(self, action: #selector(done), for: .touchUpInside)
        spin.color = .white; spin.startAnimating()
        let text = UIStackView(arrangedSubviews: [titleL, subL]); text.axis = .vertical; text.spacing = 4
        let row = UIStackView(arrangedSubviews: [thumb, text, spin]); row.spacing = 12; row.alignment = .center
        let btns = UIStackView(arrangedSubviews: [closeB, openB]); btns.distribution = .fillEqually
        let col = UIStackView(arrangedSubviews: [row, btns]); col.axis = .vertical; col.spacing = 16
        col.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(col)
        // 카드 전체를 눌러도 그 상품 화면으로
        card.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(openApp)))
        NSLayoutConstraint.activate([
            card.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            card.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            card.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -16),
            col.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 16),
            col.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -16),
            col.topAnchor.constraint(equalTo: card.topAnchor, constant: 16),
            col.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -12),
            thumb.widthAnchor.constraint(equalToConstant: 56), thumb.heightAnchor.constraint(equalToConstant: 56),
        ])
    }

    private func show(_ title: String, sub: String, ok: Bool) {
        DispatchQueue.main.async {
            self.spin.stopAnimating(); self.spin.isHidden = true
            self.titleL.text = title; self.subL.text = sub
            self.openB.isHidden = !ok
            UINotificationFeedbackGenerator().notificationOccurred(ok ? .success : .warning)
        }
    }

    // 받은 것: 글자·URL·제목 (타오바오 复制链接 문장은 글자로 온다)
    private func collect(_ done: @escaping (String, String, String) -> Void) {
        var text = "", url = "", title = ""
        let items = (extensionContext?.inputItems as? [NSExtensionItem]) ?? []
        title = items.first?.attributedContentText?.string ?? ""
        let g = DispatchGroup()
        for it in items {
            for p in it.attachments ?? [] {
                if p.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                    g.enter()
                    p.loadItem(forTypeIdentifier: UTType.url.identifier) { v, _ in
                        if let u = v as? URL, url.isEmpty { url = u.absoluteString }
                        g.leave()
                    }
                } else if p.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                    g.enter()
                    p.loadItem(forTypeIdentifier: UTType.plainText.identifier) { v, _ in
                        if let s = v as? String { text += (text.isEmpty ? "" : "\n") + s }
                        g.leave()
                    }
                }
            }
        }
        g.notify(queue: .main) { done(text, url, title) }
    }

    private func send(text: String, url: String, title: String) {
        if text.isEmpty && url.isEmpty { return show("담을 내용이 없어요", sub: "상품 링크나 공유 글을 보내 주세요.", ok: false) }
        var req = URLRequest(url: KG.base.appendingPathComponent("/seller/collect/share"))
        req.httpMethod = "POST"; req.timeoutInterval = 45
        req.setValue("application/x-www-form-urlencoded; charset=utf-8", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("ios-share", forHTTPHeaderField: "X-KG-Source")
        if let c = Vault.cookieHeader, !c.isEmpty { req.setValue(c, forHTTPHeaderField: "Cookie") }
        if let t = Vault.token, !t.isEmpty { req.setValue("Bearer " + t, forHTTPHeaderField: "Authorization") }
        var f = URLComponents(); f.queryItems = [URLQueryItem(name: "text", value: text), URLQueryItem(name: "url", value: url),
                                                 URLQueryItem(name: "title", value: title), URLQueryItem(name: "src", value: "ios-share")]
        req.httpBody = (f.percentEncodedQuery ?? "").replacingOccurrences(of: "+", with: "%2B").data(using: .utf8)
        URLSession.shared.dataTask(with: req) { [weak self] data, resp, err in
            guard let self = self else { return }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            if err != nil || code == 0 { return self.show("연결이 안 돼요", sub: "인터넷을 확인한 뒤 다시 공유해 주세요.", ok: false) }
            if code == 401 || code == 403 || (resp?.url?.path.contains("/login") ?? false) {
                return self.show("로그인이 풀렸어요", sub: "고가브릿지 앱을 한 번 열어 로그인해 주세요.", ok: false)
            }
            if code >= 400 { return self.show("담지 못했어요 (\(code))", sub: "잠시 뒤 다시 공유해 주세요.", ok: false) }
            // JSON 이면 상품 정보를, 아니면(HTML 결과 화면) 담김으로만 본다
            var name = "담았어요", sub = "수집 목록에 들어갔어요", img: String?, okFlag = true
            if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                let obj = (j["item"] as? [String: Any]) ?? j
                if let t = obj["title"] as? String, !t.isEmpty { sub = t }
                img = (obj["thumb"] ?? obj["thumbnail"] ?? obj["image"]) as? String
                if let p = (obj["path"] ?? obj["url"]) as? String, p.hasPrefix("/") { self.openPath = p }
                else if let id = obj["item_id"] ?? obj["id"] ?? obj["iid"] { self.openPath = "/seller/m/item/\(id)" }
                if (j["ok"] as? Bool) == false { name = "담지 못했어요"; sub = (j["error"] as? String) ?? "잠시 뒤 다시 공유해 주세요."; okFlag = false }
                if (j["dup"] as? Bool) == true || (j["state"] as? String) == "dup" { name = "이미 담은 상품이에요" }
            } else if let u = resp?.url, u.path.hasPrefix("/seller/") { self.openPath = u.path }
            self.show(name, sub: sub, ok: okFlag)
            if let s = img, let iu = URL(string: s, relativeTo: KG.base) {
                URLSession.shared.dataTask(with: iu.absoluteURL) { d, _, _ in
                    if let d = d, let im = UIImage(data: d) { DispatchQueue.main.async { self.thumb.image = im } }
                }.resume()
            }
        }.resume()
    }

    // 본앱의 그 상품 화면으로 (확장에서는 응답 사슬로 openURL 을 찾아 부른다)
    @objc private func openApp() {
        guard !openB.isHidden else { return }
        var c = URLComponents(); c.scheme = KG.scheme; c.host = "open"; c.queryItems = [URLQueryItem(name: "path", value: openPath)]
        if let u = c.url {
            // 확장에선 UIApplication.open 을 직접 못 부른다 → 응답 사슬에서 앱 객체를 찾아 런타임으로 부른다
            let sel = NSSelectorFromString("openURL:options:completionHandler:")
            var r: UIResponder? = self
            while let x = r {
                if x.responds(to: sel), let imp = x.method(for: sel) {
                    typealias OpenFn = @convention(c) (AnyObject, Selector, NSURL, NSDictionary, AnyObject?) -> Void
                    unsafeBitCast(imp, to: OpenFn.self)(x, sel, u as NSURL, NSDictionary(), nil)
                    break
                }
                r = x.next
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.done() }
    }
    @objc private func done() { extensionContext?.completeRequest(returningItems: nil) }
}
