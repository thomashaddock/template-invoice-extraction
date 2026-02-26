import json
import os
from datetime import datetime, timezone
from io import BytesIO

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from models import DriveFile

SCOPES = ["https://www.googleapis.com/auth/drive"]


class GDriveClient:
    def __init__(self):
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if os.path.isfile(sa_json):
            credentials = service_account.Credentials.from_service_account_file(
                sa_json, scopes=SCOPES
            )
        else:
            service_account_info = json.loads(sa_json)
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
        self.service = build("drive", "v3", credentials=credentials)
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()

    def upload_file(self, file_bytes: bytes, filename: str) -> DriveFile:
        file_metadata = {
            "name": filename,
            "parents": [self.folder_id],
        }
        media = MediaIoBaseUpload(
            BytesIO(file_bytes), mimetype="application/pdf", resumable=True
        )
        result = (
            self.service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, createdTime, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

        return DriveFile(
            file_id=result["id"],
            name=result.get("name", filename),
            url=result.get("webViewLink", ""),
            last_modified=_parse_drive_time(result.get("createdTime")),
        )

    def list_files(self) -> list[DriveFile]:
        query = (
            f"'{self.folder_id}' in parents"
            " and mimeType='application/pdf'"
            " and trashed=false"
        )
        results = (
            self.service.files()
            .list(
                q=query,
                fields="files(id, name, createdTime, webViewLink)",
                orderBy="createdTime desc",
                pageSize=50,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )

        files = []
        for f in results.get("files", []):
            files.append(
                DriveFile(
                    file_id=f["id"],
                    name=f.get("name", ""),
                    url=f.get("webViewLink", ""),
                    last_modified=_parse_drive_time(f.get("createdTime")),
                )
            )
        return files

    def get_download_url(self, file_id: str) -> str:
        """Return a direct download URL for the file."""
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    def download_file(self, file_id: str) -> bytes:
        """Download file content by ID."""
        request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
        from googleapiclient.http import MediaIoBaseDownload

        buffer = BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()


def _parse_drive_time(time_str: str | None) -> datetime | None:
    if not time_str:
        return None
    return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
