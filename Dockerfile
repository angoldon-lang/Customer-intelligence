# Le dipendenze sono installate in uno stadio separato: nell'immagine
# finale finisce solo il risultato, non pip, la cache e gli header.
FROM python:3.13-slim AS build

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.13-slim

# Utente senza privilegi: se un giorno la dashboard e' esposta in rete, un
# problema nell'applicazione non trova root dentro al container.
RUN useradd --system --create-home --uid 10001 cim

COPY --from=build /install /usr/local

WORKDIR /app
COPY app/ ./app/

# /data tiene il database, app/static/branding il logo del report: sono i
# due percorsi su cui l'applicazione scrive, montati come volumi dal
# compose. Vengono creati qui con il proprietario giusto, altrimenti
# Docker li creerebbe di root al primo avvio e l'utente cim non potrebbe
# scriverci.
RUN mkdir -p /data /app/app/static/branding \
    && chown -R cim:cim /data /app/app/static/branding

USER cim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=sqlite:////data/app.db \
    HOST=0.0.0.0 \
    PORT=8001

# Dichiara la porta a scopo di documentazione: NON la pubblica sull'host.
# Il compose non mappa questa porta, l'applicazione e' raggiungibile solo
# dal reverse proxy sulla rete interna di Docker.
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/login', timeout=4).status < 500 else 1)"]

# Un solo worker, di proposito: la ricerca automatica e' uno scheduler
# interno al processo. Con piu' worker partirebbe in ognuno e lo stesso
# report verrebbe inviato piu' volte.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
