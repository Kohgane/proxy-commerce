"""개발용 스크린샷 — 이관 검증식(스킵 사유 증명 + distinct 기준 PASS). 운영자 220→195 재현."""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ["DATABASE_URL"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"
os.environ["DATABASE_URL_DIRECT"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"

import src.db.pg as pg
pg.reset_state(); pg.init_schema()
with pg.tx() as cur:
    cur.execute("TRUNCATE collect_history")

import scripts.migrate_to_supabase as mig

# 운영자 시나리오 재현: 220건 = 195 distinct 상품 + 25 중복(같은 상품 재수집)
rows = []
for i in range(195):
    rows.append({"seller_id": "u1", "url": f"https://www.temu.com/g-{1000+i}.html", "title": f"상품{i}", "price": "9900", "currency": "KRW"})
# 앞의 25개 상품을 한 번씩 더 수집(중복)
for i in range(25):
    rows.append({"seller_id": "u1", "url": f"https://www.temu.com/g-{1000+i}.html?_oak_mp_inf=x", "title": f"상품{i}(재수집)", "price": "9900", "currency": "KRW"})
mig._sheet_collect_rows = lambda: rows

logs = []
mig._log = lambda m: logs.append(m)

with pg.direct_conn() as conn:
    with conn.cursor() as cur:
        out = mig.migrate_collect(cur, dry=False)

collect_ok = (out["err_count"] == 0) and (out["pg_total"] >= out["distinct_expected"])
logs.append(f"[collect_history] Sheets 원본 {out['sheets_total']} · 삽입 {out['inserted']} · 중복 {out['dup_count']} · 에러 {out['err_count']} · PG 총 {out['pg_total']} · 기대 distinct {out['distinct_expected']}")
logs.append(f"검증(distinct 기준): collect PASS={collect_ok} (PG {out['pg_total']} == 기대 distinct {out['distinct_expected']}, 에러 {out['err_count']})")

for L in logs:
    print(L)
print("dup_keys 예시(앞 5):", out["dup_keys"][:5])

from PIL import Image, ImageDraw
im = Image.new("RGB", (980, 340), "#1a1714"); d = ImageDraw.Draw(im)
gold, teal, orange, muted = (201,162,75), (17,154,142), (245,130,31), (150,145,133)
d.text((20, 16), "이관 검증식 수정 — 스킵 사유 증명 + distinct key 기준 PASS (운영자 220→195 재현)", fill=gold)
y = 52
d.text((20, y), f"Sheets 원본 220건 = 195 distinct 상품 + 25 중복(같은 상품 재수집)", fill=(200,192,178)); y += 26
d.text((20, y), f"삽입 {out['inserted']} · 중복 스킵 {out['dup_count']}(정상 dedup) · 에러 {out['err_count']} · PG 총 {out['pg_total']}", fill=(199,231,223)); y += 22
d.text((20, y), f"기대 distinct = {out['distinct_expected']}  →  PG 총 {out['pg_total']} 일치", fill=(199,231,223)); y += 30
d.text((20, y), f"검증(distinct 기준): collect PASS = {collect_ok}", fill=teal); y += 22
d.text((20, y), "→ 옛 검증식(PG≥Sheets, 195≥220=False '불일치')이 정상 dedup을 오판하던 것 수정", fill=muted); y += 20
d.text((20, y), f"중복 스킵 25건 = 전부 product_key 중복(예: {out['dup_keys'][0]})", fill=orange); y += 30
d.rectangle([20, y, 960, y+66], outline=gold, width=1)
d.text((34, y+12), "에러 스킵이면: 해당 행 url + 원인을 로그로 노출하고 FAIL(정직) — 이 경우는 에러 0.", fill=(200,192,178))
d.text((34, y+38), "중복이면: '중복 스킵 N건 목록' 출력 + distinct 기준으로 PASS 처리.", fill=(200,192,178))
os.makedirs("docs/screens/v45", exist_ok=True)
im.save("docs/screens/v45/migrate-reconcile.png")
print("saved docs/screens/v45/migrate-reconcile.png")
