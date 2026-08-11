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

# --- complaint ledger: one documented complaint per breach day, 21-day deadline ---
AUTHORITIES = {
    "Delhi": "Delhi Pollution Control Committee (DPCC) / CPCB",
    "Noida": "Uttar Pradesh Pollution Control Board (UPPCB) / CPCB",
    "Ghaziabad": "Uttar Pradesh Pollution Control Board (UPPCB) / CPCB",
    "Gurugram": "Haryana State Pollution Control Board (HSPCB) / CPCB",
    "Faridabad": "Haryana State Pollution Control Board (HSPCB) / CPCB",
}
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
    doc = [f"# Air quality complaint — {today}", ""]
    doc.append("To: " + "; ".join(sorted({AUTHORITIES[b['city']] for b in breaches})))
    doc.append("")
    doc.append("Subject: Documented breach of WHO 24-hour air quality guidelines "
               f"in Delhi NCR on {today}, per CPCB's own monitoring stations")
    doc.append("")
    doc.append("The following city-wide averages, computed from CPCB real-time "
               "station data published on data.gov.in, exceeded the WHO 2021 "
               "24-hour guidelines (PM2.5: 15 ug/m3, PM10: 45 ug/m3):")
    doc.append("")
    doc.append("| City | Pollutant | Reading (ug/m3) | x WHO limit |")
    doc.append("|------|-----------|-----------------|-------------|")
    for b in breaches:
        doc.append(f"| {b['city']} | {b['pollutant']} | {b['value']} | {b['multiple']}x |")
    doc.append("")
    doc.append("We request acknowledgement of this exceedance and a statement of "
               "remedial action underway. Per CPGRAMS grievance-redressal norms, "
               f"a response is due within 21 days, i.e. by {deadline}.")
    doc.append("")
    doc.append("This complaint is logged in a public, timestamped ledger: "
               "https://github.com/mayankJFT/aqi-ncr")
    os.makedirs("complaints", exist_ok=True)
    with open(f"complaints/{today}.md", "w") as f:
        f.write("\n".join(doc))
    complaints.append({"date": today, "deadline": deadline, "breaches": breaches,
                       "doc": f"complaints/{today}.md", "status": "awaiting response"})
    with open("complaints.json", "w") as f:
        json.dump(complaints, f, indent=2)
    print(f"\nComplaint documented: complaints/{today}.md (response due {deadline})")

print("\n".join(lines))
