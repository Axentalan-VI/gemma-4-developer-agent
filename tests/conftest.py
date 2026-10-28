"""Shared fixtures.

Nine tests read `data/tasks/tasks.jsonl` -- the competition's own task file,
with its gold patches. That file is deliberately not committed (see
`.gitignore`): this repository is public and cannot redistribute the
organisers' data. It is present on a working machine, so those tests run here;
on a fresh clone it is absent and they used to fail with a raw traceback, which
reads as a broken repository rather than as missing input.

They skip now, with the reason and the fix in the message.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "data" / "tasks" / "tasks.jsonl"


@pytest.fixture(scope="session")
def task_data() -> Path:
    """The competition's `tasks.jsonl`, or skip the test that needs it."""
    if not TASKS.exists():
        pytest.skip(
            "needs data/tasks/tasks.jsonl, which this repository does not "
            "redistribute. Download the competition data from "
            "kaggle.com/competitions/gemma-4-developer-agent and place "
            "tasks.jsonl at that path."
        )
    return TASKS
