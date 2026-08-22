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

## Quick start

1. **Clone e setup**
   ```bash
   git clone <repo>
   cd Customer-intelligence
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Database**
   ```bash
   python -c "from app.database import init_db; init_db()"
   ```

3. **Configurazione**
   - Copiare `.env.example` a `.env`
   - Impostare `CLAUDE_API_KEY` per classificazione AI

4. **Avvio**
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Accesso dashboard**
   - http://localhost:8000

## Workflow

1. Import Excel/CSV anagrafica
2. Pulizia e normalizzazione dati
3. Creazione cluster automatici
4. Configurazione destinatari report
5. Ricerca notizie per azienda
6. Classificazione AI
7. Generazione report draft
8. Approvazione e invio

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
