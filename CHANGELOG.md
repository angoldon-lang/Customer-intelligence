# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue [Keep a Changelog](https://keepachangelog.com/) e il progetto
usa [Semantic Versioning](https://semver.org/lang/it/).

## [0.3.1] - 2026-08-22

### Fixed
- **GDELT 429 "Too Many Requests"**: nessuna pausa tra le richieste faceva
  saturare quasi subito il rate limit gratuito di GDELT su anagrafiche
  grandi, azzerando i risultati per (quasi) tutte le aziende dopo le prime.
  Aggiunto un ritmo minimo tra le richieste (~1.2s) e un circuit breaker:
  su un 429 persistente, GDELT viene disattivato per il resto del run
  invece di continuare a martellarlo per ogni azienda restante.
- **`Esegui monitoraggio ORA` non si fermava con Ctrl+C**: essendo una
  richiesta HTTP sincrona, interrompere il server con Ctrl+C annullava solo
  la risposta HTTP, non il thread che eseguiva davvero la ricerca - che
  continuava a girare "orfano" in background (visibile dai log GDELT che
  continuavano a comparire anche dopo "Finished server process"). Ora
  `POST /api/monitoring/run-now` avvia il run su un thread background e
  risponde subito; lo stato/risultato si segue da Impostazioni (polling di
  `GET /api/monitoring/status`, che ora espone anche `run_in_progress`).
  Un secondo run richiesto mentre uno è già in corso risponde 409 invece di
  accodarsi silenziosamente.

## [0.3.0] - 2026-08-22

### Added
- Ricerca notizie reale multi-provider: GDELT (gratuito, sempre attivo),
  GNews.io (opzionale, richiede `GNEWS_API_KEY`) e RSS di fonti ufficiali
  (configurabili da Impostazioni → "Fonti notizie" o via `/api/news-sources`).
- Deduplica delle notizie per URL, tra provider diversi e contro il database,
  prima di passarle a Claude.
- Gating delle aziende ambigue (nome generico senza sito web/P.IVA): non
  vengono più cercate alla cieca, ma contate separatamente in
  `companies_needing_enrichment` finché non vengono arricchite.
- Disambiguazione in Claude: sito web e P.IVA/codice fiscale vengono passati
  come contesto per abbassare `confidence_score` quando una notizia
  potrebbe riferirsi a un omonimo, invece di scartarla in silenzio.
- Schedulazione a livelli basata sulla frequenza dei cluster (`daily`,
  `2-3x_week`, `weekly`, `monthly`): ogni azienda eredita la frequenza più
  alta tra i cluster a cui appartiene; un limite `MAX_COMPANIES_PER_RUN`
  protegge run e quota API quando l'anagrafica è molto grande.
- Nuovo campo `Company.last_monitored_at` con migrazione additiva
  automatica all'avvio (nessuna perdita di dati sulle aziende esistenti).
- Endpoint `GET /api/monitoring/providers` e CRUD `/api/news-sources` per
  gestire le fonti RSS.

### Fixed
- `NewsClassifier.classify_news()` ora accetta gli argomenti realmente
  passati dal resto della pipeline (bug che azzerava sempre le notizie
  salvate).
- `NewsItem.source_type`, `access_status` e `license_scope` vengono ora
  effettivamente salvati (prima restavano sempre ai valori di default).
- **Bug critico**: tutte le pagine (dashboard, upload, aziende, cluster,
  notizie, report, impostazioni) potevano rispondere 500 "unhashable type:
  dict" a seconda della versione di `starlette` installata. Causa reale:
  `main.py` chiamava `TemplateResponse(nome, contesto)` (stile vecchio),
  ma le versioni recenti di starlette richiedono
  `TemplateResponse(request, nome, contesto)` - con la chiamata vecchia gli
  argomenti finiscono scambiati e il dizionario di contesto viene usato come
  nome del template, mandando in crash la cache interna di Jinja2. Risolto
  con un helper `render()` che rileva automaticamente quale firma è
  installata, così l'app funziona con entrambe le versioni. Era la causa
  dell'errore che aveva già colpito `/monitoring` in una versione precedente.
- **Import Excel/CSV**: `_remove_duplicate_headers` confrontava ogni riga
  con la prima riga del file invece che con i nomi delle colonne - la prima
  riga risultava sempre "uguale a se stessa" e veniva scartata, perdendo
  silenziosamente la prima azienda di ogni import.
- **Import Excel/CSV**: le celle vuote diventavano la stringa letterale
  `"nan"` invece di essere vuote (es. sito web salvato come `"https://nan"`,
  P.IVA come `"nan"`), sporcando i dati e vanificando il gating sulle
  aziende ambigue introdotto in questa stessa versione. Corretto leggendo i
  file con `dtype=str` e gestendo esplicitamente i valori mancanti; risolve
  anche la troncatura/notazione scientifica di P.IVA numeriche lette come
  float da pandas.

## [0.2.0] - 2026-08-22

### Fixed
- Il monitoraggio notizie salvava sempre 0 notizie: la chiamata a
  `NewsClassifier.classify_news()` passava argomenti sbagliati e falliva
  silenziosamente per ogni articolo trovato.
- `NewsClassifier` ora usa una classificazione neutra di default quando non è
  configurata una API key Claude, invece di sollevare un errore.
- `TestNewsProvider` esportato correttamente da `app/providers/__init__.py`.
- Lo scheduler ora si ferma con `wait=False` e viene fermato esplicitamente
  allo shutdown dell'app, per evitare che `Ctrl+C` resti bloccato.
- Rimossa la ricerca su Google News (bloccata da restrizioni di rete/proxy),
  sostituita dal provider di test per lo sviluppo.

### Added
- Numero di versione dell'app centralizzato in `app/__init__.py`, esposto via
  `GET /api/health` e mostrato in `/settings`.
- `CHANGELOG.md` e istruzioni di versionamento nel README.

## [0.1.0] - MVP iniziale

- Prima versione funzionante: import Excel/CSV, gestione aziende e cluster,
  ricerca e classificazione notizie, generazione e invio report email,
  scheduler di monitoraggio, dashboard completa a 6 pagine.
