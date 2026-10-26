"""Breadcrumbs engine.

Turns a set of photos into a cumulative "where does this person live" estimate,
explains which photos and which image regions drive it, and plans the smallest
set of edits that pushes the estimate away from the user's home.

Model: GeoCLIP (Vivanco Cepeda et al., NeurIPS 2023). GeoCLIP scores an image
against any GPS coordinate, which lets us evaluate every photo on one shared set
of candidate locations and fuse the evidence across photos.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter

torch.set_grad_enabled(False)

EARTH_KM = 6371.0088

# Fusion settings.
TEMPERATURE = 1.0        # softens each photo's distribution before fusion
FLOOR = 0.02             # each photo may be "elsewhere" (a trip, a friend's place)
PRIOR_ALPHA = 0.5        # strength of the density-prior correction (see summarize)
MASS = 0.75              # search area = radius holding this share of belief
HOME_KM = 2.0            # "your neighbourhood" = within this distance of home
SAFE_MASS = 0.10         # fixed when < 10% of the belief is left near home
PATCH_GRID = 4           # occlusion grid per photo (4 x 4 regions)


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


@dataclass
class Photo:
    name: str
    image: Image.Image
    feature: torch.Tensor | None = None                         # (512,)
    patch_features: list[torch.Tensor] = field(default_factory=list)


class Engine:
    def __init__(self, cache_dir: str | None = None):
        from geoclip import GeoCLIP

        self.model = GeoCLIP()
        self.model.eval()
        self.scale = float(self.model.logit_scale.exp())
        self.gallery = self.model.gps_gallery.float()            # (N, 2) lat, lon
        self.gallery_np = self.gallery.numpy()
        cache = os.path.join(cache_dir or os.path.dirname(__file__), "cache", "gallery_feats.pt")
        if os.path.exists(cache):
            self.gallery_feats = torch.load(cache)
        else:
            feats = []
            for i in range(0, len(self.gallery), 8192):
                feats.append(F.normalize(self.model.location_encoder(self.gallery[i:i + 8192]), dim=1))
            self.gallery_feats = torch.cat(feats)
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            torch.save(self.gallery_feats, cache)
        self.cells = Cells(self.gallery_np)

    # ------------------------------------------------------------------ features
    def _encode(self, images: list[Image.Image]) -> torch.Tensor:
        enc = self.model.image_encoder
        x = torch.cat([enc.preprocess_image(im.convert("RGB")) for im in images])
        return F.normalize(enc(x), dim=1)

    def encode_photos(self, photos: list[Photo], with_patches: bool = True, progress=None):
        for idx, p in enumerate(photos):
            imgs = [p.image]
            if with_patches:
                imgs += [occlude(p.image, r, c) for r in range(PATCH_GRID) for c in range(PATCH_GRID)]
            feats = []
            for i in range(0, len(imgs), 6):
                feats.append(self._encode(imgs[i:i + 6]))
            feats = torch.cat(feats)
            p.feature = feats[0]
            p.patch_features = list(feats[1:])
            if progress:
                progress(idx + 1, len(photos))

    # ------------------------------------------------------------------ beliefs
    def logp(self, feature: torch.Tensor, loc_feats: torch.Tensor, logz: float) -> np.ndarray:
        """Log-probability of each location for one photo, with a floor so one
        misleading photo can't veto the others."""
        logits = (self.scale * (loc_feats @ feature)) / TEMPERATURE
        lp = logits - logz
        n = len(self.gallery)
        mixed = torch.logaddexp(lp + math.log(1 - FLOOR), torch.full_like(lp, math.log(FLOOR / n)))
        return mixed.numpy()

    def logz(self, feature: torch.Tensor) -> float:
        return float(torch.logsumexp((self.scale * (self.gallery_feats @ feature)) / TEMPERATURE, dim=0))

    def gallery_logp(self, feature: torch.Tensor) -> np.ndarray:
        return self.logp(feature, self.gallery_feats, self.logz(feature))


def occlude(img: Image.Image, r: int, c: int) -> Image.Image:
    """Hide one region of the photo behind a heavy blur (what the user would do)."""
    w, h = img.size
    box = (int(c * w / PATCH_GRID), int(r * h / PATCH_GRID), int((c + 1) * w / PATCH_GRID), int((r + 1) * h / PATCH_GRID))
    out = img.convert("RGB").copy()
    region = out.crop(box).filter(ImageFilter.GaussianBlur(radius=max(w, h) / 25))
    out.paste(region, box)
    return out


def blur_regions(img: Image.Image, regions: list[int]) -> Image.Image:
    out = img.convert("RGB")
    for k in regions:
        out = occlude(out, k // PATCH_GRID, k % PATCH_GRID)
    return out


# ---------------------------------------------------------------------- fusion
CELL_DEG = 0.015   # ~1.7 km cells: photos near home are rarely taken at one exact point


class Cells:
    """Bins the GPS gallery into ~1.7 km cells and smooths each photo's belief
    over neighbouring cells, so photos taken around the same neighbourhood
    reinforce each other instead of disagreeing about individual points."""

    def __init__(self, gallery: np.ndarray):
        lat, lon = gallery[:, 0], gallery[:, 1]
        ci = np.floor(lat / CELL_DEG).astype(np.int64)
        cj = np.floor(lon * np.cos(np.radians(lat)) / CELL_DEG).astype(np.int64)
        keys = ci * 1_000_000 + cj
        self.ukeys, self.point_cell = np.unique(keys, return_inverse=True)
        self.m = len(self.ukeys)
        lookup = {int(k): n for n, k in enumerate(self.ukeys)}
        ui, uj = self.ukeys // 1_000_000, self.ukeys % 1_000_000
        # fix negative modulo for western longitudes
        uj = np.where(uj > 500_000, uj - 1_000_000, uj); ui = (self.ukeys - uj) // 1_000_000
        rows, cols = [], []
        for n in range(self.m):
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    k = int((ui[n] + di) * 1_000_000 + (uj[n] + dj))
                    t = lookup.get(k)
                    if t is not None:
                        rows.append(n); cols.append(t)
        self.nb_rows, self.nb_cols = np.array(rows), np.array(cols)
        w = np.bincount(self.point_cell, minlength=self.m).astype(float)
        self.lat = np.bincount(self.point_cell, weights=lat, minlength=self.m) / w
        self.lon = np.bincount(self.point_cell, weights=lon, minlength=self.m) / w

        self.log_prior = self.log_mass(None)

    def log_mass(self, lp: np.ndarray | None) -> np.ndarray:
        if lp is None:   # the gallery's own density = the model's built-in prior
            p = np.full(len(self.point_cell), 1.0 / len(self.point_cell))
        else:
            p = np.exp(lp - lp.max()); p /= p.sum()
        mass = np.bincount(self.point_cell, weights=p, minlength=self.m)
        smooth = np.bincount(self.nb_rows, weights=mass[self.nb_cols], minlength=self.m) / 9.0
        smooth = 0.5 * mass + 0.5 * smooth
        smooth /= smooth.sum()
        return np.log((1 - FLOOR) * smooth + FLOOR / self.m)


def summarize(engine: Engine, logps: list[np.ndarray], feats=None, home=None, top=400):
    """Fuse the photos' cell beliefs (a product of experts) and report the best
    guess, the search area that holds 90% of the belief, and the distance to home."""
    cells = engine.cells
    # Product of experts. Each photo's belief already contains the gallery's
    # density prior (where photos tend to be taken), so divide it back out
    # (k-1) times; otherwise dense cities win just for being photographed a lot.
    # We apply it at half strength: full strength over-rewards sparsely
    # photographed cells, where a single gallery point makes the ratio unstable.
    total = (np.sum([cells.log_mass(lp) for lp in logps], axis=0)
             - PRIOR_ALPHA * (len(logps) - 1) * cells.log_prior)
    post = np.exp(total - total.max()); post /= post.sum()
    best = int(post.argmax())
    b_lat, b_lon = float(cells.lat[best]), float(cells.lon[best])
    d = haversine_km(b_lat, b_lon, cells.lat, cells.lon)
    order = np.argsort(d)
    cum = np.cumsum(post[order])
    k = int(np.searchsorted(cum, MASS))
    radius = float(max(d[order[min(k, len(order) - 1)]], 1.0))
    idx = np.argsort(post)[::-1][:top]
    heat = [[round(float(cells.lat[i]), 5), round(float(cells.lon[i]), 5), round(float(post[i]), 6)] for i in idx if post[i] > 1e-5]
    out = {"lat": round(b_lat, 5), "lon": round(b_lon, 5), "radius_km": round(radius, 2), "heat": heat,
           "confidence": round(float(post[best]), 4)}
    if home is not None:
        out["home_km"] = round(float(haversine_km(b_lat, b_lon, home[0], home[1])), 2)
        # share of the AI's belief that sits in the user's own neighbourhood
        near = haversine_km(home[0], home[1], cells.lat, cells.lon) <= HOME_KM
        out["home_mass"] = round(float(post[near].sum()), 4)
    return out


def overlap(a: np.ndarray, b: np.ndarray) -> float:
    """Bhattacharyya coefficient between two photos' individual beliefs:
    1 = they point at exactly the same place, 0 = no agreement."""
    pa = np.exp(a - a.max()); pa /= pa.sum()
    pb = np.exp(b - b.max()); pb /= pb.sum()
    return float(np.sum(np.sqrt(pa * pb)))


def analyze(engine: Engine, photos: list[Photo], home=None, target_km: float = 5.0, progress=None):
    engine.encode_photos(photos, progress=progress)
    n = len(photos)
    logps = [engine.gallery_logp(p.feature) for p in photos]
    feats = [p.feature for p in photos]

    # 1. Cumulative replay: what the AI knows after each additional photo.
    replay = []
    for k in range(1, n + 1):
        s = summarize(engine, logps[:k], home=home)
        single = summarize(engine, [logps[k - 1]], home=home, top=0)
        s["photo_alone"] = {kk: single[kk] for kk in ("lat", "lon", "radius_km", "home_km") if kk in single}
        replay.append(s)
    final = replay[-1]
    metric = "home_km" if home is not None else "radius_km"

    # 2. Which photos matter: leave each one out and see how far the guess moves.
    influence = []
    for i in range(n):
        rest = [l for j, l in enumerate(logps) if j != i]
        rf = [f for j, f in enumerate(feats) if j != i]
        s = summarize(engine, rest, home=home, top=0) if rest else None
        influence.append({"without_home_km": s.get("home_km") if s else None,
                          "without_home_mass": s.get("home_mass") if s else None,
                          "without_radius_km": s["radius_km"] if s else None})

    # 3. Which regions leak: blur each region and measure how much less the photo
    #    supports the fused best guess.
    g = engine.gallery_np
    near = haversine_km(final["lat"], final["lon"], g[:, 0], g[:, 1]) < max(final["radius_km"], 2.0)
    regions = []
    patch_logps = []
    for i, p in enumerate(photos):
        base = _support(logps[i], near)
        pl = [engine.gallery_logp(pf) for pf in p.patch_features]
        patch_logps.append(pl)
        drops = [max(0.0, base - _support(x, near)) for x in pl]
        m = max(drops) or 1.0
        regions.append({"support": round(base, 3), "leak": [round(d / m, 3) for d in drops], "raw": [round(d, 3) for d in drops]})

    # 4. Cross-photo corroboration: which photos point at the same place.
    links = []
    for i in range(n):
        for j in range(i + 1, n):
            o = overlap(logps[i], logps[j])
            if o > 0.15:
                links.append([i, j, round(o, 3)])

    # 5. Fix plan: greedily apply the single edit (blur a photo's worst region, or
    #    drop the photo) that pushes the guess furthest, until it clears the target.
    plan = fix_plan(engine, photos, logps, patch_logps, regions, home, target_km)

    return {
        "photos": [{"name": p.name} for p in photos],
        "replay": replay,
        "influence": influence,
        "regions": regions,
        "links": links,
        "plan": plan,
        "metric": metric,
        "target_km": target_km,
        "model": "GeoCLIP (ViT-L/14 image encoder, 100k-point GPS gallery)",
    }


def _support(lp: np.ndarray, mask: np.ndarray) -> float:
    p = np.exp(lp - lp.max()); p /= p.sum()
    return float(math.log(max(p[mask].sum(), 1e-12)))


def fix_plan(engine, photos, logps, patch_logps, regions, home, target_km, max_steps=10):
    """Greedy: repeatedly apply the one edit that removes the most belief from
    the user's neighbourhood. Edits are 'blur this photo's leakiest region' or
    'don't post this photo'; blurs are preferred because they keep the photo."""
    use_home = home is not None
    state_lp = list(logps)
    blurred = {i: [] for i in range(len(photos))}
    dropped: set[int] = set()
    steps = []

    def objective(lps):
        s = summarize(engine, lps, home=home, top=0)
        return (s["home_mass"] if use_home else -s["radius_km"]), s

    def done(s):
        if use_home:
            return s["home_mass"] < SAFE_MASS and s["home_km"] >= target_km
        return s["radius_km"] >= target_km

    zones: dict[int, tuple[list[int], np.ndarray]] = {}

    def zone(i):
        """The photo's leak zone: its three leakiest regions, blurred together."""
        if i not in zones:
            ks = [int(r) for r in np.argsort(regions[i]["raw"])[::-1][:3]]
            f = engine._encode([blur_regions(photos[i].image, ks)])[0]
            zones[i] = (ks, engine.gallery_logp(f))
        return zones[i][0]

    def zone_lp(i):
        zone(i)
        return zones[i][1]

    cur, cur_s = objective(state_lp)
    for _ in range(max_steps):
        if done(cur_s):
            break
        best = None
        alive = [i for i in range(len(photos)) if i not in dropped]
        for i in alive:
            pos = alive.index(i)
            options = [("drop", None)]
            if not blurred[i]:
                options.append(("blur", zone(i)))
            for kind, kk in options:
                if kind == "drop":
                    trial = state_lp[:pos] + state_lp[pos + 1:]
                    if not trial:
                        continue
                else:
                    trial = list(state_lp)
                    trial[pos] = zone_lp(i)
                val, s = objective(trial)
                penalty = 0.04 if (kind == "drop" and use_home) else (0.15 * abs(cur) if kind == "drop" else 0.0)
                if best is None or val + penalty < best[0]:
                    best = (val + penalty, kind, i, kk, trial)
        if best is None:
            break
        _, kind, i, kk, trial = best
        if kind == "drop":
            dropped.add(i)
            state_lp = trial
        else:
            blurred[i] = list(kk)
            state_lp = trial
        cur, cur_s = objective(state_lp)
        step = {"action": kind, "photo": i, "region": kk, "home_km": cur_s.get("home_km"),
                "home_mass": cur_s.get("home_mass"), "radius_km": cur_s["radius_km"]}
        steps.append(step)
    final = summarize(engine, state_lp, home=home)
    return {"steps": steps, "after": final, "blurred": {str(k): v for k, v in blurred.items() if v},
            "dropped": sorted(dropped), "cleared": done(final)}
