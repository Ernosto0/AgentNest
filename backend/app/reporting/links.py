"""Where a report number leads (plan H1).

A link is ``{"api": <API path>, "route": <frontend route>}``; either may be ``None``. The metric
``link`` is its drill-down list, which runs the very same row set as the number (AC-E3).
``screen_link`` exists only where an existing screen can be filtered *exactly* like the metric
(a pending approval, an item on hold); no other metric has one.
"""

import uuid
from datetime import date

API_ROOT = "/api/v1/workspaces"

Link = dict[str, str | None]


def _link(api: str | None, route: str | None) -> Link:
    return {"api": api, "route": route}


def metric_link(
    workspace_id: uuid.UUID, local_date: date, key: str, snapshot_id: uuid.UUID | None = None
) -> Link:
    ws = str(workspace_id)
    query = f"?snapshot_id={snapshot_id}" if snapshot_id else ""
    return _link(
        f"{API_ROOT}/{ws}/reports/daily/{local_date.isoformat()}/metrics/{key}{query}",
        f"/w/{ws}/more/reports/{local_date.isoformat()}/{key}{query}",
    )


def screen_link(workspace_id: uuid.UUID, key: str) -> Link | None:
    ws = str(workspace_id)
    if key == "pending_approvals_now":
        return _link(f"{API_ROOT}/{ws}/approvals?status=pending", f"/w/{ws}/approvals")
    if key == "content_on_hold_now":
        return _link(
            f"{API_ROOT}/{ws}/content-items?status=on_hold", f"/w/{ws}/content?status=on_hold"
        )
    return None


def conversation_link(workspace_id: uuid.UUID, conversation_id: uuid.UUID) -> Link:
    ws = str(workspace_id)
    return _link(
        f"{API_ROOT}/{ws}/conversations/{conversation_id}", f"/w/{ws}/inbox/{conversation_id}"
    )


def content_link(workspace_id: uuid.UUID, content_id: uuid.UUID) -> Link:
    ws = str(workspace_id)
    return _link(f"{API_ROOT}/{ws}/content-items/{content_id}", f"/w/{ws}/content/{content_id}")


def approval_link(workspace_id: uuid.UUID, approval_id: uuid.UUID) -> Link:
    ws = str(workspace_id)
    return _link(f"{API_ROOT}/{ws}/approvals/{approval_id}", f"/w/{ws}/approvals")


def operation_link(workspace_id: uuid.UUID, operation_id: uuid.UUID, route: str | None) -> Link:
    return _link(f"{API_ROOT}/{workspace_id}/operations/{operation_id}", route)


def knowledge_link(workspace_id: uuid.UUID) -> Link:
    return _link(None, f"/w/{workspace_id}/more/knowledge")


def more_link(workspace_id: uuid.UUID) -> Link:
    return _link(None, f"/w/{workspace_id}/more")
