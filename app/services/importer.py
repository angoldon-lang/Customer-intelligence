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
            # dtype=str keeps numeric-looking columns (P.IVA, codice fiscale,
            # CAP with leading zeros) as text instead of pandas silently
            # casting them to float and mangling/truncating the digits.
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)
        elif filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_content), encoding="utf-8", dtype=str)
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
        """Remove data rows that just repeat the column header names.

        Some Excel exports embed the header line again as a data row
        (e.g. copy-pasted sheets). Compare against the real column names,
        not against the first data row - comparing to df.iloc[0] would
        always match row 0 against itself and silently drop it.
        """
        if len(df) == 0:
            return df

        header_values = [str(c).strip() for c in df.columns]

        def is_header_row(row) -> bool:
            return [self._clean_value(v) or "" for v in row.tolist()] == header_values

        mask = df.apply(is_header_row, axis=1)
        return df[~mask].reset_index(drop=True)

    @staticmethod
    def _clean_value(value: Any) -> str | None:
        """Convert a pandas cell to a clean string, treating NaN/empty as None."""
        if pd.isna(value):
            return None
        text = str(value).strip()
        return text or None

    def _process_row(self, row: pd.Series) -> Dict[str, Any] | None:
        """
        Process single row.

        Returns:
            Company dict or None if row is invalid
        """
        # Check required field
        company_name = self._clean_value(row.get("Ragione Sociale"))
        if not company_name:
            return None

        company = {
            "company_name": company_name,
            "relationship_type": self._clean_value(row.get("Tipo")) or "Unknown",
            "status": self._clean_value(row.get("Stato")) or "Unknown",
            "internal_customer_code": self._clean_value(row.get("Codice Cliente")),
            "company_email": self._clean_value(row.get("E-Mail")),
            "ateco_description": self._clean_value(row.get("Codice Ateco")),
            "tax_code": self._clean_value(row.get("Codice Fiscale")),
            "website": self._clean_value(row.get("Sito Web")),
            "account_owner": self._clean_value(row.get("Referente Commerciale")),
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
