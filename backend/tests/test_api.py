"""
Tests for the FastAPI endpoints in main.py

Run with:
    cd backend
    pytest tests/ -v
"""

import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from main import app

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_SVG = b"""
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600">
  <rect width="400" height="600" fill="#FFFFFF"/>
  <text x="200" y="300" text-anchor="middle" font-size="40">TEST</text>
</svg>
"""

FAKE_PDF = b"%PDF-1.4 fake pdf content"


def svg_file(content: bytes = SIMPLE_SVG, filename: str = "test.svg"):
    return ("application/svg+xml", content, filename)


# ── GET /health ───────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_ok_status(self):
        response = client.get("/health")
        assert response.json() == {"status": "ok"}


# ── POST /generate-pdf ────────────────────────────────────────────────────────

class TestGeneratePdfEndpoint:
    def _post(self, table_numbers='["1"]', wr_codes='["https://example.com/t/1"]',
              business_id="test_restaurant", fronte=None, retro=None):
        return client.post(
            "/generate-pdf",
            data={
                "business_id": business_id,
                "table_numbers": table_numbers,
                "wr_codes": wr_codes,
            },
            files={
                "fronte": ("fronte.svg", fronte or SIMPLE_SVG, "image/svg+xml"),
                "retro":  ("retro.svg",  retro  or SIMPLE_SVG, "image/svg+xml"),
            },
        )

    def test_returns_pdf_on_valid_input(self):
        with patch("main.generate_tables_pdf", return_value=FAKE_PDF):
            response = self._post()
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_pdf_filename_contains_business_id(self):
        with patch("main.generate_tables_pdf", return_value=FAKE_PDF):
            response = self._post(business_id="my_restaurant")
        disposition = response.headers["content-disposition"]
        assert "my_restaurant" in disposition

    def test_mismatched_arrays_returns_422(self):
        with patch("main.generate_tables_pdf", return_value=FAKE_PDF):
            response = self._post(
                table_numbers='["1", "2"]',
                wr_codes='["https://example.com/t/1"]',  # only 1 code for 2 tables
            )
        assert response.status_code == 422

    def test_invalid_table_numbers_returns_422(self):
        with patch("main.generate_tables_pdf", return_value=FAKE_PDF):
            # commas only → split produces empty list → 422
            response = self._post(table_numbers=",,,")
        assert response.status_code == 422

    def test_comma_separated_table_numbers_accepted(self):
        with patch("main.generate_tables_pdf", return_value=FAKE_PDF):
            response = self._post(
                table_numbers="1, 2, 3",
                wr_codes="https://ex.com/1, https://ex.com/2, https://ex.com/3",
            )
        assert response.status_code == 200

    def test_pdf_generation_error_returns_500(self):
        with patch("main.generate_tables_pdf", side_effect=Exception("render failed")):
            response = self._post()
        assert response.status_code == 500
        assert "render failed" in response.json()["detail"]

    def test_missing_fronte_file_returns_422(self):
        response = client.post(
            "/generate-pdf",
            data={
                "business_id": "test",
                "table_numbers": '["1"]',
                "wr_codes": '["https://example.com/t/1"]',
            },
            files={
                "retro": ("retro.svg", SIMPLE_SVG, "image/svg+xml"),
                # fronte intentionally omitted
            },
        )
        assert response.status_code == 422

    def test_missing_business_id_returns_422(self):
        response = client.post(
            "/generate-pdf",
            data={
                "table_numbers": '["1"]',
                "wr_codes": '["https://example.com/t/1"]',
                # business_id intentionally omitted
            },
            files={
                "fronte": ("fronte.svg", SIMPLE_SVG, "image/svg+xml"),
                "retro":  ("retro.svg",  SIMPLE_SVG, "image/svg+xml"),
            },
        )
        assert response.status_code == 422
