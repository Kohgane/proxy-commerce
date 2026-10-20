"""Y13-H 캡처: 마켓에 실제로 나가는 본문 두 가지 — ① 네이버 KC 대상 카테고리 상세(맨 위 구매대행 고지)
② 쿠팡 상세(설명 칸이 가게 배너뿐인 상품). 같은 스크립트를 main 워크트리(전)와 이 브랜치(후)에서 돌린다.
사용: python scripts/_devshot_y13h.py OUT TAG"""
import glob, html, json, os, sys
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
OUT, TAG = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
from src.uploaders import naver_kc as K
K.kc_required = lambda cid, up=None: True                     # BLACKHOLES 벽등 50003332 = KC 대상(10-20 실측)
from src.uploaders.naver_uploader import NaverSmartStoreUploader as NU
nb = NU(account=None)._build_product_payload({"title": "블랙홀 미니 무드등", "price": 52390, "images": ["https://a/b.jpg"],
                                               "category_id": "50003332",
                                               "description_html": "<p>우주를 테마로 한 블랙홀 미니 벽등입니다.</p>"})
naver_html = nb["originProduct"]["detailContent"]

from src.seller_console import upload_dispatcher as D
from src.channel_sync._channel_bridge import to_collected
from src.channel_sync.coupang_uploader import prepared_input
from src.uploaders.coupang_uploader import CoupangUploader as CU
CU.detail_image_urls = lambda self, p: []
AI = {"provider": "anthropic", "text": "혼자만의 휴식이 필요한 공간에 편안하게 자리 잡는 1인용 라운지 소파입니다.\n\n"
      "- 몸을 기대앉거나 길게 누울 수 있는 넉넉한 구조로, 독서나 낮잠 등 다양한 자세로 편히 쉴 수 있습니다."}
item = {"id": "x", "extra_json": json.dumps({"detail_auto": AI})}
pd = D.build_dispatch_payload({"title": "1인 회전 라운지 소파 의자 거실 디자이너 체어", "sell_price_krw": 588900,
                               "description": "菲尚丽家旗舰店\n5.0\n好评率98%\n物流好评率98%\n客服满意度93%"}, item)
up = CU.__new__(CU)
cp_body = up._build_contents(up.prepare_product(to_collected(prepared_input(pd))))[-1]["contentDetails"][0]["content"]

page = f"""<!doctype html><meta charset=utf-8><style>
body{{font-family:Pretendard,'Noto Sans KR',sans-serif;background:#FBF8F1;color:#1A1714;margin:24px;width:760px}}
h2{{font-size:15px;margin:18px 0 6px;color:#3A352E}} .box{{background:#fff;border:1px solid #E6DECB;border-radius:12px;padding:14px 16px}}
.tag{{font-size:12px;color:#8A8275}}</style>
<div class=tag>{TAG}</div>
<h2>① 네이버 상세(KC 대상 카테고리 · 특례 OVERSEAS)</h2><div class=box>{naver_html}</div>
<h2>② 쿠팡 상세(설명 칸 = 가게 배너뿐)</h2><div class=box>{cp_body if '<' in cp_body else html.escape(cp_body)}</div>"""
p = os.path.join(OUT, f"y13h-body-{TAG}.html")
open(p, "w", encoding="utf-8").write(page)
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=exe)
    pg = b.new_page(viewport={"width": 820, "height": 600})
    pg.goto("file://" + os.path.abspath(p))
    pg.screenshot(path=os.path.join(OUT, f"y13h-body-{TAG}.png"), full_page=True)
    print(TAG, pg.inner_text("body").replace("\n", " / ")[:400])
    b.close()
os.remove(p)
