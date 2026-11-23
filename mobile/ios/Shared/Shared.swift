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
