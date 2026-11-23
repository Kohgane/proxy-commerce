// 본앱 ↔ 공유 확장이 같이 보는 금고(키체인 공유 그룹). 로그인 세션 쿠키와 개인 토큰을 여기에 둔다.
// App Group 대신 키체인 공유를 쓴다 — 포털에 그룹을 따로 만들 필요 없이 자동 서명만으로 된다(브리가네와 같은 방식).
import Foundation
import Security

enum KG {
    static let base = URL(string: "https://kohganepercentiii.com")!
    static let host = "kohganepercentiii.com"
    static let startPath = "/seller/m"
    static let scheme = "gogabridj"
    static var group: String {
        let p = (Bundle.main.object(forInfoDictionaryKey: "KGAppIdPrefix") as? String) ?? ""
        return p + "org.kohgane.gogabridj.shared"
    }
}

enum Vault {
    private static let service = "org.kohgane.gogabridj.session"
    static func set(_ key: String, _ value: String?) {
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                   kSecAttrAccount as String: key, kSecAttrAccessGroup as String: KG.group]
        SecItemDelete(base as CFDictionary)
        guard let v = value, !v.isEmpty, let d = v.data(using: .utf8) else { return }
        var add = base
        add[kSecValueData as String] = d
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(add as CFDictionary, nil)
    }
    static func get(_ key: String) -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: key, kSecAttrAccessGroup as String: KG.group,
                                kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }
    // 쿠키 헤더 한 줄("a=1; b=2")과 개인 토큰
    static var cookieHeader: String? { get { get("cookie") } set { set("cookie", newValue) } }
    static var token: String? { get { get("token") } set { set("token", newValue) } }
    static var loggedIn: Bool { (cookieHeader?.isEmpty == false) || (token?.isEmpty == false) }
}

// ── 공유로 담을 한 건 + 못 보낸 것 보관함(연결되면 본앱이 다시 보낸다) ──
struct ShareItem: Codable {
    var text: String
    var url: String
    var title: String
    var ts: Double
}

enum Outbox {
    static func all() -> [ShareItem] {
        guard let s = Vault.get("outbox"), let d = s.data(using: .utf8),
              let a = try? JSONDecoder().decode([ShareItem].self, from: d) else { return [] }
        return a
    }
    static func save(_ a: [ShareItem]) {
        if a.isEmpty { Vault.set("outbox", nil); return }
        guard let d = try? JSONEncoder().encode(Array(a.suffix(50))) else { return }
        Vault.set("outbox", String(data: d, encoding: .utf8))
    }
    static func add(_ i: ShareItem) { var a = all(); a.append(i); save(a) }
}

enum CollectResult {
    case ok(Data?, URL?)
    case offline
    case auth
    case fail(Int)
}

enum Collect {
    // POST /seller/collect/share — 서버가 타오바오 复制链接 글·쿠팡·사파리 주소를 해석한다
    static func post(_ i: ShareItem, done: @escaping (CollectResult) -> Void) {
        var req = URLRequest(url: KG.base.appendingPathComponent("/seller/collect/share"))
        req.httpMethod = "POST"; req.timeoutInterval = 30
        req.setValue("application/x-www-form-urlencoded; charset=utf-8", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("ios-share", forHTTPHeaderField: "X-KG-Source")
        if let c = Vault.cookieHeader, !c.isEmpty { req.setValue(c, forHTTPHeaderField: "Cookie") }
        if let t = Vault.token, !t.isEmpty { req.setValue("Bearer " + t, forHTTPHeaderField: "Authorization") }
        var f = URLComponents()
        f.queryItems = [URLQueryItem(name: "text", value: i.text), URLQueryItem(name: "url", value: i.url),
                        URLQueryItem(name: "title", value: i.title), URLQueryItem(name: "src", value: "ios-share")]
        req.httpBody = (f.percentEncodedQuery ?? "").replacingOccurrences(of: "+", with: "%2B").data(using: .utf8)
        URLSession.shared.dataTask(with: req) { data, resp, err in
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            if err != nil || code == 0 { return done(.offline) }
            if code == 401 || code == 403 || (resp?.url?.path.contains("/login") ?? false) { return done(.auth) }
            if code >= 500 { return done(.offline) }          // 서버가 잠깐 아프면 보관했다가 다시
            if code >= 400 { return done(.fail(code)) }
            done(.ok(data, resp?.url))
        }.resume()
    }
    // 응답에서 그 상품 화면 경로를 뽑는다
    static func itemPath(_ data: Data?, _ final: URL?) -> String? {
        if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
            let obj = (j["item"] as? [String: Any]) ?? j
            if let p = (obj["path"] ?? obj["url"]) as? String, p.hasPrefix("/") { return p }
            if let id = obj["item_id"] ?? obj["id"] ?? obj["iid"] { return "/seller/m/item/\(id)" }
        }
        if let u = final, u.path.hasPrefix("/seller/") { return u.path }
        return nil
    }
}
