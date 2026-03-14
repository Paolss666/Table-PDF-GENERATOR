import io
from concurrent.futures import ThreadPoolExecutor, as_completed

import cairosvg
import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# ── Constants ────────────────────────────────────────────────────────────────

DPI = 150
TABLE_NUMBER_Y = 0.35   # vertical center of table number text (relative to image height)
QR_Y           = 0.55   # vertical center of QR code (relative to image height)
QR_SIZE_RATIO  = 1 / 3  # QR size relative to min(width, height)
MAX_TEXT_WIDTH = 0.80   # max text width relative to image width
MIN_FONT_SIZE  = 16

SYSTEM_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _svg_to_png(svg_bytes: bytes) -> bytes:
    """Convert SVG to PNG at the configured DPI."""
    return cairosvg.svg2png(bytestring=svg_bytes, scale=DPI / 96)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Return the first available system bold font, falling back to Pillow default."""
    for path in SYSTEM_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int) -> ImageFont.FreeTypeFont:
    """Shrink font size until the text fits within max_width."""
    img_width = int(max_width / MAX_TEXT_WIDTH)
    font_size = max(MIN_FONT_SIZE * 3, img_width // 6)
    font = _load_font(font_size)

    while font_size > MIN_FONT_SIZE:
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            break
        font_size -= 4
        font = _load_font(font_size)

    return font


def _make_qr(data: str, size: int) -> Image.Image:
    """Generate a QR code image with a transparent background."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    # Make white pixels transparent
    pixels = img.getdata()
    img.putdata([
        (r, g, b, 0) if r > 200 and g > 200 and b > 200 else (r, g, b, a)
        for r, g, b, a in pixels
    ])

    return img.resize((size, size), Image.LANCZOS)


def _page_layout(image_size: tuple[int, int]) -> tuple[float, float, float, float]:
    """Return (draw_w, draw_h, x_offset, y_offset) to center the image on an A4 page."""
    img_w, img_h = image_size
    a4_w, a4_h = A4
    scale    = min(a4_w / img_w, a4_h / img_h)
    draw_w   = img_w * scale
    draw_h   = img_h * scale
    x_offset = (a4_w - draw_w) / 2
    y_offset = (a4_h - draw_h) / 2
    return draw_w, draw_h, x_offset, y_offset


# ── Core image builder ────────────────────────────────────────────────────────

def _build_retro_page(retro_png: bytes, table_number: str, wr_code: str) -> bytes:
    """Overlay table number and QR code onto the retro PNG and return the result as PNG bytes."""
    img  = Image.open(io.BytesIO(retro_png)).convert("RGBA")
    w, h = img.size
    cx   = w // 2
    draw = ImageDraw.Draw(img)

    # Table number
    font  = _fit_font(draw, table_number, int(w * MAX_TEXT_WIDTH))
    bbox  = draw.textbbox((0, 0), table_number, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (cx - tw // 2, int(h * TABLE_NUMBER_Y) - th // 2),
        table_number,
        fill=(0, 0, 0, 255),
        font=font,
    )

    # QR code
    qr_size = int(min(w, h) * QR_SIZE_RATIO)
    qr_img  = _make_qr(wr_code, size=qr_size)
    img.paste(qr_img, (cx - qr_size // 2, int(h * QR_Y)), mask=qr_img.split()[3])

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


# ── Public API ────────────────────────────────────────────────────────────────

def generate_tables_pdf(
    fronte_svg: bytes,
    retro_svg: bytes,
    table_numbers: list[str],
    wr_codes: list[str],
    table_number_element_id: str | None = None,
    qr_placeholder_id: str | None = None,
) -> bytes:
    """
    Generate a PDF with 2 pages per table: front (unchanged) + back (table number + QR).

    SVGs are converted to PNG once. Back pages are built in parallel for performance.
    Returns the complete PDF as bytes.
    """
    fronte_png     = _svg_to_png(fronte_svg)
    retro_png_base = _svg_to_png(retro_svg)
    draw_w, draw_h, x, y = _page_layout(Image.open(io.BytesIO(fronte_png)).size)

    # Build all retro pages in parallel
    pairs = list(zip(table_numbers, wr_codes))
    retro_pages: dict[int, bytes] = {}

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_build_retro_page, retro_png_base, tn, wc): idx
            for idx, (tn, wc) in enumerate(pairs)
        }
        for future in as_completed(futures):
            retro_pages[futures[future]] = future.result()

    # Assemble PDF in order
    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)

    for idx in range(len(pairs)):
        c.drawImage(ImageReader(io.BytesIO(fronte_png)), x, y, draw_w, draw_h)
        c.showPage()
        c.drawImage(ImageReader(io.BytesIO(retro_pages[idx])), x, y, draw_w, draw_h)
        c.showPage()

    c.save()
    pdf_buf.seek(0)
    return pdf_buf.read()
