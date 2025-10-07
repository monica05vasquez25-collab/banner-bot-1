from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
import io, os, uuid, textwrap
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageDraw, ImageFont, ImageColor
import io, os, uuid

# --- eXp brand color presets ---
# Alpha 180 ≈ nice translucent overlay
EXP_PRESETS = {
    "exp-blue":   {"banner": (25, 70, 157, 180),  "text": (255, 255, 255, 255)},  # #19469D
    "deep-navy":  {"banner": (0, 2, 26, 180),     "text": (255, 255, 255, 255)},  # #00021A
    "gold":       {"banner": (249, 168, 26, 180), "text": (0, 0, 0, 255)},        # #F9A81A
    "orange":     {"banner": (245, 130, 31, 180), "text": (0, 0, 0, 255)},        # #F5821F
}

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
    """Loads Greycliff if available, else falls back to a system font."""
    font_dir = os.path.join(os.path.dirname(__file__), "fonts")

    # Path to your Greycliff Bold font
    greycliff_path = os.path.join(font_dir, "GreycliffCF-Bold.otf")

    # Try Greycliff first
    if os.path.exists(greycliff_path):
        try:
            return ImageFont.truetype(greycliff_path, preferred_size)
        except Exception as e:
            print("Error loading Greycliff:", e)

    # Fallback options (system fonts)
    for candidate in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, preferred_size)

    # Last resort fallback
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
<!-- eXp Color Presets -->
<hr>
<label for="color_preset"><b>Color Preset</b></label>
<select id="color_preset" name="color_preset">
  <option value="">— Custom (Use RGBA below) —</option>
  <option value="exp-blue">eXp Blue</option>
  <option value="deep-navy">Deep Navy</option>
  <option value="gold">Gold</option>
  <option value="orange">Orange</option>
</select>
<small>Pick an eXp brand color preset or leave blank to use custom RGBA values.</small>

<!-- Capsule Badge -->
<hr>
<label><input type="checkbox" name="enable_badge"> Add Capsule Badge</label>

<div style="margin:6px 0 12px 20px;">
  <label for="badge_text">Badge Text</label>
  <input id="badge_text" name="badge_text" placeholder="PRICE DROP">

  <label for="badge_corner" style="margin-left:8px;">Badge Position</label>
  <select id="badge_corner" name="badge_corner">
    <option value="top-right">Top Right</option>
    <option value="top-left">Top Left</option>
  </select>
  <small>Capsule auto-sizes to fit text.</small>
</div>

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

@app.post("/generate")
async def generate(
    photo: UploadFile = File(...),
    text: str = Form(""),
    width_pct: str = Form("22"),
    opacity: str = Form("180"),
    bg_rgba: str = Form("0,0,0,180"),
    text_rgba: str = Form("255,255,255,255"),
    # new fields
    color_preset: str = Form(""),
    enable_badge: str = Form("off"),
    badge_text: str = Form(""),
    badge_corner: str = Form("top-right"),
):

    try:
        from io import BytesIO
        import re

        # Load image
        raw = await photo.read()
        img = Image.open(BytesIO(raw)).convert("RGBA")

        # --- parse form fields ---
        banner_pct = float(width_pct or "22")
        alpha = int(opacity or "180")

        def parse_rgba(s, default):
            try:
                parts = [int(x.strip()) for x in s.split(",")]
                if len(parts) == 4:
                    return tuple(parts)
            except Exception:
                pass
            return default

        banner_rgba = parse_rgba(bg_rgba, (0, 0, 0, alpha))
        if banner_rgba[3] != alpha:
            banner_rgba = (banner_rgba[0], banner_rgba[1], banner_rgba[2], alpha)
        text_color = parse_rgba(text_rgba, (255, 255, 255, 255))

        # --- eXp preset override ---
        preset = color_preset.strip()
        if preset in EXP_PRESETS:
            banner_rgba = EXP_PRESETS[preset]["banner"]
            text_color = EXP_PRESETS[preset]["text"]

        # --- draw left banner with autofit ---
        message = text.strip() or "PRICE DROP"
        result = draw_banner_with_autofit(
            img=img,
            banner_pct=banner_pct,
            banner_rgba=banner_rgba,
            text_rgba=text_color,
            message=message,
        )

        # --- capsule badge (optional) ---
        if enable_badge == "on" and badge_text.strip():
            badge_alpha = min(230, banner_rgba[3] + 40)
            badge_fill = (banner_rgba[0], banner_rgba[1], banner_rgba[2], badge_alpha)
            result = draw_capsule_badge(
                base=result,
                text=badge_text.strip(),
                badge_rgba=badge_fill,
                text_rgba=text_color,
                corner=badge_corner or "top-right",
            )

        # --- save final image ---
        OUTPUT_DIR = "outputs"
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        def _slug(s):
            s = s.lower().strip()
            s = re.sub(r"[^a-z0-9]+", "-", s)
            return re.sub(r"-+", "-", s).strip("-") or "banner"

        base_name = os.path.splitext(photo.filename or "photo")[0]
        label_src = badge_text if (enable_badge == "on" and badge_text) else message
        out_name = f"banner-{_slug(label_src)[:30]}-{_slug(base_name)}.jpg"
        out_path = os.path.join(OUTPUT_DIR, out_name)

        result_rgb = result.convert("RGB")
        result_rgb.save(out_path, "JPEG", quality=92, optimize=True)

        return FileResponse(out_path, media_type="image/jpeg", filename=out_name)




    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# Health check for Render
@app.get("/healthz")
def healthz():
    return {"ok": True}
