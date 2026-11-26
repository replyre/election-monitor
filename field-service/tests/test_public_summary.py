"""GET /acs/{n}/field/public/summary: anyone may read it, and it holds totals only."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pulse.api.main import create_app
from pulse.common.clock import utcnow
from pulse.ledger import service as ledger
from pulse.ledger.service import ExpenseInput
from pulse.reports import service as reports
from tests.helpers import bucket_id

URL = "/acs/32/field/public/summary"
D = Decimal
# Keys that would identify a person or a place they stood: none may appear anywhere.
FORBIDDEN = {"display_name", "name", "member_id", "from_member_id", "to_member_id", "created_by",
             "reporter_member_id", "assigned_to", "note_text", "transcript_hi", "lat", "lon",
             "phone", "txn_id", "txn_no", "close_note", "report_id"}


def _category(conn, code):
    return conn.execute("SELECT category_id FROM field.report_category WHERE code = %s",
                        (code,)).fetchone()["category_id"]


@pytest.fixture
def world(conn, core, limits, team):
    p, a = team["principal"], team["incharge-a"]
    row = ledger.create_advance(conn, core, p, to_member_id=a, amount=D("50000"), limits=limits)
    ledger.acknowledge(conn, row["txn_id"], a)
    food = bucket_id(conn, "FOOD")
    for who, amount in (("worker-a1", "1000"), ("incharge-a", "500")):
        ledger.create_expense(conn, core, team[who], ExpenseInput(amount=D(amount), bucket_id=food),
                              limits=limits)
    worker = conn.execute("SELECT * FROM field.member WHERE member_id = %s",
                          (team["worker-a1"],)).fetchone()
    now = utcnow()
    for code, status in (("HEALTH", "new"), ("HEALTH", "resolved"), ("LAW", "new"), ("HEALTH", "draft")):
        rid = reports.open_draft(conn, core, worker, now=now, created_via="web")["report_id"]
        reports.add_note(conn, rid, "Ramesh said the pump is broken", actor=worker["member_id"], now=now)
        reports.set_area(conn, core, rid, "blk-a", "area-a1", "chosen", actor=worker["member_id"], now=now)
        reports.set_location(conn, rid, 24.18, 86.30, actor=worker["member_id"], now=now)
        reports.set_category(conn, rid, _category(conn, code), actor=worker["member_id"], now=now)
        if status != "draft":
            reports.file(conn, core, rid, how="web", actor=worker["member_id"], now=now)
        if status == "resolved":
            conn.execute("UPDATE field.report SET status = 'resolved', resolved_at = now() "
                         "WHERE report_id = %s", (rid,))
    conn.execute(
        "INSERT INTO field.issue (issue_no, ac_id, title, category_id, block_id, area_id, opened_by) "
        "VALUES ('32-I-000001', 'ac-32', 'Hand pump broken', %s, 'blk-a', 'area-a1', %s)",
        (_category(conn, "HEALTH"), p))
    return team


@pytest.fixture
def anonymous(settings, pool, core, fake_tg, world):
    app = create_app(settings, pool=pool, core=core, telegram_client=fake_tg)
    with TestClient(app) as c:
        yield c


def _keys(value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(value, list):
        for v in value:
            _keys(v, out)
    return out


def test_anyone_reads_it_without_a_token(anonymous):
    r = anonymous.get(URL)
    assert r.status_code == 200, r.text


def test_spend_is_expenses_only(anonymous):
    spend = anonymous.get(URL).json()["spend"]
    assert D(spend["total"]) == D("1500.00")      # the 50,000 advance is money given, not spent
    assert spend["entries"] == 2
    assert [b["code"] for b in spend["by_bucket"]] == ["FOOD"]


def test_restricted_and_draft_reports_are_left_out(anonymous):
    reports = anonymous.get(URL).json()["reports"]
    assert reports["filed"] == 2 and reports["open"] == 1
    assert {c["code"] for c in reports["by_category"]} == {"HEALTH"}


def test_nothing_identifies_a_person_or_a_spot(anonymous):
    body = anonymous.get(URL).json()
    assert not (_keys(body, set()) & FORBIDDEN)
    assert "Ramesh" not in anonymous.get(URL).text and "86.3" not in anonymous.get(URL).text


def test_open_issues_are_listed_with_their_block(anonymous):
    issues = anonymous.get(URL).json()["issues"]
    assert issues["open"] == 1
    assert issues["list"][0]["title"] == "Hand pump broken"
    assert issues["list"][0]["block_id"] == "blk-a"
    assert issues["list"][0]["block_en"] == "Demo Block A"


def test_it_only_reads(anonymous):
    for method in ("post", "put", "patch", "delete"):
        assert getattr(anonymous, method)(URL).status_code == 405


def test_an_unknown_constituency_is_404(anonymous):
    assert anonymous.get("/acs/99/field/public/summary").status_code == 404
