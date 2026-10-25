"""Lettori delle singole fonti.

Ogni lettore restituisce una lista di annunci "grezzi" (dict) con le chiavi
usate da classify.classify(). Se una fonte non risponde solleva un'eccezione:
run.py la registra come "errore" e continua con le altre.
"""

import datetime as dt
import os
import re
import time

import requests

from classify import salary_eur, salary_text, strip_html

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 cpp-job-radar"
TIMEOUT = 25


def get(url, **kw):
	headers = kw.pop("headers", {})
	headers.setdefault("User-Agent", UA)
	resp = requests.get(url, headers=headers, timeout=TIMEOUT, **kw)
	resp.raise_for_status()
	return resp


def iso_from_unix(value, ms=False):
	if not value:
		return None
	try:
		value = float(value) / (1000 if ms else 1)
		return dt.datetime.fromtimestamp(value, dt.timezone.utc).date().isoformat()
	except (TypeError, ValueError, OSError):
		return None


def iso_from_text(value):
	if not value:
		return None
	m = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
	return m.group(1) if m else None


# ---------------------------------------------------------------- Hacker News


RE_HN_ROLE = re.compile(r"(?:(?:senior|staff|sr\.?|mid|lead)\s+)?[\w+#/.\- ]{0,40}?(?:engineer|developer|programmer)s?", re.I)


def hn_who_is_hiring(cfg):
	story = get("https://hn.algolia.com/api/v1/search_by_date", params={"query": "\"who is hiring\"", "tags": "story,author_whoishiring", "hitsPerPage": 5}).json()
	hits = [h for h in story.get("hits", []) if "who is hiring" in (h.get("title") or "").lower()]
	if not hits:
		return []
	story_id = hits[0]["objectID"]
	out, seen = [], set()
	for query in cfg.get("queries", ["C++", "Unreal"]):
		data = get("https://hn.algolia.com/api/v1/search", params={"tags": f"comment,story_{story_id}", "query": query, "hitsPerPage": 300}).json()
		for hit in data.get("hits", []):
			if hit["objectID"] in seen or hit.get("parent_id") != int(story_id):
				continue
			seen.add(hit["objectID"])
			text = strip_html(hit.get("comment_text"))
			first = text.split("  ")[0][:300]
			parts = [p.strip() for p in first.split("|")]
			if len(parts) < 2:
				continue
			company = parts[0]
			role = next((p for p in parts[1:] if RE_HN_ROLE.search(p)), None)
			if not role:
				m = RE_HN_ROLE.search(text)
				role = m.group(0).strip() if m else parts[1]
			location = " | ".join(p for p in parts[1:] if re.search(r"remote|onsite|on-site|hybrid|\b[A-Z][a-z]+,|europe|eu\b|anywhere", p, re.I))
			out.append({
				"company": company,
				"title": role,
				"url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
				"location": location,
				"remote": None,
				"description": text,
				"posted": iso_from_unix(hit.get("created_at_i")),
				"source": "Hacker News – Who is hiring",
			})
	return out


# ---------------------------------------------------------------- Himalayas (API ufficiale)


def himalayas(cfg):
	out = []
	for query in cfg.get("queries", ["C++"]):
		for page in range(1, cfg.get("pages", 2) + 1):
			data = get("https://himalayas.app/jobs/api/search", params={"q": query, "country": "Italy", "sort": "recent", "page": page}).json()
			jobs = data.get("jobs", [])
			for j in jobs:
				countries = j.get("locationRestrictions") or []
				out.append({
					"company": j.get("companyName"),
					"title": j.get("title"),
					"url": j.get("applicationLink") or j.get("guid"),
					"location": "Remoto: " + (", ".join(countries[:5]) + ("…" if len(countries) > 5 else "") if countries else "ovunque"),
					"remote": True,
					"countries": countries or ["worldwide"],
					"description": j.get("description") or j.get("excerpt"),
					"posted": iso_from_unix(j.get("pubDate")),
					"salary": salary_text(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod")),
					"salaryEur": salary_eur(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod")),
					"source": "Himalayas (API)",
				})
			if len(jobs) < 20:
				break
			time.sleep(1)
	return out


# ---------------------------------------------------------------- Remotive / Arbeitnow (API pubbliche)


def remotive(cfg):
	out = []
	for query in cfg.get("queries", ["c++"]):
		data = get("https://remotive.com/api/remote-jobs", params={"search": query, "limit": 100}).json()
		for j in data.get("jobs", []):
			out.append({
				"company": j.get("company_name"),
				"title": j.get("title"),
				"url": j.get("url"),
				"location": "Remoto: " + (j.get("candidate_required_location") or "n.d."),
				"remote": True,
				"description": j.get("description"),
				"posted": iso_from_text(j.get("publication_date")),
				"salary": j.get("salary") or "",
				"source": "Remotive (API)",
			})
	return out


def arbeitnow(cfg):
	out = []
	for page in range(1, cfg.get("pages", 3) + 1):
		data = get("https://www.arbeitnow.com/api/job-board-api", params={"page": page}).json()
		for j in data.get("data", []):
			out.append({
				"company": j.get("company_name"),
				"title": j.get("title"),
				"url": j.get("url"),
				"location": ("Remoto" if j.get("remote") else "") + (" · " if j.get("remote") and j.get("location") else "") + (j.get("location") or ""),
				"remote": bool(j.get("remote")),
				"description": j.get("description"),
				"posted": iso_from_unix(j.get("created_at")),
				"source": "Arbeitnow (API)",
			})
		time.sleep(1)
	return out


# ---------------------------------------------------------------- ATS degli studi


def workable(cfg):
	def fetch(company):
		data = get(f"https://apply.workable.com/api/v1/widget/accounts/{company['slug']}").json()
		# Workable pubblica lo stesso annuncio una volta per paese: li raggruppo per titolo
		# e raccolgo i paesi ammessi, così la geografia si decide sull'elenco completo.
		groups = {}
		for j in data.get("jobs", []):
			g = groups.setdefault(j.get("title"), {"job": j, "countries": set(), "remote": False, "cities": set()})
			if j.get("country"):
				g["countries"].add(j["country"])
			if j.get("city"):
				g["cities"].add(j["city"])
			g["remote"] = g["remote"] or bool(j.get("telecommuting"))
		out = []
		for title, g in groups.items():
			j = g["job"]
			countries = sorted(g["countries"])
			out.append({
				"company": company.get("name") or data.get("name"),
				"title": title,
				"url": j.get("url") or j.get("application_url"),
				"location": ("Remoto · " if g["remote"] else "") + ", ".join(sorted(g["cities"]) + countries),
				"remote": g["remote"],
				"countries": countries if g["remote"] else [],
				"description": f"{j.get('department') or ''} {j.get('function') or ''}",
				"posted": iso_from_text(j.get("published_on")),
				"gaming": company.get("gaming", True),
				"default_tech": company.get("tech"),
				"source": f"{company.get('name')} (Workable)",
			})
		return out

	return each_company(cfg, fetch)


def greenhouse(cfg):
	def fetch(company):
		out = []
		host = "boards-api.eu.greenhouse.io" if company.get("eu") else "boards-api.greenhouse.io"
		data = get(f"https://{host}/v1/boards/{company['slug']}/jobs", params={"content": "true"}).json()
		for j in data.get("jobs", []):
			loc = (j.get("location") or {}).get("name", "")
			out.append({
				"company": company.get("name"),
				"title": j.get("title"),
				"url": j.get("absolute_url"),
				"location": loc,
				"remote": None,
				"description": j.get("content"),
				"posted": iso_from_text(j.get("updated_at")),
				"gaming": company.get("gaming", True),
				"default_tech": company.get("tech"),
				"source": f"{company.get('name')} (Greenhouse)",
			})
		return out

	return each_company(cfg, fetch)


def lever(cfg):
	def fetch(company):
		out = []
		host = "api.eu.lever.co" if company.get("eu") else "api.lever.co"
		data = get(f"https://{host}/v0/postings/{company['slug']}", params={"mode": "json"}).json()
		for j in data:
			cats = j.get("categories") or {}
			workplace = (j.get("workplaceType") or "").lower()
			out.append({
				"company": company.get("name"),
				"title": j.get("text"),
				"url": j.get("hostedUrl"),
				"location": (cats.get("location") or "") + (f" · {workplace}" if workplace else ""),
				"remote": workplace == "remote" or None,
				"description": j.get("descriptionPlain"),
				"posted": iso_from_unix(j.get("createdAt"), ms=True),
				"gaming": company.get("gaming", True),
				"default_tech": company.get("tech"),
				"source": f"{company.get('name')} (Lever)",
			})
		return out

	return each_company(cfg, fetch)


def ashby(cfg):
	def fetch(company):
		out = []
		data = get(f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}").json()
		for j in data.get("jobs", []):
			out.append({
				"company": company.get("name"),
				"title": j.get("title"),
				"url": j.get("jobUrl"),
				"location": j.get("location") or "",
				"remote": bool(j.get("isRemote")),
				"description": j.get("descriptionPlain"),
				"posted": iso_from_text(j.get("publishedAt")),
				"gaming": company.get("gaming", True),
				"default_tech": company.get("tech"),
				"source": f"{company.get('name')} (Ashby)",
			})
		return out

	return each_company(cfg, fetch)


# ---------------------------------------------------------------- Meeting C++ (pagina HTML)


def meetingcpp(cfg):
	html_text = get("https://meetingcpp.com/jobs/").text
	out, seen = [], set()
	for m in re.finditer(r'href="(/jobs/items/[^"]+\.html)"[^>]*>(.*?)</a>', html_text, re.S):
		path, label = m.group(1), strip_html(m.group(2))
		if path in seen or not label:
			continue
		seen.add(path)
		remote = bool(re.search(r"remote", label, re.I))
		loc = re.search(r"\(([^)]+)\)\s*$", label)
		out.append({
			"company": "",
			"title": label if re.search(r"engineer|developer|programmer", label, re.I) else f"C++ {label}",
			"url": "https://meetingcpp.com" + path,
			"location": loc.group(1) if loc else "",
			"remote": remote,
			"description": "C++ " + label,
			"posted": None,
			"gaming": False,
			"source": "Meeting C++ Jobs",
		})
	return out


# ---------------------------------------------------------------- API con chiave gratuita (facoltative)


def jooble(cfg):
	key = os.environ.get("JOOBLE_API_KEY")
	if not key:
		raise SkipSource("manca il secret JOOBLE_API_KEY")
	out = []
	for search in cfg.get("searches", []):
		resp = requests.post(f"https://jooble.org/api/{key}", json={"keywords": search["keywords"], "location": search.get("location", "")}, timeout=TIMEOUT)
		resp.raise_for_status()
		for j in resp.json().get("jobs", []):
			out.append({
				"company": j.get("company"),
				"title": j.get("title"),
				"url": j.get("link"),
				"location": j.get("location") or search.get("location", ""),
				"remote": None,
				"description": j.get("snippet"),
				"posted": iso_from_text(j.get("updated")),
				"salary": j.get("salary") or "",
				"source": f"Jooble (API) · {j.get('source') or ''}".strip(" ·"),
			})
		time.sleep(1)
	return out


def adzuna(cfg):
	app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
	if not app_id or not app_key:
		raise SkipSource("mancano i secret ADZUNA_APP_ID / ADZUNA_APP_KEY")
	out = []
	for search in cfg.get("searches", []):
		data = get(f"https://api.adzuna.com/v1/api/jobs/{cfg.get('country', 'it')}/search/1", params={"app_id": app_id, "app_key": app_key, "what": search["what"], "where": search.get("where", ""), "results_per_page": 50, "content-type": "application/json"}).json()
		for j in data.get("results", []):
			out.append({
				"company": (j.get("company") or {}).get("display_name"),
				"title": j.get("title"),
				"url": j.get("redirect_url"),
				"location": (j.get("location") or {}).get("display_name", ""),
				"remote": None,
				"description": j.get("description"),
				"posted": iso_from_text(j.get("created")),
				"salary": salary_text(j.get("salary_min"), j.get("salary_max"), "EUR", "year"),
				"salaryEur": salary_eur(j.get("salary_min"), j.get("salary_max"), "EUR", "year"),
				"source": "Adzuna (API)",
			})
		time.sleep(1)
	return out


def reddit_cpp(cfg):
	cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
	if not cid or not secret:
		raise SkipSource("mancano i secret REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET")
	ua = "cpp-job-radar/1.0 (personal job search)"
	token = requests.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret), data={"grant_type": "client_credentials"}, headers={"User-Agent": ua}, timeout=TIMEOUT)
	token.raise_for_status()
	headers = {"Authorization": f"bearer {token.json()['access_token']}", "User-Agent": ua}
	found = get("https://oauth.reddit.com/r/cpp/search", headers=headers, params={"q": 'title:"C++ Jobs"', "restrict_sr": 1, "sort": "new", "limit": 5}).json()
	posts = [p["data"] for p in found["data"]["children"] if re.search(r"C\+\+ Jobs\s*-\s*Q\d", p["data"].get("title", ""))]
	if not posts:
		return []
	post = posts[0]
	thread = get(f"https://oauth.reddit.com/comments/{post['id']}", headers=headers, params={"depth": 1, "limit": 500}).json()
	out = []
	for child in thread[1]["data"]["children"]:
		c = child.get("data", {})
		body = c.get("body") or ""

		def field(name):
			m = re.search(rf"\*\*{name}:?\*\*:?\s*(.+)", body, re.I)
			return m.group(1).strip() if m else ""

		company = field("Company")
		if not company:
			continue
		ctype = field("Type")
		remote_txt = field("Remote")
		out.append({
			"company": re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", company),
			"title": f"C++ {ctype}" if ctype and not re.search(r"engineer|developer|programmer", ctype, re.I) else (ctype or "C++ Developer"),
			"url": "https://www.reddit.com" + c.get("permalink", ""),
			"location": f"{field('Location')} · Remote: {remote_txt}".strip(" ·"),
			"remote": bool(re.search(r"^yes|fully|remote", remote_txt, re.I)),
			"description": body,
			"posted": iso_from_unix(c.get("created_utc")),
			"salary": field("Compensation"),
			"gaming": None,
			"source": "r/cpp – C++ Jobs",
		})
	return out


LAST_ERRORS = {}  # tipo fonte -> errori dei singoli studi nell'ultimo giro


def each_company(cfg, fetch):
	"""Esegue fetch(company) per ogni studio; uno slug sbagliato non blocca gli altri."""
	out, errors = [], []
	for company in cfg.get("companies", []):
		try:
			out.extend(fetch(company))
		except Exception as exc:  # noqa: BLE001
			errors.append(f"{company.get('name')}: {type(exc).__name__} {str(exc)[:80]}")
	LAST_ERRORS[cfg["type"]] = errors
	if errors and not out and len(errors) == len(cfg.get("companies", [])):
		raise RuntimeError("; ".join(errors))
	return out


class SkipSource(Exception):
	"""Fonte facoltativa non configurata: non è un errore."""


READERS = {
	"hn": hn_who_is_hiring,
	"himalayas": himalayas,
	"remotive": remotive,
	"arbeitnow": arbeitnow,
	"workable": workable,
	"greenhouse": greenhouse,
	"lever": lever,
	"ashby": ashby,
	"meetingcpp": meetingcpp,
	"jooble": jooble,
	"adzuna": adzuna,
	"reddit": reddit_cpp,
}
