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
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from classify import RULES_VERSION, classify, dedupe_key, slug  # noqa: E402
from sources import LAST_ERRORS, READERS, SkipSource, session  # noqa: E402

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


# Frasi che le pagine degli annunci mostrano quando la posizione è chiusa.
RE_CLOSED = re.compile(r"no longer (accepting|available|open)|position has been filled|job (is )?(closed|expired)|listing has ended|this job has expired|"
	r"non è più disponibile|candidature non sono più accettate|offerta scaduta|annuncio scaduto|ogłoszenie zarchiwizowane", re.I)


def read_source(src):
	"""Legge una fonte e restituisce (src, annunci grezzi, errore, errori parziali, secondi)."""
	start = time.monotonic()
	try:
		raw = READERS[src["type"]](src)
		return src, raw, None, LAST_ERRORS.pop(src["type"], []), time.monotonic() - start
	except Exception as exc:  # noqa: BLE001 - una fonte rotta non deve fermare le altre
		if not isinstance(exc, SkipSource):
			traceback.print_exc()
		return src, [], exc, [], time.monotonic() - start


def check_link(job):
	"""Apre la pagina dell'annuncio: 'chiuso' se 404/410 o se dice che non è più disponibile,
	'ok' se risponde normalmente, None se non si può dire (blocchi, timeout, pagine dinamiche)."""
	try:
		resp = session().get(job["url"], timeout=15, allow_redirects=True)
	except Exception:  # noqa: BLE001
		return None
	if resp.status_code in (404, 410):
		return "chiuso"
	if resp.status_code != 200:
		return None
	return "chiuso" if RE_CLOSED.search(resp.text[:300000]) else "ok"


def verify_links(jobs, now):
	"""Ricontrolla i link degli annunci aperti non verificati da più di N giorni (al massimo M per giro)."""
	every = CONFIG.get("linkCheckEveryDays", 7)
	limit = CONFIG.get("linkCheckMaxPerRun", 80)
	due = [j for j in jobs if j.get("status") != "chiuso" and (not j.get("linkCheckedAt") or (dt.date.fromisoformat(now) - dt.date.fromisoformat(j["linkCheckedAt"])).days >= every)]
	due.sort(key=lambda j: j.get("linkCheckedAt") or "")
	due = due[:limit]
	closed = 0
	with ThreadPoolExecutor(max_workers=8) as pool:
		for job, verdict in zip(due, pool.map(check_link, due)):
			if verdict is None:
				continue
			job["linkCheckedAt"] = now
			if verdict == "chiuso":
				job["status"] = "chiuso"
				job["closedAt"] = now
				closed += 1
	return len(due), closed


def main():
	now = today()
	# Gli annunci automatici classificati con regole vecchie vengono scartati e rivalutati da capo.
	previous = {j["id"]: j for j in load("jobs.json", []) if j.get("origin") != "auto" or j.get("rules") == RULES_VERSION}
	by_key = {dedupe_key(j): j["id"] for j in previous.values()}

	found = {}          # id -> job
	ok_sources = set()  # id delle fonti lette con successo
	statuses = []

	# Le fonti sono indipendenti: si leggono in parallelo. L'ordine dei risultati resta quello di config.json,
	# così a parità di annuncio vince sempre la stessa fonte.
	with ThreadPoolExecutor(max_workers=6) as pool:
		results = list(pool.map(read_source, CONFIG["sources"]))

	new_by_source = {}
	for src, raw_jobs, error, partial, seconds in results:
		entry = {"id": src["id"], "name": src["name"], "group": src["group"], "url": src["url"], "kind": "auto", "note": src.get("note", ""), "lastRead": now, "seconds": round(seconds, 1)}
		if isinstance(error, SkipSource):
			entry.update(lastStatus="non configurata", lastCount=0, error=str(error))
		elif error:
			entry.update(lastStatus="errore", lastCount=0, error=f"{type(error).__name__}: {str(error)[:200]}")
		else:
			kept = 0
			for raw in raw_jobs:
				job = classify(raw, raw.get("default_tech"), CONFIG.get("excludeGaming", False))
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
				if job_id not in previous:
					new_by_source[src["id"]] = new_by_source.get(src["id"], 0) + 1
				kept += 1
			entry.update(lastStatus="parziale" if partial else "ok", lastCount=kept, found=len(raw_jobs))
			if partial:
				entry["error"] = "; ".join(partial)[:300]
			ok_sources.add(src["id"])
		statuses.append(entry)
		print(f"[{entry['lastStatus']}] {src['name']}: {entry.get('lastCount', 0)} pertinenti su {entry.get('found', 0)} letti ({entry['seconds']} s)")

	for entry in statuses:
		entry["newCount"] = new_by_source.get(entry["id"], 0)

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
		job["linkCheckedAt"] = now  # la fonte lo elenca ancora: il link è vivo, inutile riaprirlo
		job["missingRuns"] = 0
		job["addedAt"] = old.get("addedAt", now) if old else now
		if not old:
			new_count += 1
		job.pop("priority", None)
		result.append(job)

	for job_id, old in previous.items():
		if job_id in found:
			continue
		closed_at = old.get("closedAt")
		if closed_at and (dt.date.fromisoformat(now) - dt.date.fromisoformat(closed_at)).days > 30:
			continue  # chiuso da più di un mese: lo eliminiamo
		if old.get("origin") != "auto":
			result.append(old)  # annunci inseriti a mano: i dati non si toccano, solo il controllo del link
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

	checked, closed_by_link = verify_links(result, now)
	closed_count += closed_by_link
	print(f"Link ricontrollati: {checked}, chiusi: {closed_by_link}")

	result.sort(key=lambda j: (j.get("status") == "chiuso", j.get("addedAt") or "", j.get("posted") or ""), reverse=False)
	errors = [s["name"] for s in statuses if s.get("lastStatus") == "errore"]
	summary = f"{new_count} nuovi, {closed_count} chiusi" + (f", fonti in errore: {', '.join(errors)}" if errors else "")

	save("jobs.json", result)
	save("sources.json", statuses)
	save("meta.json", {"lastUpdate": now, "lastSummary": summary})
	print(summary)


if __name__ == "__main__":
	main()
