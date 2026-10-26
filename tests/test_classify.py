"""Test delle regole di classificazione, costruiti su annunci reali visti nei primi aggiornamenti.

Se una modifica a scraper/classify.py rompe uno di questi casi, il workflow si ferma
prima di toccare i dati del sito.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scraper"))

from classify import classify, dedupe_key, strip_html  # noqa: E402


def job(title, company="Acme", location="", remote=None, countries=None, description="", default_tech=None, gaming=None, exclude_gaming=False):
	raw = {"company": company, "title": title, "url": "https://example.com/" + title.replace(" ", "-"), "location": location, "remote": remote, "countries": countries or [], "description": description, "source": "test", "gaming": gaming}
	return classify(raw, default_tech, exclude_gaming)


# ---------------------------------------------------------------- annunci da tenere

def test_vehicle_physics_remote_europe():
	j = job("Senior Programmer (Unreal Engine) – Vehicular & Physics Systems", "Odisi", location="Remote (Americas & Europe)", remote=True, description="Excellent C++ skills, Chaos physics")
	assert j and j["geo"] == "ok" and j["level"] == "senior"
	assert "C++" in j["tech"] and "Unreal" in j["tech"]
	assert "physics" in j["spec"] and "vehicle" in j["spec"]


def test_rome_hybrid_cpp():
	j = job("Senior Engineer C++", "Capgemini", location="Roma", description="Sviluppo C++ in modalità ibrida 3+2")
	assert j and j["city"] == "Roma" and j["geo"] == "ok" and j["mode"] == "ibrido"


def test_test_engineer_python_cpp_rome():
	j = job("Test Engineer Python & C++", "Capgemini", location="Roma")
	assert j and j["geo"] == "ok"


def test_remote_uk_or_eu_in_title():
	j = job("Senior Rendering Engineer - MPG - Fully remote from the UK or the EU", "Climax Studios", remote=True, default_tech=["C++", "Unreal"], gaming=True)
	assert j and j["geo"] == "ok"


def test_title_eu_wins_over_partial_country_list():
	j = job("Senior Rendering Engineer - MPG - Fully remote from the UK or the EU", "Climax Studios", remote=True, countries=["Spain"], default_tech=["C++", "Unreal"], gaming=True)
	assert j and j["geo"] == "ok"


def test_workable_country_list_with_italy():
	j = job("Senior Gameplay Programmer - Talent Pipeline", "Forgotten Empires", remote=True, countries=["Germany", "Italy", "Spain"], default_tech=["C++", "Unreal"], gaming=True)
	assert j and j["geo"] == "ok"


def test_home_based_emea_counts_as_remote_europe():
	j = job("C++/Rust Graphics and Windowing System Software Engineer - Mir", "Canonical", location="Home Based - EMEA", description="C++ and Rust")
	assert j and j["geo"] == "ok" and j["mode"] == "remoto"


def test_padova_cpp_robotics_kept_for_review():
	j = job("C++ Software Engineer for Robotics - Padova, Italy", "Xaba", location="Padova, Italy")
	assert j and j["geo"] == "verificare"


# ---------------------------------------------------------------- annunci da scartare

def test_generic_fullstack_listing_many_languages():
	assert job("Senior React Full-stack Developer", "Lemon.io", remote=True, countries=["Italy"], description="React, Node, C++, Unity, Go") is None


def test_backend_role_without_cpp_in_title():
	assert job("Senior Backend Engineer - MPG - Fully remote from the UK or the EU", "Climax Studios", remote=True, default_tech=["C++"], gaming=True) is None


def test_single_cpp_mention_in_description():
	assert job("Senior Software Engineer (Monitor Ingestion team)", "Sysdig", remote=True, countries=["Italy"], description="Go services, some C++ knowledge") is None


def test_remote_excluding_italy():
	assert job("Senior C++ Engineer", remote=True, countries=["Germany"], description="C++ C++") is None


def test_us_only_remote():
	assert job("Senior Gameplay Engineer C++", location="Remote (USA)", remote=True) is None


def test_onsite_outside_italy():
	assert job("Senior C++ Developer", location="London, UK", remote=False, description="C++ C++") is None


def test_junior_and_lead_excluded():
	assert job("Junior C++ Developer", location="Roma") is None
	assert job("Lead Gameplay Programmer C++", remote=True, location="Remote, Europe") is None


def test_unity_only_outside_gaming_excluded():
	assert job("Unity Developer", location="Roma", description="Unity, C# for industrial dashboards") is None


# ---------------------------------------------------------------- utilità

def test_escaped_html_is_cleaned():
	assert strip_html("&lt;p&gt;Modern &lt;b&gt;C++&lt;/b&gt;&lt;/p&gt;") == "Modern C++"


def test_dedupe_same_job_from_two_sources():
	a = {"company": "Odisi, Inc.", "title": "Senior Programmer (Unreal Engine) – Vehicular & Physics Systems"}
	b = {"company": "Odisi", "title": "Senior Programmer (Unreal Engine) – Vehicular & Physics Systems - Fully Remote (Americas & Europe)"}
	assert dedupe_key(a) == dedupe_key(b)


# ---------------------------------------------------------------- focus C++ non-gaming (excludeGaming = true)

def test_non_gaming_focus_drops_game_studios():
	assert job("Senior Gameplay Programmer C++", remote=True, location="Remote, Europe", description="Unreal game", exclude_gaming=True) is None
	assert job("Senior Gameplay Programmer - Talent Pipeline", "Forgotten Empires", remote=True, countries=["Italy"], default_tech=["C++"], gaming=True, exclude_gaming=True) is None


def test_non_gaming_focus_requires_explicit_cpp():
	assert job("Unreal Engine Developer", location="Roma", description="Unreal per simulatori industriali", exclude_gaming=True) is None


def test_non_gaming_focus_keeps_rome_embedded_qt():
	j = job("Sviluppatore C++ Qt", "Azienda", location="Roma", description="C++17, Qt/QML, Linux embedded, real-time", exclude_gaming=True)
	assert j and j["area"] == "non-gaming" and j["city"] == "Roma"
	assert {"C++", "Qt", "Linux", "C++ moderno"} <= set(j["tech"])
	assert "embedded" in j["spec"] and "ui" in j["spec"]


def test_non_gaming_focus_keeps_remote_systems_role():
	j = job("Software Engineer - Cross-platform C++ - Multipass", "Canonical", location="Home Based - EMEA", description="Modern C++ on Linux, distributed systems", exclude_gaming=True)
	assert j and j["geo"] == "ok" and "systems" in j["spec"]


def test_simulation_and_robotics_tags():
	j = job("C++ Software Engineer for Robotics - Padova, Italy", "Xaba", location="Padova, Italy", description="C++ motion planning, ROS2, simulation", exclude_gaming=True)
	assert j and "robotics" in j["spec"] and "simulation" in j["spec"]


# ---------------------------------------------------------------- arricchimento dalla descrizione

def test_company_flag_beats_gaming_words_in_description():
	j = job("Software Engineer - Cross-platform C++ - Multipass", "Canonical", location="Home Based - EMEA", description="C++ on Linux. Ubuntu is great for gaming and games.", gaming=False)
	assert j and j["area"] == "non-gaming"


def test_protected_categories_excluded():
	assert job("SW Developer C++ categorie protette L.68/99 - Full Remote", "Develer", remote=True, countries=["Italy"]) is None


def test_level_from_years_in_description():
	assert job("C++ Developer", location="Roma", description="Almeno 7 anni di esperienza in C++")["level"] == "senior"
	assert job("C++ Developer", location="Roma", description="3+ years of C++ experience")["level"] == "mid"
	assert job("C++ Developer", location="Roma", description="1-2 anni di esperienza in C++") is None


def test_salary_from_description():
	j = job("Sviluppatore C++", location="Roma", description="C++ su Linux. RAL 35.000 - 45.000 in base all'esperienza")
	assert j["salaryEur"] == 40000 and j["salary"].startswith("35.000")
	j = job("Senior C++ Engineer", location="Roma", description="C++ realtime, salary €50k-60k")
	assert j["salaryEur"] == 55000
