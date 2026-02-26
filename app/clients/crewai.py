import os

import requests


class CrewAiClient:
    _URL = os.getenv("CREWAI_ENTERPRISE_API_URL")
    _API_KEY = os.getenv("CREWAI_ENTERPRISE_BEARER_TOKEN")
    _WEBHOOK_URL = os.getenv("CREWAI_WEBHOOK_URL")
    _WEBHOOK_BEARER_TOKEN = os.getenv("WEBHOOK_BEARER_TOKEN", "")

    @property
    def webhooks_enabled(self) -> bool:
        return bool(self._WEBHOOK_URL)

    def kickoff(self, drive_file_id: str, source_filename: str) -> dict:
        payload: dict = {
            "inputs": {
                "drive_file_id": drive_file_id,
                "source_filename": source_filename,
            },
        }

        if self._WEBHOOK_URL:
            payload["crewWebhookUrl"] = self._WEBHOOK_URL

        response = requests.post(
            f"{self._URL}/kickoff",
            json=payload,
            headers=self._headers,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def status(self, uuid: str) -> dict:
        response = requests.get(
            f"{self._URL}/status/{uuid}",
            headers=self._headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._API_KEY}"}
