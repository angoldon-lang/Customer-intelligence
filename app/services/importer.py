"""Data importer for Excel and CSV files."""

import io
from typing import List, Dict, Any
import pandas as pd
from app.services.normalizer import DataNormalizer


class DataImporter:
    """Import company data from Excel or CSV files."""

    REQUIRED_COLUMNS = ["Ragione Sociale"]
    OPTIONAL_COLUMNS = [
        "Tipo",
        "Stato",
        "Codice Cliente",
        "E-Mail",
        "Codice Ateco",
        "Codice Fiscale",
        "Sito Web",
        "Referente Commerciale",
    ]

    def __init__(self):
        self.normalizer = DataNormalizer()

    def import_file(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Import company data from file.

        Args:
            file_content: File bytes
            filename: Original filename

        Returns:
            Dict with parsed companies and metadata
        """
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(file_content))
        elif filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_content), encoding="utf-8")
        else:
            raise ValueError(f"Unsupported file format: {filename}")

        return self._process_dataframe(df)

    def _process_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Process DataFrame: clean, normalize, and validate.

        Returns:
            Dict with companies and validation results
        """
        result = {
            "companies": [],
            "validation_errors": [],
            "validation_warnings": [],
            "total_rows": len(df),
            "processed_rows": 0,
            "skipped_rows": 0,
        }

        # Strip whitespace from column names
        df.columns = df.columns.str.strip()

        # Remove completely empty rows
        df = df.dropna(how="all")

        # Remove duplicate headers
        df = self._remove_duplicate_headers(df)

        for idx, row in df.iterrows():
            try:
                company = self._process_row(row)
                if company:
                    result["companies"].append(company)
                    result["processed_rows"] += 1
                else:
                    result["skipped_rows"] += 1
            except Exception as e:
                result["validation_errors"].append(f"Row {idx}: {str(e)}")
                result["skipped_rows"] += 1

        # Normalize all companies
        for company in result["companies"]:
            self.normalizer.normalize_company(company)

        # Check for duplicates
        duplicates = self._find_duplicates(result["companies"])
        if duplicates:
            result["validation_warnings"].append(f"Found {len(duplicates)} potential duplicates")

        return result

    def _remove_duplicate_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove rows that are duplicate headers."""
        header_row = df.iloc[0]
        df = df[~df.apply(lambda x: (x == header_row).all(), axis=1).iloc[1:]]
        return df.reset_index(drop=True)

    def _process_row(self, row: pd.Series) -> Dict[str, Any] | None:
        """
        Process single row.

        Returns:
            Company dict or None if row is invalid
        """
        # Check required field
        company_name = str(row.get("Ragione Sociale", "")).strip()
        if not company_name or company_name.lower() == "nan":
            return None

        company = {
            "company_name": company_name,
            "relationship_type": str(row.get("Tipo", "Unknown")).strip() or "Unknown",
            "status": str(row.get("Stato", "Unknown")).strip() or "Unknown",
            "internal_customer_code": str(row.get("Codice Cliente", "")).strip() or None,
            "company_email": str(row.get("E-Mail", "")).strip() or None,
            "ateco_description": str(row.get("Codice Ateco", "")).strip() or None,
            "tax_code": str(row.get("Codice Fiscale", "")).strip() or None,
            "website": str(row.get("Sito Web", "")).strip() or None,
            "account_owner": str(row.get("Referente Commerciale", "")).strip() or None,
            "enrichment_status": "pending",
        }

        return company

    def _find_duplicates(self, companies: List[Dict]) -> List[List[Dict]]:
        """Find potential duplicate companies."""
        duplicates = []
        seen = {}

        for company in companies:
            name_lower = company["company_name"].lower()
            if name_lower in seen:
                # Found duplicate
                if name_lower not in [d[0]["company_name"].lower() for d in duplicates]:
                    duplicates.append([seen[name_lower], company])
                else:
                    # Add to existing duplicate group
                    for dup_group in duplicates:
                        if dup_group[0]["company_name"].lower() == name_lower:
                            dup_group.append(company)
                            break
            else:
                seen[name_lower] = company

        return duplicates
