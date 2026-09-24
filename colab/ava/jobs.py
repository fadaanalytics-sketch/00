"""A single-worker background job queue with progress, status messages and cancel.

One worker on purpose: transcription (GPU) and exports (GPU/CPU encode) would only
slow each other down if run concurrently on a Colab VM.
"""
import logging
import queue
import threading
import time
import traceback

from . import storage
from .errors import Cancelled, UserError

logger = logging.getLogger(__name__)

ACTIVE = ("queued", "running")
MAX_KEPT = 200


class Job:
    def __init__(self, kind: str, project_id: str | None):
        self.id = storage.new_id("job")
        self.kind = kind
        self.project_id = project_id
        self.status = "queued"
        self.progress = 0.0
        self.message = "في الانتظار..."
        self.result = None
        self.error = None
        self.created_at = time.time()
        self.cancel_event = threading.Event()

    def update(self, progress: float | None = None, message: str | None = None):
        if progress is not None:
            self.progress = max(0.0, min(1.0, float(progress)))
        if message is not None:
            self.message = message

    def check_cancel(self):
        if self.cancel_event.is_set():
            raise Cancelled()

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "project_id": self.project_id,
                "status": self.status, "progress": round(self.progress, 4),
                "message": self.message, "result": self.result, "error": self.error}


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._worker = None

    def submit(self, kind: str, project_id: str | None, fn) -> Job:
        with self._lock:
            if project_id and any(j.project_id == project_id and j.kind == kind and j.status in ACTIVE
                                  for j in self._jobs.values()):
                raise UserError("هذه العملية قيد التنفيذ بالفعل لهذا المشروع")
            job = Job(kind, project_id)
            self._jobs[job.id] = job
            self._prune()
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, daemon=True, name="ava-jobs")
                self._worker.start()
        self._queue.put((job, fn))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job and job.status in ACTIVE:
            job.cancel_event.set()
            job.message = "جارٍ الإلغاء..."
        return job

    def list(self, project_id: str | None = None, active_only: bool = False) -> list[Job]:
        jobs = [j for j in self._jobs.values()
                if (project_id is None or j.project_id == project_id)
                and (not active_only or j.status in ACTIVE)]
        return sorted(jobs, key=lambda j: j.created_at)

    def _prune(self):
        if len(self._jobs) <= MAX_KEPT:
            return
        done = sorted((j for j in self._jobs.values() if j.status not in ACTIVE), key=lambda j: j.created_at)
        for j in done[: len(self._jobs) - MAX_KEPT]:
            del self._jobs[j.id]

    def _run(self):
        while True:
            job, fn = self._queue.get()
            if job.cancel_event.is_set():
                job.status, job.message = "cancelled", "تم الإلغاء"
                continue
            job.status, job.message = "running", "جارٍ التنفيذ..."
            try:
                job.result = fn(job)
                job.status, job.progress, job.message = "done", 1.0, "تم بنجاح"
            except Cancelled:
                job.status, job.message = "cancelled", "تم الإلغاء"
            except UserError as e:
                job.status, job.error, job.message = "error", str(e), str(e)
            except Exception as e:  # noqa: BLE001 - surfaced to the UI, full trace logged
                logger.error("job %s (%s) failed:\n%s", job.id, job.kind, traceback.format_exc())
                job.status, job.error, job.message = "error", str(e), "حدث خطأ"
