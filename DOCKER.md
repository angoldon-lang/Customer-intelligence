# Installazione con Docker e HTTPS

Due container: l'applicazione e un reverse proxy che fa HTTPS.

La guida è scritta per una macchina che **ha già altri servizi e altri
container**: il primo passo è censire le porte, e c'è una variante per
quando la 80 e la 443 sono già occupate (il caso più probabile).

Tutto quello che segue è stato costruito ed eseguito davvero, in entrambe
le varianti.

---

## Come è fatto

```
   Internet
      │  443 (e 80, per il redirect e il certificato)
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
proxy, sulla rete interna. Vale in tutte le varianti descritte sotto.

---

## 1. Censimento delle porte

Prima di installare, guarda cosa c'è. Questi comandi non modificano
niente.

```bash
# Tutto ciò che è in ascolto sulla macchina, con il processo
sudo ss -tlnp

# Solo le porte che ci interessano
sudo ss -tlnp | grep -E ':(80|443|8001) '

# Cosa pubblicano i container già attivi
docker ps --format 'table {{.Names}}\t{{.Ports}}'

# Compresi quelli fermi, che si riprenderanno la porta al riavvio
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Il risultato decide quale delle tre varianti seguire:

| Situazione | Variante |
|---|---|
| 80 e 443 libere | **A** — stack completo |
| Hai già un reverse proxy (nginx, Apache, Traefik, Caddy) | **B** — dietro il tuo proxy |
| 80 o 443 occupate da un'applicazione che non è un proxy | **C** |
| Vuoi tutto su una sola porta, es. la 8001 | **D** — porta unica |

Se non sei sicuro di avere un reverse proxy, questo te lo dice:

```bash
sudo ss -tlnp | grep -E ':(80|443) '
systemctl is-active nginx apache2 httpd caddy traefik 2>/dev/null
docker ps --format '{{.Image}} {{.Ports}}' | grep -E ':80->|:443->'
```

---

## 2. Prerequisiti

Docker ce l'hai già. Serve il plugin `compose` (non il vecchio comando
`docker-compose` con il trattino):

```bash
docker compose version
```

Se risponde `docker: 'compose' is not a docker command`:

```bash
sudo apt install -y docker-compose-v2     # Debian / Ubuntu
sudo dnf install -y docker-compose        # Fedora / RHEL
```

---

## 3. Codice e configurazione

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
di esso anche `docker compose ps` si interrompe con
`env file ... not found`.

Il minimo indispensabile:

```ini
CLAUDE_API_KEY=sk-ant-...
TZ=Europe/Rome
```

Più le righe della variante scelta, qui sotto.

Tre valori del `.env` **vengono ignorati dentro Docker**, perché il
compose li imposta da sé: `DATABASE_URL` (punta al volume),
`SESSION_COOKIE_SECURE` (sempre `True`) e `PORT` (8001 nel container).

Lo stack si chiama sempre `customer-intelligence` (`name:` nel compose),
qualunque sia il nome della cartella: container, rete e volumi non si
confondono con gli altri stack della macchina.

---

## 4. Variante A — 80 e 443 libere

Nel `.env`:

```ini
SITE_ADDRESS=https://intelligence.esempio.it
# oppure, per provare in locale:
# SITE_ADDRESS=https://localhost
```

```bash
docker compose up -d --build
docker compose ps
```

Caddy richiede, installa e rinnova il certificato da solo. Con
`https://localhost` il certificato è emesso dalla sua autorità locale e
il browser mostra un avviso: normale in locale.

Le porte pubblicate si possono spostare senza toccare il compose:

```ini
HTTP_PORT=8080
HTTPS_PORT=8443
HTTP_BIND=127.0.0.1     # pubblica solo sulla macchina stessa
```

**Ma attenzione**: spostando la 80 il rilascio automatico del certificato
Let's Encrypt non funziona più (vedi la variante C). Le porte alternative
hanno senso con `https://localhost`, o quando a stare davanti c'è un
altro proxy — e in quel caso la variante B è più pulita.

---

## 5. Variante B — dietro il proxy che hai già

È il caso tipico di una macchina con molti servizi: nginx o Traefik tiene
80 e 443, i certificati sono già gestiti lì, e questa applicazione deve
solo aggiungersi.

Nel `.env`:

```ini
APP_PORT=8001        # cambiala se la 8001 è occupata
```

`SITE_ADDRESS` non serve: il proxy di questo progetto non viene avviato.

```bash
docker compose -f docker-compose.yml -f docker-compose.behind-proxy.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.behind-proxy.yml ps
```

Devi vedere **un solo container**, l'app, con la porta pubblicata così:

```
NAME                        PORTS
customer-intelligence-app-1 127.0.0.1:8001->8001/tcp
```

`127.0.0.1:` davanti è la parte importante: la porta è raggiungibile dal
proxy che gira su questa macchina, **non dalla rete**.

Per non ripetere i due `-f` ogni volta:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.behind-proxy.yml
```

o mettilo nel `.env` come `COMPOSE_FILE=docker-compose.yml:docker-compose.behind-proxy.yml`.

### Da aggiungere al tuo proxy

**nginx** — nuovo file in `/etc/nginx/sites-available/`, poi collegato in
`sites-enabled/`:

```nginx
server {
    listen 443 ssl;
    server_name intelligence.esempio.it;

    ssl_certificate     /etc/letsencrypt/live/intelligence.esempio.it/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/intelligence.esempio.it/privkey.pem;

    # L'import dell'anagrafica carica file Excel: il limite di default di
    # nginx è 1 MB e li rifiuterebbe con un 413.
    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        # Senza questo l'applicazione si crede in HTTP e il login non
        # funziona: il cookie di sessione è marcato "secure".
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

**Caddy** (se è lui a tenere la 443) — nel tuo `Caddyfile`:

```
intelligence.esempio.it {
	request_body {
		max_size 25MB
	}
	reverse_proxy 127.0.0.1:8001
}
```

Caddy manda gli header `X-Forwarded-*` da sé.

**Apache**:

```apache
<VirtualHost *:443>
    ServerName intelligence.esempio.it
    SSLEngine on
    SSLCertificateFile    /etc/letsencrypt/live/intelligence.esempio.it/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/intelligence.esempio.it/privkey.pem

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass        / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

**Il tuo proxy deve servire HTTPS.** Il compose marca il cookie di
sessione come "secure": su HTTP il browser **non lo salva affatto**, e il
login rimanda alla pagina di accesso senza nessun messaggio d'errore.
Verificato con un browser vero su un nome di dominio: con il proxy in
HTTPS si entra, con lo stesso proxy in HTTP puro il cookie non viene
memorizzato e si torna a `/login`.

Attenzione a come lo provi, perché è una trappola: su `localhost` e
`127.0.0.1` i browser trattano l'origine come fidata e **accettano il
cookie "secure" anche in HTTP**. Quindi una prova in locale riesce, e lo
stesso proxy sul dominio vero fallisce. Prova sempre con il nome di
dominio che userai.

Se davvero devi servire in HTTP (solo rete interna, con un nome di
dominio), aggiungi al `.env`:

```ini
SESSION_COOKIE_SECURE=False
```

e togli la riga corrispondente dal `docker-compose.yml`, che altrimenti
vince sul `.env`.

---

## 6. Variante C — 80 o 443 occupate da un'applicazione

Qui le strade sono tre, in ordine di preferenza.

**1. Metti davanti un reverse proxy.** Se la 443 è occupata da
un'applicazione servita direttamente, prima o poi te ne servirà uno
comunque: installa nginx, sposta quell'applicazione dietro di lui e segui
la variante B per questa. È l'unica soluzione che fa convivere più siti
HTTPS sullo stesso indirizzo IP.

**2. Libera le porte**, se chi le occupa non ti serve più:

```bash
sudo ss -tlnp | grep -E ':(80|443) '      # chi è
sudo systemctl disable --now nginx         # esempio
```

**3. Porte alternative** → usa direttamente la **variante D** qui sotto.

Su una porta diversa dalla 80 e dalla 443 il certificato non può essere di
Let's Encrypt (la verifica del dominio è servita solo su quelle due porte),
quindi serve una configurazione diversa da quella della variante A: un
certificato dell'autorità locale di Caddy, dichiarato esplicitamente. È
esattamente quello che fa la variante D, e vale anche se ti servono due
porte alternative anziché una: cambia `PUBLIC_PORT`.

Non impostare semplicemente `HTTP_PORT`/`HTTPS_PORT` sulla variante A con
un dominio pubblico: Caddy tenterebbe un rilascio Let's Encrypt destinato
a fallire, su porte dove la verifica non arriva.

---

## 6-bis. Variante D — tutto su una sola porta (8001)

Una sola porta pubblicata sull'host, niente 80 e niente 443:
`https://indirizzo-del-server:8001`.

Nel `.env`:

```ini
SITE_HOST=192.168.1.50        # l'IP o il nome del server, SENZA https:// e senza porta
PUBLIC_PORT=8001              # opzionale, è il default
# PUBLIC_BIND=127.0.0.1       # per limitarla alla macchina stessa
```

`SITE_HOST` deve essere **esattamente l'indirizzo con cui aprirai la
dashboard**: `192.168.1.50` se la raggiungi per IP, `intelligence.interna`
se per nome. Questa variante non usa `SITE_ADDRESS`.

Va scritto giusto perché da lì dipende il certificato, e un browser che si
collega a un **indirizzo IP non manda il campo SNI** (il protocollo non lo
prevede per gli IP): senza sapere in anticipo per quale indirizzo
rispondere, Caddy non saprebbe quale certificato presentare e la
connessione fallirebbe con un errore TLS, prima ancora di arrivare
all'applicazione. Il `Caddyfile.single-port` risolve questo con
`default_sni`, che legge `SITE_HOST`. Se lo sbagli, il certificato risulta
emesso per un altro nome e il browser lo rifiuta per nome non
corrispondente.

```bash
docker compose -f docker-compose.yml -f docker-compose.single-port.yml up -d --build
```

Per non ripetere i due `-f` ogni volta, nel `.env`:

```ini
COMPOSE_FILE=docker-compose.yml:docker-compose.single-port.yml
```

Il risultato: due container, ma **una sola porta pubblicata**.

```
NAME                            PORTS
customer-intelligence-app-1     8001/tcp
customer-intelligence-proxy-1   80/tcp, 443/tcp, 2019/tcp, 443/udp, 0.0.0.0:8001->8001/tcp
```

Legge solo le frecce: **l'unica è `0.0.0.0:8001->8001/tcp`**. La 80, la
443 e la 2019 compaiono senza freccia perché l'immagine di Caddy le
dichiara, ma non sono pubblicate e dall'esterno non esistono. Verificato
anche sulle regole di Docker, dove l'unica voce è:

```
DNAT  tcp dpt:8001  to:172.18.0.3:8001
```

L'app, come sempre, non pubblica niente: la porta 8001 dell'host arriva al
proxy, che parla con l'applicazione sulla rete interna.

### Il certificato: cosa aspettarsi

Su una porta diversa dalla 80 e dalla 443 **non si può avere un
certificato Let's Encrypt**: la verifica del dominio viene servita solo su
quelle due porte e non è spostabile. Questa variante usa quindi
`tls internal`, cioè l'autorità locale di Caddy, dichiarata
esplicitamente nel `Caddyfile.single-port` perché il comportamento sia
prevedibile e Caddy non tenti ogni volta un rilascio destinato a fallire.

In pratica: **la connessione è cifrata**, ma al primo accesso il browser
mostra un avviso di sicurezza, perché non conosce chi ha emesso il
certificato. Per una dashboard interna è accettabile.

Se l'avviso ti dà fastidio, il certificato radice di Caddy si può
installare sui computer che useranno la dashboard. Lo estrai così:

```bash
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

e lo importi fra le autorità di certificazione attendibili (su macOS:
Accesso Portachiavi → Sistema → trascina il file → doppio clic → "Fidati
sempre"; su Windows: doppio clic → Installa certificato → Computer locale
→ Autorità di certificazione radice attendibili).

Verificato: la catena del certificato servito si verifica contro quel file
radice e copre l'indirizzo in `SITE_HOST` (anche quando è un IP). Quindi
importarlo elimina davvero l'avviso, non lo aggira.

Se invece ti serve un certificato pubblicamente valido, l'unica strada è
che qualcosa risponda sulla 443: la variante B, dietro un reverse proxy
che tiene lui le porte standard.

### Preferisci HTTP semplice?

Se la dashboard è solo su rete interna e l'avviso del certificato ti
pesa più della cifratura, servirla in HTTP su una sola porta richiede due
modifiche:

```ini
SESSION_COOKIE_SECURE=False
```

e due modifiche ai file, perché altrimenti vincono loro:

- togliere `SESSION_COOKIE_SECURE: "True"` dal `docker-compose.yml`
- nel `Caddyfile.single-port`, togliere `tls internal` e il blocco
  globale `default_sni`, e cambiare l'indirizzo del sito da
  `https://{$SITE_HOST:localhost}:8001` a `http://{$SITE_HOST:localhost}:8001`

Senza entrambe le modifiche il login non funziona: il cookie di sessione
resta marcato "secure" e il browser non lo salva su HTTP (vedi la fine
della variante B). È il motivo per cui la variante parte in HTTPS.

---

## 7. Dopo l'avvio, in tutte le varianti

```bash
docker compose ps
```

L'app deve essere `healthy`. Poi apri l'indirizzo e **crea
l'amministratore** nella pagina `/setup` che ti viene proposta: non esiste
una password predefinita, e finché non ne scegli una nessuna pagina è
raggiungibile.

---

## 8. Le porte, in dettaglio

Questa parte merita attenzione: è il punto in cui è più facile aprire in
rete qualcosa senza accorgersene.

| | Cosa fa |
|---|---|
| `expose: "8001"` | raggiungibile dagli altri container della stessa rete. Sull'host non apre niente |
| `ports: "8001:8001"` | pubblicata su **tutte** le interfacce dell'host, quindi anche dall'esterno |
| `ports: "127.0.0.1:8001:8001"` | pubblicata solo sull'host stesso, non dalla rete |

Nella variante A l'app ha solo `expose`. Nella variante B ha la forma
legata a `127.0.0.1`. In nessuna delle due è esposta alla rete.

### Perché non basta il firewall

Su una macchina con `ufw` attivo, una porta pubblicata da Docker **resta
raggiungibile anche se `ufw` la nega**. Non è un errore di
configurazione: Docker inserisce le proprie regole di reindirizzamento
nella tabella `nat` e il traffico verso i container attraversa la catena
`FORWARD`, mentre le regole di `ufw` agiscono su `INPUT`. Il pacchetto non
passa dove `ufw` lo sta aspettando.

Sullo stack avviato si vede così (`iptables -t nat -L DOCKER`):

```
DNAT  tcp dpt:80   to:172.18.0.3:80
DNAT  tcp dpt:443  to:172.18.0.3:443
```

Due regole, per le due porte del proxy. Nessuna menziona la 8001.

**Conseguenza pratica**: su questa macchina, con altri container già
attivi, controlla con quel comando cosa è davvero pubblicato — non fidarti
delle regole di `ufw`. Per limitare per indirizzo IP una porta pubblicata,
le regole vanno nella catena `DOCKER-USER`, che Docker lascia apposta a
disposizione e che viene valutata prima delle sue.

### Una porta che vedrai e non è un problema

`docker compose ps` elenca anche `2019/tcp` sul proxy: è l'interfaccia di
amministrazione di Caddy. Non è pubblicata sull'host e Caddy la lega a
`localhost` *dentro il proprio container*: dal container dell'app il
collegamento viene rifiutato (verificato).

---

## 9. Dove stanno i dati

| Volume | Contenuto |
|---|---|
| `customer-intelligence_db` | database: aziende, cluster, notizie, impostazioni, utenza |
| `customer-intelligence_logos` | logo caricato per il report |
| `customer-intelligence_caddy_data` | certificati HTTPS |
| `customer-intelligence_caddy_config` | stato del proxy |

I dati **sopravvivono** a `docker compose down`, alla ricostruzione
dell'immagine e all'aggiornamento del codice. Verificato distruggendo il
container e ricreandolo: amministratore e dati ancora al loro posto.

Spariscono solo con `docker compose down -v`: non usare `-v` a meno che
sia proprio quello che vuoi.

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

```cron
0 3 * * * cd /opt/customer-intelligence && docker compose exec -T app python -c "import sqlite3; s=sqlite3.connect('/data/app.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()" && docker compose cp app:/data/backup.db ./backups/app-$(date +\%F).db && docker compose exec -T app rm /data/backup.db && find ./backups -name 'app-*.db' -mtime +30 -delete
```

(nel crontab il `%` va scritto `\%`; crea prima la cartella `backups`).

---

## 10. Comandi di tutti i giorni

```bash
cd /opt/customer-intelligence

docker compose logs -f app          # log dell'applicazione
docker compose logs -f proxy        # log del proxy e dei certificati
docker compose restart app          # dopo una modifica al .env
docker compose down                 # ferma (i dati restano)
docker compose up -d                # riavvia
```

Nella variante B ricordati i due `-f`, o imposta `COMPOSE_FILE`.

Gli esiti delle ricerche non stanno nei log di Docker ma in
**Impostazioni > Log delle ricerche**, con filtro per azienda ed esito e
scarico in CSV.

---

## 11. Aggiornare

```bash
cd /opt/customer-intelligence
# backup prima (paragrafo 9)
git pull
docker compose up -d --build
docker image prune -f              # recupera lo spazio delle immagini vecchie
```

Le modifiche allo schema del database vengono applicate da sole
all'avvio: nessuna migrazione da lanciare a mano.

---

## 12. Se qualcosa non va

**`env file ... /.env not found`** → crea il `.env` prima di ogni comando
compose: `cp .env.example .env`.

**`port is already allocated`** oppure
**`bind: address already in use`** → la porta scelta è occupata. Trova da
cosa e spostati:
```bash
sudo ss -tlnp | grep ':8443 '
docker ps -a --format 'table {{.Names}}\t{{.Ports}}' | grep 8443
```
poi cambia `HTTP_PORT`, `HTTPS_PORT` o `APP_PORT` nel `.env`.

**`could not find an available, non-overlapping IPv4 address pool among the defaults`**
→ succede con molti stack Docker sulla stessa macchina: le reti
predefinite sono esaurite. Assegna una sottorete libera a questo stack
aggiungendo in fondo al `docker-compose.yml`:
```yaml
networks:
  internal:
    ipam:
      config:
        - subnet: 172.31.250.0/24
```
Controlla prima che non sia già in uso, e che non si sovrapponga alla tua
LAN o a una VPN:
```bash
docker network inspect $(docker network ls -q) --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}'
ip route
```

**Il proxy si riavvia in continuazione** → è quasi sempre il `Caddyfile`:
```bash
docker compose logs proxy | grep -i error
```
Caddy non parte affatto se il file non è valido.

**Il certificato non viene emesso** →
```bash
docker compose logs proxy | grep -i -E "certificate|acme|challenge"
```
Cause tipiche: il dominio non punta a questo server, la porta 80 non è
raggiungibile da Internet, `HTTP_PORT` è stato spostato (vedi variante C),
o si è superato il limite settimanale di Let's Encrypt per quel dominio.

**L'app resta `starting` e non diventa `healthy`** →
```bash
docker compose logs app | tail -30
```
Il controllo di salute interroga `/login` ogni 30 secondi, con 20 secondi
di tolleranza iniziale.

**Il login rimanda alla pagina di accesso, senza errori** → il proxy
davanti serve in HTTP, oppure non manda `X-Forwarded-Proto: https`. Il
cookie di sessione è "secure" e il browser non lo salva. Si riconosce
dagli strumenti di sviluppo del browser: dopo l'invio del modulo, fra i
cookie non c'è `ci_session`. Vedi la fine della variante B — e non
provarlo su `localhost`, dove funzionerebbe comunque.

**Non riesco più a entrare** → si azzera l'utenza e l'app ripropone
`/setup`:
```bash
docker compose exec -T app python -c "
import sqlite3
c = sqlite3.connect('/data/app.db')
c.execute(\"DELETE FROM app_settings WHERE key LIKE 'ADMIN_%'\")
c.commit()"
docker compose restart app
```

**Permessi sui volumi** → l'applicazione gira come utente `cim`
(uid 10001), non root. Se hai sostituito i volumi con cartelle dell'host:
```bash
sudo chown -R 10001:10001 /percorso/della/cartella
```

---

## 13. Cose da non fare

- **Non aggiungere `--workers` a uvicorn.** La ricerca automatica è uno
  scheduler interno al processo: con più worker partirebbe in ognuno, e ti
  arriverebbero gli stessi report in copia.
- **Non pubblicare la 8001 su `0.0.0.0`** contando sul firewall
  (paragrafo 8). Nella variante B la forma con `127.0.0.1:` davanti è
  quella giusta.
- **Non usare `docker compose down -v`** per un riavvio: `-v` cancella i
  volumi, cioè il database.
- **Non mettere la chiave API nel `docker-compose.yml`.** Sta nel `.env`,
  che non entra nell'immagine: un valore scritto in un livello
  dell'immagine resta leggibile con `docker history`.
