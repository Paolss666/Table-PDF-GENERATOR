# Table PDF Generator

FastAPI service that generates a PDF with a front and back page for each restaurant table. The back page is dynamically injected with a table number and QR code.

---

## How it works

```
fronte.svg  ──► PNG (converted once, reused for all tables)
retro.svg   ──► PNG (converted once)
                 │
                 ▼  for each table (parallel)
          overlay table number  (centered at table_number_y)
          overlay QR code       (centered at qr_y)
                 │
                 ▼
     PDF:  [front | back] × N tables
```

- Both SVGs are converted to PNG **once** and reused across all tables
- Back pages are built **in parallel** via `ThreadPoolExecutor`
- 200 tables typically completes in ~5 seconds

---

## Project structure

```
PDF_GEN/
├── backend/
│   ├── main.py              # FastAPI app and endpoints
│   ├── pdf_generator.py     # Core PDF generation logic
│   ├── requirements.txt
│   └── tests/
│       ├── test_api.py          # API endpoint tests
│       └── test_pdf_generator.py # Unit tests for core functions
└── mock/
    ├── fronte.svg           # Sample front SVG for testing
    └── retro.svg            # Sample back SVG for testing
```

---

## Setup

### System dependency

`cairosvg` requires the Cairo graphics library:

```bash
# Debian / Ubuntu
sudo apt-get install libcairo2

# macOS
brew install cairo
```

### Install & run

```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

- API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

### Run tests

```bash
source venv/bin/activate
pip install pytest httpx
cd backend
pytest tests/ -v
```

---

## API

### `GET /health`

```json
{ "status": "ok" }
```

---

### `POST /generate-pdf`

Generates the PDF and returns it as a binary download.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `fronte` | File (SVG) | yes | — | Front page SVG — same for every table |
| `retro` | File (SVG) | yes | — | Back page SVG — number + QR injected per table |
| `business_id` | string | yes | — | Used as the output filename: `{business_id}_pdf.pdf` |
| `table_numbers` | string | yes | — | JSON array or comma-separated: `["1","2","A3"]` |
| `wr_codes` | string | yes | — | JSON array of QR codes — must match `table_numbers` length |
| `table_number_y` | float | no | `0.35` | Vertical center of the table number (0.0 – 1.0) |
| `qr_y` | float | no | `0.55` | Vertical center of the QR code (0.0 – 1.0) |
| `table_number_element_id` | string | no | — | SVG element ID for the table number zone |
| `qr_placeholder_id` | string | no | — | SVG element ID for the QR code zone |

**Response:** `application/pdf`

---

### Example

```bash
curl -X POST http://localhost:8000/generate-pdf \
  -F "fronte=@mock/fronte.svg;type=image/svg+xml" \
  -F "retro=@mock/retro.svg;type=image/svg+xml" \
  -F "business_id=my_restaurant" \
  -F 'table_numbers=["1","2","3","Terrazza"]' \
  -F 'wr_codes=["https://example.com/t/1","https://example.com/t/2","https://example.com/t/3","https://example.com/t/terrazza"]' \
  --output my_restaurant.pdf
```

With custom positioning:

```bash
curl -X POST http://localhost:8000/generate-pdf \
  -F "fronte=@mock/fronte.svg;type=image/svg+xml" \
  -F "retro=@mock/retro.svg;type=image/svg+xml" \
  -F "business_id=my_restaurant" \
  -F 'table_numbers=["1","2"]' \
  -F 'wr_codes=["https://example.com/t/1","https://example.com/t/2"]' \
  -F "table_number_y=0.30" \
  -F "qr_y=0.60" \
  --output my_restaurant.pdf
```

---

## PDF output format

2 pages per table, in order:

```
Page 1  →  Table 1 front  (unchanged SVG)
Page 2  →  Table 1 back   (number + QR injected)
Page 3  →  Table 2 front
Page 4  →  Table 2 back
...
```

---

## Back page positioning

The table number and QR code are placed at positions relative to the image height:

| Element | Default position | How to override |
|---|---|---|
| Table number | 35% from top | `table_number_y=0.35` |
| QR code | 55% from top | `qr_y=0.55` |

To find the right values for your SVG design:

```
table_number_y = desired_y_in_svg / svg_height
qr_y           = desired_y_in_svg / svg_height

# Example: SVG height 842, want number at y=250 and QR at y=550
table_number_y = 250 / 842 = 0.30
qr_y           = 550 / 842 = 0.65
```

The table number auto-scales to always fit within 80% of the image width.
