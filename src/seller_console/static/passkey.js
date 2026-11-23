/* passkey.js — v40-D: 패스키(WebAuthn) 프론트 글루.
 * 서버 옵션(base64url) ↔ 브라우저 ArrayBuffer 변환 + 등록/로그인 세리머니.
 * navigator.credentials.create/get → 기기 생체인증(지문·Face·PIN) → 서버 검증.
 */
(function () {
  function b64urlToBuf(s) {
    s = (s || "").replace(/-/g, "+").replace(/_/g, "/");
    var pad = s.length % 4; if (pad) s += "====".slice(pad);
    var bin = atob(s), buf = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }
  function bufToB64url(buf) {
    var bytes = new Uint8Array(buf), bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function supported() {
    return !!(window.PublicKeyCredential && navigator.credentials && navigator.credentials.create);
  }

  // 등록 옵션(서버 JSON) → create()용 PublicKeyCredentialCreationOptions
  function prepCreate(opts) {
    opts.challenge = b64urlToBuf(opts.challenge);
    opts.user.id = b64urlToBuf(opts.user.id);
    (opts.excludeCredentials || []).forEach(function (c) { c.id = b64urlToBuf(c.id); });
    return opts;
  }
  function prepGet(opts) {
    opts.challenge = b64urlToBuf(opts.challenge);
    (opts.allowCredentials || []).forEach(function (c) { c.id = b64urlToBuf(c.id); });
    return opts;
  }
  function regCredToJSON(cred) {
    var r = cred.response;
    return {
      id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: bufToB64url(r.clientDataJSON),
        attestationObject: bufToB64url(r.attestationObject),
      },
      clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
    };
  }
  function authCredToJSON(cred) {
    var r = cred.response;
    return {
      id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: bufToB64url(r.clientDataJSON),
        authenticatorData: bufToB64url(r.authenticatorData),
        signature: bufToB64url(r.signature),
        userHandle: r.userHandle ? bufToB64url(r.userHandle) : null,
      },
      clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
    };
  }
  // 감독 11-23(TestFlight WKWebView): 브라우저 예외(DOMException)의 영어 메시지를 그대로 보이지 않는다.
  //   우리 코드가 던진 Error(서버가 준 한국어 사유)는 그대로 둔다.
  var KGP_PK_MSG = {
    NotAllowedError: "패스키 인증이 취소됐거나 이 기기에 등록된 패스키가 없어요. 다른 로그인을 쓰세요.",
    AbortError: "패스키 인증이 중간에 멈췄어요. 다시 눌러 주세요.",
    SecurityError: "이 주소에서는 패스키를 쓸 수 없어요(보안 설정). 다른 로그인을 쓰세요.",
    InvalidStateError: "이 기기에는 이미 패스키가 등록돼 있어요.",
    NotSupportedError: "이 브라우저/기기는 패스키를 지원하지 않아요. 다른 로그인을 쓰세요.",
    TypeError: "서버에 연결하지 못했어요. 네트워크를 확인하고 다시 시도하세요.",
  };
  var KGP_PK_FALLBACK = "패스키로 마치지 못했어요. 다른 로그인을 쓰세요.";
  function friendlyError(e) {
    if (!e) return KGP_PK_FALLBACK;
    if (e.kgpFriendly) return e.message;                 // 이미 한국어로 바꾼 것
    var name = e.name || "";
    if (KGP_PK_MSG[name]) return KGP_PK_MSG[name];
    if (name === "Error" && e.message) return e.message; // 우리 코드가 던진 한국어 사유
    return KGP_PK_FALLBACK;                               // 모르는 브라우저 예외 — 영어 원문 노출 금지
  }
  function wrapped(e) {
    var err = new Error(friendlyError(e));
    err.kgpFriendly = true;
    err.kgpCause = (e && e.name) || "";
    return err;
  }

  async function postJSON(url, body) {
    var resp = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return { status: resp.status, data: await resp.json().catch(function () { return {}; }) };
  }

  // 패스키 등록(로그인 상태) — "이 기기에 패스키 등록"
  async function register(label) {
    if (!supported()) throw new Error("이 브라우저/기기는 패스키를 지원하지 않아요. 구글/이메일을 쓰세요.");
    try {
      var o = await postJSON("/auth/passkey/register/options", {});
      if (!o.data.ok) throw new Error(o.data.error || "패스키 옵션을 받지 못했어요.");
      var cred = await navigator.credentials.create({ publicKey: prepCreate(o.data.options) });
      var v = await postJSON("/auth/passkey/register/verify", { credential: regCredToJSON(cred), label: label || "이 기기" });
      if (!v.data.ok) throw new Error(v.data.error || "패스키 등록 검증에 실패했어요.");
      return true;
    } catch (e) { throw wrapped(e); }
  }

  // 패스키로 로그인
  async function login() {
    if (!supported()) throw new Error("이 브라우저/기기는 패스키를 지원하지 않아요. 구글/이메일을 쓰세요.");
    try {
      var o = await postJSON("/auth/passkey/login/options", {});
      if (!o.data.ok) throw new Error(o.data.error || "로그인 옵션을 받지 못했어요.");
      var cred = await navigator.credentials.get({ publicKey: prepGet(o.data.options) });
      var v = await postJSON("/auth/passkey/login/verify", { credential: authCredToJSON(cred) });
      if (!v.data.ok) throw new Error(v.data.error || "패스키 로그인에 실패했어요.");
      return v.data.redirect || "/seller/dashboard";
    } catch (e) { throw wrapped(e); }
  }

  window.kgpPasskey = { supported: supported, register: register, login: login, friendlyError: friendlyError };
})();
