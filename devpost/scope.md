---
doc: scope
status: approved
---

# Breadcrumbs

See how close an AI geolocator gets to your home by combining the photos you've already posted — and which photos to hold back.

## The Unique Kernel
Location privacy measured across a **whole feed**, not one photo. Each photo alone is vague ("a big city"); together they triangulate a neighbourhood. Breadcrumbs fuses the evidence from every photo, shows the moment the AI locks on, and finds the smallest change to the feed that breaks the lock. Existing tools (EXIF strippers, face/plate blurrers, single-image geoprivacy research) all work one image at a time.

## Who It's For
Anyone who posts photos publicly and doesn't want strangers to find where they live: people dealing with a stalker or an ex, creators with a following, parents, journalists. Today they strip GPS and blur faces, then assume they're safe.

## The Core Loop
Pick the photos you've posted (in posting order) and optionally mark your home on a map → watch the replay, photo by photo, as the AI's odds of picking your neighbourhood climb → see which photos and which parts of them give it away → apply the fix plan and watch the odds fall. People come back before posting a new batch.

## Inspiration & Identity
Serious, calm, a little unsettling — an investigation file, not a hacker toy. Off-white paper, black ink, one warning red. Editorial serif headlines.
References: GeoSpy and the 2025 stalking coverage (https://www.malwarebytes.com/blog/news/2025/01/ai-tool-geospy-analyzes-images-and-identifies-locations-in-seconds), "Doxing via the Lens" (https://arxiv.org/abs/2504.19373).

## Why This Matters to the Learner
Wanted a genuinely original, globally relevant entry rather than another AI wrapper ("I want a 10 on 10 not a 5 on 10"). Chose this after prior-art research showed every existing defence works on single photos.

## What "Working" Looks Like
Open the app, start the demo feed, press play: a real model's odds of picking the persona's neighbourhood climb from ~15% to ~86% across 11 ordinary photos (snow, cherry blossoms, a bookstore). Then the fix plan holds back a few photos and the odds fall to ~5%, with the AI's guess moved out of the neighbourhood. **The "oh" beat:** none of the photos shows an address, yet together they find the block.

## The POC Boundary
- Analyse 2–24 uploaded photos with one open geolocation model (GeoCLIP).
- Cumulative replay, leave-one-out photo ranking, region-level leak map, greedy fix plan re-verified with the model.
- A bundled demo feed that works with no backend, for judges.
- Optional home pin, kept local.

## Later
Second geolocation model for cross-checking; inpainting instead of blur; browser extension that checks before you post; per-platform import.

## Explicitly Cut
- **Looking up anyone's profile or scraping accounts** — the tool must stay defensive; it only analyses photos the user hands it.
- **Commercial VLM geolocators** — need paid keys and may refuse; an open model keeps every number reproducible.
- **Accounts and stored history** — privacy tool; nothing is kept.
