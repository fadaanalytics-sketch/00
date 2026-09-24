import threading
import time

import pytest

from ava.errors import UserError
from ava.jobs import JobManager


def wait(job, timeout=5):
    deadline = time.time() + timeout
    while job.status in ("queued", "running") and time.time() < deadline:
        time.sleep(0.02)
    return job


def test_job_success_progress_and_result():
    m = JobManager()

    def work(job):
        job.update(0.5, "نص الطريق")
        return {"ok": 1}

    job = wait(m.submit("x", "p1", work))
    assert job.status == "done" and job.result == {"ok": 1} and job.progress == 1.0


def test_user_error_message_is_shown_as_is():
    m = JobManager()

    def work(job):
        raise UserError("لازم تفرّغ الأول")

    job = wait(m.submit("x", "p1", work))
    assert job.status == "error" and job.message == "لازم تفرّغ الأول"


def test_unexpected_error_keeps_details():
    m = JobManager()
    job = wait(m.submit("x", "p1", lambda job: 1 / 0))
    assert job.status == "error" and "division" in job.error


def test_cancel_running_job():
    m = JobManager()
    started = threading.Event()

    def work(job):
        started.set()
        while True:
            job.check_cancel()
            time.sleep(0.01)

    job = m.submit("x", "p1", work)
    assert started.wait(2)
    m.cancel(job.id)
    assert wait(job).status == "cancelled"


def test_duplicate_active_job_rejected_but_other_kinds_queue():
    m = JobManager()
    gate = threading.Event()
    first = m.submit("export", "p1", lambda job: gate.wait(5))
    with pytest.raises(UserError):
        m.submit("export", "p1", lambda job: None)
    other = m.submit("preview", "p1", lambda job: "ok")
    assert other.status == "queued"  # single worker: waits its turn
    gate.set()
    assert wait(first).status == "done" and wait(other).status == "done"
    assert [j.kind for j in m.list("p1")] == ["export", "preview"]
    assert m.list("p1", active_only=True) == []
