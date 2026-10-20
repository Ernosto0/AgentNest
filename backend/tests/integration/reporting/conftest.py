"""A workspace with an owner, a manager and staff, holding the scripted day of AC-E1.

The clock stands at the end of that day (``DAY`` is a past day, ``DAY + 1`` is today), so a
report generated now covers exactly the scripted period and the snapshot metrics are as of the
instant the fixture was built for.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.reporting.periods import day_bounds
from tests.helpers.env import Env, build_env
from tests.helpers.reporting import DAY, TIMEZONE, Builder, Scenario, build_day


@dataclass
class ReportEnv:
    env: Env
    scenario: Scenario
    clock: FrozenClock
    factory: sessionmaker[Session]

    def builder(self) -> Builder:
        """Add more records to the scripted workspace (same simulated account)."""
        return Builder(
            self.env.session,
            self.env.workspace,
            self.env.owner.user,
            simulated=True,
            account=self.scenario.account,
        )


@pytest.fixture
def report_env(
    db_session: Session,
    make_client: Callable[[], TestClient],
    clock: FrozenClock,
    shared_session_factory: sessionmaker[Session],
) -> ReportEnv:
    _, end = day_bounds(DAY, TIMEZONE)
    clock.advance(end - clock.now())  # before anyone signs in: sessions are issued at this time
    env = build_env(db_session, make_client, clock)
    scenario = build_day(db_session, workspace=env.workspace, user=env.owner.user)
    db_session.commit()
    return ReportEnv(env, scenario, clock, shared_session_factory)
