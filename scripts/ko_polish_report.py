"""T1/T2 검증 보고 — 정리 규칙(ko_polish)이 실제 데이터에 무엇을 했나.

  python scripts/ko_polish_report.py [fixture.json]

출력: ① VRSUK 16값 — 규칙 결과·남은 한자·28자 축약 ② 상품명 번역본 — 정리 전/후·지운 말 ③ 옵션 값 표본 —
규칙만으로 끝난 값 / 번역기가 필요한 값(남은 한자) ④ 이미지 OCR 번역문 — 표시광고 위험 문구.
번역기 단계는 이 스크립트가 부르지 않는다(환경에 번역기가 없을 수 있다 — 운영 관리자 보고 화면이 부른다).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.collectors import ko_polish as kp  # noqa: E402

FIX = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/ko_polish/recent48_2026-09-30.json")


def main():
    d = json.loads(FIX.read_text(encoding="utf-8"))
    print(f"# ko_polish 검증 보고 — 표 버전 {kp.rules().get('version')} · 해시 {kp.rules_hash()}\n")
    print("## ① VRSUK 16값(옵션 값 → 쿠팡 28자)\n")
    print("| # | 원문 | 규칙 결과 | 남은 한자 | 쿠팡 값(≤28) | 길이 |\n|---|---|---|---|---|---|")
    outs = []
    for i, v in enumerate(d["vrsuk_values"], 1):
        r = kp.option_value(v)
        s = kp.shorten(r["value"] or r["draft"])
        outs.append(s)
        print(f"| {i} | {v} | {r['draft']} | {r['left'] or '0'} | {s} | {len(s)} |")
    print(f"\n고유 {len(set(outs))}/{len(outs)} · 한자 잔존 {sum(1 for v in d['vrsuk_values'] if kp.option_value(v)['left'])}건\n")

    print("## ② 상품명 번역본 정리(지운 말)\n")
    print("| id | 번역본(정리 전) | 정리 후 | 지운 말 |\n|---|---|---|---|")
    del_total = 0
    for iid, _cn, ko in d["titles"]:
        h: dict = {}
        after = kp.polish_ko(ko, hits=h)
        dels = h.get("delete") or []
        del_total += len(dels)
        if dels:
            print(f"| {iid} | {ko} | {after} | {', '.join(dels)} |")
    print(f"\n상품명 {len(d['titles'])}건 중 삭제 적중 {del_total}회(없는 건 표에서 뺌)\n")

    print("## ③ 옵션 값 표본 — 규칙만으로 끝 / 번역기 필요\n")
    done, need = [], []
    for v in d["values_sample"]:
        if not kp.has_han(v):
            continue
        r = kp.option_value(v)
        (done if r["value"] else need).append((v, r))
    print(f"한자 있는 표본 {len(done) + len(need)}개: 규칙만으로 끝 {len(done)} · 번역기 필요 {len(need)}\n")
    print("| 원문 | 결과(≤28) | 규칙 적중 |\n|---|---|---|")
    for v, r in done:
        print(f"| {v} | {kp.shorten(r['value'])} | {len((r['hits'].get('replace') or [])) + len((r['hits'].get('delete') or []))} |")
    print("\n| 원문 | 규칙 뒤 초안(번역기로 갈 몫) | 남은 한자 |\n|---|---|---|")
    for v, r in need:
        print(f"| {v} | {r['draft']} | {r['left']} |")

    print("\n## ④ 이미지 OCR 번역문 — 표시광고 위험 · 정리 후\n")
    t = d["vrsuk_image0"]["target_text"]
    print(f"- 위험 문구: {kp.ban_hits(t) + kp.ban_hits(d['vrsuk_image0']['source_text'])}")
    print(f"- 정리 후(참고 — 이미지 글자는 텐센트가 이미 그려서 보내므로 **바뀌지 않는다**): {kp.polish_ko(t)}")


if __name__ == "__main__":
    main()
