"""
Tests for pdf_generator.py

Run with:
    cd backend
    pytest tests/ -v
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image, ImageDraw

from pdf_generator import (
    _svg_to_png,
    _load_font,
    _fit_font,
    _make_qr,
    _page_layout,
    _build_retro_page,
    generate_tables_pdf,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_SVG = b"""
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600">
  <rect width="400" height="600" fill="#FFFFFF"/>
  <text x="200" y="300" text-anchor="middle" font-size="40">FRONT</text>
</svg>
"""

RETRO_SVG = b"""
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600">
  <rect width="400" height="600" fill="#2C2C2C"/>
  <text x="200" y="300" text-anchor="middle" font-size="40" fill="white">BACK</text>
</svg>
"""


def _make_png(width: int = 400, height: int = 600, color: str = "white") -> bytes:
    """Helper: create a minimal PNG in memory."""
    img = Image.new("RGBA", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


# ── _load_font ────────────────────────────────────────────────────────────────

class TestLoadFont:
    def test_returns_font_object(self):
        font = _load_font(32)
        assert font is not None

    def test_accepts_various_sizes(self):
        for size in [12, 24, 48, 96]:
            font = _load_font(size)
            assert font is not None


# ── _fit_font ─────────────────────────────────────────────────────────────────

class TestFitFont:
    def setup_method(self):
        img = Image.new("RGB", (400, 600), "white")
        self.draw = ImageDraw.Draw(img)

    def test_short_text_fits(self):
        font = _fit_font(self.draw, "5", max_width=300)
        bbox = self.draw.textbbox((0, 0), "5", font=font)
        assert (bbox[2] - bbox[0]) <= 300

    def test_long_text_fits(self):
        font = _fit_font(self.draw, "TABLE 999", max_width=300)
        bbox = self.draw.textbbox((0, 0), "TABLE 999", font=font)
        assert (bbox[2] - bbox[0]) <= 300


# ── _make_qr ──────────────────────────────────────────────────────────────────

class TestMakeQr:
    def test_returns_correct_size(self):
        qr = _make_qr("https://example.com", size=200)
        assert qr.size == (200, 200)

    def test_returns_rgba_image(self):
        qr = _make_qr("https://example.com", size=100)
        assert qr.mode == "RGBA"

    def test_background_is_transparent(self):
        qr = _make_qr("https://example.com", size=200)
        pixels = list(qr.getdata())
        # At least some pixels should be fully transparent (white background removed)
        transparent_pixels = [p for p in pixels if p[3] == 0]
        assert len(transparent_pixels) > 0

    def test_different_data_produces_different_qr(self):
        qr1 = _make_qr("https://table1.example.com", size=200)
        qr2 = _make_qr("https://table2.example.com", size=200)
        assert list(qr1.getdata()) != list(qr2.getdata())


# ── _page_layout ──────────────────────────────────────────────────────────────

class TestPageLayout:
    def test_returns_four_values(self):
        result = _page_layout((400, 600))
        assert len(result) == 4

    def test_image_fits_within_a4(self):
        from reportlab.lib.pagesizes import A4
        a4_w, a4_h = A4
        draw_w, draw_h, x, y = _page_layout((400, 600))
        assert draw_w <= a4_w + 0.1
        assert draw_h <= a4_h + 0.1

    def test_offsets_are_non_negative(self):
        draw_w, draw_h, x, y = _page_layout((400, 600))
        assert x >= 0
        assert y >= 0

    def test_image_centered_on_a4(self):
        from reportlab.lib.pagesizes import A4
        a4_w, a4_h = A4
        draw_w, draw_h, x, y = _page_layout((400, 600))
        # Check centering: offset should be (A4 - drawn) / 2
        assert abs(x - (a4_w - draw_w) / 2) < 0.1
        assert abs(y - (a4_h - draw_h) / 2) < 0.1


# ── _build_retro_page ─────────────────────────────────────────────────────────

class TestBuildRetroPage:
    def test_returns_bytes(self):
        retro_png = _make_png()
        result = _build_retro_page(retro_png, table_number="5", wr_code="https://example.com/t/5")
        assert isinstance(result, bytes)

    def test_output_is_valid_png(self):
        retro_png = _make_png()
        result = _build_retro_page(retro_png, table_number="12", wr_code="https://example.com/t/12")
        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"

    def test_output_has_same_dimensions(self):
        retro_png = _make_png(width=400, height=600)
        result = _build_retro_page(retro_png, table_number="3", wr_code="https://example.com/t/3")
        img = Image.open(io.BytesIO(result))
        assert img.size == (400, 600)

    def test_long_table_number(self):
        retro_png = _make_png()
        result = _build_retro_page(retro_png, table_number="TABLE-999-VIP", wr_code="https://example.com")
        assert isinstance(result, bytes)


# ── generate_tables_pdf ───────────────────────────────────────────────────────

class TestGenerateTablesPdf:
    def test_returns_bytes(self):
        result = generate_tables_pdf(
            fronte_svg=SIMPLE_SVG,
            retro_svg=RETRO_SVG,
            table_numbers=["1"],
            wr_codes=["https://example.com/t/1"],
        )
        assert isinstance(result, bytes)

    def test_output_starts_with_pdf_header(self):
        result = generate_tables_pdf(
            fronte_svg=SIMPLE_SVG,
            retro_svg=RETRO_SVG,
            table_numbers=["1"],
            wr_codes=["https://example.com/t/1"],
        )
        assert result[:4] == b"%PDF"

    def test_multiple_tables(self):
        result = generate_tables_pdf(
            fronte_svg=SIMPLE_SVG,
            retro_svg=RETRO_SVG,
            table_numbers=["1", "2", "3"],
            wr_codes=[
                "https://example.com/t/1",
                "https://example.com/t/2",
                "https://example.com/t/3",
            ],
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_pdf_grows_with_more_tables(self):
        pdf_1_table = generate_tables_pdf(
            fronte_svg=SIMPLE_SVG,
            retro_svg=RETRO_SVG,
            table_numbers=["1"],
            wr_codes=["https://example.com/t/1"],
        )
        pdf_5_tables = generate_tables_pdf(
            fronte_svg=SIMPLE_SVG,
            retro_svg=RETRO_SVG,
            table_numbers=["1", "2", "3", "4", "5"],
            wr_codes=[f"https://example.com/t/{i}" for i in range(1, 6)],
        )
        assert len(pdf_5_tables) > len(pdf_1_table)

    def test_alphanumeric_table_numbers(self):
        result = generate_tables_pdf(
            fronte_svg=SIMPLE_SVG,
            retro_svg=RETRO_SVG,
            table_numbers=["A1", "B2", "VIP"],
            wr_codes=[
                "https://example.com/t/A1",
                "https://example.com/t/B2",
                "https://example.com/t/VIP",
            ],
        )
        assert isinstance(result, bytes)
