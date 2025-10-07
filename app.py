from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
import io, os, uuid, textwrap

app = FastAPI(title="Photo Banner Bot")

# ----- Config -----
OUTPUT_DIR = "outputs"
FONT_PATHS = [
    "fonts/DejaVuSans-Bold.ttf",   # include this in your repo
    "fonts/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Static (optional for downloads)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ----- Helpers -----
def load_font(preferred_size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, preferred_size)
            except Exception:
                continue
    return ImageFont.load_default()

def fit_text_to_box(draw: ImageDraw.ImageDraw, text: str, font_path_size: int, box_w: int, box_h: int, line_spacing: float = 1.0):
    size = font_path_size
    while size >= 10:
        font = load_font(size)
        max_chars = max(1, int(box_w / (size * 0.55)))
        wrapped = []
        for raw in text.split("\n"):
            wrapped.extend(textwrap.wrap(raw.strip(), width=max_chars) or [""])
        total_h = 0
        for line in wrapped:
            w, h = draw.textbbox((0, 0), line, font=font)[2:]
            total_h += h
            total_h += int(h * (line_spacing - 1))
        if total_h <= box_h:
            return font, wrapped
        size -= 2
    return load_font(10), textwrap.wrap(text, width=max(1, int(box_w / 6))) or [""]

def add_left_banner(img: Image.Image, text: str, width_ratio: float = 0.22,
                    bg_rgba=(0,0,0,180), text_fill=(255,255,255,255), padding_ratio=0.06):
    w, h = img.size
    banner_w = max(40, int(w * width_ratio))
    banner_x0, banner_y0 = 0, 0
    banner_x1, banner_y1 = banner_w, h

    overlay = Image.new("RGBA", img.size, (0,0,0,0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([banner_x0, banner_y0, banner_x1, banner_y1], fill=bg_rgba)
    img = Image.alpha_composite(img.convert("RGBA"), overlay)

    pad = int(banner_w * padding_ratio)
    text_x0 = banner_x0 + pad
    text_y0 = banner_y0 + pad
    text_w = banner_w - (2 * pad)
    text_h = h - (2 * pad)

    draw = ImageDraw.Draw(img)
    font, lines = fit_text_to_box(draw, text, font_path_size=int(banner_w * 0.28), box_w=text_w, box_h=text_h, line_spacing=1.05)

    line_heights = []
    total_h = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lh = bbox[3] - bbox[1]
        line_heights.append(lh)
        total_h += lh
    total_h += int((len(lines) - 1) * (line_heights[0] * 0.05))

    current_y = text_y0 + max(0, (text_h - total_h) // 2)
    for i, line in enumerate(lines):
        lbbox = draw.textbbox((0, 0), line, font=font)
        lw = lbbox[2] - lbbox[0]
        line_x = text_x0 + max(0, (text_w - lw) // 2)
        draw.text((line_x, current_y), line, font=font, fill=text_fill)
        current_y += line_heights[i] + int(line_heights[i] * 0.05)

    return img.convert("RGB")

def sanitize_text(s: str) -> str:
    return " ".join((s or "").strip().split())

# ----- Routes -----
@app.get("/", response_class=HTMLResponse)
def index():
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Photo Banner Bot</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 24px; }
  .card { max-width: 920px; border: 1px solid #e5e7eb; border-radius: 16px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  h1 { margin: 0 0 12px 0; }
  label { display:block; margin-top: 12px; font-weight: 600; }
  input[type="file"], input[type="text"], select { width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .actions { margin-top: 16px; display:flex; gap:8px; flex-wrap: wrap;}
  button { padding: 10px 14px; border: none; border-radius: 10px; cursor:pointer; background:black; color:white; font-weight:600; }
  .note { color:#6b7280; font-size: 13px; }
  .preview { margin-top: 16px; }
  details { margin-top: 12px; }
</style>
<script>
  function setPreset() {
    const preset = document.getElementById('preset').value;
    if (!preset) return;
    document.getElementById('text').value = preset;
  }
</script>
</head>
<body>
  <div class="card">
    <h1>Photo Banner Bot</h1>
    <p class="note">Upload a listing photo, pick a preset or type custom copy, and get a left-side banner that fits perfectly.</p>

    <form action="/generate" method="post" enctype="multipart/form-data" target="_blank">
      <label>Photo (JPG/PNG)</label>
      <input type="file" name="photo" accept="image/*" required />

      <div class="row">
        <div>
          <label>Preset (one-click)</label>
          <select id="preset" onchange="setPreset()">
            <option value="">— Select a preset —</option>
            <option>PRICE DROP</option>
            <option>1/0 BUY DOWN STARTING @ 3.99%</option>
            <option>OPEN HOUSE THIS SAT 11–2</option>
            <option>BUILDER INCENTIVE: $15,000</option>
            <option>NOW FHA/VA ELIGIBLE</option>
          </select>
        </div>
        <div>
          <label>Custom Text (overrides empty)</label>
          <input type="text" id="text" name="text" placeholder="Type your banner text…" />
        </div>
      </div>

      <div class="row">
        <div>
          <label>Banner Width % (left strip)</label>
          <input type="text" name="width_pct" value="22" />
          <span class="note">Typical: 15–30. Wider = bigger strip.</span>
        </div>
        <div>
          <label>Opacity (0–255)</label>
          <input type="text" name="opacity" value="180" />
          <span class="note">180 is a nice translucent black.</span>
        </div>
      </div>

      <details>
        <summary>Advanced (optional)</summary>
        <div class="row">
          <div>
            <label>Banner Color (RGBA, comma-sep)</label>
            <input type="text" name="bg_rgba" value="0,0,0,180" />
          </div>
          <div>
            <label>Text Color (RGBA, comma-sep)</label>
            <input type="text" name="text_rgba" value="255,255,255,255" />
          </div>
        </div>
      </details>

      <div class="actions">
        <button type="submit">Generate Banner</button>
      </div>
    </form>
    <p class="note preview">Result opens in a new tab and is saved under <code>/outputs</code>.</p>
  </div>
</body>
</html>
    """
    return HTMLResponse(content=html)

@app.post("/generate")
async def generate(
    photo: UploadFile = File(...),
    text: str = Form(""),
    width_pct: str = Form("22"),
    opacity: str = Form("180"),
    bg_rgba: str = Form("0,0,0,180"),
    text_rgba: str = Form("255,255,255,255"),
):
    try:
        raw = await photo.read()
        img = Image.open(io.BytesIO(raw)).convert("RGBA")

        txt = sanitize_text(text) or "PRICE DROP"
        try:
            width_ratio = max(0.10, min(0.40, float(width_pct)/100.0))
        except:
            width_ratio = 0.22

        def parse_rgba(s, default):
            try:
                parts = [int(x.strip()) for x in s.split(",")]
                if len(parts) == 4:
                    return tuple(parts)
            except:
                pass
            return default

        bg = parse_rgba(bg_rgba, (0,0,0,int(opacity or "180")))
        fg = parse_rgba(text_rgba, (255,255,255,255))

        out = add_left_banner(img, txt, width_ratio=width_ratio, bg_rgba=bg, text_fill=fg)

        file_id = str(uuid.uuid4())[:8]
        base, ext = os.path.splitext(photo.filename or "image.jpg")
        out_name = f"{base}_{file_id}.jpg"
        out_path = os.path.join(OUTPUT_DIR, out_name)
        out.save(out_path, quality=95)

        return FileResponse(out_path, media_type="image/jpeg", filename=out_name)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# Health check for Render
@app.get("/healthz")
def healthz():
    return {"ok": True}
