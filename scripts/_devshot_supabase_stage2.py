"""개발용 스크린샷 — DB 이관 2단계 market_links(연동정보·암호화 컬럼). psycopg3/DATABASE_URL."""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ["DATABASE_URL"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"
os.environ.setdefault("MARKET_CRED_ENC_KEY",
                      __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())

import src.db.pg as pg
pg.reset_state(); pg.init_schema()
with pg.tx() as cur:
    cur.execute("TRUNCATE market_links")

from src.seller_console import market_credentials as mc
mc.save("u1", "coupang", {"COUPANG_ACCESS_KEY": "AK-xxx", "COUPANG_SECRET_KEY": "SECRET-9f8e", "COUPANG_VENDOR_ID": "A00012345"})
pg.reset_state()
got = mc.get("u1", "coupang")
with pg.query() as cur:
    cur.execute("SELECT enc_blob, is_encrypted FROM market_links WHERE user_id='u1' AND market='coupang'")
    blob, enc = cur.fetchone()
other_empty = (mc.get("u2", "coupang") == {})
deleted = mc.delete("u1", "coupang") and (mc.get("u1", "coupang") == {})
plaintext_leak = "SECRET-9f8e" in blob

from PIL import Image, ImageDraw
im = Image.new("RGB", (940, 420), "#1a1714"); d = ImageDraw.Draw(im)
gold, teal, orange = "#c9a24b", "#119a8e", "#f5821f"
d.text((24, 18), "DB 이관 2단계 — market_links (마켓 연동정보 · 암호화 컬럼) · psycopg3", gold)
d.text((24, 48), "data/<seller>.json(Render 재배포 시 소실) → Postgres(영속). 값은 Fernet 암호문(enc_blob)에만 저장.", fill="#b7ae9c")
d.text((24, 98), "저장→재시작→유지", teal)
d.text((44, 124), f"save(쿠팡) → 연결 초기화(재시작) → get: ACCESS={got.get('COUPANG_ACCESS_KEY')} · VENDOR={got.get('COUPANG_VENDOR_ID')} (유지)", fill="#c7e7df")
d.text((24, 168), "DB엔 암호문만(평문 노출 0)", teal)
d.text((44, 194), f"is_encrypted={enc} · 평문 SECRET 노출? {plaintext_leak} · enc_blob 앞부분: {blob[:20]}…", fill="#c7e7df")
d.text((24, 238), "셀러 격리 · 소프트삭제", teal)
d.text((44, 264), f"타 셀러 미노출: {other_empty} · delete 후 get 비었음: {deleted}", fill="#c7e7df")
d.rectangle([24, 308, 916, 388], outline=gold, width=1)
d.text((44, 324), "접속: DATABASE_URL(하드코딩 0). DDL/마이그레이션=직접 연결(5432). 암호화 키=MARKET_CRED_ENC_KEY.", orange)
d.text((44, 354), "로컬 PostgreSQL 16 psycopg3 실검증. 미설정이면 기존 data/ 파일 폴백(무회귀).", fill="#8a8272")
os.makedirs("docs/screens/v45", exist_ok=True); im.save("docs/screens/v45/supabase-stage2.png")
print(f"access={got.get('COUPANG_ACCESS_KEY')} is_enc={enc} plaintext_leak={plaintext_leak} other_empty={other_empty} deleted={deleted}")
print("saved docs/screens/v45/supabase-stage2.png")
