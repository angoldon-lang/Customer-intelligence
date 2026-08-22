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

## Testing

```bash
pytest tests/
```

## Licenza

MIT
