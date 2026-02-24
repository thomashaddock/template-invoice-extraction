import json
import os
from typing import Any, Type

import psycopg2
from pydantic import BaseModel, Field

from crewai.tools import BaseTool


class DBWriterInput(BaseModel):
    """Input schema for DBWriterTool."""

    record_json: str = Field(
        ...,
        description=(
            "A JSON string representing the invoice record to insert. "
            "Must be a valid JSON object with keys matching the invoices table columns."
        ),
    )


class DBWriterTool(BaseTool):
    name: str = "db_writer"
    description: str = (
        "Inserts a single invoice record into the Heroku Postgres invoices table. "
        "Accepts a JSON string of the record. "
        "Returns a result with success status and the new record ID."
    )
    args_schema: Type[BaseModel] = DBWriterInput

    def _get_connection_string(self) -> str:
        db_url = os.environ["DATABASE_URL"]
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        if "sslmode" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url += f"{separator}sslmode=require"
        return db_url

    def _run(self, record_json: str | dict[str, Any] = "", **kwargs) -> dict[str, Any]:
        if isinstance(record_json, dict):
            record = record_json
        else:
            try:
                record = json.loads(record_json)
            except (json.JSONDecodeError, TypeError) as e:
                return {"success": False, "record_id": None, "error_detail": f"Invalid JSON: {e}"}
        columns = [
            "invoice_number",
            "order_id",
            "vendor_name",
            "bill_to_name",
            "bill_to_address",
            "ship_to_address",
            "invoice_date",
            "due_date",
            "ship_mode",
            "line_items",
            "subtotal",
            "discount_percent",
            "discount_amount",
            "shipping_cost",
            "tax_amount",
            "total_amount",
            "currency",
            "source_email",
            "source_filename",
            "raw_extracted_text",
            "extraction_status",
        ]

        try:
            values = []
            for col in columns:
                val = record.get(col)
                if col == "line_items" and val is not None:
                    val = json.dumps(val) if not isinstance(val, str) else val
                values.append(val)

            placeholders = ", ".join(["%s"] * len(columns))
            col_names = ", ".join(columns)
            query = (
                f"INSERT INTO invoices ({col_names}) "
                f"VALUES ({placeholders}) "
                f"RETURNING id"
            )

            conn = psycopg2.connect(self._get_connection_string())
            try:
                with conn.cursor() as cur:
                    cur.execute(query, values)
                    record_id = cur.fetchone()[0]
                conn.commit()
            finally:
                conn.close()

            return {
                "success": True,
                "record_id": record_id,
                "error_detail": None,
            }

        except psycopg2.Error as e:
            return {
                "success": False,
                "record_id": None,
                "error_detail": str(e),
            }
        except Exception as e:
            return {
                "success": False,
                "record_id": None,
                "error_detail": f"Unexpected error: {e}",
            }
