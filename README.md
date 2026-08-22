# Customer Intelligence Monitor

Sistema di monitoraggio automatico di notizie e informazioni pubbliche relative a clienti, fornitori e aziende in anagrafica.

## Obiettivo

Costruire un agente software che monitori notizie e informazioni pubbliche relative a clienti, fornitori o aziende presenti in anagrafica. L'agente parte da un file Excel o CSV contenente l'anagrafica aziendale, cerca informazioni sul web, classifica le notizie rilevanti e genera report email per destinatari configurati.

## Funzionalità principali

- **Import Excel/CSV**: Importazione di anagrafica aziendale con pulizia automatica
- **Normalizzazione dati**: Gestione di file sporchi con duplicati, spazi, valori mancanti
- **Gestione aziende**: CRUD aziende con enrichment automatico
- **Cluster di monitoraggio**: Grouping di aziende per destinatari e frequenze
- **Ricerca notizie**: Provider astratto per ricerca da molteplici fonti
- **Classificazione AI**: Analisi automatica di rilevanza, urgenza e rischio
- **Generazione report**: Report email HTML e testo con filtri di rilevanza
- **Dashboard**: Interface semplice per gestione e configurazione

## Stack tecnico MVP

- **Backend**: Python FastAPI
- **Frontend**: Jinja templates
- **Database**: SQLite
- **Excel/CSV**: pandas + openpyxl
- **Scheduler**: APScheduler
- **AI**: Claude API
- **Email**: SMTP

## Struttura del progetto

```
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Configuration
│   ├── database.py             # SQLite setup
│   ├── models/                 # SQLAlchemy models
│   ├── schemas/                # Pydantic schemas
│   ├── api/                    # API endpoints
│   ├── services/               # Business logic
│   ├── providers/              # News source providers
│   ├── templates/              # Jinja templates
│   └── static/                 # CSS, JS, etc.
├── tests/                      # Test suite
├── requirements.txt
├── .env.example
└── README.md
```

## Quick start - macOS

### 1. Setup iniziale

```bash
# Installare Python 3.11
brew install python@3.11

# Clonare repository
cd ~/Projects
git clone https://github.com/angoldon-lang/Customer-intelligence.git
cd Customer-intelligence

# Creare virtual environment
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate

# Installare dipendenze
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configurazione

```bash
# Copiare env file
cp .env.example .env

# Editare e aggiungere API key
nano .env
```

Aggiungi la chiave Claude API:
```env
CLAUDE_API_KEY=sk-ant-YOUR_API_KEY_HERE
```

Opzionale ma consigliato per una ricerca notizie reale (senza, il sistema
usa solo GDELT, gratuito ma senza snippet): registrati su
[gnews.io](https://gnews.io) e aggiungi la chiave:
```env
GNEWS_API_KEY=YOUR_GNEWS_KEY_HERE
```
Il piano gratuito GNews (100 richieste/giorno) è pensato per lo sviluppo;
per un uso continuativo su molte aziende serve un piano a pagamento — vedi
"Architettura ricerca notizie" più sotto per i dettagli su costi e
schedulazione a livelli.

Salva con `Ctrl+O`, `Enter`, `Ctrl+X`

### 3. Inizializzare database

```bash
python3 << 'EOF'
from app.database import init_db
init_db()
EOF
```

### 4. Avviare applicazione

**Usa una porta disponibile** (se 8000 è già occupata):

```bash
# Porta 8001
uvicorn app.main:app --reload --port 8001

# Oppure 8080, 3000, 5000, etc.
uvicorn app.main:app --reload --port 8080
```

### 5. Accesso dashboard

Apri il browser:
```
http://localhost:8001
```

## Workflow

**Flusso principale di utilizzo:**

1. Import Excel/CSV anagrafica
2. Pulizia e normalizzazione dati
3. Creazione cluster automatici
4. Configurazione destinatari report
5. Ricerca notizie per azienda
6. Classificazione AI
7. Generazione report draft
8. Approvazione e invio

## Dashboard - Pagine disponibili

La dashboard è completamente funzionante con **8 pagine principali**:

### 📊 Dashboard principale
- Statistiche in tempo reale (aziende, cluster, notizie, report)
- Ultime notizie trovate
- Ultimi report generati
- Azioni rapide

### 📁 Import dati
- **Drag & drop** file Excel/CSV
- Preview e validazione dati
- Rilevamento duplicati
- Rapporto risultati importazione
- Supporto formati: `.xlsx`, `.xls`, `.csv`

### 🏢 Gestione aziende
- Tabella completa con ricerca
- Filtri per stato (Attiva, Pausa, Da verificare, Archiviata)
- Visualizza sito web, email, account owner
- Modifica ed elimina aziende (modale, con conferma per l'eliminazione)

### 🔎 Copertura ricerca
- Per ogni azienda: quando è stata cercata l'ultima volta, notizie trovate,
  e se non ne ha trovate perché (nessun risultato, fonte bloccata, errore,
  da arricchire con P.IVA/sito, o mai cercata)
- Dettaglio per-provider (es. `google_news_rss:0, gdelt:blocked, rss:2`)
- Filtri per stato e ricerca per nome azienda

### 📈 Configurazione cluster
- **Crea cluster manualmente** con frequenza e filtri rilevanza
- **Crea cluster automaticamente** da:
  - Account Owner
  - Tipo azienda (Cliente, Fornitore, etc.)
  - Settore (Codice Ateco)
- Aggiungi/rimuovi aziende dal cluster (modale "Dettagli")
- Aggiungi/rimuovi destinatari email
- Elimina cluster

### 📰 Gestione notizie
- Tabella notizie con filtri:
  - **Status**: Nuove, Approvate, Rifiutate, Da verificare
  - **Categoria**: Investment, M&A, Cybersecurity, IT/Digital, etc.
  - **Rilevanza minima**: 1-10
- Visualizza source, data, categoria
- Approva/rifiuta notizie
- Link diretto all'articolo

### 📧 Report email
- **Genera report** per cluster selezionato
- Scegli giorni da includere (1-90)
- Anteprima report HTML
- Status: Draft, Pending Approval, Sent
- Invio email
- Storico report completo

### ⚙️ Impostazioni
- Configurazione **API Claude**
- Configurazione **SMTP** (Gmail, Outlook, etc.)
- **Scheduler** monitoraggio automatico
- **Filtri di default** aziende e notizie
- Info sistema (versione, database, roadmap)

## Architettura ricerca notizie

Il flusso è pensato per dare a Claude solo un pacchetto strutturato per
notizia (titolo, fonte, url, data, snippet), mai il contenuto integrale del
web: la ricerca/estrazione è compito dei provider, Claude fa solo la parte
"intelligente" (capire se riguarda davvero l'azienda, sintetizzare,
classificare, dare un punteggio, suggerire un'azione).

```
GDELT (gratuito) + GNews.io + RSS/fonti ufficiali
        ↓
estrazione titolo, fonte, url, data, snippet (mai il testo integrale)
        ↓
deduplica (per URL, tra provider e contro il database)
        ↓
invio del pacchetto strutturato a Claude
        ↓
Claude valuta pertinenza, sintetizza, classifica, assegna punteggi
        ↓
generazione report email per cluster
```

### Provider disponibili

| Provider | Costo | Cosa fornisce | Config |
|---|---|---|---|
| **Google News RSS** (`app/providers/google_news_rss.py`) | Gratuito, nessuna chiave | Feed RSS pubblico di ricerca (non la pagina HTML, bloccata da un consent-wall) - in genere la copertura migliore per piccole aziende italiane locali | Attivo di default (`GOOGLE_NEWS_RSS_ENABLED=True`) |
| **GDELT** (`app/providers/gdelt.py`) | Gratuito, nessuna chiave | Copertura ampia: titolo, url, dominio, data. Nessuno snippet. | Attivo di default (`GDELT_ENABLED=True`) |
| **GNews.io** (`app/providers/gnews.py`) | Piano gratuito 100 richieste/giorno (solo dev secondo il loro ToS), piani a pagamento per produzione | Validazione/copertura aggiuntiva con snippet (`description`) | `GNEWS_API_KEY` in `.env` |
| **RSS ufficiali** (`app/providers/rss.py`) | Gratuito | Comunicati stampa/IR direttamente dal sito dell'azienda, la fonte più affidabile | Configurabile da Impostazioni → "Fonti notizie", o via `POST /api/news-sources` |

Se nessun provider è configurabile/raggiungibile, il sistema usa
`TestNewsProvider` (dati di esempio) così la pipeline resta testabile.

GDELT e Google News RSS sono gratuiti ma non hanno un vero SLA: il client
li richiama con un ritmo minimo tra le richieste e un circuit breaker (si
disattivano per il resto del run se continuano a rispondere 429/403 dopo un
tentativo di backoff), invece di continuare a martellarli per ogni azienda
restante.

### Testare velocemente senza aspettare l'intera anagrafica

`POST /api/monitoring/run-now?limit=N` (o il campo "Limita a N aziende" in
Impostazioni) esegue il monitoraggio solo sulle prime N aziende scadute,
utile per verificare rapidamente se la ricerca trova notizie prima di
lanciare un run completo su migliaia di aziende.

### Aziende ambigue (es. "AR Group", "ASA SRL", "ARMANDO SRL")

Le aziende senza sito web e senza P.IVA/codice fiscale in anagrafica, o con
`enrichment_status = needs_review`, **non vengono cercate automaticamente**:
una ricerca su un nome generico produrrebbe solo falsi positivi. Vengono
contate in `companies_needing_enrichment` nel risultato del monitoraggio
invece di essere processate. Arricchisci l'azienda con sito web o P.IVA
(pagina Aziende) per farla rientrare nel monitoraggio automatico.

Per le aziende identificate, sito web e P.IVA vengono comunque passati a
Claude come contesto di disambiguazione: se una notizia potrebbe riguardare
un omonimo, `confidence_score` viene abbassato invece di essere scartata in
silenzio, così resta visibile per una verifica manuale nella pagina Notizie.

Un fallback SERP (es. SerpAPI/DataForSEO) per le aziende ambigue/prioritarie
è previsto come step successivo (Fase 4), da valutare in base ai risultati
misurati nelle prime settimane d'uso.

### Schedulazione per priorità (tiering sui cluster)

La frequenza di ricerca non è più uguale per tutte le aziende: si eredita
dal campo "Frequenza report" del cluster (pagina Cluster), con la logica
"un'azienda in più cluster eredita la frequenza più alta":

| Frequenza cluster | Intervallo di ricerca |
|---|---|
| `daily` | ogni 24 ore |
| `2-3x_week` | ogni ~60 ore (2-3 volte/settimana) |
| `weekly` (default) | ogni 7 giorni |
| `monthly` | ogni 30 giorni |

Un'azienda senza cluster attivo usa il default settimanale. Ad ogni run il
sistema calcola le aziende "scadute" (mai controllate, o oltre il loro
intervallo) e processa al massimo `MAX_COMPANIES_PER_RUN` (default 200,
configurabile in `.env`) partendo dalle più scadute — un limite di
sicurezza per non far esplodere durata/quota API con migliaia di aziende in
anagrafica.

Esempio di impostazione consigliata:

| Cluster aziende | Frequenza da impostare |
|---|---|
| Top clienti strategici | `daily` |
| Clienti normali | `2-3x_week` |
| Long tail / fornitori | `weekly` |

## Roadmap

### Fase 1 - MVP
- [x] Struttura progetto
- [x] Database e modelli
- [x] Import Excel/CSV
- [x] CRUD aziende e cluster
- [x] Provider news mock
- [x] Classificazione AI base
- [x] Generazione report draft
- [x] Dashboard minimale

### Fase 2 - Ricerca reale
- [x] Provider web reale (GDELT + GNews.io)
- [x] RSS feed (fonti ufficiali configurabili)
- [x] Deduplica notizie (per URL, tra provider e contro il DB)
- [x] Scoring AI completo con disambiguazione (sito web/P.IVA)
- [x] Scheduler di monitoraggio con tiering per cluster

### Fase 3 - Automazione
- [x] Invio email automatico
- [ ] Approvazione report
- [ ] Alert critici
- [ ] Report per account owner

### Fase 4 - Fonti premium
- [ ] Fallback SERP (SerpAPI/DataForSEO) per aziende ambigue/prioritarie
- [ ] Integrazione API autorizzate aggiuntive (es. TheNewsAPI, GNews Enterprise)
- [ ] Gestione access_status e license_scope avanzata

## Design dashboard

La dashboard è costruita con:
- **Backend**: FastAPI + Jinja2 templates
- **Frontend**: HTML5 + CSS3 moderno + JavaScript vanilla
- **Styling**: CSS moderno con:
  - Sidebar navigazione fisso (250px)
  - Layout responsive (desktop, tablet, mobile)
  - Badge colorate per categorie e status
  - Modal dialog per dettagli
  - Grid layout per card statistiche
  - Smooth transitions e hover effects

### Colori del sistema
- **Primario**: #3498db (blu) - Link, pulsanti primari
- **Success**: #27ae60 (verde) - Approva, crea
- **Danger**: #e74c3c (rosso) - Elimina, rifiuta
- **Warning**: #f39c12 (arancio) - Da verificare
- **Dark**: #2c3e50 (grigio scuro) - Header sidebar

### Componenti UI
- Tabelle con hover effects
- Search box con input filtering
- Select dropdown per filtri
- Form validation lato client
- Health status badge
- Empty states con messaggi
- Loading indicators
- Alert boxes (success, danger, warning)

## Sviluppo

Il progetto è sviluppato in modo modulare e incrementale. Ogni componente è separato e facilmente testabile.

### Moduli principali

- **importer**: Importazione file Excel/CSV
- **normalizer**: Pulizia e normalizzazione dati
- **enrichment**: Arricchimento dati aziendali
- **clustering**: Gestione cluster di monitoraggio
- **providers**: Provider astratto per fonti notizie
- **search**: Ricerca e estrazione articoli
- **classifier**: Classificazione AI notizie
- **scoring**: Scoring rilevanza, urgenza, rischio
- **reporting**: Generazione report email
- **email**: Invio email (SMTP, Microsoft Graph)
- **scheduler**: APScheduler per monitoraggio periodico
- **dashboard**: Interface web Jinja/FastAPI

## Sviluppare l'app - Aggiornamenti e modifiche

### Setup per sviluppo

```bash
# Attivare venv
source venv/bin/activate

# Installare dipendenze con dev tools
pip install -r requirements.txt
pip install black flake8 pytest

# Avviare app in development mode
uvicorn app.main:app --reload --port 8001
```

### Flusso di sviluppo

#### 1. Creare un branch per la feature
```bash
git checkout -b feature/nome-feature
# es: feature/add-email-sending
```

#### 2. Fare modifiche
- **Modifica backend** → `app/main.py`, `app/services/`, `app/models.py`
- **Modifica frontend** → `app/templates/*.html`
- **Modifica database** → `app/models.py`
- **Modifica logica** → `app/services/`

#### 3. Testare i cambiamenti
```bash
# L'app ricaricha automaticamente con --reload
# Apri http://localhost:8001 nel browser

# Oppure testa via API
curl http://localhost:8001/api/health
```

#### 4. Eseguire i test
```bash
pytest tests/ -v

# Test singolo file
pytest tests/test_importer.py -v

# Test con coverage
pytest --cov=app tests/
```

#### 5. Fare commit dei cambiamenti
```bash
# Visualizzare cambiamenti
git status
git diff

# Stage dei file
git add app/main.py app/templates/

# Commit con messaggio descrittivo
git commit -m "Feature: Aggiungi funzionalità X

Descrizione dei cambiamenti:
- Punto 1
- Punto 2

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gm5bweKb7cvHgcZFGKb2Gz"
```

#### 6. Pushare i cambiamenti
```bash
# Push branch feature
git push -u origin feature/nome-feature

# Oppure push al branch principale (se autorizzato)
git push origin claude/customer-intelligence-monitor-vzirll
```

### Struttura cartelle per modifiche

```
app/
├── main.py                 ← Endpoint FastAPI (aggiorna qui per nuove route)
├── models.py              ← Modelli database (nuove tabelle)
├── config.py              ← Configurazione (variabili env)
├── database.py            ← Connessione DB
├── services/
│   ├── importer.py       ← Import file Excel/CSV
│   ├── normalizer.py     ← Pulizia dati
│   ├── classifier.py     ← Classificazione AI Claude
│   ├── clustering.py     ← Gestione cluster
│   └── reporter.py       ← Generazione report
├── providers/            ← News source providers
│   ├── base.py          ← Interfaccia astratta
│   └── mock.py          ← Provider mock per test
└── templates/           ← HTML Jinja2 templates
    ├── base.html        ← Layout principale
    ├── index.html       ← Dashboard
    ├── upload.html      ← Upload file
    ├── companies.html   ← Gestione aziende
    ├── clusters.html    ← Configurazione cluster
    ├── news.html        ← Visualizza notizie
    ├── reports.html     ← Genera report
    └── settings.html    ← Impostazioni
```

### Aggiungere una nuova pagina

1. **Crea template HTML** in `app/templates/nuova_pagina.html`
   - Estendi `base.html`
   - Usa lo stesso CSS e struttura

2. **Aggiungi endpoint** in `app/main.py`
   ```python
   @app.get("/nuova-pagina", response_class=HTMLResponse)
   def nuova_pagina(request: Request):
       return templates.TemplateResponse("nuova_pagina.html", {"request": request})
   ```

3. **Aggiungi link nel menu** in `app/templates/base.html`
   ```html
   <a href="/nuova-pagina">📌 Nuova pagina</a>
   ```

4. **Test e commit**

### Aggiungere una nuova API

1. **Aggiungi endpoint** in `app/main.py`
   ```python
   @app.post("/api/azione")
   def azione(param1: str, db: Session = Depends(get_db)):
       # Logica qui
       return {"result": "ok"}
   ```

2. **Testa via curl**
   ```bash
   curl -X POST "http://localhost:8001/api/azione?param1=value"
   ```

3. **Commit e push**

### Aggiungere una nuova funzionalità nei services

1. **Crea o modifica file** in `app/services/`
2. **Importa in main.py**
   ```python
   from app.services.nuovo_servizio import NuovoServizio
   ```
3. **Usa nell'endpoint**
   ```python
   servizio = NuovoServizio()
   risultato = servizio.metodo()
   ```
4. **Testa e commit**

### Aggiungere test per nuove funzioni

1. **Crea file test** in `tests/test_nuova_funzione.py`
   ```python
   import pytest
   from app.services.nuova_funzione import NuovaFunzione

   def test_funzione():
       func = NuovaFunzione()
       result = func.metodo()
       assert result is not None
   ```

2. **Esegui test**
   ```bash
   pytest tests/test_nuova_funzione.py -v
   ```

3. **Commit con test**

### Checklist prima di pushare

- [ ] App avviata senza errori
- [ ] Nuove funzioni testate manualmente
- [ ] Test suite passa (`pytest tests/`)
- [ ] Nessun warning nei log
- [ ] Browser aperto a http://localhost:8001
- [ ] Modifiche testate sul browser
- [ ] Git status clean (`git status`)
- [ ] Commit message descrittivo
- [ ] Push eseguito (`git push`)
- [ ] Versione app aggiornata se la modifica è una release (vedi sotto)

### Versionamento

L'unica fonte di verità per la versione dell'app è `__version__` in `app/__init__.py`.
Viene mostrata automaticamente in Impostazioni (`/settings`) e nella risposta di
`GET /api/health`, quindi basta aggiornarla in un solo posto.

Ad ogni modifica rilevante (nuova funzionalità, fix importante):

1. Apri `app/__init__.py` e incrementa `__version__` seguendo [semver](https://semver.org/lang/it/):
   - `MAJOR` per cambi che rompono compatibilità
   - `MINOR` per nuove funzionalità retrocompatibili
   - `PATCH` per bug fix
2. Aggiungi una riga in cima al `CHANGELOG.md` con versione, data e riepilogo.
3. Fai commit di entrambi i file insieme alla modifica.

```bash
# Esempio
# app/__init__.py: __version__ = "0.2.0" -> "0.2.1"
git add app/__init__.py CHANGELOG.md
git commit -m "Bump version to 0.2.1 - fix XYZ"
```

## Testing

```bash
pytest tests/
```

## Licenza

MIT
