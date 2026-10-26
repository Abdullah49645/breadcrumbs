---
doc: spec
status: approved
---

# Breadcrumbs — Technical Spec

## How This Works, In Plain Language
- **The geolocator (GeoCLIP).** An open AI model that turns a photo into a "fingerprint" and can score that fingerprint against any GPS coordinate. It ships with 100,000 reference coordinates spread over the world.
- **The engine.** For each photo it gets a probability for each reference coordinate, then groups coordinates into ~1.7 km cells. Photos taken around the same neighbourhood rarely share an exact point, so cells let them agree.
- **Fusion.** Multiply the photos' cell probabilities together (a "product of experts"): places every photo finds plausible rise, places only one photo likes fade. Because every photo's opinion already includes "lots of photos are taken in big cities", that shared bias is divided back out at half strength. Each photo is also allowed a 2% chance of being "somewhere else" so one trip photo can't veto the rest.
- **Explanations, by measuring.** Leave each photo out and re-fuse to see how much it mattered. Blur each of 16 regions of a photo and re-score it to see which region leaks.
- **Fix plan.** A greedy search tries "hold back photo X" or "blur photo X's three leakiest regions", keeps the one that removes the most belief from the neighbourhood, and repeats until less than 10% of the belief remains within 2 km of home and the best guess is at least 5 km away.
- **The web app.** A single static page that draws the result on a map. It can load a precomputed demo session or talk to the local server.

This shape keeps every number reproducible (one open model, no keys) and keeps the photos on the user's machine.

## The Core Journey Through the System
PRD ref: `prd.md > The Core Journey`.
1. User clicks **Watch it find a home** → `web/app.js` fetches `web/demo/session.json` → renders feed, replay, ranking, plan.
2. Or user uploads photos → `POST /api/analyze` (`server/app.py`) strips EXIF, resizes, starts a background job → `engine.analyze()` encodes each photo plus 16 blurred variants → returns a session object → the page polls `GET /api/jobs/{id}` → same rendering path.
3. Play → `setStep(k)` shows `replay[k-1]` on the map and panel.
4. Giveaways → ranking from `influence`, heatmap from `regions[i].leak`, corroboration from `links`.
5. Apply → steps from `plan.steps`, result from `plan.after`.

## Stack
- Python 3.11+ (tested 3.13), **PyTorch** (CPU) — https://pytorch.org
- **GeoCLIP** 1.x (Vivanco Cepeda et al., NeurIPS 2023) — https://github.com/VicenteVivan/geo-clip
- **FastAPI** + Uvicorn — https://fastapi.tiangolo.com
- **Pillow**, **NumPy**
- Front end: plain HTML/CSS/JS, **Leaflet 1.9** — https://leafletjs.com, OpenStreetMap tiles.
Rationale: no build step for the front end; the demo can be hosted as static files.

## Where It Runs and How Someone Tries It
- Demo only: serve `web/` statically (e.g. GitHub Pages) and open it.
- Full app: `pip install -r requirements.txt`, then `uvicorn server.app:app --port 8000`, open http://localhost:8000. First run downloads GeoCLIP weights (~1.6 GB).
- Rebuild demo: `python -m server.precompute demo/photos --home 40.6712,-73.9790 --order ...`.
- Demo video is a screen recording of the demo flow.

## Look and Feel
Paper #f6f3ec, card #fffdf8, ink #16140f, red #d6402b, blue #1f4fd1. Instrument Serif (headlines, the big %), Inter (UI), JetBrains Mono (numbers, labels). Calm and spacious on the landing page; denser three-column layout in analysis. Map tiles desaturated with a CSS filter. Copy is plain and direct.

## Components

### Engine — `server/engine.py`
`Engine` loads GeoCLIP and caches gallery location features. `Cells` bins the gallery and smooths per-photo mass over 3×3 neighbours. `summarize()` fuses and reports best guess, search radius, home distance, neighbourhood odds. `analyze()` produces replay, influence, regions, links, plan. `fix_plan()` runs the greedy search.
PRD ref: `prd.md > Features and Behavior`.

### Server — `server/app.py`
Upload, background job, polling, photo serving (original or fixed). Photos kept in memory only.
PRD ref: `prd.md > States and Boundaries`.

### Demo builder — `server/precompute.py`
Runs `analyze()` on `demo/photos`, writes `web/demo/session.json` and images with credits.

### Web app — `web/index.html`, `web/app.js`, `web/styles.css`
Landing, upload, analysis views; Leaflet map; replay, giveaways, fix plan.
PRD ref: `prd.md > Screens and Layout`.

## Data Model
Session JSON:
- `photos[i]`: `name`, `src`, `fixed`, `credit`, `truth`
- `replay[k]`: `lat`, `lon`, `radius_km`, `confidence`, `home_km`, `home_mass`, `heat[[lat,lon,w]]`, `photo_alone`
- `influence[i]`: `without_home_mass`, `without_home_km`, `without_radius_km`
- `regions[i]`: `support`, `leak[16]` (normalised), `raw[16]`
- `links`: `[i, j, overlap]`
- `plan`: `steps[]`, `after`, `blurred{i: [regions]}`, `dropped[]`, `cleared`
- `home`: `[lat, lon]`
Nothing is persisted between server restarts.

## File Structure
```
breadcrumbs/
├── server/
│   ├── engine.py        # fusion, explanations, fix plan
│   ├── app.py           # FastAPI server
│   └── precompute.py    # builds the bundled demo session
├── web/
│   ├── index.html       # landing, upload, analysis
│   ├── app.js           # map + UI logic
│   ├── styles.css
│   └── demo/            # session.json + demo images
├── demo/photos/         # source demo photos + credits.json
├── docs/screenshots/    # README images
├── devpost/             # scope, prd, spec, checklist
├── requirements.txt
└── README.md
```

## External Services and Dependencies
- GeoCLIP weights from Hugging Face (downloaded by the `geoclip` package on first run; free, no key).
- OpenStreetMap tiles (free, attribution required, light use).
- Leaflet and Google Fonts via CDN.
No paid APIs, no keys.

## Important Failure Modes
- **Model too vague on a user's photos** → odds stay low; the replay honestly shows "the AI never settles on your neighbourhood" and the plan is empty.
- **Server not running** → upload page explains; demo still works.
- **Region blurs too weak to matter** → the plan falls back to holding back photos (this is what happens on the demo feed).

## What Was Simplified and Why
- **Blur** instead of inpainting — enough to measure leakage; inpainting would need a diffusion model.
- **One model** instead of cross-model verification — keeps it reproducible; a second model would strengthen "the fix transfers".
- **Greedy search** instead of exact set optimisation — fast and explainable; exact search is exponential.
- **Demo persona** built from public Commons photos instead of a real person's feed — avoids exposing anyone's home.

## Decisions and Open Issues
- Half-strength density-prior correction (learner accepted the agent's recommendation after seeing both extremes: no correction drifted to a 7 km-away dense area; full correction drifted to a sparse cell 15 km away).
- Neighbourhood = 2 km; "cleared" = <10% belief within 2 km and best guess ≥5 km away.
- Genuine uncertainty discussed: whether fusing photos actually sharpens GeoCLIP's estimate. Investigated in the build by measuring the demo feed; it does (15% → 86%), but results depend on the model and the photos.
- Open: transfer to commercial geolocators untested.
