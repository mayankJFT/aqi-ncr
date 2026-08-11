import json, os, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

RESOURCE = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"

# local runs: pick up DATA_GOV_KEY from a gitignored .env
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.strip().partition("=")
                os.environ.setdefault(k, v)

KEY = os.environ.get("DATA_GOV_KEY", "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b")
FOCUS_CITIES = ["Delhi", "Noida", "Ghaziabad", "Gurugram", "Faridabad"]
FOCUS_STATES = ["Delhi", "Uttar Pradesh", "Haryana"]
WHO_LIMITS = {"PM2.5": 15, "PM10": 45}

BASE = f"https://api.data.gov.in/resource/{RESOURCE}"

HDRS = {"User-Agent": "Mozilla/5.0"}

def try_url(url):
    try:
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"  -> HTTP {e.code}: {e.read()[:120]}")
    except Exception as e:
        print(f"  -> {e}")
    return None

def fetch(field, value, max_records=400):
    # The shared sample key truncates every response to 10 records,
    # so page with offset until `total` (or max_records) is reached.
    v = urllib.parse.quote(value)
    base = f"{BASE}?api-key={KEY}&format=json&limit=100&filters%5B{field}%5D={v}"
    records, offset, total = [], 0, None
    while True:
        data = None
        for _ in range(4):
            data = try_url(f"{base}&offset={offset}")
            if data is not None and "records" in data:
                break
            time.sleep(20)
        if not data or not data.get("records"):
            break
        recs = data["records"]
        records += recs
        total = int(data.get("total") or 0)
        offset += len(recs)
        if offset >= min(total, max_records):
            break
        time.sleep(3)
    print(f"{value}: {len(records)}/{total} records")
    return records

records = []
for c in FOCUS_CITIES:
    records += fetch("city", c)

for s in FOCUS_STATES:
    records += fetch("state", s, max_records=300)

if not records:
    print("No data at all today; exiting gracefully.")
    raise SystemExit(0)

# city and state fetches overlap; keep one record per station+pollutant
seen = set()
deduped = []
for rec in records:
    k = (rec.get("station"), rec.get("pollutant_id"))
    if k in seen:
        continue
    seen.add(k)
    deduped.append(rec)
records = deduped

cities = {}
for rec in records:
    city = rec.get("city", "")
    pol = rec.get("pollutant_id", "")
    try:
        val = float(rec.get("pollutant_avg") or rec.get("avg_value"))
    except (TypeError, ValueError):
        continue
    if val <= 0 or val > 1500:
        continue
    cities.setdefault(city, {}).setdefault(pol, []).append(val)

report = {c: {p: round(sum(v)/len(v), 1) for p, v in pols.items()} for c, pols in cities.items()}

ist = timezone(timedelta(hours=5, minutes=30))
today = datetime.now(ist).strftime("%Y-%m-%d")
ranking = sorted(((c, d["PM2.5"]) for c, d in report.items() if "PM2.5" in d), key=lambda x: -x[1])

lines = [f"# Air Report - {today}", ""]
for name in FOCUS_CITIES:
    d = report.get(name)
    if not d:
        lines.append(f"## {name}: no data reported today\n")
        continue
    lines.append(f"## {name}")
    for p, v in sorted(d.items()):
        limit = WHO_LIMITS.get(p)
        if limit:
            flag = "BREACH" if v > limit else "ok"
            lines.append(f"- {p}: {v} ug/m3 = {round(v/limit,1)}x WHO limit [{flag}]")
        else:
            lines.append(f"- {p}: {v}")
    lines.append("")

if len(ranking) > 2:
    lines.append("## Worst PM2.5 in monitored states today")
    for i, (c, v) in enumerate(ranking[:10], 1):
        lines.append(f"{i}. {c}: {v} ug/m3")

os.makedirs("reports", exist_ok=True)
with open(f"reports/{today}.md", "w") as f:
    f.write("\n".join(lines))
with open("latest.json", "w") as f:
    json.dump({"date": today, "cities": report, "ranking": ranking[:10]}, f, indent=2)

history = {}
if os.path.exists("history.json"):
    try:
        with open("history.json") as f:
            history = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
history[today] = {c: report[c] for c in FOCUS_CITIES if c in report}
with open("history.json", "w") as f:
    json.dump(dict(sorted(history.items())), f, indent=2)

# --- complaint ledger: one documented DRAFT per breach day, 21-day deadline ---
AUTHORITIES = {
    "Delhi": "Delhi Pollution Control Committee (DPCC) / CPCB",
    "Noida": "Uttar Pradesh Pollution Control Board (UPPCB) / CPCB",
    "Ghaziabad": "Uttar Pradesh Pollution Control Board (UPPCB) / CPCB",
    "Gurugram": "Haryana State Pollution Control Board (HSPCB) / CPCB",
    "Faridabad": "Haryana State Pollution Control Board (HSPCB) / CPCB",
}

# Curated delivery channels — kept out of the LLM so nothing is invented.
# Verify each before first use; portal filings (CPGRAMS) start the tracked
# response clock that the 21-day deadline refers to.
CHANNELS = [
    ("CAQM — Commission for Air Quality Management in NCR",
     "statutory body created specifically for NCR air quality",
     "https://caqm.nic.in"),
    ("CPCB — Central Pollution Control Board",
     "national regulator; operates the monitoring stations cited in this complaint",
     "https://cpcb.nic.in/contact-us/"),
    ("DPCC — Delhi Pollution Control Committee",
     "responsible for Delhi readings",
     "https://www.dpcc.delhigovt.nic.in/contact_us"),
    ("UPPCB — Uttar Pradesh Pollution Control Board",
     "responsible for Noida and Ghaziabad readings",
     "https://uppcb.up.gov.in/en/page/public-grievances"),
    ("HSPCB — Haryana State Pollution Control Board",
     "responsible for Gurugram and Faridabad readings",
     "https://hspcb.org.in"),
    ("CPGRAMS — Centralised Public Grievance Portal",
     "official channel whose filing starts the tracked 21-day response window",
     "https://pgportal.gov.in"),
]

def draft_with_groq(table_md, today, deadline):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    prompt = (
        "Draft the body of a formal air-quality complaint letter to Indian "
        "pollution control authorities (CAQM, CPCB, DPCC, UPPCB, HSPCB) for "
        f"{today}. Use ONLY the readings below; do not invent numbers, names, "
        "email addresses, or laws beyond the Air (Prevention and Control of "
        "Pollution) Act, 1981 and the WHO 2021 guidelines. Cite that the data "
        "comes from CPCB's own real-time stations via data.gov.in. Request "
        "acknowledgement and a statement of remedial action, noting a response "
        f"is expected within 21 days (by {deadline}). Firm, factual, courteous; "
        "no placeholders like [Name]; sign off as 'A resident of Delhi NCR "
        "(public ledger: https://github.com/mayankJFT/aqi-ncr)'. "
        "Return only the letter body in markdown, no preamble.\n\n" + table_md
    )
    body = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3,
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (aqi-ncr complaint drafter)"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.load(r)
        return out["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  -> Groq draft failed ({e}); using template body")
        return None
breaches = []
for c in FOCUS_CITIES:
    d = report.get(c, {})
    for p in ("PM2.5", "PM10"):
        if p in d and d[p] > WHO_LIMITS[p]:
            breaches.append({"city": c, "pollutant": p, "value": d[p],
                             "multiple": round(d[p] / WHO_LIMITS[p], 1)})

complaints = []
if os.path.exists("complaints.json"):
    try:
        with open("complaints.json") as f:
            complaints = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass

if breaches and not any(x["date"] == today for x in complaints):
    deadline = (datetime.now(ist) + timedelta(days=21)).strftime("%Y-%m-%d")
    table = ["| City | Pollutant | Reading (ug/m3) | x WHO limit |",
             "|------|-----------|-----------------|-------------|"]
    for b in breaches:
        table.append(f"| {b['city']} | {b['pollutant']} | {b['value']} | {b['multiple']}x |")
    table_md = "\n".join(table)

    letter = draft_with_groq(table_md, today, deadline)
    if not letter:
        letter = (
            "The following city-wide averages, computed from CPCB real-time "
            "station data published on data.gov.in, exceeded the WHO 2021 "
            "24-hour guidelines (PM2.5: 15 ug/m3, PM10: 45 ug/m3).\n\n"
            "We request acknowledgement of this exceedance and a statement of "
            "remedial action underway. A response is expected within 21 days, "
            f"i.e. by {deadline}.")

    doc = [f"# Air quality complaint — DRAFT — {today}", ""]
    doc.append("> **DRAFT ONLY — not sent.** Review the letter, verify the "
               "recipient channels below, and file it yourself. The 21-day "
               "response clock starts when the complaint is actually filed.")
    doc.append("")
    doc.append("To: " + "; ".join(sorted({AUTHORITIES[b['city']] for b in breaches})))
    doc.append("")
    doc.append("Subject: Documented breach of WHO 24-hour air quality guidelines "
               f"in Delhi NCR on {today}, per CPCB's own monitoring stations")
    doc.append("")
    doc.append(letter)
    doc.append("")
    doc.append("## Readings cited (generated from CPCB data, not the LLM)")
    doc.append("")
    doc.append(table_md)
    doc.append("")
    doc.append("## Suggested delivery channels — verify before sending")
    doc.append("")
    for name, why, url in CHANNELS:
        doc.append(f"- **{name}** — {why} — {url}")
    doc.append("")
    doc.append("Public ledger of every draft: https://github.com/mayankJFT/aqi-ncr")
    os.makedirs("complaints", exist_ok=True)
    with open(f"complaints/{today}.md", "w") as f:
        f.write("\n".join(doc))
    complaints.append({"date": today, "deadline": deadline, "breaches": breaches,
                       "doc": f"complaints/{today}.md", "status": "draft"})
    with open("complaints.json", "w") as f:
        json.dump(complaints, f, indent=2)
    print(f"\nComplaint draft: complaints/{today}.md (respond-by if filed today: {deadline})")

print("\n".join(lines))
