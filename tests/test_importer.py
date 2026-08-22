"""Tests for data importer."""

import pytest
import io
from app.services.importer import DataImporter


@pytest.fixture
def importer():
    return DataImporter()


def test_import_csv_basic(importer):
    """Test basic CSV import."""
    csv_content = b"""Ragione Sociale,Tipo,Stato,E-Mail,Sito Web
ABC Company,Cliente,Attiva,info@abc.it,www.abc.it
XYZ SpA,Fornitore,Attiva,contact@xyz.it,xyz.it
"""

    result = importer.import_file(csv_content, "test.csv")

    assert result["total_rows"] == 2
    assert result["processed_rows"] == 2
    assert len(result["companies"]) == 2
    assert result["companies"][0]["company_name"] == "ABC Company"
    assert result["companies"][0]["relationship_type"] == "Cliente"


def test_import_skip_empty_rows(importer):
    """Test that empty rows are skipped."""
    csv_content = b"""Ragione Sociale,Tipo,Stato
ABC Company,Cliente,Attiva


XYZ SpA,Fornitore,Attiva
"""

    result = importer.import_file(csv_content, "test.csv")

    assert result["processed_rows"] == 2
    assert len(result["companies"]) == 2


def test_import_missing_required_field(importer):
    """Test that rows without company name are skipped."""
    csv_content = b"""Ragione Sociale,Tipo,Stato
ABC Company,Cliente,Attiva
,Fornitore,Attiva
XYZ SpA,Cliente,Attiva
"""

    result = importer.import_file(csv_content, "test.csv")

    assert result["processed_rows"] == 2
    assert len(result["companies"]) == 2


def test_import_default_values(importer):
    """Test that missing optional fields get defaults."""
    csv_content = b"""Ragione Sociale
ABC Company
"""

    result = importer.import_file(csv_content, "test.csv")

    company = result["companies"][0]
    assert company["company_name"] == "ABC Company"
    assert company["relationship_type"] == "Unknown"
    assert company["status"] == "Unknown"


def test_normalize_website(importer):
    """Test website normalization."""
    csv_content = b"""Ragione Sociale,Sito Web
ABC Company,abc.it
XYZ SpA,https://xyz.it
TEST Company,test.com.
"""

    result = importer.import_file(csv_content, "test.csv")

    assert result["companies"][0]["website"] == "https://abc.it"
    assert result["companies"][1]["website"] == "https://xyz.it"
    assert result["companies"][2]["website"] == "https://test.com"


def test_import_duplicates_detection(importer):
    """Test detection of duplicate company names."""
    csv_content = b"""Ragione Sociale,Tipo
ABC Company,Cliente
ABC Company,Fornitore
XYZ SpA,Cliente
"""

    result = importer.import_file(csv_content, "test.csv")

    assert result["processed_rows"] >= 2
    assert len(result["validation_warnings"]) > 0
