"""Calendar REST endpoints (list, connect-mock, patch, appointments, disconnect).

Split from ``agent/test_calendar_agent.py``: that module is marked ``commits`` (real commits and
truncation), while these tests run inside the rolled-back ``db_session`` transaction.
"""

import uuid

from app.integrations.calendar.models import CalendarConnection


def test_calendar_api_endpoints_and_oauth_flow(db_session, make_client, clock):
    """Test calendar REST endpoints (list, connect-mock, patch, appointments, disconnect)."""
    from tests.helpers.env import build_env

    env = build_env(db_session, make_client, clock)
    # Initially empty
    res = env.call(env.owner, "GET", "/calendar")
    assert res.status_code == 200
    assert res.json()["items"] == []

    # Staff cannot connect calendar
    res_staff = env.call(env.staff, "POST", "/calendar/connect-mock", json={})
    assert res_staff.status_code == 403

    # Owner connects mock calendar
    res_conn = env.call(
        env.owner,
        "POST",
        "/calendar/connect-mock",
        json={
            "account_email": "owner@golkent.test",
            "calendar_summary": "Golkent Bookings",
            "default_slot_duration_minutes": 45,
        },
    )
    assert res_conn.status_code == 201
    conn_data = res_conn.json()
    conn_id = conn_data["id"]
    assert conn_data["account_email"] == "owner@golkent.test"
    assert conn_data["default_slot_duration_minutes"] == 45
    assert conn_data["status"] == "connected"
    assert conn_data["is_simulated"] is True

    # Update slot duration
    res_patch = env.call(
        env.owner,
        "PATCH",
        f"/calendar/{conn_id}",
        json={"default_slot_duration_minutes": 60},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["default_slot_duration_minutes"] == 60

    # List appointments
    res_appts = env.call(env.owner, "GET", "/calendar/appointments")
    assert res_appts.status_code == 200
    assert res_appts.json()["items"] == []

    # Disconnect
    res_disc = env.call(env.owner, "POST", f"/calendar/{conn_id}/disconnect")
    assert res_disc.status_code == 200
    assert res_disc.json()["status"] == "disconnected"
    conn_row = db_session.get(CalendarConnection, uuid.UUID(conn_id))
    assert (
        conn_row is not None
        and conn_row.token_ciphertext is None
        and conn_row.refresh_token_ciphertext is None
    )
