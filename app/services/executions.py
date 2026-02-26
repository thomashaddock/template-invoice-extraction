import json
import logging
import time

from clients import CrewAiClient, GDriveClient
from models import Execution
# from webhook_server import wait_for_result

logger = logging.getLogger(__name__)


class ExecutionsService:
    def __init__(self):
        self.gdrive = GDriveClient()
        self.crewai = CrewAiClient()

    # @property
    # def uses_webhooks(self) -> bool:
    #     return self.crewai.webhooks_enabled

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

    def wait_for_result(self, kickoff_id: str, timeout: int = 300, progress_cb=None) -> dict | None:
        """
        Wait for the execution result by polling GET /status/{kickoff_id}.

        *progress_cb* is an optional callable(pct, text) for UI updates.
        """
        return self._wait_via_polling(kickoff_id, timeout, progress_cb)

    # def _wait_via_webhook(self, kickoff_id: str, timeout: int) -> dict | None:
    #     logger.info("Waiting for webhook result for %s (timeout=%ds)", kickoff_id, timeout)
    #     result = wait_for_result(kickoff_id, timeout=timeout)
    #     if result:
    #         return result
    #
    #     logger.info("Webhook timeout for %s — trying single status poll fallback", kickoff_id)
    #     return self._check_execution(kickoff_id)

    def _wait_via_polling(self, kickoff_id: str, timeout: int, progress_cb=None) -> dict | None:
        logger.info("Polling for %s (timeout=%ds)", kickoff_id, timeout)
        elapsed = 0
        poll_interval = 5
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            if progress_cb:
                pct = min(40 + int((elapsed / timeout) * 55), 95)
                progress_cb(pct, f"Waiting for results... ({elapsed}s)")

            result = self._check_execution(kickoff_id)
            if result:
                return result

            try:
                response = self.crewai.status(kickoff_id)
                state = response.get("state", "")
                if state in ("FAILURE", "REVOKED"):
                    return {
                        "extraction_status": "failed",
                        "error_message": f"Execution {state.lower()}",
                    }
            except Exception:
                continue

        return None

    def _check_execution(self, file_id: str) -> dict | None:
        try:
            response = self.crewai.status(file_id)
        except Exception:
            return None

        state = response.get("state")
        if state not in ("SUCCESS",):
            return None

        result_json = response.get("result_json")
        if isinstance(result_json, dict) and result_json:
            return result_json

        result_raw = response.get("result")
        if not result_raw:
            return None

        try:
            if isinstance(result_raw, str):
                return json.loads(result_raw)
            return result_raw
        except (json.JSONDecodeError, TypeError):
            return None
