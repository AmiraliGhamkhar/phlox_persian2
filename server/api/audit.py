"""Audit log read/export endpoints.

Read-only surface for the audit trail written by AuditMiddleware.
"""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from server.database.repositories.audit import get_events

router = APIRouter(tags=["audit"])


@router.get("")
def list_audit(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
):
    """Return audit events newest-first, paginated."""
    return {"events": get_events(limit=limit, offset=offset, from_date=from_date, to_date=to_date)}


@router.get("/generation-stats")
def generation_stats(limit: int = Query(200, ge=1, le=1000)):
    """Aggregate generation-quality telemetry (plan ref C3).

    Counts from the file-based generation reports: how many processed notes
    carried verification findings, and how many flagged points persisted into
    the saved note versus were resolved by clinician edits. Read-only; no
    clinical content is exposed — only counters and reasons.
    """
    from server.utils.generation_reports import stats

    return stats(limit=limit)


@router.get("/export")
def export_audit(format: str = Query("csv", pattern="^(csv|json)$")):
    """Stream the full audit log as CSV (default) or JSON lines."""
    events = get_events(limit=10000)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if format == "json":
        import json

        buf = io.StringIO()
        for e in events:
            buf.write(json.dumps(e, default=str))
            buf.write("\n")
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f'attachment; filename="audit-{stamp}.ndjson"'},
        )

    def rows():
        out = io.StringIO()
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "id",
                "timestamp",
                "actor",
                "method",
                "path",
                "status",
                "client_ip",
                "duration_ms",
            ],
        )
        writer.writeheader()
        yield out.getvalue()
        out.seek(0)
        out.truncate(0)
        for e in events:
            writer.writerow(e)
            yield out.getvalue()
            out.seek(0)
            out.truncate(0)

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{stamp}.csv"'},
    )
