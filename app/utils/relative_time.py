from datetime import datetime, timezone

import humanize


def relative_time(label: str, dt: datetime):
    if not dt:
        return {"body": f"**{label}:** N/A"}

    now = datetime.now(timezone.utc)
    diff = now - dt

    return {
        "body": f"**{label}:** {humanize.naturaltime(diff)}",
        "help": dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
