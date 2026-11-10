# Installazione con Docker e HTTPS

Due container: l'applicazione e un reverse proxy che fa HTTPS. Si avviano
con un comando e si aggiornano con tre.

Tutto quello che segue è stato costruito ed eseguito davvero: immagine
compilata, stack avviato, certificato emesso, amministratore creato via
HTTPS, import Excel attraverso il proxy, backup, e verifica che la porta
dell'applicazione non sia raggiungibile dall'esterno.

---

## Come è fatto

```
   Internet
      │  443 (e 80, solo per il redirect e il certificato)
      ▼
 ┌──────────────┐
 │    proxy     │  Caddy: termina HTTPS, certificato automatico
 │ (pubblica    │
 │  80 e 443)   │
 └──────┬───────┘
        │  rete interna di Docker, nessuna porta sull'host
        ▼
 ┌──────────────┐
 │     app      │  uvicorn sulla 8001, utente senza privilegi
 │ (nessuna     │
 │  porta)      │
 └──────┬───────┘
        ▼
   volumi: database, logo del report, certificati
```

**L'applicazione non pubblica nessuna porta.** È raggiungibile solo dal
proxy, sulla rete interna. Il paragrafo "La porta" spiega perché è scritto
così e cosa cambierebbe facendolo diversamente.

---

## 1. Prerequisiti

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git

# Fedora / RHEL
sudo dnf install -y docker docker-compose git

sudo systemctl enable --now docker
```

Verifica (serve il plugin `compose`, non il vecchio `docker-compose`):

```bash
docker --version
docker compose version
```

---

## 2. Codice e configurazione

```bash
sudo mkdir -p /opt/customer-intelligence
sudo chown "$USER" /opt/customer-intelligence
git clone https://github.com/angoldon-lang/Customer-intelligence.git /opt/customer-intelligence
cd /opt/customer-intelligence
git checkout claude/customer-intelligence-monitor-vzirll

cp .env.example .env
nano .env
chmod 600 .env
```

Il `.env` va creato **prima** di qualunque comando `docker compose`: senza
di esso anche un semplice `docker compose ps` si interrompe con
`env file ... not found`.

Nel `.env` servono la chiave API e l'indirizzo del sito:

```ini
CLAUDE_API_KEY=sk-ant-...

# In locale, per provare:
SITE_ADDRESS=https://localhost

# In produzione, il tuo dominio:
# SITE_ADDRESS=https://intelligence.esempio.it

TZ=Europe/Rome
```

`SITE_ADDRESS` è l'unico valore che decide il comportamento dell'HTTPS, e
lo legge il proxy. Email, fonti e personalizzazione del report restano
come sempre nella pagina Impostazioni.

Tre valori del `.env` **vengono ignorati dentro Docker**, perché il
compose li imposta da sé: `DATABASE_URL` (punta al volume),
`SESSION_COOKIE_SECURE` (sempre `True`, dato che il proxy serve solo
HTTPS) e `PORT` (8001 nel container). Non toccarli nel `.env`: non
avrebbe effetto.

---

## 3. Avvio

```bash
docker compose up -d --build
```

La prima volta costruisce l'immagine, servono alcuni minuti. Poi:

```bash
docker compose ps
```

Devi vedere l'app `healthy` e il proxy `Up`:

```
SERVICE   STATUS                    PORTS
app       Up 12 seconds (healthy)   8001/tcp
proxy     Up About a minute         0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

Guarda la colonna PORTS: l'app dice `8001/tcp` **senza** nessuna freccia
`0.0.0.0:...->`. Quella freccia significa "pubblicata sull'host", e
l'applicazione non ce l'ha.

Apri `https://localhost` (o il tuo dominio) e crea l'amministratore nella
pagina `/setup` che ti viene proposta.

**Con `https://localhost` il browser mostra un avviso di sicurezza**: il
certificato è emesso da un'autorità locale di Caddy, non da una pubblica.
È normale in locale; con un dominio vero il certificato è di Let's
Encrypt e l'avviso non compare.

### Messa in produzione con un dominio

1. Il dominio deve puntare all'indirizzo IP del server (record A).
2. Le porte 80 e 443 devono essere raggiungibili da Internet.
3. `SITE_ADDRESS=https://intelligence.esempio.it` nel `.env`.
4. `docker compose up -d`.

Il certificato viene richiesto, installato e rinnovato da solo. La porta
80 serve anche dopo: ci passa la verifica del dominio a ogni rinnovo.

Se vuoi ricevere gli avvisi di scadenza da Let's Encrypt (utile se un
rinnovo si rompe), scommenta le tre righe in cima al `Caddyfile` e metti
il tuo indirizzo.

---

## 4. La porta

Questa parte merita attenzione, perché è il punto in cui è più facile
aprire in rete qualcosa senza accorgersene.

Nel `docker-compose.yml` l'applicazione ha `expose` e **non** `ports`:

```yaml
app:
  expose:
    - "8001"     # documenta la porta verso gli altri container
```

| | Cosa fa |
|---|---|
| `expose: "8001"` | la porta è raggiungibile dagli altri container della stessa rete. Sull'host non apre niente |
| `ports: "8001:8001"` | la porta è pubblicata su **tutte** le interfacce dell'host, quindi anche dall'esterno |
| `ports: "127.0.0.1:8001:8001"` | pubblicata solo sull'host stesso, non dalla rete |

Solo il proxy ha `ports`, e solo per 80 e 443.

### Perché non basta il firewall

Su una macchina con `ufw` attivo, una porta pubblicata da Docker **resta
raggiungibile anche se `ufw` la nega**. Non è un difetto di
configurazione: Docker inserisce le proprie regole di reindirizzamento
nella tabella `nat` e il traffico verso i container attraversa la catena
`FORWARD`, mentre le regole di `ufw` agiscono su `INPUT`. Il pacchetto non
passa dove `ufw` lo sta aspettando.

Sullo stack avviato si vede esattamente così (`iptables -t nat -L DOCKER`):

```
DNAT  tcp dpt:80   to:172.18.0.3:80
DNAT  tcp dpt:443  to:172.18.0.3:443
```

Due regole, per le due porte del proxy. Nessuna regola menziona la 8001:
l'applicazione non è pubblicata, e nessun errore nelle regole del
firewall potrebbe esporla.

**Conseguenza pratica**: non aggiungere `ports` all'app contando sul
firewall per proteggerla. Se ti serve raggiungerla direttamente per una
diagnosi, usa la forma legata a localhost:

```yaml
    ports:
      - "127.0.0.1:8001:8001"     # solo dalla macchina stessa
```

e raggiungila da remoto con un tunnel SSH:

```bash
ssh -L 8001:127.0.0.1:8001 utente@server
```

Se invece devi limitare per indirizzo IP una porta che *è* pubblicata, le
regole vanno nella catena `DOCKER-USER`, che Docker lascia apposta a
disposizione e che viene valutata prima delle sue.

### Una porta che vedrai e non è un problema

`docker compose ps` elenca anche `2019/tcp` sul proxy: è l'interfaccia di
amministrazione di Caddy. Non è pubblicata sull'host e Caddy la lega a
`localhost` *dentro il proprio container*: dal container dell'app il
collegamento viene rifiutato (verificato).

---

## 5. Dove stanno i dati

Quattro volumi gestiti da Docker, non cartelle sparse:

| Volume | Contenuto |
|---|---|
| `db` | il database: aziende, cluster, notizie, impostazioni, utenza |
| `logos` | il logo caricato per il report |
| `caddy_data` | i certificati HTTPS |
| `caddy_config` | lo stato del proxy |

I dati **sopravvivono** a `docker compose down`, alla ricostruzione
dell'immagine e all'aggiornamento del codice: stanno nei volumi, non nei
container. Verificato distruggendo il container e ricreandolo:
l'amministratore e i dati erano ancora al loro posto.

Spariscono solo con `docker compose down -v`, che cancella i volumi: non
usare `-v` a meno che sia proprio quello che vuoi.

### Backup

Nell'immagine non c'è il comando `sqlite3`, ma il backup coerente si fa
con Python, a container avviato, senza fermare niente:

```bash
cd /opt/customer-intelligence

docker compose exec -T app python -c "
import sqlite3
src = sqlite3.connect('/data/app.db')
dst = sqlite3.connect('/data/backup.db')
src.backup(dst)
dst.close()"

docker compose cp app:/data/backup.db "./backup-$(date +%F).db"
docker compose exec -T app rm /data/backup.db
```

`src.backup(dst)` è lo stesso meccanismo del comando `.backup` di SQLite:
tiene conto del journal WAL, mentre copiare il file con `cp` a database
attivo darebbe un backup incoerente.

Da salvare c'è anche il `.env`, che contiene la chiave API e le
credenziali SMTP.

Ogni notte alle 3, tenendo 30 giorni:

```bash
crontab -e
```

```cron
0 3 * * * cd /opt/customer-intelligence && docker compose exec -T app python -c "import sqlite3; s=sqlite3.connect('/data/app.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()" && docker compose cp app:/data/backup.db ./backups/app-$(date +\%F).db && docker compose exec -T app rm /data/backup.db && find ./backups -name 'app-*.db' -mtime +30 -delete
```

(nel crontab il `%` va scritto `\%`; crea prima la cartella `backups`).

---

## 6. Comandi di tutti i giorni

```bash
cd /opt/customer-intelligence

docker compose logs -f app          # log dell'applicazione
docker compose logs -f proxy        # log del proxy e dei certificati
docker compose restart app          # riavvio dopo una modifica al .env
docker compose down                 # ferma tutto (i dati restano)
docker compose up -d                # riavvia
```

Gli esiti delle ricerche non stanno nei log di Docker ma in
**Impostazioni > Log delle ricerche**, con il filtro per azienda ed esito
e lo scarico in CSV.

---

## 7. Aggiornare

```bash
cd /opt/customer-intelligence

# backup prima (vedi sopra)
git pull
docker compose up -d --build
```

Le modifiche allo schema del database vengono applicate da sole
all'avvio: non c'è nessuna migrazione da lanciare a mano.

Per recuperare spazio dalle immagini vecchie:

```bash
docker image prune -f
```

---

## 8. Se qualcosa non va

**`docker compose ps` mostra il proxy che si riavvia** → è quasi sempre il
`Caddyfile`:
```bash
docker compose logs proxy | grep -i error
```
Un errore `adapting config` indica una riga malformata; Caddy non parte
affatto se il file non è valido.

**Il certificato non viene emesso** (con un dominio vero) →
```bash
docker compose logs proxy | grep -i -E "certificate|acme|challenge"
```
Le cause tipiche: il dominio non punta ancora a questo server, la porta 80
non è raggiungibile da Internet, oppure si è superato il limite
settimanale di Let's Encrypt per quel dominio (per fare prove ripetute,
usa prima `https://localhost`).

**`env file ... /.env not found`** → qualsiasi comando `docker compose`
in questa cartella richiede il `.env`, perché è da lì che l'applicazione
prende la chiave API. Creane uno prima di tutto il resto:
```bash
cp .env.example .env
```

**`docker compose up` si ferma su "port is already allocated"** → qualcosa
occupa già la 80 o la 443, tipicamente un nginx o un Apache installati sul
server:
```bash
sudo ss -tlnp | grep -E ':(80|443) '
sudo systemctl disable --now nginx     # se non ti serve più
```

**L'app resta `starting` e non diventa `healthy`** →
```bash
docker compose logs app | tail -30
```
Il controllo di salute interroga `/login` ogni 30 secondi e concede 20
secondi iniziali.

**"Non riesco più a entrare"** → si azzera l'utenza e l'app ripropone
`/setup`:
```bash
docker compose exec -T app python -c "
import sqlite3
c = sqlite3.connect('/data/app.db')
c.execute(\"DELETE FROM app_settings WHERE key LIKE 'ADMIN_%'\")
c.commit()"
docker compose restart app
```

**Permessi sui volumi** → dentro al container l'applicazione gira come
utente `cim` (uid 10001), non root, e i due percorsi su cui scrive
(`/data` e il logo) sono creati con il proprietario giusto
nell'immagine. Se hai sostituito i volumi con cartelle dell'host, devi
allinearne il proprietario:
```bash
sudo chown -R 10001:10001 /percorso/della/cartella
```

---

## 9. Cose da non fare

- **Non aggiungere `--workers` a uvicorn.** La ricerca automatica è uno
  scheduler interno al processo: con più worker partirebbe in ognuno, e
  ti arriverebbero gli stessi report in copia.
- **Non pubblicare la 8001** contando sul firewall (paragrafo 4).
- **Non usare `docker compose down -v`** per un riavvio: `-v` cancella i
  volumi, cioè il database.
- **Non mettere la chiave API nel `docker-compose.yml`.** Sta nel `.env`,
  che non entra nell'immagine (è escluso dal `.dockerignore`): un valore
  scritto in un livello dell'immagine resta leggibile con
  `docker history`.
