import threading
import time
import uuid


class AsyncTaskQueue:
    MAX_ATTEMPTS = 3
    BASE_DELAY = 1.0

    def __init__(self, base_delay=None):
        self._results = {}  # task_id -> dict
        self._lock = threading.Lock()
        self._base_delay = base_delay if base_delay is not None else self.BASE_DELAY

    def enqueue(self, task_fn, *args, **kwargs):
        task_id = str(uuid.uuid4())
        with self._lock:
            self._results[task_id] = {
                "status": "pending",
                "result": None,
                "error": None,
                "attempts": 0,
            }
        t = threading.Thread(
            target=self._run, args=(task_id, task_fn, args, kwargs), daemon=True
        )
        t.start()
        return task_id

    def _run(self, task_id, task_fn, args, kwargs):
        delay = self._base_delay
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            with self._lock:
                self._results[task_id]["status"] = "running"
                self._results[task_id]["attempts"] = attempt
            try:
                result = task_fn(*args, **kwargs)
                with self._lock:
                    self._results[task_id]["status"] = "done"
                    self._results[task_id]["result"] = result
                return
            except Exception as exc:
                with self._lock:
                    self._results[task_id]["error"] = str(exc)
                if attempt < self.MAX_ATTEMPTS:
                    time.sleep(delay)
                    delay *= 2
        with self._lock:
            self._results[task_id]["status"] = "failed"

    def get_result(self, task_id):
        with self._lock:
            return dict(self._results.get(task_id, {}))

    def get_status(self, task_id):
        with self._lock:
            entry = self._results.get(task_id)
            return entry["status"] if entry else "unknown"

    def retry_failed(self, task_id):
        """Re-enqueue a failed task by resetting its state and running again."""
        with self._lock:
            entry = self._results.get(task_id)
            if entry is None or entry["status"] != "failed":
                return False
            # We cannot re-run without the original fn; store it for retry support
            task_fn = entry.get("_task_fn")
            args = entry.get("_args", ())
            kwargs = entry.get("_kwargs", {})
            if task_fn is None:
                return False
            entry["status"] = "pending"
            entry["result"] = None
            entry["error"] = None
            entry["attempts"] = 0
        t = threading.Thread(
            target=self._run, args=(task_id, task_fn, args, kwargs), daemon=True
        )
        t.start()
        return True

    def enqueue_retryable(self, task_fn, *args, **kwargs):
        """Like enqueue but stores task fn so retry_failed works."""
        task_id = str(uuid.uuid4())
        with self._lock:
            self._results[task_id] = {
                "status": "pending",
                "result": None,
                "error": None,
                "attempts": 0,
                "_task_fn": task_fn,
                "_args": args,
                "_kwargs": kwargs,
            }
        t = threading.Thread(
            target=self._run, args=(task_id, task_fn, args, kwargs), daemon=True
        )
        t.start()
        return task_id
