# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.
Il formato segue [Keep a Changelog](https://keepachangelog.com/) e il progetto
usa [Semantic Versioning](https://semver.org/lang/it/).

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
