from models import DriveFile


def download_link(file: DriveFile):
    if file and file.url:
        return f'<a href="{file.url}" target="_blank">View in Drive</a>'
    return "N/A"
