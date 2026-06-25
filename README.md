# Catania Spesa Top

App mobile Expo + backend FastAPI per confrontare le offerte dei supermercati di Catania.

## URL di produzione

- Backend Render: `https://catania-spesa-top.onrender.com`
- Endpoint principale usato dall'app: `https://catania-spesa-top.onrender.com/offers`
- Metadata pubblici: `https://catania-spesa-top.onrender.com/metadata`

Il frontend continua a usare `/offers` come endpoint principale. Non è stato cambiato.

## Struttura backend

```text
backend/
  app/
    config.py
    database.py
    main.py
    schemas.py
    services/
      catalog.py
      flyer_fetcher.py
      flyer_parser.py
      flyer_sources.py
      flyer_updater.py
      offer_extractor.py
      offer_normalizer.py
      offers.py
      source_discovery.py
      source_registry.py
      update_metadata.py
      update_runner.py
      vision.py
  data/
    demo_offers.json
  requirements.txt
frontend/
  App.js
  app.json
Dockerfile
```

## Endpoint disponibili

- `GET /health`
- `GET /offers`
- `GET /stores`
- `GET /offers/best`
- `GET /metadata`
- `POST /offers/ingest`
- `POST /admin/update-offers`
- `POST /admin/update-store/{store_name}`

Alias di compatibilità ancora disponibili:

- `GET /api/health`
- `GET /api/offers`
- `GET /api/stores`
- `GET /api/offers/best`
- `GET /api/metadata`

## Come funzionano gli aggiornamenti automatici

1. Il backend carica le fonti configurabili da `backend/app/services/source_registry.py`.
2. `source_discovery.py` controlla la sorgente e prova a trovare un nuovo volantino o una pagina offerte.
3. `flyer_fetcher.py` scarica PDF, immagini o HTML con timeout, retry limitato e user-agent esplicito.
4. `flyer_parser.py` estrae offerte da HTML oppure delega PDF e immagini a `vision.py`.
5. `offer_normalizer.py` normalizza i dati nel formato compatibile con `/offers`.
6. `update_runner.py` confronta URL e hash, aggiorna solo le fonti cambiate e non blocca tutto se una singola fonte fallisce.
7. `update_metadata.py` salva stato, errori, ultimo controllo e ultimo aggiornamento riuscito.
8. `/offers` espone solo offerte attive e non scadute.
9. `/metadata` espone lo stato pubblico dell'aggiornamento automatico periodico.

## Fonti configurabili per supermercato

I supermercati supportati sono:

- Coop
- Conad
- Decò
- Famila
- MD
- Eurospin
- Lidl
- Spaccio Alimentare
- Crai

La configurazione delle fonti vive in:

- `backend/app/services/source_registry.py`

Ogni fonte contiene almeno:

- `store`
- `source_url`
- `source_type`
- `city_filter`
- `province_filter`
- `active`
- `priority`
- `parser_strategy`
- `notes`
- `selectors`
- `direct_flyer_url`
- `store_location`

Per evitare URL inventati, le fonti non ancora verificate usano il placeholder esplicito `TODO_VERIFY_SOURCE_URL`.

Finché una fonte resta su `TODO_VERIFY_SOURCE_URL`, gli endpoint admin la considerano configurata solo a livello strutturale e la saltano con stato `pending_configuration` o `idle`, senza inventare offerte.

## Fonti reali configurate

Al momento le fonti reali attive e verificate sono:

- CRAI Cibele Catania:
  `https://crai.it/negozi-e-volantini/6257-crai-cibele`
- Eurospin Catania Via Castaldi:
  `http://eurospin.it/punti-vendita/catania-via-castaldi/`

Comportamento attuale:

- Eurospin viene letto da una pagina reale del punto vendita e poi dal viewer ufficiale, con estrazione offerte tramite API del viewer.
- Crai viene rilevato correttamente come PDF reale del punto vendita, ma per estrarre offerte vere dal PDF serve `VISION_PROVIDER=openai` oppure un caricamento manuale verificato.
- Le altre insegne restano configurabili, ma inattive finché non viene impostato un URL reale verificato.

## Variabili ambiente backend

Esempio completo in `backend/.env.example`:

```env
APP_NAME="Catania Spesa Top API"
ENVIRONMENT="development"
DATABASE_PATH="backend/data/offers.db"
UPLOAD_DIR="backend/uploads"
POPPLER_PATH=""
SEED_DEMO_DATA="true"
CORS_ORIGINS="*"
ADMIN_UPDATE_TOKEN=""
UPDATE_USER_AGENT="CataniaSpesaTopBot/1.0 (+https://catania-spesa-top.onrender.com)"
UPDATE_TIMEOUT_SECONDS="25"
MAX_FLYERS_PER_STORE="3"
VISION_PROVIDER="mock"
OPENAI_API_KEY=""
OPENAI_MODEL="gpt-4o"
OPENAI_IMAGE_MAX_PX="1800"
OPENAI_PDF_PAGES_PER_REQUEST="4"
PDF_RENDER_DPI="180"
REQUEST_TIMEOUT_SECONDS="90"
```

Su Render devi impostare almeno:

- `ADMIN_UPDATE_TOKEN`

Se usi OCR OpenAI in produzione:

- `VISION_PROVIDER=openai`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

## Avvio locale backend

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
backend\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Il container produzione usa:

```bash
gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:${PORT:-8000}
```

## PDF e OCR

Per convertire i PDF prima dell'OCR viene usato `pdf2image`.

Su Windows:

1. Installa Poppler.
2. Verifica `pdftoppm -h`.
3. Se necessario imposta `POPPLER_PATH` verso la cartella `bin` di Poppler.

Esempio:

```env
POPPLER_PATH="C:\\poppler\\Library\\bin"
```

## Aggiornamento manuale delle offerte

L'endpoint `POST /offers/ingest` accetta:

- `store`
- `replace_existing=true|false`
- `file` in formato PDF, JPG, JPEG o PNG

Esempio `curl`:

```bash
curl -X POST "https://catania-spesa-top.onrender.com/offers/ingest" \
  -F "store=Crai" \
  -F "replace_existing=true" \
  -F "file=@volantino-crai.pdf;type=application/pdf"
```

Questo fallback serve quando una fonte online non è facilmente leggibile.

## Aggiornamento automatico tramite endpoint admin

Aggiorna tutte le fonti attive:

```bash
curl -X POST "https://catania-spesa-top.onrender.com/admin/update-offers" \
  -H "Authorization: Bearer IL_TUO_ADMIN_UPDATE_TOKEN"
```

Aggiorna un solo supermercato:

```bash
curl -X POST "https://catania-spesa-top.onrender.com/admin/update-store/Crai" \
  -H "Authorization: Bearer IL_TUO_ADMIN_UPDATE_TOKEN"
```

```bash
curl -X POST "https://catania-spesa-top.onrender.com/admin/update-store/Eurospin" \
  -H "Authorization: Bearer IL_TUO_ADMIN_UPDATE_TOKEN"
```

Risposta tipica:

```json
{
  "status": "ok",
  "stores_checked": ["Crai", "Conad"],
  "stores_updated": ["Crai"],
  "sources_checked": 2,
  "flyers_found": 1,
  "flyers_changed": 1,
  "offers_extracted": 34,
  "offers_added": 20,
  "offers_updated": 14,
  "offers_skipped": 0,
  "errors": [],
  "started_at": "2026-06-20T09:30:00",
  "finished_at": "2026-06-20T09:30:18"
}
```

## Metadata pubblici

`GET /metadata` restituisce:

- `last_successful_update`
- `last_attempted_update`
- `last_check`
- `offers_count`
- `active_offers_count`
- `stores_supported`
- `stores_updated`
- `sources_checked`
- `last_errors`
- `status`
- `next_suggested_check`
- `data_mode`

Esempio:

```json
{
  "status": "ok",
  "last_successful_update": "2026-06-20T09:30:00",
  "last_attempted_update": "2026-06-20T09:30:00",
  "last_check": "2026-06-20T09:30:00",
  "offers_count": 248,
  "active_offers_count": 248,
  "stores_supported": ["Coop", "Conad", "Crai"],
  "stores_updated": ["Crai", "Conad"],
  "sources_checked": 3,
  "last_errors": [],
  "next_suggested_check": "2026-06-20T21:30:00",
  "data_mode": "live"
}
```

## Schedulazione consigliata

Render free può andare in sleep, quindi è meglio chiamare l'endpoint admin da un cron esterno.

Frequenze consigliate:

- controllo leggero ogni 12 ore
- aggiornamento completo una volta al giorno
- evitare polling aggressivo

Opzioni pratiche:

- [cron-job.org](https://cron-job.org)
- GitHub Actions schedule
- Render Cron Job, se disponibile nel piano

Puoi chiamare `POST /admin/update-offers` ogni 12 ore oppure una volta al giorno, in base a quanto spesso vuoi controllare i volantini.

### Esempio GitHub Actions

```yaml
name: Update supermarket offers

on:
  schedule:
    - cron: "0 */12 * * *"
  workflow_dispatch:

jobs:
  update-offers:
    runs-on: ubuntu-latest
    steps:
      - name: Call update endpoint
        run: |
          curl -X POST "https://catania-spesa-top.onrender.com/admin/update-offers" \
            -H "Authorization: Bearer ${{ secrets.ADMIN_UPDATE_TOKEN }}"
```

## Frontend

Variabile ambiente:

```env
EXPO_PUBLIC_API_BASE_URL=https://catania-spesa-top.onrender.com
```

Avvio locale:

```powershell
cd frontend
npm install
npx expo start
```

Il frontend:

- legge le offerte da `/offers`
- legge i metadata da `/metadata`
- continua a funzionare anche se una fonte fallisce, finché `/offers` ha dati attivi o in cache
- non dichiara aggiornamento in tempo reale

## Build Android con Expo EAS

```powershell
cd frontend
eas build --platform android --profile preview
```

## Verifiche rapide

- `GET /health`
- `GET /offers`
- `GET /metadata`
- `POST /admin/update-offers`
- `POST /admin/update-store/Crai`

## Note importanti

- `/offers` è rimasto compatibile con il frontend esistente.
- Se una fonte fallisce, le offerte precedenti restano disponibili.
- Il backend non inventa offerte o prezzi: se il parser non è sicuro, scarta il dato o segnala errore nei metadata.
- I dati demo restano chiaramente tracciabili tramite `data_mode=demo` finché non arrivano aggiornamenti reali o upload manuali.
