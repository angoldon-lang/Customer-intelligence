# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue [Keep a Changelog](https://keepachangelog.com/) e il progetto
usa [Semantic Versioning](https://semver.org/lang/it/).

## [0.17.0] - 2026-08-27

### Added
- **Log delle ricerche in Impostazioni**: l'esito di ogni azienda a ogni
  ricerca — cosa e' stato trovato, con quali fonti, e l'errore quando
  qualcosa non ha funzionato. Righe colorate per esito, conteggi per stato,
  filtro per azienda e per esito, piu' lo **storico dei monitoraggi**
  (quando, quante aziende, quante notizie, quanti errori, durata).
- **Download CSV** del log ricerche e dello storico monitoraggi
  (`GET /api/logs/export`). Generato con il modulo `csv`, non concatenando
  stringhe: nomi azienda e messaggi d'errore contengono punti e virgola,
  virgolette e a capo che romperebbero un file costruito a mano. Il BOM
  iniziale fa aprire il file a Excel in UTF-8, senza accenti corrotti.

### Changed
- **Interfaccia rifatta.** Sistema di token (colori, spaziature, ombre) in
  un solo punto invece di valori sparsi pagina per pagina, tipografia e
  gerarchie riviste, tabelle e form piu' leggibili, barra laterale
  raggruppata per aree (Anagrafica / Intelligence / Sistema).
- **Icone SVG al posto delle emoji.** Le emoji cambiavano aspetto su ogni
  sistema, non prendevano il colore del testo e non si allineavano al
  testo. Ora sono simboli vettoriali definiti una volta sola e riusati:
  restano nitidi a qualsiasi dimensione ed ereditano il colore.
- I menu a tendina fuori dai `form-group` restavano quelli grezzi del
  browser accanto a quelli formattati: ora ogni controllo ha lo stesso
  aspetto, freccia inclusa.
- I pulsanti che sono link (`<a class="btn">`) non compaiono piu'
  sottolineati.
- Corretti gli accenti in alcuni messaggi ("perche'" -> "perché",
  "gia'" -> "già", "piu'" -> "più").

## [0.16.0] - 2026-08-26

### Fixed
- **Una notizia cancellata tornava alla ricerca successiva.** La deduplica
  guardava solo la tabella delle notizie: cancellandone una, il run dopo la
  trattava come nuova, la rimetteva in archivio e **la faceva riclassificare
  a Claude una seconda volta**. Ora un registro delle notizie gia' viste
  sopravvive alla cancellazione, e il controllo avviene **prima** della
  classificazione, quindi non consuma crediti.
  Il registro riconosce anche la stessa notizia ripresa da un'altra testata
  (stesso titolo, URL diverso), va per azienda (due clienti possono
  legittimamente comparire nello stesso articolo) e viene alimentato anche
  al momento della cancellazione, cosi' copre le notizie salvate prima di
  questa versione.
  Via d'uscita se cancelli per sbaglio: **Impostazioni > Manutenzione >
  "Dimentica notizie cancellate"**. Si disattiva con
  `REMEMBER_DELETED_NEWS=False`.
- **Le fonti cercavano su periodi diversi**: 30 giorni Google News e
  APITube, **3 mesi** GDELT. Ora la finestra e' una sola per tutte.

### Added
- **Finestra di ricerca configurabile** (`NEWS_SEARCH_DAYS`, 30 giorni di
  default) da Impostazioni. GDELT viene troncato a 90 giorni, che e' il
  limite del suo servizio. Allargarla costa poco dopo la prima ricerca: le
  notizie gia' viste vengono saltate senza essere riclassificate.
- **Personalizzazione del report** in Impostazioni:
  - **logo aziendale** (PNG/JPG/GIF, max 1 MB), allegato alla mail come
    immagine inline con `Content-ID`. Non un `data:` URI ne' un link al
    server locale: Gmail scarta le immagini `data:` e un indirizzo
    `127.0.0.1` e' irraggiungibile per chi riceve la mail;
  - **colore dell'intestazione**, accettato solo se esadecimale, visto che
    finisce dritto nel CSS della mail;
  - **titolo, testo di apertura e piè di pagina**;
  - **punteggi mostrabili o nascondibili**, per una mail piu' sintetica
    verso destinatari esterni;
  - **anteprima** che apre il report reale con la personalizzazione
    applicata, invece di doverlo indovinare.

## [0.15.0] - 2026-08-25

### Added
- **Azioni massive nella pagina Aziende**: checkbox su ogni riga,
  "seleziona tutte le visibili" (rispetta i filtri attivi) e barra azioni:
  - **metti in pausa / riattiva / archivia** un gruppo di aziende;
  - **aggiungi a un cluster** in blocco, che e' il modo rapido di sistemare
    le "aziende senza cluster" segnalate dalla guida al flusso settimanale;
  - **elimina** in blocco, con le notizie collegate.
  La conferma dice sempre la conseguenza ("NON verranno piu' cercate
  notizie"), non solo quante righe cambiano.
- Nella tabella ogni azienda non attiva e' marcata **"non monitorata"** ed
  e' resa in grigio: lo stato non e' piu' un'etichetta da interpretare.

### Verificato
- **Un'azienda in "Pausa" non viene cercata.** Vale anche per "Archiviata"
  e "Needs Review": solo "Attiva" entra nel monitoraggio. Il comportamento
  era gia' corretto, ora e' fissato da test propri, incluso il passaggio
  pausa -> riattivazione, cosi' non puo' rompersi in silenzio.

## [0.14.0] - 2026-08-25

### Fixed
- **Il link nel report portava a una pagina XML.** Gli id degli articoli di
  Google News sono sempre piu' spesso blob opachi che non contengono l'URL
  dell'editore, e il percorso `/rss/` su cui stanno serve XML grezzo
  ("Questo feed non e' disponibile") invece di reindirizzare. Il decoder
  faceva bene a fallire, ma senza titolo restituiva comunque il link rotto:
  meglio nessun link che uno che si sa non funzionare. Ora il report
  risolve il link **al momento della generazione**, quindi funziona anche
  per le notizie salvate prima della correzione, senza dover lanciare la
  manutenzione.
- **Titoli e testi non venivano messi in sicurezza nella mail**: arrivano
  da feed di terze parti e finivano nell'HTML cosi' com'erano.

### Added
- **Link evidente nella mail**: il titolo e' cliccabile e sotto c'e' un
  pulsante "Leggi l'articolo →". Prima l'unico link era il nome della fonte
  in piccolo.
- **Due o tre righe di testo sotto ogni titolo**, con la sintesi
  dell'articolo e il "perche' e' importante" del classificatore.
- `why_it_matters` e `suggested_action` ora vengono **salvati**: il
  classificatore li produceva a ogni notizia e venivano scartati. Il
  "perche' e' importante" compare anche nella card della pagina Notizie.
  La colonna viene aggiunta al database automaticamente all'avvio.

## [0.13.0] - 2026-08-25

### Fixed
- **Notizie che non parlano affatto dell'azienda finivano nel flusso.**
  Google News allarga da solo una query tra virgolette quando trova pochi
  risultati, quindi cercando `"CMC RAVENNA SPA"` restituiva cronaca locale
  su cantieri e viabilita' che non nomina mai CMC.
  Il classificatore riceveva gia' l'istruzione di abbassare
  `confidence_score` per gli omonimi, e il punteggio veniva salvato... e
  **ignorato**: nessuna decisione lo leggeva. Ora:
  - al classificatore viene chiesto un verdetto esplicito
    (`is_about_company`) e viene detto se il nome dell'azienda compare
    davvero nel titolo o nello snippet;
  - una notizia giudicata non pertinente viene salvata come **Rifiutata**
    invece che come nuova: resta visibile con il filtro "Rifiutate",
    recuperabile e cancellabile in blocco, ma non entra nei report;
  - il conteggio compare nel log del run, cosi' il filtro non agisce in
    silenzio;
  - si disattiva con `AUTO_REJECT_OFF_TOPIC=False`.
- Il controllo sul nome ora richiede **tutte** le parole distintive: prima
  il classificatore gratuito si accontentava di una sola, quindi qualsiasi
  articolo su Ravenna sembrava una notizia su "CMC RAVENNA SPA". Le forme
  societarie (SPA, SRL, Group...) non contano come corrispondenza.

### Added
- **"Rivedi notizie non pertinenti"** in Impostazioni > Manutenzione: passa
  in rassegna l'archivio esistente e trova le notizie in cui l'azienda non
  e' mai nominata. Il controllo e' testuale, **non consuma crediti**.
  Mostra prima un'anteprima con esempi e sposta in "Rifiutate" solo dopo
  conferma; le notizie gia' approvate o rifiutate a mano non vengono
  toccate.

## [0.12.1] - 2026-08-25

### Fixed
- **Sommari con HTML grezzo nelle card** (`<a href="https://news.google.com/
  rss/articles/CBMixgF...`). La pulizia toglieva i tag completi, ma quando
  il testo arrivava **troncato a meta' tag** mancava il `>` di chiusura e
  la regex non trovava nulla: il markup finiva integro nella pagina. Ora il
  frammento pendente viene rimosso, e un sommario che si riduce al solo
  link viene scartato invece di essere mostrato.
  Anche **"Correggi link notizie"** in Impostazioni ora ripara davvero
  questi record: prima usava la stessa pulizia difettosa.
- **La card sfondava la larghezza della pagina**: gli id base64 di Google
  News sono una stringa unica senza spazi, che allargava la card e spingeva
  i pulsanti fuori dallo schermo. Ora il testo va a capo e un sommario
  troppo lungo viene contenuto in altezza.
- La pagina Notizie **ripulisce il sommario anche in visualizzazione**, cosi'
  i record salvati male restano leggibili senza dover prima lanciare la
  manutenzione.

## [0.12.0] - 2026-08-25

### Added
- **Fonti notizie gestibili da Impostazioni**: ogni fonte si attiva o
  disattiva con un click e si riordina con ▲▼. L'ordine e' quello con cui
  vengono effettivamente interrogate, quindi puoi mettere per prime quelle
  che rendono di piu' sulla tua anagrafica senza toccare il `.env`
  (`PROVIDER_ORDER`, `POST /api/monitoring/providers/order`).
  Una fonte non elencata nell'ordine viene comunque interrogata, per ultima:
  aggiungerne una in futuro non la disattiva per sbaglio.
- **Guida al flusso settimanale** in Copertura ricerca
  (`GET /api/workflow/status`): sei controlli che rispondono a una sola
  domanda — "se non faccio altro, la settimana prossima il report parte da
  solo?". Per ogni passaggio mancante dice cosa fare e porta alla pagina
  giusta: aziende importate, ricerca automatica attiva, notizie da
  approvare, aziende senza cluster, cluster senza destinatari, SMTP.
- **Approvazione rapida per azienda** dalla Copertura
  (`POST /api/workflow/approve-company/{id}`): un click approva tutte le
  notizie in attesa di quell'azienda, senza aprire la pagina Notizie e
  spuntarle una a una. La colonna "Da approvare" mostra dove serve.

### Fixed
- **Lo scheduler non sopravviveva al riavvio del server**: nulla lo
  riavviava all'avvio, quindi "Avvia scheduler" durava fino al primo
  riavvio e poi il monitoraggio si fermava in silenzio. Ora la scelta e'
  salvata nel database e lo scheduler riparte da solo.
- **L'intervallo veniva richiesto a ogni avvio** con un popup. Ora usa il
  valore del campo "Intervallo automatico", che viene ricordato.
- Lo stato mostra **quando e' prevista la prossima ricerca**, non solo che
  lo scheduler e' acceso.
- **`interval_hours=0` veniva sostituito silenziosamente con 24**: essendo
  falsy scivolava oltre il controllo di validita'. Ora un intervallo fuori
  scala (0, o oltre 168 ore) viene rifiutato con un messaggio.

## [0.11.0] - 2026-08-24

### Added
- **Provider APITube** (`app/providers/apitube.py`). A differenza delle
  fonti gratuite restituisce articoli arricchiti (`description` + `body`,
  dominio e rank della fonte, sentiment, entita'), quindi e' la base per la
  rassegna stampa. Essendo a consumo, e' costruito per spendere poco:
  - interrogato **solo per le aziende su cui le fonti gratuite non hanno
    trovato nulla** (`APITUBE_FALLBACK_ONLY`), cioe' dove una ricerca a
    pagamento ha davvero senso;
  - **tetto di richieste per run** (`APITUBE_MAX_REQUESTS_PER_RUN`, 25 di
    default): senza, un solo giro su 194 aziende esaurirebbe una chiave di
    prova;
  - si disattiva per il resto del run su chiave non valida (401/403) o
    quota finita (402/429), invece di continuare a chiamare;
  - il nome azienda e' cercato come frase esatta, altrimenti "Sag Tubi
    Tredozio" troverebbe articoli con quelle parole sparse.
- Nuovo attributo `fallback_only` sui provider: il searcher salta le fonti
  che lo dichiarano quando le altre hanno gia' trovato qualcosa.
- **Preset SMTP per Gmail e Microsoft 365** in Impostazioni, che compilano
  server, porta e cifratura, e selettore STARTTLS / SSL.

### Fixed
- **La porta SMTP 465 non poteva funzionare**: il codice chiamava sempre
  `starttls()`, ma la 465 parla TLS dal primo byte e richiede `SMTP_SSL`.
  Chi la impostava otteneva un timeout inspiegabile. Ora la modalita' e'
  scelta dalla porta (o forzata con `SMTP_USE_SSL`), e i server senza
  STARTTLS non mandano piu' in errore la connessione.
- **Errori SMTP incomprensibili**: `(535, b'5.7.8 Username and Password not
  accepted')` mandava a reimpostare una password che non era il problema.
  Ora il messaggio dice cosa fare davvero, distinguendo Gmail (serve la
  password per le app, non quella dell'account), Microsoft 365 (serve che
  un amministratore abiliti SMTP AUTH sulla casella), mittente rifiutato,
  porta/cifratura sbagliate, host inesistente e timeout.
- **Configurazione SMTP incompleta**: si tentava comunque la connessione,
  fallendo in modo oscuro. Ora dice subito quale campo manca.
- Il pulsante **Test SMTP** prova la configurazione a schermo invece
  dell'ultima salvata: non serve piu' salvare a ogni tentativo.

## [0.10.0] - 2026-08-24

### Added
- **Autenticazione con un amministratore.** Fino a ieri chiunque potesse
  raggiungere la porta dell'app vedeva l'anagrafica clienti: ora ogni
  pagina e ogni endpoint richiedono una sessione.
  - **Primo avvio**: l'app apre `/setup` e chiede di creare l'utente. Non
    esiste una password predefinita, quindi non c'e' nessuna finestra in
    cui la dashboard e' raggiungibile con credenziali note; una volta
    creato l'amministratore la pagina di setup si chiude per sempre.
  - **Password** salvata solo come hash PBKDF2-SHA256 con salt per
    password (240.000 iterazioni), mai in chiaro e mai nel `.env`.
    Minimo 10 caratteri.
  - **Sessione** in un cookie firmato HMAC-SHA256, `HttpOnly` e
    `SameSite=Lax`, con scadenza (12h di default, `SESSION_TTL_HOURS`).
    `SESSION_COOKIE_SECURE=True` per servire l'app in HTTPS.
  - **Blocco anti-forza-bruta**: dopo 8 tentativi falliti il login resta
    chiuso 5 minuti. Il messaggio d'errore non rivela mai se ad essere
    sbagliato fosse l'utente o la password.
  - **Cambio password** da Impostazioni: richiede quella attuale e
    **disconnette tutte le altre sessioni** (il segreto di firma viene
    rigenerato), mantenendo attiva solo quella che ha fatto la modifica.
  - Le API rispondono `401` in JSON invece di un redirect, e la dashboard
    riporta da sola al login quando la sessione scade.
  - Nessuna nuova dipendenza: tutto con la libreria standard, quindi
    aggiornare resta un semplice `git pull`.

### Security
- Le credenziali non passano dal form generico delle impostazioni e non
  compaiono in `GET /api/settings`: si scrivono solo dagli endpoint
  dedicati, che verificano la password attuale.
- `?next=` dopo il login accetta solo percorsi interni, cosi' un link
  costruito ad arte non puo' rimbalzare altrove subito dopo l'accesso.

## [0.9.1] - 2026-08-23

### Fixed
- **"database is locked" salvando dalla dashboard durante un monitoraggio**
  (destinatari, cluster, impostazioni). Il run scriveva tutto in un'unica
  transazione aperta dall'inizio alla fine: su un'anagrafica grande sono
  decine di minuti in cui SQLite blocca qualsiasi altra scrittura. Tre
  correzioni:
  - **commit per azienda** invece di uno solo a fine run, e **commit per
    notizia** invece di un flush: prima il lock restava preso anche durante
    ogni chiamata di classificazione a Claude;
  - **journal WAL** attivo, cosi' la dashboard continua a leggere mentre il
    monitoraggio scrive;
  - **busy timeout a 30s** (il default e' 5s): una scrittura concorrente
    aspetta il suo turno invece di fallire subito.
- **Rete assente: 60s persi per ogni azienda.** Un errore di connessione
  (DNS/proxy/offline) ora ha un solo retry rapido invece della scala
  completa 5s/15s/40s, che resta per timeout ed errori HTTP temporanei.
- **Retry inutili durante un blocco di Google News.** Se anche l'azienda
  precedente ha fallito, Google sta limitando sistematicamente e ritentare
  ogni azienda per un minuto ritarda soltanto la pausa: la prima azienda usa
  la scala completa, le successive un solo tentativo rapido. La pausa inoltre
  **raddoppia** a ogni blocco consecutivo (180s, 360s, ... fino a 30 minuti)
  invece di riprovare ogni 3 minuti per tutto il run, e si riazzera appena
  una ricerca va a buon fine.
- **`[GNews] Quota/auth error (403)` era fuorviante**: un 403/401 e' la
  chiave `GNEWS_API_KEY` non valida, non la quota esaurita (che e' il 429).
  Ora il log dice quale dei due e'.
- **Invio report senza destinatari**: rispondeva `400 Bad Request` senza
  spiegazione. Ora il messaggio dice quale cluster e dove aggiungerli.

## [0.9.0] - 2026-08-23

### Added
- **Impostazioni salvate davvero** (`GET`/`POST /api/settings`, tabella
  `app_settings`): la configurazione SMTP e i filtri di default non mostrano
  piu' "sara' implementato nella Fase 2/3". I valori salvati dalla dashboard
  hanno la precedenza su quelli in `.env`, senza riavviare il server. La
  password SMTP non viene mai rimandata al browser e lasciare il campo vuoto
  non la cancella.
- **Invio schedulato del report per cluster**: ogni cluster usa la propria
  frequenza (giornaliera / 2-3 volte a settimana / settimanale / mensile) per
  decidere quando e' in scadenza; con lo scheduler attivo un controllo
  giornaliero genera e invia il report ai destinatari del cluster
  (`app/services/report_scheduler.py`).
- **Nuova sezione "Invio automatico per cluster"** nella pagina Report:
  frequenza, numero di destinatari, ultimo invio e prossimo invio per ogni
  cluster, con "Invia ora" per singolo cluster, "Invia quelli in scadenza" e
  "Invia tutti ora" (`GET /api/reports/schedule`, `POST /api/reports/send-due`).
- **Pulsante "📧 Invia" direttamente nella lista report**: non serve piu'
  aprire l'anteprima per inviare.
- **Scelta di modello e modalita' di classificazione dalla dashboard**
  (AI Claude / euristica offline gratuita / disattivata), per tenere sotto
  controllo il consumo di crediti Anthropic.

### Fixed
- **Un errore temporaneo di Google News interrompeva l'intero run**: bastavano
  due errori (tipicamente `503 Service Unavailable`, cioe' "stai andando
  troppo veloce", non un guasto) perche' il provider principale venisse
  disabilitato fino alla fine del run e tutte le aziende successive
  risultassero non cercate. Ora:
  - le richieste sono distanziate di 2,5s (e' cio' che evita davvero i 503);
  - gli errori temporanei (429/500/502/503/504) vengono ritentati con
    backoff crescente, rispettando l'header `Retry-After`;
  - il provider si mette in **pausa** solo dopo 4 aziende consecutive fallite
    e **si riattiva da solo** dopo 3 minuti, invece di restare spento;
  - un `403` (muro di consenso) non viene ritentato: non si sbloccherebbe.
  Stesso trattamento per GDELT: dopo un rate limit va in pausa 5 minuti e
  poi riprende, invece di essere spento per tutto il run.
- **Aziende saltate a causa di un blocco venivano segnate come "controllate"**:
  `last_monitored_at` veniva aggiornato anche quando nessuna fonte aveva
  risposto, quindi l'azienda non veniva ricontrollata fino al turno
  successivo (anche una settimana) per colpa di un'interruzione di due
  minuti. Ora una ricerca bloccata non consuma il turno e l'azienda rientra
  nel run seguente.
- **Modale "Dettagli" del cluster troppo alta**: con molte aziende cresceva
  oltre lo schermo e i pulsanti (Chiudi compreso) finivano fuori dalla
  finestra. Ora la modale e' alta al massimo 88vh, intestazione e pulsanti
  restano sempre visibili, le tabelle interne scorrono, e si chiude con ESC
  o cliccando fuori.
- **Salvataggio dell'intervallo dello scheduler ignorato** quando lo
  scheduler era gia' avviato: il job ora viene rischedulato e l'intervallo
  attivo e' mostrato nel form.

## [0.8.1] - 2026-08-23

### Fixed
- **"Fonte bloccata" mostrato per aziende in cui la ricerca aveva funzionato
  davvero**: bastava che GDELT o GNews fossero esauriti perche' la riga
  venisse marcata come bloccata, anche quando Google News RSS aveva cercato
  regolarmente e non aveva trovato nulla. Ora, se almeno un provider
  completa la richiesta, il risultato viene considerato attendibile e
  riportato come "Nessun risultato"; lo stato "bloccata" resta solo quando
  *tutti* i provider hanno fallito.
- **Log illeggibile**: una volta disabilitato un provider, veniva stampata
  una riga per ogni azienda successiva ("Skipping 'X': disabled earlier this
  run"), seppellendo tutto il resto su anagrafiche grandi. Ora l'avviso
  compare una volta sola per run.

## [0.8.0] - 2026-08-23

### Added
- **Cambia azienda su una notizia** (🏢, `PUT /api/news/{id}/company`): la
  ricerca associa per nome, quindi un titolo su BPER puo' arrivare sotto
  Banca Sella. Invece di doverla solo rifiutare, ora la sposti sull'azienda
  giusta; la notizia torna in "Da verificare" perche' i punteggi erano
  calcolati sull'azienda sbagliata.
- **Azioni massive nella pagina Notizie**: checkbox su ogni notizia,
  "seleziona tutte le visibili", e approva / rifiuta / elimina in blocco
  (`POST /api/news/bulk-status`, `DELETE /api/news`).
- **"Elimina tutte le rifiutate"** per ripulire in un colpo solo le notizie
  gia' scartate.

### Fixed
- **Il sommario mostrava HTML grezzo** (`<a href="https://news.google.com/rss/
  articles/CBMi...`): Google News mette markup, non testo, nel campo
  description. Ora i tag vengono rimossi e, se il testo ripete solo il
  titolo, il sommario viene omesso. "🔗 Correggi link notizie" ripulisce
  anche i sommari gia' salvati.

### Verificato
- Le aziende in **Pausa** o **Archiviata** non vengono cercate dal
  monitoraggio (il comportamento era gia' corretto, ora c'e' una verifica
  esplicita).

## [0.7.2] - 2026-08-23

### Fixed
- **I link portavano ancora al feed XML** ("/rss/unsupported"): togliere il
  segmento `/rss` non bastava, Google reindirizza comunque. Ora l'ID
  dell'articolo viene **decodificato**: per i link "vecchi" l'URL del
  giornale e' contenuto nell'ID base64 (protobuf) e viene estratto, quindi
  "Leggi" apre direttamente l'articolo vero; per gli ID recenti, opachi e
  risolvibili solo da Google, si ripiega su una ricerca sul titolo - che
  porta comunque all'articolo, invece che su una pagina morta.
  "🔗 Correggi link notizie" applica la stessa logica alle notizie gia'
  salvate.
- **Layout delle schede notizia rotto** (titolo schiacciato in una colonna
  stretta, badge e pulsanti sulla stessa riga): sostituiti gli stili inline
  con classi CSS dedicate (`.news-card`), dove ogni sezione e' un blocco a
  larghezza piena e non puo' finire in linea con le altre.
- I titoli delle notizie ora passano per un escape HTML: contengono
  spesso «», & e virgolette, che iniettati grezzi rompevano il markup
  (ed erano un potenziale XSS, visto che il testo arriva da feed esterni).
- Stati delle notizie tradotti in italiano nella scheda (Nuova, Approvata,
  Rifiutata, Da verificare).

## [0.7.1] - 2026-08-23

### Fixed
- **Cliccando su una notizia si apriva un feed XML di Google News**
  ("Questo feed non e' disponibile"): i link salvati erano quelli RSS
  (`news.google.com/rss/articles/...`), che nel browser servono l'XML
  invece di reindirizzare all'articolo. Ora vengono normalizzati al
  salvataggio; per le notizie gia' archiviate c'e' il pulsante
  "🔗 Correggi link notizie" in Impostazioni → Manutenzione
  (`POST /api/admin/fix-news-urls`).
- I pulsanti Approva / Rifiuta / Riclassifica non avevano `type="button"`:
  in HTML il default e' `submit`, quindi potevano provocare una
  navigazione anziche' limitarsi alla chiamata API.
- Aggiunto `rel="noopener noreferrer"` ai link esterni delle notizie.

## [0.7.0] - 2026-08-23

### Fixed
- **Impossibile cancellare un'azienda** ("JSON.parse: unexpected character at
  line 1 column 1"): la tabella `search_logs`, aggiunta in 0.5.0, non aveva il
  cascade sulla foreign key verso `companies`. La cancellazione violava il
  vincolo, l'eccezione non gestita restituiva un 500 in testo semplice, e il
  browser falliva sul `JSON.parse`. Ora il cascade c'e' e la cancellazione
  rimuove anche notizie e log collegati.
- Aggiunto un handler globale: un errore server risponde sempre in JSON, mai
  piu' con HTML/testo che il frontend non sa interpretare.

### Added
- **Come NON consumare crediti Anthropic** - nuova opzione `CLASSIFIER_MODE`:
  - `heuristic`: classificazione per parole chiave, **completamente gratuita
    e offline** (`app/services/heuristic_classifier.py`). Assegna categoria e
    punteggi, e soprattutto abbassa la rilevanza del rumore (cronaca, sport,
    necrologi) che riempiva i risultati di aziende come Banca d'Italia.
  - `off`: salva le notizie senza punteggi, classifichi a mano.
  - `ai` (default): Claude, qualita' migliore.
- **Modello configurabile** (`CLAUDE_MODEL`), con default `claude-haiku-4-5`,
  molto piu' economico di Sonnet e piu' che adeguato per valutare uno snippet.
  Il parametro `thinking` viene ora inviato solo ai modelli che lo accettano.
- **Copertura ricerca**: la colonna notizie e' ora un link diretto alle notizie
  di quell'azienda (`/news?company_id=...`), invece del solo numero dell'ultimo
  run; il dettaglio fonti e' scritto in italiano leggibile ("GDELT: limite
  raggiunto" al posto di "gdelt:error(HTTP 429)"); nuovo pulsante
  "Pulisci errori" per rimuovere dallo storico le righe fallite
  (`DELETE /api/coverage`).
- `/api/news` accetta ora il filtro `company_id`.

## [0.6.1] - 2026-08-23

### Added
- **Circuit breaker sulla classificazione AI**: se l'account Anthropic
  restituisce un errore che non può risolversi da solo (credito esaurito,
  API key non valida o senza permessi), la classificazione viene sospesa
  per il resto del run invece di ritentare per ogni articolo. Nel run
  dell'utente questo significava 150 chiamate destinate a fallire (con la
  relativa latenza e centinaia di righe di log); ora ne basta una.
  Il breaker si azzera ad ogni nuovo run, quindi appena ricarichi i crediti
  riprende da solo senza riavviare il server.
- Il motivo dello stop è ora **visibile in Impostazioni** al termine del
  monitoraggio ("credito Anthropic esaurito", "API key non valida", ...),
  con il link diretto a console.anthropic.com e il promemoria di usare
  ↻ Riclassifica - invece di essere sepolto nei log del terminale.
  Esposto anche via `GET /api/monitoring/status` (`classification_issue`).
- Messaggi di errore leggibili al posto del dump grezzo dell'API in
  "Test API" e nella riclassificazione (HTTP 402 con la causa reale).
- Il risultato del monitoraggio riporta ora anche `news_unclassified`.

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
