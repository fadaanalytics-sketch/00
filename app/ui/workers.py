"""Run blocking work (transcription, AI calls, ffmpeg export) off the UI thread."""
from PySide6.QtCore import QThread, Signal


class WorkerThread(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(float)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(result)
