"""Bounded worker queue with cooperative cancellation and persistent results."""

from __future__ import annotations
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from .safety import InputError
from .storage import Store


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Cancelled(Exception):
    pass


class JobContext:
    def __init__(self, manager: "Jobs", job_id: str, signal: threading.Event):
        self.manager, self.id, self.signal = manager, job_id, signal

    def check(self) -> None:
        if self.signal.is_set():
            raise Cancelled(
                "The job was cancelled. Check any outputs and desktop actions that already completed."
            )

    def progress(self, value: int, message: str = "") -> None:
        self.check()
        self.manager.store.execute(
            "UPDATE jobs SET progress=?,message=? WHERE id=?",
            (max(0, min(100, value)), message[:300], self.id),
        )


class Jobs:
    def __init__(self, store: Store):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="local-work")
        self.signals: dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.store.execute(
            "UPDATE jobs SET status='interrupted',error=? "
            "WHERE status IN ('queued','running')",
            ("The previous app session ended before this job finished.",),
        )

    def submit(self, kind: str, work) -> str:
        with self.lock:
            active = self.store.one(
                "SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running')"
            )["n"]
            if active >= 8:
                raise InputError("The queue is full. Wait for a job to finish.")
            job_id = uuid.uuid4().hex
            signal = threading.Event()
            self.signals[job_id] = signal
            self.store.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, kind, "queued", utcnow(), None, 0, "", None, None),
            )
            self.pool.submit(self._run, job_id, signal, work)
        return job_id

    def _run(self, job_id: str, signal: threading.Event, work) -> None:
        context = JobContext(self, job_id, signal)
        try:
            context.check()
            self.store.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
            result = work(context)
            context.check()
            self.store.execute(
                "UPDATE jobs SET status='done',finished=?,progress=100,result=? WHERE id=?",
                (utcnow(), json.dumps(result, ensure_ascii=False), job_id),
            )
        except Cancelled as exc:
            self.store.execute(
                "UPDATE jobs SET status='cancelled',finished=?,error=? WHERE id=?",
                (utcnow(), str(exc), job_id),
            )
        except Exception as exc:
            self.store.execute(
                "UPDATE jobs SET status='failed',finished=?,error=? WHERE id=?",
                (utcnow(), f"{type(exc).__name__}: {str(exc)[:500]}", job_id),
            )
        finally:
            with self.lock:
                self.signals.pop(job_id, None)

    def get(self, job_id: str) -> dict:
        row = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row is None:
            raise InputError("The job does not exist.")
        row["result"] = json.loads(row["result"]) if row["result"] else None
        return row

    def recent(self) -> list[dict]:
        return self.store.rows(
            "SELECT id,kind,status,created,finished,progress,message,error FROM jobs "
            "ORDER BY created DESC,rowid DESC LIMIT 12"
        )

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            signal = self.signals.get(job_id)
            if signal:
                signal.set()
        return {"requested": signal is not None}

    def close(self) -> None:
        for signal in list(self.signals.values()):
            signal.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
