# Photo Banner Bot
FastAPI service that adds MLS-safe banners to listing photos. Presets (1–5), brands, and custom text.

## Local run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export INVITE_CODE=coach123        # optional
export API_KEY=supersecret         # optional
uvicorn app:app --reload
```
Open http://127.0.0.1:8000/ to use the tiny upload form. If `INVITE_CODE` is set, type it in the form.

## API
- `GET /healthz` → `{ ok: true }`
- `GET /presets` → brands + preset map
- `POST /make_banner` (multipart form)
  - headers: `X-API-Key: <key>` if `API_KEY` set
  - form fields:
    - `file`: image (required)
    - `preset`: 0–5 (0 means none)
    - `text`: custom text (overrides preset)
    - `style`: `auto|left_strip|bottom_ribbon`
    - `brand`: `coventry|davidson|...`
    - `max_px`: optional long-edge size (default 2048)
    - `invite`: only for HTML form if `INVITE_CODE` set

**cURL**
```bash
curl -s -H 'X-API-Key: supersecret'   -F file=@sample.jpg -F preset=1 -F style=auto   -F text='1/0 BUY DOWN STARTING @ 3.99%'   https://YOUR-RENDER-URL/make_banner | jq
```
Then:
```bash
curl -o out.jpg https://YOUR-RENDER-URL/outputs/<id>.png
```

## Render deployment
Set env vars as needed:
- `INVITE_CODE` (optional, gates the HTML form)
- `API_KEY` (optional, required for API calls)
- `MAX_LONG_EDGE` (default 2048)

### Standard Web Service
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`

### Blueprint deploy
`render.yaml` included.

## Brands
Edit `BRANDS` in `app.py` to add your builder colorways and default labels.

## MLS notes
- Text auto-wrap + centering avoids cut-offs.
- Use `left_strip` for the classic vertical rectangle.
