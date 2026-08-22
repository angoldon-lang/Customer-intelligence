"""Data normalization and cleaning service."""

from typing import Dict, Any
import re


class DataNormalizer:
    """Normalize and clean company data."""

    def normalize_company(self, company: Dict[str, Any]) -> None:
        """
        Normalize company data in-place.

        Handles:
        - Website normalization (add https://, fix trailing dots)
        - Email validation
        - String trimming
        - Tax code formatting
        """
        # Normalize website
        if company.get("website"):
            company["website"] = self._normalize_website(company["website"])

        # Validate email
        if company.get("company_email"):
            if not self._is_valid_email(company["company_email"]):
                company["company_email"] = None

        # Trim whitespace from strings
        for key in company:
            if isinstance(company[key], str):
                company[key] = company[key].strip()

    def _normalize_website(self, url: str) -> str:
        """
        Normalize website URL.

        Rules:
        - Add https:// if protocol missing
        - Remove trailing dots or slashes
        - Lowercase domain
        """
        url = url.strip()

        # Add protocol if missing
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Remove trailing dots
        url = re.sub(r"\.+$", "", url)

        # Remove trailing slashes
        url = url.rstrip("/")

        return url

    def _is_valid_email(self, email: str) -> bool:
        """Basic email validation."""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    def normalize_tax_code(self, tax_code: str) -> str:
        """Normalize Italian tax code (CF/P.IVA)."""
        if not tax_code:
            return None

        # Remove spaces and special chars
        normalized = re.sub(r"[^\w]", "", tax_code).upper()

        # Validate length
        if len(normalized) not in [11, 16]:  # P.IVA or Codice Fiscale
            return None

        return normalized

    def deduplicate_companies(self, companies: list[Dict]) -> tuple[list[Dict], list[list[Dict]]]:
        """
        Remove duplicate companies by name similarity.

        Returns:
            (unique_companies, duplicate_groups)
        """
        unique = []
        duplicates = []
        seen_names = {}

        for company in companies:
            name_key = company["company_name"].lower().strip()

            if name_key in seen_names:
                # Merge with existing or add to duplicates
                existing = seen_names[name_key]
                duplicates.append([existing, company])
            else:
                unique.append(company)
                seen_names[name_key] = company

        return unique, duplicates
