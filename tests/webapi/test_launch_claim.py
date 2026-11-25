"""Regression: a run must be claimed exactly once before engine.start().

Incident 25/11/2026 (run b00dbb4a): the background launch left the run 'queued'
in the DB for the whole clone; the periodic drain_queue tick re-picked it and
called engine.start a second time. The duplicate clone died with "destination
path ... already exists and is not empty", the run was marked failed, and the
first launch continued as a ghost workflow.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from src.webapi.models import RUN_PREPARING, RUN_QUEUED, Run
from src.webapi.runsvc import _launch


class CountingEngine:
    def __init__(self):
        self.calls = 0

    async def start(self, run, job, repo):
        self.calls += 1


async def test_double_launch_starts_engine_once(session_maker):
    run_id = uuid.uuid4()
    async with session_maker() as s:
        s.add(Run(id=run_id, job_id=uuid.uuid4(), trigger_type="manual",
                  status=RUN_QUEUED, session_id="sess-claim", task_queue="q-claim",
                  data_dir="/tmp/vigilo-test-claim"))
        await s.commit()

    engine = CountingEngine()
    async with session_maker() as s:
        run = await s.get(Run, run_id)
        await _launch(s, engine, run, SimpleNamespace(), None)
        await _launch(s, engine, run, SimpleNamespace(), None)

    assert engine.calls == 1
    async with session_maker() as s:
        run = await s.get(Run, run_id)
        assert run.status == RUN_PREPARING
        assert run.started_at is not None
