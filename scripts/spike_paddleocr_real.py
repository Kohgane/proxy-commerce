"""D3-7 보강 — PaddleOCR **실모델**(기본값 그대로) 1회 실측. 오너가 Vultr에서 돌린다.

CC 컨테이너는 모델 호스트(HF·ModelScope·AIStudio·BOS) 송신이 막혀 실모델을 못 받았다(2026-09-26 실측:
「No model hoster is available」). 대역(PP-OCRv4 ONNX) 숫자만 볼트에 있다 — 이 스크립트가 실제 숫자를 잰다.

    . /root/spike/bin/activate                    # 오너 Vultr venv(StealthyFetcher 돌린 그 venv)
    pip install paddlepaddle paddleocr
    python scripts/spike_paddleocr_real.py "https://res.cloudinary.com/<cloud>/image/upload/<...>.jpg"

⚠️ Vultr는 **python 3.14**다(오너 실측). paddlepaddle 휠이 3.14를 아직 안 내면 pip이 「No matching
distribution」로 끝난다 — 그러면 3.12 venv로 한 번 더(`uv venv -p 3.12 /root/ocr312` 등). 그 오류 원문도
그대로 결과다(설치 가능 여부가 배치 판단의 첫 칸). RAM 950MB(가용 711MB)라 peak RSS가 판정의 핵심.

출력(JSON 한 덩어리 — 그대로 볼트에 붙인다):
- versions: paddlepaddle · paddleocr 버전
- install_mb: 설치 크기(패키지 폴더) + 모델 캐시 크기(~/.paddlex/official_models) — **모델 이름 목록**도 같이
  (어떤 모델이 기본으로 내려왔는지 = PP-OCRv6인지 여기서 확인. 추측으로 적지 않는다)
- sec: 초기화 · 첫 장(콜드) · 둘째 장(웜) — 같은 이미지 2회
- peak_rss_mb: 프로세스 최대 RSS
- boxes: 글자 줄마다 {text, score, box(4점)}

이 스크립트는 앱 코드를 바꾸지 않는다. 판정(배치 위치 — 앱 워커 vs Vultr OCR 워커)은 이 숫자를 보고 오너가 한다.
"""
import json
import os
import resource
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def _dir_mb(p: Path) -> float:
    total = 0
    if p.exists():
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
    return round(total / 1024 / 1024, 1)


def _pkg_dirs():
    out = {}
    for name in ("paddle", "paddleocr", "paddlex"):
        try:
            mod = __import__(name)
            out[name] = _dir_mb(Path(mod.__file__).parent)
        except Exception as exc:
            out[name] = f"없음({type(exc).__name__})"
    return out


def _versions():
    out = {}
    for dist in ("paddlepaddle", "paddleocr", "paddlex"):
        try:
            from importlib.metadata import version
            out[dist] = version(dist)
        except Exception:
            out[dist] = ""
    return out


def _rows(result):
    """predict() 결과 → [{text, score, box}]. 3.x 결과 객체는 dict처럼 읽힌다(키 이름 그대로 사용)."""
    rows = []
    for res in result or []:
        d = None
        for get in (lambda r: dict(r), lambda r: r.json.get("res", r.json)):
            try:
                d = get(res)
                break
            except Exception:
                continue
        if not isinstance(d, dict):
            rows.append({"raw": str(res)[:300]})
            continue
        texts = d.get("rec_texts") or []
        scores = d.get("rec_scores") or []
        polys = d.get("rec_polys") if d.get("rec_polys") is not None else (d.get("dt_polys") or [])
        for i, t in enumerate(texts):
            box = polys[i] if i < len(polys) else None
            try:
                box = [[int(x), int(y)] for x, y in (box.tolist() if hasattr(box, "tolist") else box)]
            except Exception:
                box = str(box)[:120]
            sc = scores[i] if i < len(scores) else None
            rows.append({"text": t, "score": round(float(sc), 3) if sc is not None else None, "box": box})
    return rows


def main(argv):
    if len(argv) < 2:
        print("사용: python scripts/spike_paddleocr_real.py <이미지 URL>")
        return 2
    url = argv[1]
    out = {"url": url, "versions": _versions()}
    tmp = Path(tempfile.mkdtemp()) / "img"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tmp.write_bytes(r.read())
        out["image_bytes"] = tmp.stat().st_size
    except Exception as exc:
        out["error"] = f"이미지를 못 받음: {type(exc).__name__}: {exc}"
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 1

    t0 = time.perf_counter()
    try:
        from paddleocr import PaddleOCR
        # 기본값 그대로(모델 선택을 우리가 바꾸지 않는다) — 방향 분류·펴기만 끈다(상품 이미지엔 불필요).
        ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                        use_textline_orientation=False)
    except Exception as exc:
        out["error"] = f"초기화 실패: {type(exc).__name__}: {exc}"
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 1
    t1 = time.perf_counter()
    first = ocr.predict(str(tmp))
    t2 = time.perf_counter()
    second = ocr.predict(str(tmp))
    t3 = time.perf_counter()

    cache = Path(os.path.expanduser("~/.paddlex/official_models"))
    out["models_downloaded"] = sorted(p.name for p in cache.iterdir()) if cache.exists() else []
    out["install_mb"] = {"packages": _pkg_dirs(), "model_cache": _dir_mb(cache)}
    out["sec"] = {"init": round(t1 - t0, 2), "first_image_cold": round(t2 - t1, 2),
                  "second_image_warm": round(t3 - t2, 2)}
    out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    out["cpu_count"] = os.cpu_count()
    out["boxes"] = _rows(first)
    out["boxes_n"] = len(out["boxes"])
    out["warm_same_count"] = len(_rows(second)) == out["boxes_n"]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
