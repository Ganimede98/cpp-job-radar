"""Regole per classificare un annuncio senza intervento umano.

Ogni funzione lavora su testo semplice (titolo + descrizione + luogo) e
restituisce i campi usati dal sito: tech, spec, level, mode, geo, ecc.
Le regole sono volutamente prudenti: quando un dato non è chiaro il campo
resta "n.d." o "verificare" invece di indovinare.
"""

import html
import re

# Versione delle regole: quando cambia, gli annunci automatici classificati con regole vecchie vengono rivalutati.
RULES_VERSION = 7

# ---------------------------------------------------------------- testo


def strip_html(text):
	if not text:
		return ""
	text = html.unescape(text)  # alcune API (Greenhouse) mandano l'HTML già "escapato"
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
RE_QT = re.compile(r"\bqt\b|\bqml\b", re.I)
RE_LINUX = re.compile(r"\blinux\b|\bposix\b|yocto|embedded linux", re.I)
RE_MODERN_CPP = re.compile(r"c\+\+ ?(1[47]|2[03])\b|modern c\+\+", re.I)
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
	if RE_QT.search(text):
		tech.append("Qt")
	if RE_LINUX.search(text):
		tech.append("Linux")
	if RE_MODERN_CPP.search(text):
		tech.append("C++ moderno")
	return tech


# ---------------------------------------------------------------- ambito e specialità

# Unreal e Unity da soli non bastano: si usano anche in simulazione, XR e industria.
RE_GAMING = re.compile(r"\bgames?\b|gaming|videogam|gameplay|playstation|xbox|nintendo|\bsteam\b", re.I)

SPEC_RULES = [
	("gameplay", r"gameplay|game ?play|game mechanics|meccaniche di gioco"),
	("physics", r"physics|fisica|chaos|rigid ?body|collision"),
	("vehicle", r"vehic|veicol|driving|car physics|automotive|racing|motorsport"),
	("racing", r"racing|motorsport|race game|corse"),
	("simulation", r"simulat|digital twin|autonomous|sistemi autonomi|real[- ]time sim"),
	("ai", r"\bai programmer|\bgame ai\b|artificial intelligence|behaviou?r tree|navigation|pathfinding|\bai engineer"),
	("engine", r"engine programmer|engine developer|core tech|performance|optimi[sz]|profil|multithread|low[- ]level"),
	("graphics", r"graphics|render|shader|vulkan|directx|opengl"),
	("tools", r"tools programmer|tools engineer|editor tool|pipeline tool"),
	("embedded", r"embedded|firmware|rtos|microcontroll|fpga|linux kernel|driver|real[- ]time"),
	("robotics", r"robot|motion planning|\bros2?\b|autonom|drone|uav"),
	("vision", r"computer vision|visione artificiale|opencv|perception|point cloud|lidar|slam"),
	("hpc", r"\bhpc\b|high[- ]performance computing|cuda|simd|vectori[sz]|gpu comput|parallel comput"),
	("systems", r"database|storage|distributed|kernel|compiler|llvm|browser|chromium|operating system|networking stack|low[- ]latency"),
	("dsp", r"signal processing|\bdsp\b|radar|sonar|\bsar\b|audio|telecom|5g"),
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


RE_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs|anni)", re.I)


def years_required(description):
	"""Anni di esperienza richiesti secondo la descrizione (il valore più alto plausibile), o None."""
	values = [int(m.group(1)) for m in RE_YEARS.finditer(description or "")]
	values = [v for v in values if 1 <= v <= 15]
	return max(values) if values else None


def detect_level(title, description=""):
	"""Restituisce None se il ruolo va escluso (junior, lead, ...).

	Il titolo ha la precedenza; se non dice nulla si usano gli anni richiesti nella descrizione:
	fino a 1 anno = junior (escluso), 2-4 = mid, 5 o più = senior.
	"""
	if RE_EXCLUDE_LEVEL.search(title or ""):
		return None
	if RE_SENIOR.search(title or ""):
		return "senior"
	if RE_MID.search(title or ""):
		return "mid"
	years = years_required(description)
	if years is None:
		return "n.d."
	if years <= 1:
		return None
	return "mid" if years <= 4 else "senior"


# ---------------------------------------------------------------- modalità e geografia

RE_HYBRID = re.compile(r"hybrid|ibrid|smart working|\d\s?\+\s?\d", re.I)
RE_REMOTE = re.compile(r"remote|remoto|da remoto|telelavoro|work from home|wfh|home[- ]based|anywhere|fully distributed", re.I)
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
	if remote and (RE_ITALY.search(title) or RE_EU_OK.search(title)):
		return "ok", "", "Il titolo dell'annuncio indica Italia/Europa."
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


RE_SALARY_RANGE = re.compile(r"(?:ral|€|eur|euro|salary|stipendio|retribuzione)[^0-9]{0,25}(\d{2,3})[.,]?(\d{3})?\s*(k)?\s*(?:€|eur)?\s*[-–a]\s*(?:€\s*)?(\d{2,3})[.,]?(\d{3})?\s*(k)?", re.I)


def salary_from_text(text):
	"""Cerca una fascia di stipendio annuo in euro nella descrizione (es. "RAL 35.000 - 45.000", "€40k-50k")."""
	m = RE_SALARY_RANGE.search(text or "")
	if not m:
		return "", None

	def value(head, tail, k):
		v = int(head) * 1000 if (tail or k) else int(head)
		return v

	low, high = value(m.group(1), m.group(2), m.group(3)), value(m.group(4), m.group(5), m.group(6))
	if not (15000 <= low <= high <= 250000):
		return "", None
	return f"{low:,}–{high:,} € / anno".replace(",", "."), int(round((low + high) / 2, -2))


# Motivo dell'ultimo scarto, letto da run.py per le statistiche della scheda Fonti.
LAST_REJECT = {"reason": None}


def reject(reason):
	LAST_REJECT["reason"] = reason
	return None


RE_EXCLUDE_TEXT = re.compile(r"categorie protette|l\.?\s?68/99|stage curriculare|tirocinio|neolaureat", re.I)

# ---------------------------------------------------------------- classificazione completa


def classify(raw, default_tech=None, exclude_gaming=False):
	"""Trasforma un annuncio grezzo in un documento per il sito, o None se scartato.

	raw: dict con company, title, url, location, remote (bool|None), countries (list),
	     description, posted (YYYY-MM-DD|None), salary (testo), salaryEur (num|None), source.
	"""
	title = strip_html(raw.get("title"))
	company = strip_html(raw.get("company")) or "Azienda non indicata"
	description = strip_html(raw.get("description"))[:6000]
	location = strip_html(raw.get("location"))
	if not title or not raw.get("url", "").startswith("https://"):
		return reject("dati incompleti")

	text = f"{title} {description}"
	if not RE_DEV_ROLE.search(title):
		return reject("non è un ruolo di sviluppo")
	# Ruoli web/backend/mobile/dati: esclusi, a meno che il titolo non citi esplicitamente C++.
	if RE_OFF_TOPIC_ROLE.search(title) and not RE_CPP.search(title):
		return reject("ruolo web/backend/mobile/dati")

	if RE_EXCLUDE_TEXT.search(title):
		return reject("categorie protette / stage / neolaureati")
	level = detect_level(title, description)
	if level is None:
		return reject("livello junior o lead")

	tech = detect_tech(text)
	# Rilevanza: la tecnologia deve stare nel titolo, oppure essere citata almeno due volte nella descrizione.
	# Evita gli annunci generici che elencano C++ in mezzo a venti linguaggi.
	title_hit = bool(RE_CPP.search(title) or RE_UNREAL.search(title) or RE_UNITY.search(title))
	desc_hits = len(RE_CPP.findall(description)) + len(RE_UNREAL.findall(description))
	# Le fonti che cercano per parola chiave (Jooble, Adzuna) hanno già filtrato su "C++": basta una citazione.
	query_hint = "c++" in (raw.get("query") or "").lower()
	if not title_hit and desc_hits < (1 if query_hint else 2) and not default_tech:
		return reject("C++/Unreal non abbastanza centrale")
	if not tech and default_tech:
		tech = list(default_tech)
	if not tech:
		return reject("nessuna tecnologia riconosciuta")
	# Se la fonte sa già se è uno studio di videogiochi, vale quello; altrimenti decide il testo.
	# (Una descrizione di Canonical che cita "gaming su Ubuntu" non rende gaming il ruolo.)
	if raw.get("gaming") is not None:
		gaming = bool(raw["gaming"]) or bool(RE_GAMING.search(title))
	else:
		gaming = bool(RE_GAMING.search(text))
	if exclude_gaming and gaming:
		return reject("gaming escluso dalla configurazione")
	if exclude_gaming and "C++" not in tech:
		return reject("fuori dal gaming senza C++")
	# Unity/C# senza C++ né Unreal interessa solo nel gaming.
	if "C++" not in tech and "Unreal" not in tech and not gaming:
		return reject("Unity/C# fuori dal gaming")

	remote = raw.get("remote")
	if remote is None:
		remote = bool(RE_REMOTE.search(f"{location} {title}"))
	geo, city, geo_note = detect_geo(location, text, remote, raw.get("countries") or [], title)
	if geo is None:
		return reject("in sede fuori Roma")
	if geo == "no":
		return reject("remoto che esclude l'Italia")

	mode = detect_mode(f"{location} {title} {description[:1500]}")
	if remote and mode == "n.d.":
		mode = "remoto"

	salary, salary_value = raw.get("salary", ""), raw.get("salaryEur")
	if not salary:
		salary, found_value = salary_from_text(description)
		salary_value = salary_value or found_value

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
		"salary": salary,
		"salaryEur": salary_value,
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
