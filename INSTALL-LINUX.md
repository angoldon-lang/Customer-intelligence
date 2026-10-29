# Installazione da zero su Linux

Guida per installare Customer Intelligence Monitor su una macchina Linux
pulita, farlo partire da solo all'avvio e tenerlo aggiornato.

I comandi sono stati provati su Python 3.11 e 3.12: con entrambi le
dipendenze si installano senza compilare niente e i 251 test passano.

---

## 1. Versione di Python: leggi questo prima

**Serve Python 3.11 o 3.12. Con Python 3.13 l'installazione si ferma.**

Il progetto usa `lxml==4.9.3`, che non pubblica un pacchetto precompilato
per 3.13: `pip` prova a compilarlo dai sorgenti e si interrompe con

```
Building lxml version 4.9.3.
Error: Please make sure the libxml2 and libxslt development packages are installed.
```

Non è un problema della tua macchina ed è inutile installare `libxml2-dev`
per aggirarlo: subito dopo si fermerebbero anche `pandas` e `numpy`, che
per 3.13 vogliono versioni più recenti di quelle fissate qui.

Quindi, prima di tutto, controlla cosa hai:

```bash
python3 --version
```

| Distribuzione | Python di serie | Esito |
|---|---|---|
| Debian 12 "bookworm" | 3.11 | va bene così |
| Ubuntu 24.04 LTS | 3.12 | va bene così |
| Ubuntu 22.04 LTS | 3.10 | installa il 3.11 (vedi sotto) |
| Fedora 40+ / Ubuntu 25.x | 3.13 | installa il 3.12 (vedi sotto) |

Se ti serve affiancare una versione, l'originale di sistema **non va
toccata** (ci girano pezzi della distribuzione): si installa a fianco.

```bash
# Ubuntu / Debian
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv

# Fedora / RHEL
sudo dnf install -y python3.12
```

---

## 2. Pacchetti di sistema

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y python3-venv python3-pip git sqlite3

# Fedora / RHEL / Rocky
sudo dnf install -y python3-pip git sqlite
```

Niente compilatori, niente librerie di sviluppo: tutte le dipendenze
arrivano come pacchetti già compilati.

`sqlite3` non serve all'applicazione ma ai backup (paragrafo 9).

---

## 3. Utente dedicato e cartella

Non far girare l'app come `root`: se un giorno la esponi in rete, un
problema nell'applicazione resta confinato a un utente senza privilegi.

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin cim
sudo mkdir -p /opt/customer-intelligence
sudo chown cim:cim /opt/customer-intelligence
```

---

## 4. Scaricare il codice

```bash
sudo -u cim git clone https://github.com/angoldon-lang/Customer-intelligence.git /opt/customer-intelligence
cd /opt/customer-intelligence
sudo -u cim git checkout claude/customer-intelligence-monitor-vzirll
```

---

## 5. Ambiente virtuale e dipendenze

Usa l'interprete della versione scelta al paragrafo 1 (`python3`,
`python3.11` o `python3.12`):

```bash
cd /opt/customer-intelligence
sudo -u cim python3.12 -m venv venv
sudo -u cim ./venv/bin/pip install --upgrade pip
sudo -u cim ./venv/bin/pip install -r requirements.txt
```

Controlla subito che l'applicazione si carichi, prima di configurare altro:

```bash
sudo -u cim ./venv/bin/python -c "import app.main; print('OK')"
```

Deve stampare `Database initialized successfully` e `OK`. Se vuoi la
verifica completa:

```bash
sudo -u cim ./venv/bin/python -m pytest -q    # 251 passed
```

---

## 6. Configurazione

```bash
sudo -u cim cp .env.example .env
sudo -u cim nano .env
sudo chmod 600 .env        # contiene la chiave API e la password SMTP
```

Il minimo indispensabile per partire:

```ini
CLAUDE_API_KEY=sk-ant-...        # da https://console.anthropic.com
CLAUDE_MODEL=claude-haiku-4-5    # il più economico, sufficiente allo scopo
HOST=127.0.0.1
PORT=8001
```

Tre scelte che vale la pena fare adesso:

- **`CLASSIFIER_MODE`** — `ai` classifica con Claude (consuma crediti),
  `heuristic` classifica per parole chiave gratis, `off` salva le notizie
  senza punteggi. Puoi partire da `heuristic` per provare il sistema senza
  spendere, e passare ad `ai` quando l'anagrafica è a posto.
- **`NEWS_SEARCH_DAYS`** — quanti giorni indietro cercare (30 di default).
- **`SCHEDULER_ENABLED`** — lascialo `False`: la ricerca automatica si
  avvia dalla dashboard e da lì la scelta viene salvata nel database, così
  riparte da sola dopo un riavvio.

Email, fonti, ordine delle fonti e personalizzazione del report **non
serve metterli qui**: si configurano dalla pagina Impostazioni, che scrive
nel database e sovrascrive il `.env`.

Il database e la chiave con cui vengono firmati i cookie di sessione
vengono creati da soli al primo avvio: non c'è nessun comando di
inizializzazione da dare, e nessun segreto da generare a mano.

---

## 7. Primo avvio a mano

Prima di mettere in piedi il servizio, provala in primo piano:

```bash
cd /opt/customer-intelligence
sudo -u cim ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Da un'altra finestra (o dal tuo browser con un tunnel SSH, vedi sotto):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/setup   # 200
```

Apri `http://127.0.0.1:8001`: al primo avvio ogni indirizzo rimanda a
**`/setup`**, dove crei l'utente amministratore. Non esiste una password
predefinita, e finché non ne scegli una nessuna pagina è raggiungibile.

Se il server è remoto e non hai ancora un reverse proxy, raggiungilo dal
tuo computer senza aprire porte:

```bash
ssh -L 8001:127.0.0.1:8001 utente@tuo-server
```

e poi apri `http://127.0.0.1:8001` sul tuo computer.

Fermalo con `Ctrl+C` quando hai finito.

---

## 8. Servizio systemd (avvio automatico)

```bash
sudo nano /etc/systemd/system/customer-intelligence.service
```

```ini
[Unit]
Description=Customer Intelligence Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=cim
Group=cim
WorkingDirectory=/opt/customer-intelligence
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/customer-intelligence/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now customer-intelligence
systemctl status customer-intelligence
```

Tre righe di quel file contano più di quanto sembri:

- **`WorkingDirectory`** è obbligatoria. Il database è configurato come
  `sqlite:///./app.db`, cioè *relativo alla cartella di lavoro*: senza
  quella riga systemd partirebbe dalla root e si creerebbe un database
  vuoto altrove, dando l'impressione di aver perso i dati.
- **nessun `--reload`**: serve solo in sviluppo, e fa girare l'app in un
  sottoprocesso che systemd non controlla bene.
- **nessun `--workers`**: la ricerca automatica è uno scheduler interno al
  processo. Con più worker partirebbe in ognuno, e ti ritroveresti la
  stessa ricerca eseguita più volte e i report inviati in copia.

I log:

```bash
journalctl -u customer-intelligence -f          # in tempo reale
journalctl -u customer-intelligence --since today
```

Gli esiti delle singole ricerche non stanno qui ma in **Impostazioni >
Log delle ricerche**, con il filtro per azienda ed esito e lo scarico in
CSV.

---

## 9. Backup

Da salvare ci sono due cose:

| Cosa | Perché |
|---|---|
| `app.db` | aziende, cluster, notizie, impostazioni, utenza amministratore |
| `.env` | chiave API e credenziali SMTP |

Il database è in modalità WAL: una parte delle scritture recenti sta nei
file `app.db-wal`. **Copiarlo con `cp` mentre il servizio gira produce un
backup incoerente.** Usa il comando di backup di SQLite, che lavora bene
anche a servizio avviato:

```bash
sudo -u cim mkdir -p /opt/customer-intelligence/backups
sudo -u cim sqlite3 /opt/customer-intelligence/app.db \
  ".backup '/opt/customer-intelligence/backups/app-$(date +%F).db'"
```

Ogni notte alle 3, tenendo 30 giorni:

```bash
sudo crontab -u cim -e
```

```cron
0 3 * * * sqlite3 /opt/customer-intelligence/app.db ".backup '/opt/customer-intelligence/backups/app-$(date +\%F).db'" && find /opt/customer-intelligence/backups -name 'app-*.db' -mtime +30 -delete
```

(nel crontab il `%` va scritto `\%`).

Per ripristinare: ferma il servizio, sostituisci `app.db` con il backup,
elimina eventuali `app.db-wal` e `app.db-shm` rimasti, riavvia.

---

## 10. Esporre la dashboard in rete (opzionale)

Se ti basta usarla dal server o via tunnel SSH, salta questo paragrafo:
così com'è, l'app ascolta solo su `127.0.0.1` e non è raggiungibile da
fuori.

Per pubblicarla, mettila **dietro HTTPS**. Il cookie di sessione, in HTTP,
viaggia in chiaro su tutta la rete.

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo nano /etc/nginx/sites-available/customer-intelligence
```

```nginx
server {
    listen 80;
    server_name intelligence.esempio.it;

    # L'import dell'anagrafica carica file Excel: il limite di default di
    # nginx e' 1 MB e rifiuterebbe i file piu' grandi con un 413.
    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/customer-intelligence /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d intelligence.esempio.it
```

**Appena l'HTTPS funziona**, nel `.env`:

```ini
SESSION_COOKIE_SECURE=True
```

e riavvia il servizio. Fallo *dopo* aver verificato l'HTTPS: con
`True` su una connessione HTTP il browser non invia il cookie e il login
non andrebbe a buon fine, senza messaggi d'errore chiari.

---

## 11. Aggiornare

```bash
cd /opt/customer-intelligence
sudo -u cim sqlite3 app.db ".backup 'backups/pre-update.db'"
sudo -u cim git pull
sudo -u cim ./venv/bin/pip install -r requirements.txt
sudo systemctl restart customer-intelligence
```

Le modifiche allo schema del database sono applicate da sole all'avvio
(vengono aggiunte le colonne mancanti): non c'è nessuna migrazione da
lanciare a mano e i dati esistenti restano al loro posto.

La versione installata si legge in **Impostazioni > Info sistema**.

---

## 12. Se qualcosa non va

**`Error: Please make sure the libxml2 and libxslt development packages are installed`**
durante `pip install` → stai usando Python 3.13. Vedi il paragrafo 1.

**`Address already in use`** → la porta è occupata:
```bash
sudo ss -tlnp | grep 8001
```
Cambia `--port` nel file systemd (e `proxy_pass` in nginx, se lo usi).

**Il servizio riparte in continuazione** →
```bash
journalctl -u customer-intelligence -n 50
```
Le due cause più comuni sono il `.env` non leggibile dall'utente `cim`
(`sudo chown cim:cim .env`) e un `WorkingDirectory` sbagliato.

**La dashboard è vuota dopo un riavvio** → quasi sempre è
`WorkingDirectory`: l'app ha creato un database nuovo in un'altra
cartella. Cerca gli altri `app.db`:
```bash
sudo find / -name 'app.db' -mtime -1 2>/dev/null
```

**Non riesco più a entrare** → la password si può solo reimpostare
cancellando l'utenza dal database; il servizio ti riporterà su `/setup` al
primo accesso:
```bash
sudo systemctl stop customer-intelligence
sudo -u cim sqlite3 app.db "DELETE FROM app_settings WHERE key LIKE 'ADMIN_%';"
sudo systemctl start customer-intelligence
```

**Il caricamento del logo nel report non funziona** → la cartella deve
essere scrivibile dal servizio:
```bash
sudo chown -R cim:cim /opt/customer-intelligence/app/static/branding
```

**Le notizie non si trovano** → prima di cercare altrove, apri
**Impostazioni > Log delle ricerche**: dice per ogni azienda se è stata
saltata, se una fonte ha risposto con un errore o se semplicemente non
c'era niente. Da server, controlla anche che le chiamate in uscita su
HTTPS non siano bloccate dal firewall.

---

## Note

Gli orari mostrati nelle pagine sono in UTC, quindi in Italia appaiono
una o due ore indietro rispetto all'ora locale. È solo visualizzazione:
i dati e le schedulazioni sono corretti.
