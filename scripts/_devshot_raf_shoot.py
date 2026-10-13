import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
SP = Path(sys.argv[1])
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    for f in ["m5_before", "m5_after", "m5_applied", "m5_fail", "pv_before", "pv_after", "pv_applied", "pv_fail"]:
        pg = b.new_page(viewport={"width": 460 if f.startswith("m5") else 800, "height": 400}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto((SP / f"{f}.html").as_uri())
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(SP / "shots" / f"{f}.png"), full_page=True)
        print(f, "errors:", errs, pg.inner_text("body")[:300].replace("\n", " | "))
    b.close()
