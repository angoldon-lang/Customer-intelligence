"""Tests for data normalizer."""

import pytest
from app.services.normalizer import DataNormalizer


@pytest.fixture
def normalizer():
    return DataNormalizer()


def test_normalize_website_with_protocol(normalizer):
    """Test website normalization with protocol."""
    assert normalizer._normalize_website("https://example.com") == "https://example.com"
    assert normalizer._normalize_website("http://example.com") == "http://example.com"


def test_normalize_website_add_protocol(normalizer):
    """Test website normalization adds protocol."""
    assert normalizer._normalize_website("example.com") == "https://example.com"
    assert normalizer._normalize_website("www.example.com") == "https://www.example.com"


def test_normalize_website_remove_trailing_chars(normalizer):
    """Test website normalization removes trailing chars."""
    assert normalizer._normalize_website("example.com.") == "https://example.com"
    assert normalizer._normalize_website("example.com/") == "https://example.com"
    assert normalizer._normalize_website("example.com/.") == "https://example.com"


def test_valid_email(normalizer):
    """Test email validation."""
    assert normalizer._is_valid_email("test@example.com") is True
    assert normalizer._is_valid_email("user+tag@domain.co.uk") is True


def test_invalid_email(normalizer):
    """Test invalid email detection."""
    assert normalizer._is_valid_email("not-an-email") is False
    assert normalizer._is_valid_email("@example.com") is False
    assert normalizer._is_valid_email("user@") is False


def test_normalize_company(normalizer):
    """Test full company normalization."""
    company = {
        "company_name": "  Test Company  ",
        "website": "test.it",
        "company_email": "info@test.it",
    }

    normalizer.normalize_company(company)

    assert company["company_name"] == "Test Company"
    assert company["website"] == "https://test.it"
    assert company["company_email"] == "info@test.it"


def test_normalize_invalid_email_removal(normalizer):
    """Test that invalid emails are removed."""
    company = {
        "company_email": "invalid-email",
    }

    normalizer.normalize_company(company)

    assert company["company_email"] is None


def test_tax_code_normalization(normalizer):
    """Test Italian tax code normalization."""
    # Valid P.IVA (11 digits)
    assert normalizer.normalize_tax_code("12 345 678 901") == "12345678901"

    # Valid Codice Fiscale (16 characters)
    assert normalizer.normalize_tax_code("ABCDEF123GHLMN45") == "ABCDEF123GHLMN45"

    # Invalid length
    assert normalizer.normalize_tax_code("123") is None


def test_deduplicate_companies(normalizer):
    """Test company deduplication."""
    companies = [
        {"company_name": "ABC Company", "type": "Cliente"},
        {"company_name": "abc company", "type": "Fornitore"},
        {"company_name": "XYZ SpA", "type": "Cliente"},
    ]

    unique, duplicates = normalizer.deduplicate_companies(companies)

    assert len(unique) == 2
    assert len(duplicates) == 1
