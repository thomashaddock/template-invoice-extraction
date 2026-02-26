from models import Execution

_BADGE_MAP = {
    "pending": {
        "label": "Pending",
        "icon": ":material/schedule:",
        "color": "orange",
    },
    "completed": {
        "label": "Completed",
        "icon": ":material/check:",
        "color": "green",
    },
    "failed": {
        "label": "Failed",
        "icon": ":material/error:",
        "color": "red",
    },
    "skipped": {
        "label": "Skipped",
        "icon": ":material/block:",
        "color": "grey",
    },
}


def render_badge(execution: Execution):
    return _BADGE_MAP.get(execution.status, _BADGE_MAP["pending"])
