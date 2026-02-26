from datetime import datetime

import humanize


def duration(label: str, started_at: datetime, completed_at: datetime):
    if not completed_at:
        return {"body": f"**{label}:** N/A"}

    diff = completed_at - started_at
    return {"body": f"**{label}:** {humanize.naturaldelta(diff)}"}
