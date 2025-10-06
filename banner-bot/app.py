from fastapi import FastAPI, UploadFile, File, Form, Header
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
import io, os, uuid
from fastapi.staticfiles import StaticFiles
app = FastAPI(title="Photo Banner Bot")
app.mount("/static", StaticFiles(directory="static"), name="static")
# --- Settings ---
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/tmp/outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
MAX_W = int(os.environ.get("MAX_LONG_EDGE", 2048))
API_KEY = os.environ.get("API_KEY", "")           # optional: if set, required for API calls
INVITE_CODE = os.environ.get("INVITE_CODE", "")     # optional: if set, required in the HTML form

# Allow Canva/localhost etc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Helpers ---

def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def resize_long_edge(img: Image.Image, long_edge: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= long_edge:
        return img
    if w >= h:
        nh = int(h * (long_edge / w))
        return img.resize((long_edge, nh), Image.LANCZOS)
    else:
        nw = int(w * (long_edge / h))
        return img.resize((nw, long_edge), Image.LANCZOS)


def ensure_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA") if img.mode != "RGBA" else img


def text_wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int):
    words = text.split()
    lines, line = [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def add_left_strip(img: Image.Image, text: str, *, strip_rel_width=0.32, 
                    padding=24, font_size_rel=0.05, 
                    strip_color=(0, 0, 0, 180), text_color=(255, 255, 255, 255),
                    corner_radius_rel=0.02):
    """Classic vertical rectangle on the LEFT; auto-wrap text; rounded inner corner."""
    img = ensure_rgba(img)
    W, H = img.size
    strip_w = int(W * strip_rel_width)
    radius = int(min(W, H) * corner_radius_rel)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(overlay)
    rect = (0, 0, strip_w, H)
    o.rounded_rectangle(rect, radius=radius, fill=strip_color)

    font = load_font(max(14, int(H * font_size_rel)))
    draw = ImageDraw.Draw(overlay)
    max_text_w = strip_w - 2 * padding
    lines = text_wrap(draw, text, font, max_text_w)

    line_h = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
    total_h = len(lines) * line_h + (len(lines) - 1) * int(line_h * 0.25)
    y = (H - total_h) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text((padding + (max_text_w - w) // 2, y), line, font=font, fill=text_color)
        y += int(line_h * 1.25)

    return Image.alpha_composite(img, overlay)


def add_bottom_ribbon(img: Image.Image, text: str, *, ribbon_rel_height=0.16, padding=24,
                      font_size_rel=0.06, ribbon_color=(0,0,0,170), text_color=(255,255,255,255)):
    img = ensure_rgba(img)
    W, H = img.size
    ribbon_h = int(H * ribbon_rel_height)
    y0 = H - ribbon_h

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(overlay)
    o.rectangle((0, y0, W, H), fill=ribbon_color)

    font = load_font(max(14, int(H * font_size_rel)))
    draw = ImageDraw.Draw(overlay)
    max_text_w = W - 2 * padding
    lines = text_wrap(draw, text, font, max_text_w)

    line_h = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
    total_h = len(lines) * line_h + (len(lines) - 1) * int(line_h * 0.25)
    y = y0 + (ribbon_h - total_h)//2
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((W - w)//2, y), line, font=font, fill=text_color)
        y += int(line_h * 1.25)

    return Image.alpha_composite(img, overlay)

# --- Brands & Presets ---
BRANDS = {
    "coventry": {"strip_color": (7, 42, 80, 200), "text_color": (255,255,255,255),
                 "label": "COVENTRY CLOSE-OUT SPECIAL", "style": "left_strip"},
    "davidson": {"strip_color": (0, 0, 0, 180), "text_color": (255,255,0,255),
                 "label": "DAVIDSON INCENTIVE", "style": "bottom_ribbon"},
}

PRESETS = {
    1: {"label": "1/0 BUY DOWN STARTING @ 3.99%", "style": "left_strip"},
    2: {"label": "PRICE IMPROVEMENT", "style": "bottom_ribbon"},
    3: {"label": "BUILDER CLOSE-OUT SPECIAL", "style": "left_strip"},
    4: {"label": "VA & FIRST‑TIME BUYER FRIENDLY", "style": "bottom_ribbon"},
    5: {"label": "OPEN HOUSE THIS WEEKEND", "style": "left_strip"},
}

@app.get("/")
def index():
    # Tiny UI for manual uploads / quick tests with Invite Code
    code_input = """
      <div>Invite code (ask your coach):
        <input type='password' name='invite' placeholder='Required if set'>
      </div>""" if INVITE_CODE else ""
    html = f"""
    <html><body style='font-family: system-ui; padding: 24px;'>
      <h2>Photo Banner Bot</h2>
      <form action='/make_banner' method='post' enctype='multipart/form-data'>
        <div><input type='file' name='file' required></div>
        <div>Preset (1-5): <input type='number' name='preset' value='1' min='0' max='5'></div>
        <div>Custom text (overrides preset): <input type='text' name='text' style='width:420px;' placeholder='e.g., 1/0 BUY DOWN STARTING @ 3.99%'></div>
        <div>Style: 
          <select name='style'>
            <option value='auto' selected>auto</option>
            <option value='left_strip'>left_strip</option>
            <option value='bottom_ribbon'>bottom_ribbon</option>
          </select>
        </div>
        <div>Brand (optional): <input name='brand' placeholder='coventry, davidson'></div>
        <div>Long-edge max px (default 2048): <input type='number' name='max_px' value='2048'></div>
        {code_input}
        <button type='submit'>Make banner</button>
      </form>
      <p>GET <code>/presets</code> • GET <code>/healthz</code></p>
    </body></html>
    """
    return HTMLResponse(html)

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/presets")
def presets():
    return {"brands": list(BRANDS.keys()), "presets": PRESETS}

@app.post("/make_banner")
async def make_banner(
    file: UploadFile = File(...),
    preset: int = Form(1),
    text: str = Form(""),
    style: str = Form("auto"),
    brand: str = Form(""),
    max_px: int = Form(None),
    x_api_key: str = Header(None),
    invite: str = Form("")
):
    # Gatekeeping: API key for programmatic calls; invite code for form usage
    if API_KEY and x_api_key != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if INVITE_CODE and invite != INVITE_CODE and not x_api_key:
        return JSONResponse({"error": "Invite required"}, status_code=401)

    content = await file.read()
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        return JSONResponse({"error": "Unsupported image"}, status_code=400)

    img = resize_long_edge(img, max_px or MAX_W)

    # Resolve text/style from preset or brand
    chosen = PRESETS.get(preset)
    if text.strip():
        label = text.strip()
    else:
        label = (chosen["label"] if chosen else "")

    if style == "auto":
        style = (chosen["style"] if chosen else "left_strip")

    # Brand overrides
    strip_color = None
    text_color = None
    if brand and brand.lower() in BRANDS:
        b = BRANDS[brand.lower()]
        label = label or b.get("label", label)
        style = b.get("style", style)
        strip_color = b.get("strip_color")
        text_color = b.get("text_color")

    if style == "left_strip":
        out = add_left_strip(img, label,
                             strip_color=strip_color or (0,0,0,180),
                             text_color=text_color or (255,255,255,255))
    elif style == "bottom_ribbon":
        out = add_bottom_ribbon(img, label,
                                ribbon_color=strip_color or (0,0,0,170),
                                text_color=text_color or (255,255,255,255))
    else:
        return JSONResponse({"error": "Unknown style"}, status_code=400)

    out_id = str(uuid.uuid4()) + ".png"
    out_path = os.path.join(OUTPUT_DIR, out_id)
    out.convert("RGB").save(out_path, quality=95)

    return {"id": out_id, "url": f"/outputs/{out_id}", "width": out.width, "height": out.height}

@app.get("/outputs/{file_id}")
async def get_output(file_id: str):
    path = os.path.join(OUTPUT_DIR, file_id)
    if not os.path.exists(path):
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(path)
