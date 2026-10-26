---
doc: checklist
status: approved
---

# Build Checklist

Build mode: fast

## Slices

- [x] **1. A photo set produces a fused location belief**
  Becomes usable: Running the engine on a folder of photos prints, per photo added, the best guess, search radius and distance from home.
  Why now: The kernel (multi-photo fusion) had to be proven before any UI.
  PRD ref: `prd.md > The Core Journey` (step 3)
  Spec ref: `spec.md > Engine — server/engine.py`
  Build: Load GeoCLIP, cache gallery location features, score each photo over the gallery, bin into cells, fuse.
  Verify (mechanical): On the demo feed, the share of belief within 2 km of home rises as photos are added.
  Learner check: Read the printed numbers and confirm the trend is real.
  Commit: `Add GeoCLIP fusion engine`

- [x] **2. Explanations and a fix plan**
  Becomes usable: The engine also returns leave-one-out influence, 4×4 region leak maps, photo-to-photo agreement, and a greedy fix plan re-verified by the model.
  Why now: "Which photos give it away" is the second half of the kernel.
  PRD ref: `prd.md > Features and Behavior` (Giveaways, Fix plan)
  Spec ref: `spec.md > Engine — server/engine.py`
  Build: Leave-one-out re-fusion, region blurs, Bhattacharyya overlap, greedy search over hold-back / blur-zone edits.
  Verify (mechanical): On the demo feed the plan clears (<10% belief within 2 km, guess ≥5 km away).
  Learner check: Read the plan and confirm it names specific photos.
  Commit: `Add explanations and fix plan`

- [x] **3. The demo feed plays in the browser**
  Becomes usable: Landing page → Watch it find a home → replay, giveaways, fix plan on a map, no backend needed.
  Why now: Judges must be able to see it working without installing anything.
  PRD ref: `prd.md > Screens and Layout`, `prd.md > Look and Feel`
  Spec ref: `spec.md > Web app`, `spec.md > Demo builder`
  Build: Precompute session.json from Commons photos with credits; static web app with Leaflet.
  Verify (mechanical): Headless browser run through all three tabs with no console errors; screenshots captured.
  Learner check: Watch the demo recording.
  Commit: `Add web app and bundled demo session`

- [x] **4. Your own photos, analysed locally**
  Becomes usable: Upload page with optional home pin; FastAPI server runs the same engine and the same views render the result.
  Why now: Turns the demo into a usable tool.
  PRD ref: `prd.md > The Core Journey` (step 2), `prd.md > States and Boundaries`
  Spec ref: `spec.md > Server — server/app.py`
  Build: Upload endpoint, background job, polling, EXIF stripping, photo serving.
  Verify (mechanical): Upload a set through the browser; result renders.
  Learner check: Try it with your own photos.
  Commit: `Add local upload and analysis server`

## Hands-on Checkpoints

- [x] Early usable behavior explored — engine numbers reviewed before the UI was built
- [ ] Final kick-the-tires exploration and feedback completed

## Final Review

- [ ] Final review complete — feedback resolved and learner confirms ready to ship

## Code Tour and App Map

- [ ] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [ ] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [ ] `devpost/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence: not started
Route and stops: not started
Edit outcome: not applicable
Reflection: not started
Activity mode: not started

## Revisions

- Fusion moved from individual GPS points to ~1.7 km cells — point-wise products locked onto a single unrelated point (Morningside Heights, 15 km away) because photos of one neighbourhood aren't taken at one exact spot.
- Added a half-strength density-prior correction — without it the guess drifted to a densely photographed area 7 km away; at full strength it drifted to a sparse cell 15 km away.
- Fix plan objective changed from "distance of the best guess" to "share of belief within 2 km of home" — the distance is step-shaped, so the greedy search had nothing to climb.
- Single-region blurs replaced by a three-region "leak zone" blur candidate — one 1/16 region barely moves GeoCLIP; on the demo feed holding back photos still wins.
