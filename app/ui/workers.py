"""Run blocking work (transcription, AI calls, ffmpeg export) off the UI thread."""
import logging
import threading

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(float)
    status = Signal(str)

    def __init__(self, fn, *args, report_progress=False, cancellable=False,
                 report_status=False, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.cancel_event = threading.Event() if cancellable else None
        if report_progress:
            self.kwargs["progress_cb"] = self.progress.emit
        if report_status:
            self.kwargs["status_cb"] = self.status.emit
        if cancellable:
            self.kwargs["cancel_event"] = self.cancel_event

    def cancel(self):
        if self.cancel_event is not None:
            self.cancel_event.set()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            logger.exception("Worker failed: %s", self.fn.__name__)
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(result)
