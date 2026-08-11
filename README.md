# NCR Air Watch (aqi-ncr)

**A public, permanent, self-updating record of the air Delhi NCR breathes.**

Every morning at 07:00 IST, a machine reads the government's own CPCB air-quality
sensors, benchmarks them against WHO 2021 health guidelines, and commits the verdict
to this repository. No servers. No cost. No human in the loop.

**Live site:** https://aqi-ncr.onrender.com — landing page
**Daily ledger:** https://aqi-ncr.onrender.com/ledger — dashboard with today's readings, history charts, and the complaint ledger

## Why

Officials can argue with an activist. They cannot argue with their own sensors,
logged every morning for months. Delhi's air makes news in November; this ledger
is about the other ten months — the "clean" monsoon mornings that still run at
several times the WHO limit and never make a headline.

## What it does, every morning

1. **Read** — pulls every CPCB station reading for Delhi, Noida, Ghaziabad,
   Gurugram, and Faridabad from the [Open Government Data Platform](https://data.gov.in)
   (paginated past the API's response caps, deduplicated across city/state queries,
   sensor artefacts ≤0 or >1500 µg/m³ discarded).
2. **Benchmark** — averages stations per city and compares PM2.5 and PM10 against
   the WHO 2021 24-hour guidelines (15 / 45 µg/m³).
3. **Record** — commits a dated markdown report, updates `latest.json` and the
   growing `history.json`, and regenerates the dashboard data.
4. **Draft complaints** — on breach days, generates a formal complaint document
   citing the readings, addressed to the responsible authorities (CAQM, CPCB, DPCC,
   UPPCB, HSPCB), with suggested delivery channels and the CPGRAMS 21-day response
   window. The letter body is drafted by an LLM (Groq, `llama-3.3-70b-versatile`)
   from the day's verified numbers only; recipients and readings are injected
   deterministically so nothing can be invented. **Drafts are never sent
   automatically** — filing is a human decision.

## Repository layout

```
fetch_aqi.py              the entire pipeline (stdlib only, no dependencies)
.github/workflows/daily.yml   the 07:00 IST cron that runs it
index.html                landing page (exposure calculator, impact metrics)
ledger.html               dashboard (tiles, history charts, complaint ledger)
favicon.svg               the halo mark
latest.json               today's readings, per city
history.json              every recorded morning, growing daily
complaints.json           the complaint ledger index
complaints/<date>.md      one complaint draft per breach day
reports/<date>.md         one markdown report per morning
render.yaml               Render static-site config with clean-URL routes
```

## Fork it for your city

1. Fork this repo.
2. Edit `FOCUS_CITIES` and `FOCUS_STATES` in `fetch_aqi.py` (any cities covered by
   CPCB's network — see the resource on data.gov.in). Update the authority mapping
   in `AUTHORITIES`/`CHANNELS` for your region's pollution control boards.
3. Get a free API key: register at https://data.gov.in, then copy the key from
   **My Account**. Add it as a repository secret named `DATA_GOV_KEY`
   (Settings → Secrets and variables → Actions). Without it, the shared sample key
   works but truncates every response to 10 records and rate-limits aggressively.
4. Optional: add a `GROQ_API_KEY` secret for LLM-drafted complaint letters
   (free tier at https://console.groq.com). Without it, drafts fall back to a
   plain template.
5. Enable the GitHub Action (it runs daily at 07:00 IST; trigger it manually once
   via the Actions tab to seed day one).
6. Host the dashboard anywhere static: Render (this repo's `render.yaml` works as
   a Blueprint), GitHub Pages, Netlify — it is plain HTML reading the JSON files
   beside it.

For local runs, put the keys in a `.env` file (gitignored):

```
DATA_GOV_KEY=your_key_here
GROQ_API_KEY=optional_key_here
```

then `python3 fetch_aqi.py` and open the site with any static server
(`python3 -m http.server`).

## Data honesty

- Every number on the site traces to a CPCB station reading published by the
  government the same morning; the fetch code, the raw JSON, and every historical
  report are in this repository.
- The health guidance bands are general public-health advice, not medical advice.
- The cigarette equivalence on the landing page uses the Berkeley Earth rule of
  thumb (~22 µg/m³ PM2.5 ≈ one cigarette) and is labeled as the approximation it is.
- Complaint drafts carry a visible DRAFT banner; the 21-day response clock starts
  only when a human actually files one.

## Credits

Adapted from [nashik-air-watch](https://github.com/shamathakur77/nashik-air-watch),
which watches the air over Nashik and Pune. Fork the idea further — every city
deserves a watchman.

Data: Central Pollution Control Board via data.gov.in ·
Benchmark: [WHO 2021 global air quality guidelines](https://www.who.int/publications/i/item/9789240034228)
