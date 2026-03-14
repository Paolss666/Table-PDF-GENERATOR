# Table PDF Generator

A FastAPI backend that generates a single PDF file containing front and back pages for each restaurant table. The back page is dynamically injected with a table number and a QR code per table.

## How it works

```
SVG front  →  PNG (converted once)
SVG back   →  PNG (converted once)
                ↓
For each table (in parallel):
  - Overlay table number text onto back PNG
  - Overlay QR code (transparent background) onto back PNG
                ↓
Assemble single PDF:  [front | back] × N tables
                ↓
Return PDF as download
```

- Both SVGs are converted to PNG **once** — reused across all tables
- Back images are generated **in parallel** using `ThreadPoolExecutor`
- 200 tables typically completes in 5–8 seconds

---

## Project structure

```
PDF_GEN/
├── backend/
│   ├── main.py            # FastAPI app and API endpoints
│   ├── pdf_generator.py   # Core PDF generation logic
│   └── requirements.txt
└── frontend/
    └── src/
        ├── api/tablePdfApi.ts              # Fetch wrapper
        ├── hooks/useGenerateTablesPdf.ts   # React hook
        └── components/TablePdfGenerator.tsx
```

---

## Backend setup

### Requirements

- Python 3.11+
- System dependency for cairosvg (Cairo library):

```bash
# Debian/Ubuntu
sudo apt-get install libcairo2

# macOS
brew install cairo
```

### Install & run

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

API is available at `http://localhost:8000`
Swagger UI at `http://localhost:8000/docs`

---

## API

### `GET /health`

Returns `{ "status": "ok" }`.

---

### `POST /generate-pdf`

Generates the PDF and returns it as a binary download.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fronte` | File (SVG) | Yes | Front side SVG — identical for every table |
| `retro` | File (SVG) | Yes | Back side SVG — table number + QR injected per table |
| `table_numbers` | string | Yes | JSON array or comma-separated list of table identifiers e.g. `["1","2","Terrazza"]` |
| `wr_codes` | string | Yes | JSON array of WR codes — must match length of `table_numbers` |
| `table_number_element_id` | string | No | SVG element ID to replace with table number text |
| `qr_placeholder_id` | string | No | SVG element ID to replace with QR code image |

**Response:** `application/pdf` — file download `tables.pdf`

**Example with curl:**

```bash
curl -X POST http://localhost:8000/generate-pdf \
  -F "fronte=@fronte.svg;type=image/svg+xml" \
  -F "retro=@retro.svg;type=image/svg+xml" \
  -F 'table_numbers=["1","2","3","Terrazza"]' \
  -F 'wr_codes=["WR001","WR002","WR003","WR004"]' \
  --output tables.pdf
```

---

## Frontend integration (React / TypeScript)

```typescript
import { generateTablesPdf, downloadPdfBlob } from './api/tablePdfApi';

const blob = await generateTablesPdf({
  fronteFile,   // File object from <input type="file">
  retroFile,
  tableNumbers: ['1', '2', '3', 'Terrazza'],
  wrCodes: ['WR001', 'WR002', 'WR003', 'WR004'],
});

downloadPdfBlob(blob, 'tables.pdf');
```

Or use the ready-made hook:

```typescript
import { useGenerateTablesPdf } from './hooks/useGenerateTablesPdf';

const { generate, isLoading, error } = useGenerateTablesPdf();

await generate({ fronteFile, retroFile, tableNumbers, wrCodes });
// triggers automatic browser download
```

---

## PDF output format

The generated PDF has **2 pages per table**, in order:

```
Page 1  →  Table 1 front  (unchanged)
Page 2  →  Table 1 back   (table number + QR code)
Page 3  →  Table 2 front
Page 4  →  Table 2 back
...
```

### Back page injection

- **Table number** is drawn centered at ~35% from the top. Font size scales down automatically for long strings (> 9 characters) to always fit within 80% of the image width.
- **QR code** is drawn centered at ~55% from the top with a transparent background, so it blends with the SVG design.
