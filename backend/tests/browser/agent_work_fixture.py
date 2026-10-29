"""Offline browser fixture: signed comment -> private reply -> DM -> durable owner wait.

Only disposable *_test databases. Uses production services with a scripted fake model;
no real Instagram call and no claim about natural-language model quality.
"""

import json
import sys
import uuid
from unittest.mock import patch

from sqlalchemy import select, text

from app.agent.coordinator import run_activation
from app.agent.models import AgentThread
from app.agent.tools.broker import build_default_broker
from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.db import Base, get_session_factory
from app.handlers import load_handlers
from app.identity.models import User
from app.inbox.models import Message
from app.integrations.llm.fake import FakeLLMProvider
from app.operations.private_reply import execute
from app.owner_requests.models import OwnerQuestion
from tests.integration.agent.test_comments import process
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, drain
from tests.integration.agent.test_owner_requests import queue_answer
from tests.integration.agent.test_private_reply import propose, ready


def main() -> None:
    settings = get_settings()
    if not settings.database_url.rsplit("/", 1)[-1].endswith("_test"):
        raise RuntimeError("Browser fixtures require a disposable *_test database")
    load_handlers()
    factory = get_session_factory()
    clock = SystemClock()
    if sys.argv[1] == "prepare":
        with factory() as db:
            tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
            db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            db.commit()
        world, ctx, target = ready(factory, clock)
        proposal = propose(factory, clock, ctx, target)
        if not proposal.ok:
            raise RuntimeError("Private reply fixture proposal failed")
        execute(
            factory, clock, world[3], world[0].workspace_id, uuid.UUID(proposal.data["action_id"])
        )
        deliver(
            factory,
            clock,
            world,
            "Can I receive an exception for my request?",
            customer="public-person",
        )
        process(factory, clock, world)
        with factory() as db:
            thread = db.scalar(
                select(AgentThread).where(
                    AgentThread.social_account_id == world[1], AgentThread.surface == "dm"
                )
            )
            thread_id = thread.id
        fake = FakeLLMProvider()
        fake.queue_step(
            result(
                "tool",
                tool_name="owner.ask",
                tool_arguments={
                    "question": "Can this customer receive a one-off exception?",
                    "required_info": "exception",
                    "visibility": "customer_reply",
                    "holding_response": False,
                },
            )
        )
        run_activation(
            deps(factory, clock, fake), world[0].workspace_id, thread_id, build_default_broker()
        )
        with factory() as db:
            question = db.scalar(select(OwnerQuestion).where(OwnerQuestion.thread_id == thread_id))
            user = db.get(User, uuid.UUID(world[0].actor.id))
            user.ui_locale = "en"
            thread = db.get(AgentThread, thread_id)
            db.commit()
            print(
                json.dumps(
                    {
                        "email": user.email,
                        "password": "correct-horse-battery",
                        "workspace": str(world[0].workspace_id),
                        "account": str(world[1]),
                        "question": str(question.id),
                        "conversation": str(thread.dm_conversation_id),
                        "comment_thread": str(ctx.thread_id),
                    }
                )
            )
    elif sys.argv[1] == "resume":
        with factory() as db:
            question = db.get(OwnerQuestion, uuid.UUID(sys.argv[2]))
            if question is None or question.answer_id is None:
                raise RuntimeError("Expected the UI's committed answer")
            from app.owner_requests.models import OwnerAnswer

            answer = db.get(OwnerAnswer, question.answer_id)
            workspace = question.workspace_id
        fake = FakeLLMProvider()
        queue_answer(fake, answer.id, answer.version)
        with patch("app.agent.jobs.deps_for", lambda _: deps(factory, clock, fake)):
            drain(factory, clock, max_jobs=100)
        with factory() as db:
            messages = list(
                db.scalars(
                    select(Message).where(
                        Message.workspace_id == workspace, Message.direction == "outbound"
                    )
                )
            )
            print(
                json.dumps({"outbound_count": len(messages), "texts": [m.text for m in messages]})
            )
    else:
        raise RuntimeError("Unknown fixture action")


if __name__ == "__main__":
    main()
