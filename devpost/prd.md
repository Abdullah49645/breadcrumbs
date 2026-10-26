---
doc: prd
status: approved
---

# Breadcrumbs — Product Requirements

A web app for people who post photos publicly that shows how an AI geolocator narrows down their home by combining their photos, and which photos to hold back.
Source: `scope.md > The Unique Kernel`, `scope.md > Who It's For`.

## The Core Journey
1. The visitor lands on a page that says what Breadcrumbs does and who it's for, with two choices: **Watch it find a home** (demo feed) or **Check my own photos**.
2. *Demo:* the analysis opens immediately with 11 openly licensed photos from one neighbourhood and a marked "home".
   *Own photos:* the user picks 2–24 photos in posting order, optionally clicks their home on a map, and presses **Analyse**; a progress bar runs while the local server works.
3. **Replay.** The user presses play. Photos are added one at a time; for each, the map updates the AI's belief, and the panel shows the chance the AI picks their neighbourhood, the best guess's distance from home, the search radius, and what this photo said on its own.
4. **Giveaways.** The user sees photos ranked by how much each one adds (leave-one-out), and for any photo a heatmap of which regions leak.
5. **Fix plan.** The user sees the ordered list of edits (hold back photo #n, or blur its leak zone) and presses **Apply**. Each step ticks off, held-back photos are marked, and the final numbers — re-run through the model — show whether the neighbourhood is out of reach.
Success: the user knows which photos are dangerous together, and the after-numbers prove the fix works.

## Screens and Layout
- **Landing:** hero statement, two buttons, three "how it works" cards, a short "why single-photo tools miss it" section.
- **Upload:** drop zone with thumbnails, a small map for the optional home pin, server status, Analyse button, progress bar.
- **Analysis:** three columns — left rail of posted photos in order; centre map; right panel with three tabs (Replay, Giveaways, Fix plan).

## Look and Feel
Investigation file: off-white paper (#f6f3ec), black ink, a single warning red (#d6402b), blue for home. Instrument Serif for headlines and the big percentage, Inter for text, JetBrains Mono for numbers and labels. Muted grey map tiles so the red belief stands out. Avoid default dashboard styling and gradients. (`scope.md > Inspiration & Identity`)

## Features and Behavior

### Replay
- Step forward/back or play automatically (one photo every ~2 s).
- Map shows: belief heat (cells sized ~1.7 km), best-guess marker, search circle (radius holding 75% of the belief), home marker and a 2 km neighbourhood ring.
- Panel shows: % of the AI's belief within 2 km of home, a bar per step, best-guess distance, search radius, and a one-line note ("On its own, this photo points 0.3 km from home. +29 points for your neighbourhood").
- [ ] Odds and map change on every step, from the real model output.

### Giveaways
- Top six photos by leave-one-out contribution, as bars ("−23 pts if removed").
- Selecting a photo shows a 4×4 leak heatmap over it and which other photos point at the same place.
- [ ] Clicking a photo in the rail or the ranking switches the heatmap.

### Fix plan
- Greedy plan of up to 10 steps; each step shows the odds and guess distance after it.
- Apply animates the steps, greys out held-back photos, swaps in blurred versions, and shows the re-computed result in green if cleared.
- Undo restores the feed.
- [ ] "After" numbers come from re-running the fused model on the edited feed, not from an estimate.

## States and Boundaries
- **No home pin (own photos):** the panel uses the model's confidence in its best cell instead of neighbourhood odds; distance-from-home shows "—".
- **Server not running:** the upload page says the demo still works and gives the start command.
- **Analysis error:** the progress text shows the error.
- **Persistence:** nothing persists. Uploaded photos live in server memory for the session only; GPS EXIF is stripped before analysis.
- **Boundary:** only photos the user uploads; no URLs, profiles, or other people's accounts.

## Product Decisions
- Measure the whole feed, not single photos — that is the gap in existing tools (learner's choice after prior-art research).
- Globally relevant framing, not tied to one country (learner's explicit requirement).
- Open model (GeoCLIP) so results are reproducible without paid keys (accepted recommendation).
- Demo persona uses openly licensed Wikimedia Commons photos with credits, so the demo is real model output on real photos.

## What We're Building
Landing, upload, and analysis screens; the fusion engine; leave-one-out ranking; region leak maps; greedy fix plan with re-verification; a bundled precomputed demo session; local FastAPI server.

## Deferred From the POC
- Hosted backend (judges use the demo; own-photo analysis runs locally) — model is ~1.6 GB and needs a server.
- Inpainting edits — blur is enough to measure leakage.

## Possible Later Enhancements
A second geolocator for cross-model checks; "check before posting" for a single new photo against an existing feed; browser extension.

## Non-Goals
- Not a geolocation tool for finding other people.
- Not a guarantee of safety: it measures one model's behaviour.

## Open Questions
None blocking. How well results transfer to commercial geolocators is untested (can wait).
