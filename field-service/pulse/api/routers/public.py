"""What anyone may read without signing in: AC-wide totals, nothing about a person.

The public site is read-only. This router answers GET only and returns sums and
counts: spend by bucket and by month (expenses only - money given is not money
spent), reports by status, category and block, and the open issues. It never
returns a ledger row, a member, a name, a note, a transcript, media or a
coordinate, and reports in a restricted category are left out entirely.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException

from pulse.api.deps import get_state
from pulse.api.routers.ledger import plain
from pulse.core_adapter import ac_by_number
from pulse.metrics import spend as sm

router = APIRouter(prefix="/acs/{ac_number}/field/public", tags=["public"])

# Reports a reader can see: filed (not a draft), not a duplicate, not restricted.
_REPORTS = ("FROM field.report r LEFT JOIN field.report_category c ON c.category_id = r.category_id "
            "WHERE r.ac_id = %(ac)s AND r.status NOT IN ('draft', 'duplicate') AND NOT r.restricted")
_OPEN = ("new", "acknowledged", "assigned", "in_progress")
_EXECUTOR = ThreadPoolExecutor(max_workers=7, thread_name_prefix="public")


@router.get("/summary")
def public_summary(ac_number: int, state=Depends(get_state)) -> dict:
    ac = ac_by_number(state.core, ac_number)
    if ac is None:
        raise HTTPException(404, "unknown AC")
    blocks = {b.block_id: b for b in state.core.list_blocks(ac.ac_id)}
    p = {"ac": ac.ac_id}
    where = "t.ac_id = %(ac)s"
    open_ = list(_OPEN)
    reads = {
        "spend_total": (f"WITH {sm.spend_cte(where)} SELECT COALESCE(SUM(amount), 0)::numeric(14, 2) AS total, "
                        f"count(*) AS entries FROM spend", p),
        "by_bucket": (f"WITH {sm.spend_cte(where)} SELECT b.code, b.name_en, b.name_hi, "
                      f"SUM(s.amount)::numeric(14, 2) AS amount FROM spend s "
                      f"JOIN field.exp_bucket b ON b.bucket_id = s.bucket_id "
                      f"GROUP BY b.code, b.name_en, b.name_hi ORDER BY amount DESC, b.code", p),
        "by_month": (f"WITH {sm.spend_cte(where)} SELECT to_char(txn_date, 'YYYY-MM') AS month, "
                     f"SUM(amount)::numeric(14, 2) AS amount FROM spend GROUP BY 1 ORDER BY 1", p),
        "by_status": (f"SELECT r.status, count(*) AS reports {_REPORTS} GROUP BY r.status ORDER BY r.status", p),
        "by_category": (f"SELECT c.code, c.name_en, c.name_hi, count(*) AS reports, "
                        f"count(*) FILTER (WHERE r.status = ANY(%(open)s)) AS open {_REPORTS} "
                        f"GROUP BY c.code, c.name_en, c.name_hi ORDER BY reports DESC, c.code",
                        {**p, "open": open_}),
        "by_block": (f"SELECT r.block_id, count(*) AS reports, "
                     f"count(*) FILTER (WHERE r.status = ANY(%(open)s)) AS open {_REPORTS} "
                     f"GROUP BY r.block_id ORDER BY reports DESC", {**p, "open": open_}),
        "issues": ("SELECT i.issue_no, i.title, i.status, i.block_id, c.code AS category_code, "
                   "c.name_en AS category_en, c.name_hi AS category_hi, "
                   "(i.created_at AT TIME ZONE 'Asia/Kolkata')::date AS opened_on "
                   "FROM field.issue i LEFT JOIN field.report_category c ON c.category_id = i.category_id "
                   "WHERE i.ac_id = %(ac)s AND NOT COALESCE(c.restricted, false) "
                   "ORDER BY i.status DESC, i.created_at DESC LIMIT 200", p),
    }

    def read(sql, params):
        with state.pool.connection() as conn:
            return conn.execute(sql, params).fetchall()

    # Seven independent reads at once: a remote database costs a round trip each.
    futures = {k: _EXECUTOR.submit(read, sql, params) for k, (sql, params) in reads.items()}
    got = {k: f.result() for k, f in futures.items()}
    spend_total = got["spend_total"][0]
    by_bucket, by_month, by_status = got["by_bucket"], got["by_month"], got["by_status"]
    by_category, by_block, issues = got["by_category"], got["by_block"], got["issues"]

    total = spend_total["total"]

    def block_names(block_id):
        b = blocks.get(block_id)
        return {"block_id": block_id, "block_en": b.name_en if b else None,
                "block_hi": b.name_hi if b else None}

    return plain({
        "ac_number": ac.ac_number,
        "spend": {
            "total": total, "entries": spend_total["entries"],
            "by_bucket": [{**dict(r), "share_pct": sm.spend_share_pct(r["amount"], total)}
                          for r in by_bucket],
            "by_month": [dict(r) for r in by_month],
        },
        "reports": {
            "filed": sum(r["reports"] for r in by_status),
            "open": sum(r["reports"] for r in by_status if r["status"] in _OPEN),
            "by_status": [dict(r) for r in by_status],
            "by_category": [dict(r) for r in by_category],
            "by_block": [{**block_names(r["block_id"]), "reports": r["reports"], "open": r["open"]}
                         for r in by_block],
        },
        "issues": {
            "open": sum(1 for i in issues if i["status"] == "open"),
            "closed": sum(1 for i in issues if i["status"] == "closed"),
            "list": [{**{k: i[k] for k in ("issue_no", "title", "status", "category_code",
                                            "category_en", "category_hi", "opened_on")},
                      **block_names(i["block_id"])} for i in issues],
        },
    })
