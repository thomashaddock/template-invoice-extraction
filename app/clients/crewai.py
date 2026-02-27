import os

import requests


class CrewAiClient:
    """Client for CrewAI Enterprise API (kickoff and status polling)."""

    _URL = os.getenv("CREWAI_ENTERPRISE_API_URL")
    _API_KEY = os.getenv("CREWAI_ENTERPRISE_BEARER_TOKEN")

    def kickoff(self, drive_file_id: str, source_filename: str) -> dict:
        payload: dict = {
            "inputs": {
                "drive_file_id": drive_file_id,
                "source_filename": source_filename,
            },
        }
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
