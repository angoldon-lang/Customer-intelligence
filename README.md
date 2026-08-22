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

La dashboard è completamente funzionante con **6 pagine principali**:

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
- Filtri per stato (Active, Paused, Needs Review, Archived)
- Visualizza sito web, email, account owner
- Edit aziende (Fase 2)
- Delete aziende (Fase 2)

### 📈 Configurazione cluster
- **Crea cluster manualmente** con frequenza e filtri rilevanza
- **Crea cluster automaticamente** da:
  - Account Owner
  - Tipo azienda (Cliente, Fornitore, etc.)
  - Settore (Codice Ateco)
- Aggiungi/rimuovi destinatari email
- Visualizza aziende associate

### 📰 Gestione notizie
- Tabella notizie con filtri:
  - **Status**: Nuove, Approvate, Rifiutate, Da verificare
  - **Categoria**: Investment, M&A, Cybersecurity, IT/Digital, etc.
  - **Rilevanza minima**: 1-10
- Visualizza source, data, categoria
- Approva/rifiuta notizie (Fase 2)
- Link diretto all'articolo

### 📧 Report email
- **Genera report** per cluster selezionato
- Scegli giorni da includere (1-90)
- Anteprima report HTML
- Status: Draft, Pending Approval, Sent
- Invio email (Fase 3)
- Storico report completo

### ⚙️ Impostazioni
- Configurazione **API Claude**
- Configurazione **SMTP** (Gmail, Outlook, etc.)
- **Scheduler** monitoraggio automatico
- **Filtri di default** aziende e notizie
- Info sistema (versione, database, roadmap)

## Roadmap

### Fase 1 - MVP (in progress)
- [x] Struttura progetto
- [ ] Database e modelli
- [ ] Import Excel/CSV
- [ ] CRUD aziende e cluster
- [ ] Provider news mock
- [ ] Classificazione AI base
- [ ] Generazione report draft
- [ ] Dashboard minimale

### Fase 2 - Ricerca reale
- [ ] Provider web reale
- [ ] RSS feed
- [ ] Deduplica notizie
- [ ] Scoring AI completo
- [ ] Scheduler di monitoraggio

### Fase 3 - Automazione
- [ ] Invio email automatico
- [ ] Approvazione report
- [ ] Alert critici
- [ ] Report per account owner

### Fase 4 - Fonti premium
- [ ] Source connector layer completo
- [ ] Integrazione API autorizzate
- [ ] Gestione access_status e license_scope

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

## Testing

```bash
pytest tests/
```

## Licenza

MIT
