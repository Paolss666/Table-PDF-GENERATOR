import json
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import io

from pdf_generator import generate_tables_pdf

app = FastAPI(title="Table PDF Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


def _parse_array_field(value: str, field_name: str) -> list[str]:
    """Accept JSON array string OR plain comma-separated values."""
    value = value.strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list) and len(parsed) > 0:
            return [str(x) for x in parsed]
        raise ValueError
    except (json.JSONDecodeError, ValueError):
        # Fallback: comma-separated plain string e.g. "1,2,3"
        items = [x.strip() for x in value.split(",") if x.strip()]
        if items:
            return items
        raise HTTPException(status_code=422, detail=f"{field_name} must be a JSON array or comma-separated string")


@app.post("/generate-pdf")
async def generate_pdf(
    fronte: UploadFile = File(..., description="SVG file for the front side"),
    retro: UploadFile = File(..., description="SVG file for the back side"),
    table_numbers: str = Form(..., description='JSON array of table identifiers e.g. ["1","2","A3"]'),
    wr_codes: str = Form(..., description="JSON array of WR codes, one per table"),
    table_number_element_id: str = Form(
        None,
        description="Optional SVG element ID to replace with the table number",
    ),
    qr_placeholder_id: str = Form(
        None,
        description="Optional SVG element ID to replace with the QR code image",
    ),
):
    """
    Generate a PDF with fronte + retro pages for each table.

    - fronte: SVG file (unchanged for every table)
    - retro: SVG file (table number + QR code injected per table)
    - table_numbers: JSON array of table identifiers (strings) e.g. ["1","2","A3","Terrazza"]
    - wr_codes: JSON array of WR codes — must have the same length as table_numbers
    - table_number_element_id: (optional) ID of the SVG text element to update
    - qr_placeholder_id: (optional) ID of the SVG element to replace with QR image
    """
    numbers = _parse_array_field(table_numbers, "table_numbers")
    codes = _parse_array_field(wr_codes, "wr_codes")

    if len(codes) != len(numbers):
        raise HTTPException(
            status_code=422,
            detail=f"table_numbers has {len(numbers)} entries but wr_codes has {len(codes)} — they must match",
        )

    fronte_bytes = await fronte.read()
    retro_bytes = await retro.read()


    try:
        pdf_bytes = generate_tables_pdf(
            fronte_svg=fronte_bytes,
            retro_svg=retro_bytes,
            table_numbers=numbers,
            wr_codes=codes,
            table_number_element_id=table_number_element_id or None,
            qr_placeholder_id=qr_placeholder_id or None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=tables.pdf"},
    )
