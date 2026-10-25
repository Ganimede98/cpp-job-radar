"""Regole per classificare un annuncio senza intervento umano.

Ogni funzione lavora su testo semplice (titolo + descrizione + luogo) e
restituisce i campi usati dal sito: tech, spec, level, mode, geo, ecc.
Le regole sono volutamente prudenti: quando un dato non è chiaro il campo
resta "n.d." o "verificare" invece di indovinare.
"""

import html
import re

# Versione delle regole: quando cambia, gli annunci automatici classificati con regole vecchie vengono rivalutati.
RULES_VERSION = 2

# ---------------------------------------------------------------- testo


def strip_html(text):
	if not text:
		return ""
	text = re.sub(r"<[^>]+>", " ", text)
	text = html.unescape(text)
	return re.sub(r"\s+", " ", text).strip()


def norm(text):
	return re.sub(r"[^a-z0-9+#]+", " ", (text or "").lower()).strip()


def slug(text):
	s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
	return s[:90] or "annuncio"


# ---------------------------------------------------------------- tecnologia

RE_CPP = re.compile(r"c\+\+|\bcpp\b|c/c\+\+", re.I)
RE_UNREAL = re.compile(r"unreal|\bue\s?[45]\b", re.I)
RE_UNITY = re.compile(r"\bunity\b", re.I)
RE_CSHARP = re.compile(r"c#|\.net\b", re.I)
RE_OFF_TOPIC_ROLE = re.compile(r"\b(back-?end|front-?end|full-?stack|react|web|android|ios|devops|sre|site reliability|data (engineer|scientist|analyst)|qa|security|sales|marketing|recruit\w*)\b", re.I)
RE_DEV_ROLE = re.compile(r"engineer|programmer|developer|sviluppatore|programmatore|software|coder|ingegnere", re.I)


def detect_tech(text):
	tech = []
	if RE_CPP.search(text):
		tech.append("C++")
	if RE_UNREAL.search(text):
		tech.append("Unreal")
	if RE_UNITY.search(text):
		tech.append("Unity")
	if RE_CSHARP.search(text):
		tech.append("C#")
	return tech


# ---------------------------------------------------------------- ambito e specialità

RE_GAMING = re.compile(r"\bgame|gaming|videogam|gameplay|studio[s]?\b.*\bgame|unreal|unity|playstation|xbox|nintendo|steam\b", re.I)

SPEC_RULES = [
	("gameplay", r"gameplay|game ?play|game mechanics|meccaniche di gioco"),
	("physics", r"physics|fisica|chaos|rigid ?body|collision"),
	("vehicle", r"vehicle|veicol|driving|car physics|automotive|racing|motorsport"),
	("racing", r"racing|motorsport|race game|corse"),
	("simulation", r"simulat|digital twin|autonomous|sistemi autonomi|real[- ]time sim"),
	("ai", r"\bai programmer|\bgame ai\b|artificial intelligence|behaviou?r tree|navigation|pathfinding|\bai engineer"),
	("engine", r"engine programmer|engine developer|core tech|performance|optimi[sz]|profil|multithread|low[- ]level"),
	("graphics", r"graphics|render|shader|vulkan|directx|opengl"),
	("tools", r"tools programmer|tools engineer|editor tool|pipeline tool"),
	("embedded", r"embedded|firmware|rtos|microcontroll|fpga|linux kernel|driver"),
	("multiplayer", r"multiplayer|network(ing)? (programmer|engineer|code)|netcode|online services"),
	("ui", r"\bui\b|user interface|umg|\bqt\b|frontend"),
	("xr", r"\bxr\b|\bvr\b|\bar\b|virtual reality|augmented reality|mixed reality"),
]


def detect_spec(text):
	return [name for name, pattern in SPEC_RULES if re.search(pattern, text, re.I)]


# ---------------------------------------------------------------- livello

RE_EXCLUDE_LEVEL = re.compile(r"\b(junior|jr\.?|intern|internship|stage|stagista|tirocini|graduate|new grad|trainee|apprentice|lead|principal|director|head of|manager|vp|chief|staff)\b", re.I)
RE_SENIOR = re.compile(r"\b(senior|sr\.?|expert|iii)\b", re.I)
RE_MID = re.compile(r"\b(mid|middle|mid-level|intermediate|regular|ii)\b", re.I)


def detect_level(title):
	"""Restituisce None se il ruolo va escluso (junior, lead, ...)."""
	if RE_EXCLUDE_LEVEL.search(title or ""):
		return None
	if RE_SENIOR.search(title or ""):
		return "senior"
	if RE_MID.search(title or ""):
		return "mid"
	return "n.d."


# ---------------------------------------------------------------- modalità e geografia

RE_HYBRID = re.compile(r"hybrid|ibrid|smart working|\d\s?\+\s?\d", re.I)
RE_REMOTE = re.compile(r"remote|remoto|da remoto|telelavoro|work from home|wfh|anywhere|fully distributed", re.I)
RE_ONSITE = re.compile(r"on-?site|in sede|in presenza|in office|office-based", re.I)
RE_ROME = re.compile(r"\b(roma|rome|frascati|fiumicino|pomezia|tivoli|guidonia)\b", re.I)
RE_ITALY = re.compile(r"\b(italy|italia|italian|milano|milan|torino|turin|bologna|napoli|naples|firenze|florence|pisa|padova|verona)\b", re.I)
RE_EU_OK = re.compile(r"\b(anywhere|worldwide|world ?wide|global(ly)?|emea|europe|european|\beu\b|eu-based|eea|cet|cest|utc ?\+ ?[0-2]\b|gmt ?\+ ?[0-2]\b)\b", re.I)
RE_ELSEWHERE = re.compile(r"\b(usa|u\.s\.|united states|us only|us-only|canada|latam|latin america|brazil|brasil|mexico|india|australia|new zealand|philippines|pakistan|japan|china|singapore|uk only|united kingdom only)\b|\b(ca|ny|tx|wa|or|ma|il|nc|ga|fl|co|az|ut)\b,|\bremote \((usa|us|canada)\)", re.I)


def detect_mode(text):
	if RE_HYBRID.search(text):
		return "ibrido"
	if RE_REMOTE.search(text):
		return "remoto"
	if RE_ONSITE.search(text):
		return "sede"
	return "n.d."


def detect_geo(location, text, remote, countries, title=""):
	"""Restituisce (geo, city, nota) oppure (None, ...) se l'annuncio va scartato.

	geo: "ok" = Italia ammessa, "verificare" = non chiaro, "no" = Italia esclusa.
	"""
	loc = location or ""
	both = f"{loc} {text}"
	if RE_ROME.search(loc) or (not loc and RE_ROME.search(text)):
		return "ok", "Roma", "Sede a Roma o dintorni."
	if countries:
		names = " ".join(countries)
		if RE_ITALY.search(names) or re.search(r"\b(eu|europe|emea)\b", names, re.I):
			return "ok", "", "L'Italia è tra i paesi ammessi."
		return "no", "", "Paesi ammessi: " + ", ".join(countries[:8]) + ("…" if len(countries) > 8 else "")
	if remote:
		head = f"{loc} {title}"
		if RE_ITALY.search(head) or RE_EU_OK.search(head):
			return "ok", "", "Remoto aperto a Europa/Italia secondo la fonte."
		if RE_ELSEWHERE.search(loc):
			return "no", "", "Remoto limitato a: " + loc
		if RE_ITALY.search(both) or RE_EU_OK.search(both):
			return "verificare", "", "La descrizione cita Europa/Italia: da confermare."
		return "verificare", "", "Remoto senza paesi indicati."
	# Non remoto e non a Roma: interessa solo se ibrido in Italia.
	if RE_ITALY.search(loc):
		return "verificare", "", "In Italia ma fuori Roma: controlla se c'è ibrido/remoto."
	if not loc.strip():
		return "verificare", "", "Sede non indicata."
	return None, "", ""


# ---------------------------------------------------------------- stipendio

RATES = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17, "PLN": 0.23, "CHF": 1.05, "SEK": 0.087, "BRL": 0.17, "CAD": 0.67}
PERIOD_FACTOR = {"year": 1, "annual": 1, "yearly": 1, "month": 12, "monthly": 12, "week": 46, "day": 220, "daily": 220, "hour": 1760, "hourly": 1760}


def salary_eur(min_v, max_v, currency, period):
	try:
		values = [float(v) for v in (min_v, max_v) if v not in (None, "", 0)]
	except (TypeError, ValueError):
		return None
	if not values:
		return None
	rate = RATES.get((currency or "EUR").upper())
	if rate is None:
		return None
	mid = sum(values) / len(values)
	factor = PERIOD_FACTOR.get((period or "year").lower(), 1)
	value = mid * factor * rate
	if value < 3000 or value > 1_000_000:
		return None
	return int(round(value, -2))


def salary_text(min_v, max_v, currency, period):
	if not min_v and not max_v:
		return ""
	cur = currency or ""
	per = {"year": "anno", "month": "mese", "hour": "ora", "day": "giorno", "week": "settimana"}.get((period or "").lower(), period or "")
	rng = f"{int(min_v):,}".replace(",", ".") if min_v else ""
	if max_v and max_v != min_v:
		rng = (rng + "–" if rng else "") + f"{int(max_v):,}".replace(",", ".")
	return f"{rng} {cur}{' / ' + per if per else ''}".strip()


# ---------------------------------------------------------------- classificazione completa


def classify(raw, default_tech=None):
	"""Trasforma un annuncio grezzo in un documento per il sito, o None se scartato.

	raw: dict con company, title, url, location, remote (bool|None), countries (list),
	     description, posted (YYYY-MM-DD|None), salary (testo), salaryEur (num|None), source.
	"""
	title = strip_html(raw.get("title"))
	company = strip_html(raw.get("company")) or "Azienda non indicata"
	description = strip_html(raw.get("description"))[:6000]
	location = strip_html(raw.get("location"))
	if not title or not raw.get("url", "").startswith("https://"):
		return None

	text = f"{title} {description}"
	if not RE_DEV_ROLE.search(title):
		return None
	# Ruoli web/backend/mobile/dati: esclusi, a meno che il titolo non citi esplicitamente C++.
	if RE_OFF_TOPIC_ROLE.search(title) and not RE_CPP.search(title):
		return None

	level = detect_level(title)
	if level is None:
		return None

	tech = detect_tech(text)
	# Rilevanza: la tecnologia deve stare nel titolo, oppure essere citata almeno due volte nella descrizione.
	# Evita gli annunci generici che elencano C++ in mezzo a venti linguaggi.
	title_hit = bool(RE_CPP.search(title) or RE_UNREAL.search(title) or RE_UNITY.search(title))
	desc_hits = len(RE_CPP.findall(description)) + len(RE_UNREAL.findall(description))
	if not title_hit and desc_hits < 2 and not default_tech:
		return None
	if not tech and default_tech:
		tech = list(default_tech)
	if not tech:
		return None
	gaming = bool(RE_GAMING.search(text)) or raw.get("gaming") is True
	# Unity/C# senza C++ né Unreal interessa solo nel gaming.
	if "C++" not in tech and "Unreal" not in tech and not gaming:
		return None

	remote = raw.get("remote")
	if remote is None:
		remote = bool(RE_REMOTE.search(f"{location} {title}"))
	geo, city, geo_note = detect_geo(location, text, remote, raw.get("countries") or [], title)
	if geo in (None, "no"):
		return None  # fuori Roma senza remoto, oppure remoto che esclude l'Italia

	mode = detect_mode(f"{location} {title} {description[:1500]}")
	if remote and mode == "n.d.":
		mode = "remoto"

	summary = description[:280].rsplit(" ", 1)[0] + "…" if len(description) > 280 else description
	return {
		"company": company,
		"title": title,
		"url": raw["url"],
		"source": raw.get("source", ""),
		"area": "gaming" if gaming else "non-gaming",
		"tech": tech,
		"spec": detect_spec(text),
		"level": level,
		"mode": mode,
		"location": location or ("Remoto" if remote else "n.d."),
		"city": city,
		"geo": geo,
		"geoNote": geo_note,
		"salary": raw.get("salary", ""),
		"salaryEur": raw.get("salaryEur"),
		"posted": raw.get("posted"),
		"status": "aperto",
		"summary": summary,
		"origin": "auto",
		"rules": RULES_VERSION,
	}


RE_COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|limited|gmbh|ag|sa|spa|s p a|srl|s r l|bv|oy|ab|plc|group|studios?|entertainment|games)\b")
RE_TITLE_NOISE = re.compile(r"\b(fully|remote|remoto|hybrid|ibrido|on site|onsite|m f d|m w d|f m x|all genders|americas|europe|emea|eu)\b")


def dedupe_key(job):
	"""Chiave per riconoscere lo stesso annuncio arrivato da fonti diverse."""
	company = RE_COMPANY_SUFFIX.sub(" ", norm(job.get("company")))
	title = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", (job.get("title") or "").lower())
	title = RE_TITLE_NOISE.sub(" ", norm(title))
	company = re.sub(r"\s+", " ", company).strip()
	title = re.sub(r"\s+", " ", title).strip()
	return f"{company}|{title}"
