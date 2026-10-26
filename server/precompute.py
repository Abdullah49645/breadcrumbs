"""Build the bundled demo session so the app can be tried with no backend.

    python -m server.precompute demo/photos --home 40.6712,-73.9790 --out web/demo
"""

import argparse
import json
import os

from PIL import Image

from .engine import Engine, Photo, analyze, blur_regions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--home", required=True, help="lat,lon of the demo persona's home")
    ap.add_argument("--order", default="", help="comma-separated file order (story order)")
    ap.add_argument("--target", type=float, default=5.0)
    ap.add_argument("--out", default="web/demo")
    a = ap.parse_args()
    home = tuple(float(x) for x in a.home.split(","))
    names = a.order.split(",") if a.order else sorted(f for f in os.listdir(a.folder) if f.lower().endswith(".jpg"))
    credits = {c["file"]: c for c in json.load(open(os.path.join(a.folder, "credits.json")))}
    photos = []
    for n in names:
        im = Image.open(os.path.join(a.folder, n)).convert("RGB")
        im.thumbnail((1280, 1280))
        photos.append(Photo(n, im))
    res = analyze(Engine(), photos, home=home, target_km=a.target,
                  progress=lambda d, t: print(f"encoded {d}/{t}", flush=True))
    os.makedirs(os.path.join(a.out, "img"), exist_ok=True)
    for i, p in enumerate(photos):
        p.image.save(os.path.join(a.out, "img", f"{i:02d}.jpg"), quality=86)
        regions = res["plan"]["blurred"].get(str(i), [])
        if regions:
            blur_regions(p.image, regions).save(os.path.join(a.out, "img", f"{i:02d}-fixed.jpg"), quality=86)
        c = credits.get(p.name, {})
        res["photos"][i].update({"src": f"demo/img/{i:02d}.jpg",
                                 "fixed": f"demo/img/{i:02d}-fixed.jpg" if regions else None,
                                 "credit": {k: c.get(k) for k in ("title", "author", "license", "source")},
                                 "truth": [c.get("lat"), c.get("lon")]})
    res["home"] = list(home)
    with open(os.path.join(a.out, "session.json"), "w") as f:
        json.dump(res, f)
    r = res["replay"]
    print("replay home_km:", [s["home_km"] for s in r])
    print("replay radius:", [s["radius_km"] for s in r]); print("home mass:", [s["home_mass"] for s in r])
    print("plan:", res["plan"]["steps"], "cleared:", res["plan"]["cleared"])


if __name__ == "__main__":
    main()
