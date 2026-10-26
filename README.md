# C++ Job Radar

Sito personale che raccoglie annunci **C++ / Unreal / Unity** di livello mid o senior, a **Roma (in sede o ibrido)** o **in remoto aperti all'Italia**, gaming e non-gaming.

Funziona da solo e gratis su GitHub, senza abbonamenti:

- **GitHub Pages** pubblica il sito (cartella `docs/`).
- **GitHub Actions** esegue lo scraper (`scraper/`) quando premi *Run workflow* e salva i risultati in `docs/data/`.

## Messa online (una volta sola, ~10 minuti)

1. **Crea il repository**: su GitHub → *New repository* → nome `cpp-job-radar` → **Public** → *Create*.
   (Se usi un nome diverso, aggiorna `<meta name="repo">` in `docs/index.html`.)
2. **Carica i file**: nella pagina del repo → *uploading an existing file* → trascina **il contenuto** della cartella del progetto (incluse le cartelle `.github`, `docs`, `scraper`) → *Commit changes*.
   > La cartella `.github` è nascosta su Mac/Windows: se non la vedi, attiva la visualizzazione dei file nascosti, oppure creala a mano su GitHub (*Add file → Create new file* → nome `.github/workflows/update.yml` → incolla il contenuto).
3. **Attiva il sito**: *Settings → Pages* → *Source: Deploy from a branch* → branch `main`, cartella `/docs` → *Save*. Dopo un minuto il sito è su `https://ganimede98.github.io/cpp-job-radar/`.
4. **Permessi del workflow**: *Settings → Actions → General → Workflow permissions* → **Read and write permissions** → *Save*.
5. **Primo aggiornamento**: tab *Actions* → *Aggiorna annunci* → *Run workflow*. Dopo 2–3 minuti ricarica il sito.

## Come si aggiorna

Il pulsante **Aggiorna ora** del sito apre la pagina del workflow su GitHub: premi *Run workflow* e ricarica il sito dopo 2–3 minuti.
Per un aggiornamento automatico ogni mattina togli il `#` dalle righe `schedule` in `.github/workflows/update.yml`. È comunque gratis.

## Gaming e non-gaming

Lo scraper raccoglie entrambi. Il punteggio di match nel sito usa due profili: uno per i ruoli gaming (Unreal, gameplay, fisica dei veicoli) e uno per il C++ non-gaming (simulazione, real-time ed embedded, robotica, sistemi, Qt). In `scraper/config.json`, `"excludeGaming": true` terrebbe solo il non-gaming.

## Fonti

Sempre attive, senza chiavi:

| Fonte | Metodo |
|---|---|
| Hacker News – Who is hiring? | API Algolia |
| Meeting C++ Jobs | pagina HTML |
| Himalayas | API ufficiale, ricerche mirate (C++, Unreal, engine, simulazione, embedded, grafica); solo remoti che ammettono l'Italia |
| Studi su Workable | Forgotten Empires, Climax Studios, Astrid Entertainment, Rebellion |
| Aziende su Greenhouse | Canonical, Mozilla |
| Aziende su Ashby | ClickHouse |
| Aziende su Lever | Xsolla |

Gli slug degli studi sono stati verificati il 26/10/2026. Remotive e Arbeitnow sono stati tolti: su centinaia di annunci letti ne restavano 0–1 pertinenti.

Facoltative, con chiave **gratuita** (in *Settings → Secrets and variables → Actions → New repository secret*):

| Fonte | Secret | Come ottenerla |
|---|---|---|
| **Jooble** (copre anche Indeed, LinkedIn e bacheche italiane) | `JOOBLE_API_KEY` | modulo su https://jooble.org/api/about, la chiave arriva via email |
| **Adzuna** | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | registrazione su https://developer.adzuna.com/signup |
| **r/cpp** (thread trimestrale C++ Jobs) | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | https://www.reddit.com/prefs/apps → *create app* → tipo **script** |

Senza chiave queste fonti risultano "Non configurata" e vengono saltate.
Jooble e Adzuna sono le più utili per **Roma**: le cercano già con "C++", "C++ ibrido" e "Unreal Engine".

### Aggiungere uno studio

In `scraper/config.json`, nella fonte `workable`, `greenhouse` o `lever`, aggiungi una riga con nome e *slug* (la parte finale dell'indirizzo della pagina carriere, es. `apply.workable.com/rebellion` → `rebellion`).
Se dopo un aggiornamento la scheda **Fonti** mostra "Errore" per uno studio, lo slug è sbagliato.

## Come lavora lo scraper

1. **Legge tutte le fonti in parallelo**, con una sessione HTTP che ritenta da sola gli errori temporanei (429, 5xx) rispettando i tempi di attesa chiesti dal server. Uno slug sbagliato o una fonte giù non bloccano le altre.
2. **Arricchisce gli annunci**: per Workable scarica descrizione e requisiti completi; da ogni descrizione ricava anni di esperienza (→ livello), fascia di stipendio, modalità (ibrido/remoto) e tecnologie (C++ moderno, Qt, Linux…).
3. **Classifica e scarta** con regole testate (`tests/`): junior/lead/stage, categorie protette, ruoli web/mobile/dati, remoti che escludono l'Italia, in sede fuori Roma.
4. **Unisce i duplicati** arrivati da fonti diverse, tenendo il link più diretto.
5. **Ricontrolla i link**: ogni 7 giorni riapre la pagina degli annunci non più confermati da una fonte (compresi quelli verificati a mano) e li segna *chiusi* se rispondono 404 o dicono che la posizione non è più disponibile. Al massimo 80 controlli per giro (`linkCheckEveryDays`, `linkCheckMaxPerRun` in `config.json`).
6. **Scrive le statistiche** di ogni fonte (letti, pertinenti, nuovi, secondi impiegati) nella scheda Fonti.

## Come vengono classificati gli annunci

Lo scraper non usa intelligenza artificiale: applica regole su parole chiave (`scraper/classify.py`).

- **Scartati**: junior, intern, graduate, lead, principal, director, manager; ruoli senza C++/Unreal (Unity/C# solo nel gaming); in sede fuori da Roma.
- **Geografia**: *ok* se Roma o remoto aperto a Italia/Europa/ovunque; *no* se il remoto è limitato ad altri paesi; *verificare* negli altri casi.
- **Modalità**: ibrido / remoto / in sede, oppure *n.d.* se l'annuncio non lo dice.
- **Chiusura**: un annuncio sparito per 2 aggiornamenti di fila dalla sua fonte viene segnato *chiuso*, e dopo 30 giorni eliminato.
- Gli annunci con `"origin": "seed"` in `docs/data/jobs.json` sono quelli verificati a mano: lo scraper non li modifica né li chiude. Cancellali a mano quando non servono più.

Il punteggio di **match** è calcolato nel sito (`docs/index.html`, funzione `scoreOf`).

## Test

`tests/test_classify.py` contiene casi reali (annunci da tenere e da scartare). Il workflow li esegue prima di ogni aggiornamento: se una modifica alle regole li rompe, l'aggiornamento si ferma e i dati del sito restano intatti.

```bash
python -m pytest -q tests
```

## Prova in locale

```bash
pip install -r scraper/requirements.txt
python scraper/run.py
python -m http.server -d docs 8000   # poi apri http://localhost:8000
```
