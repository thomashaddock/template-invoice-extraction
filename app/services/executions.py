import json
from collections import defaultdict

from clients import CrewAiClient, GDriveClient
from models import Execution


class ExecutionsService:
    def __init__(self):
        self.gdrive = GDriveClient()
        self.crewai = CrewAiClient()

    def list_executions(self) -> list[Execution]:
        files = self.gdrive.list_files()

        executions = []
        for drive_file in files:
            execution = Execution(
                uuid=drive_file.file_id,
                input_file=drive_file,
                started_at=drive_file.last_modified,
                status="pending",
            )

            result = self._check_execution(drive_file.file_id)
            if result:
                execution.status = result.get("extraction_status", "completed")
                execution.invoice_data = result.get("invoice_data")
                execution.db_record_id = result.get("db_record_id")
                execution.error_message = result.get("error_message")
                if execution.status in ("processed", "completed"):
                    execution.status = "completed"

            executions.append(execution)

        return executions

    def start_execution(self, file: bytes, filename: str) -> str:
        drive_file = self.gdrive.upload_file(file, filename)

        response = self.crewai.kickoff(drive_file.file_id, filename)
        kickoff_id = response.get("kickoff_id", drive_file.file_id)
        return kickoff_id

    def _check_execution(self, file_id: str) -> dict | None:
        try:
            response = self.crewai.status(file_id)
        except Exception:
            return None

        state = response.get("state")
        if state not in ("SUCCESS",):
            return None

        result_raw = response.get("result")
        if not result_raw:
            return None

        try:
            if isinstance(result_raw, str):
                return json.loads(result_raw)
            return result_raw
        except (json.JSONDecodeError, TypeError):
            return None
