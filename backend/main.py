import io
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from pdf_generator import generate_tables_pdf

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Table PDF Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_array(value: str, field_name: str) -> list[str]:
    """Parse a JSON array string or a comma-separated string into a list of strings."""
    value = value.strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list) and parsed:
            return [str(x) for x in parsed]
        raise ValueError
    except (json.JSONDecodeError, ValueError):
        items = [x.strip() for x in value.split(",") if x.strip()]
        if items:
            return items
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be a JSON array or comma-separated string",
        )

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/generate-pdf")
async def generate_pdf(
    fronte: UploadFile = File(..., description="SVG file for the front side"),
    retro:  UploadFile = File(..., description="SVG file for the back side"),
    business_id:   str = Form(..., description="Business identifier — used as the PDF filename"),
    table_numbers: str = Form(..., description='JSON array of table identifiers e.g. ["1","2","A3"]'),
    wr_codes:      str = Form(..., description="JSON array of WR codes, one per table"),
    table_number_element_id: str   = Form(None, description="Optional SVG element ID for the table number"),
    qr_placeholder_id:       str   = Form(None, description="Optional SVG element ID for the QR code"),
    table_number_y: float = Form(0.35, description="Vertical position of table number (0.0–1.0, default 0.35)"),
    qr_y:           float = Form(0.55, description="Vertical position of QR code (0.0–1.0, default 0.55)"),
):
    numbers = _parse_array(table_numbers, "table_numbers")
    codes   = _parse_array(wr_codes, "wr_codes")

    if len(numbers) != len(codes):
        raise HTTPException(
            status_code=422,
            detail=f"table_numbers ({len(numbers)}) and wr_codes ({len(codes)}) must have the same length",
        )

    if not (0.0 < table_number_y < 1.0) or not (0.0 < qr_y < 1.0):
        raise HTTPException(
            status_code=422,
            detail="table_number_y and qr_y must be between 0.0 and 1.0",
        )

    fronte_bytes = await fronte.read()
    retro_bytes  = await retro.read()

    try:
        pdf_bytes = generate_tables_pdf(
            fronte_svg=fronte_bytes,
            retro_svg=retro_bytes,
            table_numbers=numbers,
            wr_codes=codes,
            table_number_element_id=table_number_element_id or None,
            qr_placeholder_id=qr_placeholder_id or None,
            table_number_y=table_number_y,
            qr_y=qr_y,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={business_id}_pdf.pdf"},
    )
