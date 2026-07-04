"""개발용 스크린샷 — v45 P8 OPENAI/DEEPL '미설정'(값·재배포 완료) 근본 수리.

따옴표/공백 오염 키를 부팅 시 in-place 정제 → 이후 raw os.getenv 모듈(AI 초안·번역)도 인식.
값은 마스킹(시크릿 미노출). AI 실제 생성은 오너가 실제 키 설정 시 동작.
"""
import os, sys
sys.path.insert(0, os.getcwd())

# 오염 키 주입(가짜 데모 값 — 시크릿 아님)
os.environ["OPENAI_API_KEY"] = '"sk-demo-EXAMPLE-1234567890"'
os.environ["DEEPL_API_KEY"] = "  dl-demo-EXAMPLE:fx  "

from src.utils.env import sanitize_env_inplace, env_present

def mask(name):
    v = os.getenv(name) or ""
    if not v:
        return "(없음)"
    return v[:6] + "…" + v[-3:] if len(v) > 10 else "설정됨"

before = {
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    "DEEPL_API_KEY": os.getenv("DEEPL_API_KEY"),
}
# 정제 전: 다운스트림 raw 읽기가 '따옴표/공백 포함' 오염값을 그대로 봄 → API 401 → '미설정'처럼 폴백
before_clean = {k: (v == v.strip().strip('"').strip("'") if v else False) for k, v in before.items()}

changed = sanitize_env_inplace()
after = {
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    "DEEPL_API_KEY": os.getenv("DEEPL_API_KEY"),
}

from PIL import Image, ImageDraw, ImageFont
W, H = 980, 430
img = Image.new("RGB", (W, H), "#1a1714")
d = ImageDraw.Draw(img)
def T(x, y, s, fill="#f5efe3", size=15):
    d.text((x, y), s, fill=fill)
gold, teal, orange, danger = "#c9a24b", "#119a8e", "#f5821f", "#e5534b"

T(24, 20, "P8 — OPENAI/DEEPL '미설정'(값·재배포 완료 상태) 근본 수리", gold)
T(24, 46, "따옴표/공백이 섞인 Render 키를 부팅 시 in-place 정제 → raw os.getenv 모듈(AI 초안·번역)도 인식", "#b7ae9c")

y = 92
T(24, y, "BEFORE (오염 — 다운스트림 raw os.getenv가 그대로 봄):", danger)
T(44, y+28, "OPENAI_API_KEY = \"sk-demo-…\"   ← 감싼 따옴표 포함 → API 인증 실패 → '미설정'처럼 폴백", "#e7c9c6")
T(44, y+52, "DEEPL_API_KEY  = '␣␣dl-demo-…␣␣'  ← 앞뒤 공백 포함", "#e7c9c6")

y = 200
T(24, y, "부팅 정제:  환경변수 정제(따옴표/공백 제거): " + ", ".join(changed), orange)
T(24, y+26, "부팅 로그:  환경변수 체크: OPENAI_API_KEY=설정됨 · DEEPL_API_KEY=설정됨 …  (값 마스킹)", "#b7ae9c")

y = 262
T(24, y, "AFTER (정제 — os.getenv가 깨끗한 값):", teal)
T(44, y+28, "OPENAI_API_KEY → " + mask("OPENAI_API_KEY") + "   (따옴표 제거)", "#c7e7df")
T(44, y+52, "DEEPL_API_KEY  → " + mask("DEEPL_API_KEY") + "   (공백 제거)", "#c7e7df")
T(44, y+76, "env_present(OPENAI)=" + str(env_present("OPENAI_API_KEY")) +
            " · env_present(DEEPL)=" + str(env_present("DEEPL_API_KEY")) + "  → AI 초안·번역 경로가 키 인식", teal)

T(24, 392, "※ 실제 AI 초안/번역 동작은 오너가 Render에 유효 키 설정 시. 코드는 오염돼도 정제해 인식(시크릿 미로깅).", "#8a8272")

os.makedirs("docs/screens/v45", exist_ok=True)
img.save("docs/screens/v45/p8-env-sanitize.png")
print("changed:", changed)
print("after OPENAI:", after["OPENAI_API_KEY"])
print("after DEEPL:", after["DEEPL_API_KEY"])
print("saved docs/screens/v45/p8-env-sanitize.png")
