# Future Ideas — YIG Streaming Dashboard

Backlog of features considered during initial brainstorming but parked from v1. Ordered roughly by "value / scope-cost" — not by priority. Pull from this list when v1 is stable and you want to add another layer.

---

## ⭐ Sonification — hear the YIG drift

**The idea:** A toggle button in the header. When on, the current peak frequency drives a Web Audio oscillator. As the YIG peak drifts up, the audible tone drifts up. As it retunes (jumps), the tone steps. Watching the spectrogram while *hearing* it is the kind of thing that makes a visitor stop and say "wait, what."

**Why it's good here:** YIG drift is *slow and continuous* — perfect for sonification. A spectrogram is dense visual data; sound is a complementary, low-attention channel ("is the rig still alive while I'm reading email?"). And nobody else's lab dashboard has it.

**Implementation sketch:**
- Map peak frequency to audible range with a log mapping. E.g., 6.46 GHz → 220 Hz (A3); each 1 kHz of drift → 1 cent of pitch shift. Configurable mapping in the UI.
- One `OscillatorNode` (sine or triangle) + one `GainNode` for volume. ~30 lines of WebAudio.
- Smooth pitch updates with `oscillator.frequency.exponentialRampToValueAtTime(target, now + 0.05)` so retunes glissando rather than click.
- Toggle persists in `localStorage`. Default off (autoplay policies require user gesture anyway).
- Bonus: a "ping on retune" mode that plays a short bell whenever the tracker retunes, instead of continuous tone.

**Scope:** Small. ~80 lines, single component, no backend changes.

---

## Replay mode — watch the spectrogram build

**The idea:** Pick a window, hit play, watch the spectrogram build at 10×/100×/1000× speed. Pause, scrub, jump-to-end. Great for visitors and great for showing "look at this overnight run."

**Why it's good:** Turns a static historical view into something cinematic without inventing new data. Especially compelling because the YIG peak's smooth drift looks beautiful when sped up.

**Implementation sketch:**
- Client-side: load the full window via REST, then animate `Plotly.extendTraces` against the heatmap with a `requestAnimationFrame` loop scaled to the chosen playback speed.
- Add a transport bar: ⏮ ⏯ ⏭ + speed dropdown (1×/10×/100×/1000×) + a scrub slider.
- No backend changes if windows fit in memory client-side. For 7-day windows we'd stream-load progressively.

**Scope:** Medium. The animation timeline + transport bar is the work; the data loading reuses the range API.

---

## Annotations — the lab notebook layer

**The idea:** Click a moment on the spectrogram, leave a note ("retuned cavity", "bumped table", "swapped LO"). Notes render as flags on the time axis. Hover to read, click to edit/delete.

**Why it's good:** Turns the dashboard from "a viewer" into "a lab notebook that happens to have live data." Especially useful when reviewing what went weird at 2:47am.

**Implementation sketch:**
- New DuckDB table `notes(id, time_created, body, author)`.
- `POST /api/notes`, `GET /api/notes?from=&to=`, `DELETE /api/notes/{id}`.
- Plotly supports `layout.annotations` with arrow + label — drop them onto the spectrogram and trace plot at matching timestamps.
- The "author" field is whatever's in the session cookie (after we wire auth).

**Scope:** Medium. New table + 3 endpoints + a `<yig-notes-layer>` component.

---

## Compare two windows — A/B trace overlay

**The idea:** Pin a snapshot of the live trace ("save this trace"), then watch the live trace evolve next to it. Or pick two arbitrary times and overlay. Useful for "was the linewidth narrower yesterday?"

**Why it's good:** Memory for the eye. Drift looks slow in real time but is obvious when you compare snapshots taken hours apart.

**Implementation sketch:**
- Add a "📌 pin trace" button on the live trace view. Pinned traces persist in `localStorage` (or a server-side `pins` table for cross-device).
- Pinned traces render as faint overlays on the live trace plot.
- Stretch: a dedicated compare view that takes two time params and renders both traces side-by-side and overlaid.

**Scope:** Small for the pin-and-overlay; medium for the dedicated compare view.

---

## Alerts — webhook on signal loss

**The idea:** When peak SNR drops below a threshold for >N seconds (signal lost / cavity unlocked), fire a webhook (Slack, Discord, email-via-SMTP). The dashboard goes red.

**Why it's good:** Protects long overnight runs. You learn at 9am that you lost signal at 2am instead of finding out by looking.

**Implementation sketch:**
- Add `alert_rules(id, condition, channel, threshold)` table.
- The polling watcher already sees every new row — extend it to evaluate rules and POST to webhook URLs on transition.
- Cooldown logic to avoid spam (one alert per condition per 10 min).

**Scope:** Medium. Watcher logic + a small admin UI to configure rules.

---

## Ambient / TV mode — for the lab wall

**The idea:** `?ambient=1` strips the chrome. Fullscreen plots only, no controls, no header. Good for putting on a TV in the lab.

**Why it's good:** Trivially small and turns any laptop into a permanent lab display.

**Implementation sketch:** A query-param check + a CSS class that hides chrome. ~20 lines.

**Scope:** Trivial.

---

## Stats overlay — the "how's the rig" panel

**The idea:** A small panel always visible: drift rate per hour (kHz/hr), time since last retune, total uptime, traces collected today, current SNR.

**Why it's good:** The numbers people actually quote in lab meetings, computed automatically.

**Implementation sketch:**
- New REST endpoint `GET /api/stats?window=1h` that returns precomputed numbers.
- Server-side: SQL aggregations over the recent window.
- Component refreshes every ~30s.

**Scope:** Small. One endpoint + one panel component.

---

## CSV / PNG export — paper-ready

**The idea:** "Export current view" button. PNG via Plotly's built-in `Plotly.toImage()`. CSV via a server endpoint that streams the current window as `time,center,span,powers...`.

**Why it's good:** Skipping the "screenshot the dashboard for the paper" workflow. Real export gets you raw data when reviewers ask.

**Implementation sketch:**
- PNG: `Plotly.downloadImage()` — one line.
- CSV: `GET /api/export.csv?from=&to=` — streaming response, server-side rendering of FLOAT[] arrays into wide rows.

**Scope:** Small.

---

## Shareable URL — encode the view in the URL

**The idea:** When you scrub to a specific window, the URL becomes `?from=...&to=...`. Send the link, the recipient lands on exactly your view.

**Why it's good:** Cloudflare Tunnel + shareable URLs is the killer combo for "hey come look at this." No screenshots, no "scroll back to 2am."

**Implementation sketch:**
- `replaceState` on every scrub. Read query params on load and apply.
- ~30 lines of router-lite code in `index.html`.

**Scope:** Trivial.

---

## Health LED — is the rig alive

**The idea:** A small status dot in the header. Green = data flowing, amber = stale (no new rows in >2× cadence), red = WebSocket disconnected.

**Why it's good:** Free UX. You learn "I lost my rig" at a glance instead of "huh, the spectrogram looks frozen."

**Implementation sketch:**
- Track `last_row_ts` and `ws_connected` in client state.
- Compute color from those two values + a configured staleness threshold.

**Scope:** Trivial.

---

## How to use this list

When v1 ships and is stable, pick **one** item from this list per follow-on iteration. Don't batch — each of these has a satisfying "ship and look at it" moment, and bundling them dilutes that. The trivial ones (Ambient, Shareable URL, Health LED, Export) are great "one Friday afternoon" pickups.

Sonification is the one I'd lobby hardest for — it's the most distinctive and the smallest scope of the genuinely creative ones.
