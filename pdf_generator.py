import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import qrcode
from PIL import Image, ImageDraw, ImageFont
import cairosvg
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


def _svg_to_png(svg_bytes: bytes, dpi: int = 150) -> bytes:
    """Convert SVG bytes to PNG bytes using cairosvg. Scale is derived from DPI (SVG default is 96dpi)."""
    scale = dpi / 96
    return cairosvg.svg2png(bytestring=svg_bytes, scale=scale)


def _generate_qr(data: str, size: int = 300) -> Image.Image:
    """Generate a QR code with transparent background, resized to the given pixel size."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    # Replace white pixels with transparent
    pixels = img.getdata()
    transparent_pixels = [
        (r, g, b, 0) if r > 200 and g > 200 and b > 200 else (r, g, b, a)
        for r, g, b, a in pixels
    ]
    img.putdata(transparent_pixels)
    return img.resize((size, size), Image.LANCZOS)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try common system font paths and return the first available bold font at the given size."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _build_retro_image(retro_png: bytes, table_number: str, wr_code: str) -> bytes:
    """
    Overlay table number text and QR code onto the retro PNG.
    All positions are relative to image dimensions so it works with any SVG size.
    - Table number is drawn at ~35% from the top, horizontally centered
    - QR code is drawn at ~55% from the top, horizontally centered
    """
    img = Image.open(io.BytesIO(retro_png)).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    cx = w // 2

    # Draw table number centered at 35% height — shrink font until text fits within 80% of image width
    max_text_width = int(w * 0.80)
    font_size = max(48, w // 6)
    font = _get_font(font_size)
    while font_size > 16:
        bbox = draw.textbbox((0, 0), str(table_number), font=font)
        if (bbox[2] - bbox[0]) <= max_text_width:
            break
        font_size -= 4
        font = _get_font(font_size)
    text = str(table_number)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text(
        (cx - text_w // 2, int(h * 0.35) - text_h // 2),
        text,
        fill=(0, 0, 0, 255),
        font=font,
    )

    # Draw QR code centered at 55% height — use alpha mask for transparent background
    qr_size = min(w, h) // 3
    qr_img = _generate_qr(wr_code, size=qr_size)
    img.paste(qr_img, (cx - qr_size // 2, int(h * 0.55)), mask=qr_img.split()[3])

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def generate_tables_pdf(
    fronte_svg: bytes,
    retro_svg: bytes,
    table_numbers: list[str],
    wr_codes: list[str],
    table_number_element_id: str | None = None,
    qr_placeholder_id: str | None = None,
) -> bytes:
    """
    Generate a single PDF with 2 pages per table: fronte (unchanged) + retro (with table number and QR code).

    Both SVGs are converted to PNG only once. Pillow then overlays the dynamic content
    (table number + QR) on each retro copy, making it efficient for large batches (300+ tables).

    Returns the PDF as bytes.
    """
    # Convert SVGs to PNG once — this is the only slow step
    fronte_png = _svg_to_png(fronte_svg)
    retro_png_template = _svg_to_png(retro_svg)

    # Derive page draw area from fronte image dimensions, scaled to fit A4
    fronte_img = Image.open(io.BytesIO(fronte_png))
    svg_w, svg_h = fronte_img.size
    a4_w, a4_h = A4
    scale = min(a4_w / svg_w, a4_h / svg_h)
    draw_w = svg_w * scale
    draw_h = svg_h * scale
    x_offset = (a4_w - draw_w) / 2
    y_offset = (a4_h - draw_h) / 2

    # Build all retro images in parallel — each table gets its own QR + number overlay
    pairs = list(zip(table_numbers, wr_codes))

    retro_images: dict[int, bytes] = {}
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_build_retro_image, retro_png_template, tn, wc): idx
            for idx, (tn, wc) in enumerate(pairs)
        }
        for future in as_completed(futures):
            idx = futures[future]
            retro_images[idx] = future.result()

    # Assemble PDF in order
    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)

    for idx in range(len(pairs)):
        # Page 1: fronte — identical for every table
        c.drawImage(
            ImageReader(io.BytesIO(fronte_png)),
            x_offset, y_offset, draw_w, draw_h,
        )
        c.showPage()

        # Page 2: retro — unique per table (injected table number + QR code)
        c.drawImage(
            ImageReader(io.BytesIO(retro_images[idx])),
            x_offset, y_offset, draw_w, draw_h,
        )
        c.showPage()

    c.save()
    pdf_buf.seek(0)
    return pdf_buf.read()
