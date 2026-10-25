"""Aggiorna docs/data/*.json leggendo tutte le fonti di config.json.

Uso: python scraper/run.py
Scrive:
  docs/data/jobs.json     annunci (nuovi, aggiornati, chiusi)
  docs/data/sources.json  stato di ogni fonte all'ultimo aggiornamento
  docs/data/meta.json     data e riepilogo dell'ultimo aggiornamento
"""

import datetime as dt
import json
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from classify import RULES_VERSION, classify, dedupe_key, slug  # noqa: E402
from sources import LAST_ERRORS, READERS, SkipSource  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
CONFIG = json.loads((ROOT / "scraper" / "config.json").read_text(encoding="utf-8"))


def today():
	return dt.datetime.now(dt.timezone(dt.timedelta(hours=1))).date().isoformat()


def load(name, default):
	path = DATA / name
	if path.exists():
		return json.loads(path.read_text(encoding="utf-8"))
	return default


def save(name, value):
	DATA.mkdir(parents=True, exist_ok=True)
	(DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def too_old(posted, max_days):
	if not posted:
		return False
	try:
		return (dt.date.fromisoformat(today()) - dt.date.fromisoformat(posted)).days > max_days
	except ValueError:
		return False


def main():
	now = today()
	# Gli annunci automatici classificati con regole vecchie vengono scartati e rivalutati da capo.
	previous = {j["id"]: j for j in load("jobs.json", []) if j.get("origin") != "auto" or j.get("rules") == RULES_VERSION}
	by_key = {dedupe_key(j): j["id"] for j in previous.values()}

	found = {}          # id -> job
	ok_sources = set()  # id delle fonti lette con successo
	statuses = []

	for src in CONFIG["sources"]:
		reader = READERS[src["type"]]
		entry = {"id": src["id"], "name": src["name"], "group": src["group"], "url": src["url"], "kind": "auto", "note": src.get("note", ""), "lastRead": now}
		try:
			raw_jobs = reader(src)
			kept = 0
			for raw in raw_jobs:
				job = classify(raw, raw.get("default_tech"))
				if not job or too_old(job.get("posted"), CONFIG.get("maxAgeDays", 150)):
					continue
				job["priority"] = src.get("priority", 1)
				job["sourceId"] = src["id"]
				key = dedupe_key(job)
				job_id = by_key.get(key) or slug(f"{job['company']}-{job['title']}")
				by_key[key] = job_id
				other = found.get(job_id)
				if other:
					# Stesso annuncio da più fonti: tieni l'URL della fonte più diretta, unisci le fonti.
					sources = sorted(set(filter(None, (other["source"] + " · " + job["source"]).split(" · "))))
					best = job if job["priority"] > other["priority"] else other
					best["source"] = " · ".join(sources)
					found[job_id] = best
				else:
					found[job_id] = job
				kept += 1
			partial = LAST_ERRORS.pop(src["type"], [])
			entry.update(lastStatus="parziale" if partial else "ok", lastCount=kept, found=len(raw_jobs))
			if partial:
				entry["error"] = "; ".join(partial)[:300]
			ok_sources.add(src["id"])
		except SkipSource as exc:
			entry.update(lastStatus="non configurata", lastCount=0, error=str(exc))
		except Exception as exc:  # noqa: BLE001 - una fonte rotta non deve fermare le altre
			entry.update(lastStatus="errore", lastCount=0, error=f"{type(exc).__name__}: {str(exc)[:200]}")
			traceback.print_exc()
		statuses.append(entry)
		print(f"[{entry['lastStatus']}] {src['name']}: {entry.get('lastCount', 0)} annunci")

	for m in CONFIG.get("manual", []):
		statuses.append({"id": slug(m["name"]), "name": m["name"], "group": m["group"], "url": m["url"], "kind": "manuale", "note": m.get("note", "")})

	# ---- unione con gli annunci già noti
	result, new_count, closed_count = [], 0, 0
	for job_id, job in found.items():
		old = previous.get(job_id)
		if old and old.get("origin") != "auto":
			# Annuncio curato a mano ritrovato da una fonte: conferma che è aperto, senza riscriverne i dati.
			old.update(checkedAt=now, status="aperto")
			result.append(old)
			continue
		job["id"] = job_id
		job["checkedAt"] = now
		job["missingRuns"] = 0
		job["addedAt"] = old.get("addedAt", now) if old else now
		if not old:
			new_count += 1
		job.pop("priority", None)
		result.append(job)

	for job_id, old in previous.items():
		if job_id in found:
			continue
		if old.get("origin") != "auto":
			result.append(old)  # annunci inseriti a mano: non si toccano
			continue
		if old.get("sourceId") in ok_sources:
			old["missingRuns"] = old.get("missingRuns", 0) + 1
			if old["missingRuns"] >= CONFIG.get("closeAfterMissingRuns", 2) and old.get("status") != "chiuso":
				old["status"] = "chiuso"
				old["closedAt"] = now
				closed_count += 1
		closed_at = old.get("closedAt")
		if closed_at and (dt.date.fromisoformat(now) - dt.date.fromisoformat(closed_at)).days > 30:
			continue  # chiuso da più di un mese: lo eliminiamo
		result.append(old)

	result.sort(key=lambda j: (j.get("status") == "chiuso", j.get("addedAt") or "", j.get("posted") or ""), reverse=False)
	errors = [s["name"] for s in statuses if s.get("lastStatus") == "errore"]
	summary = f"{new_count} nuovi, {closed_count} chiusi" + (f", fonti in errore: {', '.join(errors)}" if errors else "")

	save("jobs.json", result)
	save("sources.json", statuses)
	save("meta.json", {"lastUpdate": now, "lastSummary": summary})
	print(summary)


if __name__ == "__main__":
	main()
