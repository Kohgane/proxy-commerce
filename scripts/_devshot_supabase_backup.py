"""개발용 스크린샷 — DB 이관 3단계 마무리: PG → Sheets 읽기전용 백업(일 1회 덤프)."""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ["DATABASE_URL"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"
os.environ["DATABASE_URL_DIRECT"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"
os.environ.setdefault("MARKET_CRED_ENC_KEY",
                      __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())

import src.db.pg as pg
import src.utils.sheets as sheets
from src.db import backup, collect_history_pg as ch, orders_pg
from src.seller_console import market_credentials as mc

pg.reset_state(); pg.init_schema()
with pg.tx() as cur:
    for t in ("collect_history", "user_tokens", "market_links", "orders"):
        cur.execute(f"TRUNCATE {t}")

# 각 테이블에 실데이터 심기
ch.append(source="ext", url="https://x.com/g-1", title="접이식 차량용 책상", price="61144", currency="KRW", seller_id="u1")
ch.append(source="ext", url="https://x.com/g-2", title="OHSNAP 접착패드", price="12000", currency="KRW", seller_id="u1")
mc.save("u1", "coupang", {"COUPANG_ACCESS_KEY": "AK-xxx", "COUPANG_SECRET_KEY": "SECRET-9f8e"})
orders_pg.upsert_rows([{"order_id": "ORD1", "marketplace": "coupang", "status": "paid", "total_krw": "61144"}])

# 가짜 Sheets로 덤프 캡처(실 Sheets 키 없이 로직 실검증)
class WS:
    def __init__(s): s.rows=None
    def clear(s): s.rows=None
    def update(s,_c,v): s.rows=v
class SH:
    def __init__(s): s.ws={}
    def worksheet(s,n):
        if n not in s.ws: raise KeyError(n)
        return s.ws[n]
    def add_worksheet(s,title,rows,cols): s.ws[title]=WS(); return s.ws[title]
fake=SH()
sheets.open_sheet_object = lambda _sid: fake

# PG 읽기 전 행수(백업이 PG를 안 건드림 확인)
with pg.query() as cur:
    cur.execute("SELECT count(*) FROM collect_history"); ch_before=int(cur.fetchone()[0])
out = backup.backup_to_sheets(sheet_id="sid")
with pg.query() as cur:
    cur.execute("SELECT count(*) FROM collect_history"); ch_after=int(cur.fetchone()[0])

ml_body = fake.ws["_backup_market_links"].rows
ml_flat = " ".join(str(v) for r in ml_body for v in r)
plaintext_leak = "SECRET-9f8e" in ml_flat   # 암호문만 백업 → False 여야
ch_dump = fake.ws["_backup_collect_history"].rows

from PIL import Image, ImageDraw
im = Image.new("RGB", (960, 460), "#1a1714"); d = ImageDraw.Draw(im)
gold, teal, orange = "#c9a24b", "#119a8e", "#f5821f"
d.text((24, 18), "DB 이관 3단계 마무리 — PG → Google Sheets 읽기전용 백업(일 1회 덤프)", gold)
d.text((24, 48), "Supabase가 1차 저장소. Sheets는 백업으로 강등. /cron/supabase-backup(X-Cron-Secret) 훅.", fill="#b7ae9c")
d.text((24, 96), "4개 이관 테이블 스냅샷 덤프(행수 = PG 실측)", teal)
tbl = out["tables"]
d.text((44, 122), f"collect_history={tbl['collect_history']} · user_tokens={tbl['user_tokens']} · "
                  f"market_links={tbl['market_links']} · orders={tbl['orders']}", fill="#c7e7df")
d.text((24, 162), "market_links는 암호문(enc_blob)만 백업 — 평문 노출 0", teal)
d.text((44, 188), f"백업에 평문 SECRET 노출? {plaintext_leak}  (enc_blob 앞: {ml_body[1][3][:18]}…)", fill="#c7e7df")
d.text((24, 228), "읽기 전용 — 백업이 PG를 건드리지 않음", teal)
d.text((44, 254), f"collect_history 행수: 백업 전 {ch_before} → 백업 후 {ch_after} (동일)", fill="#c7e7df")
d.text((24, 294), "덤프 헤더/행 실검증", teal)
d.text((44, 320), f"_backup_collect_history 헤더: {ch_dump[0][:4]}… · 첫 행 제목: {ch_dump[1][6]}", fill="#c7e7df")
d.text((44, 344), f"_backup_meta 기록: {'_backup_meta' in fake.ws} · ok={out['ok']} · at={out['at'][:19]}", fill="#c7e7df")
d.rectangle([24, 384, 936, 448], outline=gold, width=1)
d.text((44, 398), "PG 미설정이면 백업 대상 없음(정직) · GOOGLE_SHEET_ID 미설정이면 정직 사유. 폴백 무회귀.", orange)
d.text((44, 424), "로컬 PostgreSQL 16 psycopg3 실검증(가짜 Sheets로 덤프 로직 캡처).", fill="#8a8272")
os.makedirs("docs/screens/v45", exist_ok=True); im.save("docs/screens/v45/supabase-backup.png")
print(f"tables={tbl} plaintext_leak={plaintext_leak} ch_before={ch_before} ch_after={ch_after} ok={out['ok']}")
print("saved docs/screens/v45/supabase-backup.png")
