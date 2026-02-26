import os

import requests


class CrewAiClient:
    _URL = os.getenv("CREWAI_ENTERPRISE_API_URL")
    _API_KEY = os.getenv("CREWAI_ENTERPRISE_BEARER_TOKEN")
    _WEBHOOK_URL = os.getenv("CREWAI_WEBHOOK_URL")

    def kickoff(self, drive_file_id: str, source_filename: str):
        payload = {
            "inputs": {
                "drive_file_id": drive_file_id,
                "source_filename": source_filename,
            },
        }
        if self._WEBHOOK_URL:
            payload["webhook_url"] = self._WEBHOOK_URL

        response = requests.post(
            f"{self._URL}/kickoff",
            json=payload,
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    def status(self, uuid: str):
        response = requests.get(
            f"{self._URL}/status/{uuid}",
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self._API_KEY}"}
