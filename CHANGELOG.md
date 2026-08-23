# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue [Keep a Changelog](https://keepachangelog.com/) e il progetto
usa [Semantic Versioning](https://semver.org/lang/it/).

## [0.6.0] - 2026-08-23

Revisione globale del codice concentrata su ricerca e visualizzazione notizie.

### Fixed
- **LA causa per cui "le notizie non si vedono"**: se la classificazione AI
  falliva, la notizia veniva **scartata** (`continue`) invece di essere
  salvata. Nell'ultimo run dell'utente questo ha buttato via ~100 articoli
  italiani reali e pertinenti, già trovati correttamente dai provider.
  Ora una notizia non viene MAI persa per un errore dell'AI: viene salvata
  con una classificazione neutra, marcata `Needs Review` e categoria
  "Da classificare", e resta visibile in pagina Notizie.
- Aggiunto il pulsante **"↻ Riclassifica"** (e `POST /api/news/{id}/reclassify`)
  per rilanciare la classificazione AI sulle notizie salvate senza, una volta
  sistemata la configurazione Claude.
- **`/api/news` non restituiva `url`**: tutti i link "Fonte" e "→ Leggi" nella
  pagina Notizie puntavano a `undefined`. Aggiunti anche `summary`,
  `published_date` e `confidence_score`, ora mostrati nella scheda notizia.
- **Un singolo punteggio nullo faceva sparire TUTTE le notizie**:
  `n.relevance_score.toFixed(1)` sollevava un TypeError che interrompeva il
  rendering dell'intera lista. Ora ogni campo è protetto.
- **L'invio report andava sempre in errore**: usava `report.html_content` /
  `report.text_content`, campi inesistenti (nel modello sono `body_html` /
  `body_text`) - AttributeError garantito ad ogni invio.
- **L'anteprima report non funzionava**: `viewReport('${r.id}')` passava una
  stringa confrontata con `===` contro un id numerico, quindi non trovava mai
  il report; e mostrava comunque solo un placeholder. Ora c'è
  `GET /api/reports/{id}` e l'anteprima renderizza l'HTML reale in un iframe.
- **I report escludevano silenziosamente le notizie senza data di
  pubblicazione** (frequente: GDELT e vari RSS non la forniscono): il
  confronto con `published_date` NULL è NULL, quindi l'articolo spariva. Ora
  si usa `COALESCE(published_date, created_at)`.
- `/api/reports` non restituiva `created_at` (la colonna "Data creazione"
  mostrava la fine periodo).
- `/api/news` restituiva come `total` il numero di elementi già limitati dal
  `limit`, non il totale reale (contatore dashboard sbagliato).
- `/api/health` controllava solo `CLAUDE_API_KEY`, ignorando
  `ANTHROPIC_API_KEY` benché supportata ovunque.

### Added
- **Controllo versione SDK all'avvio**: se la libreria `anthropic` installata
  è troppo vecchia per la Messages API, ora l'app lo dice a caratteri cubitali
  all'avvio e in Impostazioni, invece di fallire silenziosamente una volta per
  articolo. Aggiunta la riga "SDK anthropic" in Info sistema.
- GDELT: intervallo minimo tra richieste alzato da 1.2s a 5s e backoff da 20s
  a 30s (nei log dell'utente il rate limit scattava comunque quasi subito).

## [0.5.1] - 2026-08-23

### Fixed
- **Bug critico che rompeva SEMPRE la classificazione AI**: `requirements.txt`
  pinnava `anthropic==0.7.1`, una versione della SDK precedente
  all'introduzione della Messages API - ha solo `client.completions`, non
  `client.messages`, da cui l'errore `'Anthropic' object has no attribute
  'messages'` su ogni singola notizia trovata. Aggiornato a `anthropic==1.0.0`.
- Il modello Claude usato per la classificazione (`claude-3-5-sonnet-20241022`)
  è una snapshot ormai ritirata; aggiornato a `claude-sonnet-5` (il livello
  Sonnet corrente, coerente con la scelta originale di un modello economico
  per un volume alto di classificazioni).
- **Bug critico separato, probabilmente la causa reale per chi aveva già
  configurato la chiave**: `Anthropic()` veniva istanziato senza argomenti,
  che legge automaticamente solo la variabile nativa della SDK
  `ANTHROPIC_API_KEY` - ma le nostre istruzioni di setup (`.env.example`,
  README, pagina Impostazioni) dicono di usare `CLAUDE_API_KEY`. Chi aveva
  configurato solo quella non stava mai autenticando davvero. Ora la chiave
  viene passata esplicitamente al client.
- Aggiunto `thinking: disabled` alle chiamate di classificazione (compito
  semplice e strutturato, il thinking adattivo di default su Sonnet 5
  aggiungeva solo costo/latenza) ed estrazione del testo dalla risposta resa
  robusta all'ordine dei blocchi restituiti.

## [0.5.0] - 2026-08-22

### Added
- **Pagina "🔎 Copertura ricerca"** (`/coverage`): per ogni azienda mostra
  quando è stata cercata l'ultima volta, se sono state trovate notizie e se
  no perché (nessun risultato genuino, fonte bloccata/rate-limited, errore,
  saltata perché ambigua, o mai cercata), con il dettaglio per-provider
  (es. "google_news_rss:0, gdelt:blocked, rss:2"). Storico persistito nella
  nuova tabella `search_logs`, un record per azienda per run.
- **Gestione cluster manuale completa**, prima mancante quasi del tutto:
  - Aggiungere/rimuovere aziende da un cluster (nel modale "Dettagli")
  - Eliminare un cluster
  - Vedere ed eliminare i destinatari email (prima la lista era hardcoded a
    "nessun destinatario" anche quando ce n'erano già di salvati)
- **"Approva"/"Rifiuta" nella pagina Notizie** ora aggiornano davvero lo
  stato della notizia invece di mostrare un alert placeholder.
- **"Modifica"/"Elimina" nella pagina Aziende** ora salvano/cancellano
  davvero invece di mostrare un alert placeholder.
- **"Test API" e "Test SMTP"** in Impostazioni ora eseguono un controllo
  reale (una chiamata minima a Claude / un tentativo di connessione SMTP)
  invece di mostrare un alert placeholder.

### Fixed
- **Bug di visibilità critico**: quando GDELT/Google News RSS fallivano
  (rate limit, blocco, errore di rete) PRIMA che il circuit breaker
  scattasse (il primo di due tentativi falliti), il fallimento veniva
  etichettato silenziosamente come "0 risultati trovati" - indistinguibile
  da "il provider ha davvero cercato e non ha trovato nulla". Ora ogni
  provider espone l'esito reale dell'ultima chiamata, visibile nella nuova
  pagina Copertura ricerca invece di sparire nei log del terminale.
- Filtro stato azienda nella pagina Aziende (e la select di modifica)
  usava valori in inglese (`Active`/`Paused`/`Archived`) che non hanno mai
  corrisposto ai valori reali salvati in italiano (`Attiva`/`Pausa`) dal
  resto del sistema (import, scheduler, filtri di Impostazioni) - il filtro
  non poteva mai funzionare.
- `EmailSender`/Test SMTP non avevano un timeout sulla connessione: con
  host SMTP irraggiungibile o rete bloccata, la richiesta restava sospesa
  a tempo indeterminato invece di fallire con un errore. Ora c'è un
  timeout di 15s.

## [0.4.0] - 2026-08-22

### Added
- **Google News RSS come nuova fonte** (`app/providers/google_news_rss.py`),
  gratuita e senza chiave API: usa il feed RSS pubblico di ricerca
  (`news.google.com/rss/search`), non la pagina HTML già bloccata in
  precedenza da un consent-wall/proxy. Ha in genere una copertura molto
  migliore di GDELT/GNews per piccole aziende italiane locali, che i grandi
  aggregator spesso non indicizzano. Attiva di default
  (`GOOGLE_NEWS_RSS_ENABLED=True`), con lo stesso ritmo/circuit-breaker di
  GDELT per evitare blocchi.
- `POST /api/monitoring/run-now?limit=N` per testare il monitoraggio su un
  numero ridotto di aziende senza modificare `.env` e riavviare - anche da
  Impostazioni con il nuovo campo "Limita a N aziende".
- `POST /api/admin/cleanup` (bottone "🧹 Pulisci database" in Impostazioni,
  ora funzionante): rimuove notizie non approvate/inviate più vecchie di
  180 giorni e lo storico monitoraggi oltre lo stesso periodo.
- `POST /api/admin/reset` (bottone "🔄 Reset sistema", ora funzionante):
  cancella tutti i dati (aziende, cluster, notizie, report, fonti) tenendo
  lo schema del database intatto. Irreversibile, richiede `confirm=RESET`
  e doppia conferma lato browser.

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
