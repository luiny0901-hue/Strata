"""Durable one-shot Desktop handoffs hosted by the existing external supervisor.

The runtime adapter owns platform/session details. This controller never launches
an inference loop, adopts a process from disk, or replays an interrupted handoff.
It must outlive the Desktop/MCP caller; MCP EOF is not a cancellation signal.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time


_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SESSION = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_NONCE = re.compile(r"^[a-f0-9]{32}$")
_TERMINAL = frozenset({"ready", "cancelled", "failed", "needs_attention"})
_STATES = _TERMINAL | {"queued", "waiting_for_handoff", "quitting", "continuing", "reopening"}


class _Abort(RuntimeError):
    def __init__(self, state, code=None):
        self.state, self.code = state, code
        super().__init__(code or state)


class DesktopRestartController:
    """Serialize Desktop handoffs and retain their exact execution receipts.

    ``runtime.prepare_binding`` is read-only and returns bounded JSON metadata,
    never credentials or conversation text. Later runtime methods must honor the
    supplied cancellation event/deadline and must not retry uncertain input.
    ``reopen`` is a bounded, idempotent recovery action for the verified app.
    """

    def __init__(self, directory: Path, runtime, *, publish_fn, clock=time.monotonic):
        root = Path(directory)
        if root.is_symlink() or (root / "desktop").is_symlink():
            raise ValueError("Desktop receipt directory must not be a symlink")
        self.directory = root / "desktop"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runtime, self.publish, self.clock = runtime, publish_fn, clock
        self.lock = threading.RLock()
        self.records = {}
        self.events = {}
        self.cancelled_ids = set()
        self.storage_failed = set()
        self.shutdown_timed_out = set()
        self.blocked_reason = None
        self.active_id = None
        self.worker = None
        self.closed = False
        self._load()

    @staticmethod
    def _validate_id(value):
        if not isinstance(value, str) or not _ID.fullmatch(value):
            raise ValueError("Desktop operation_id must contain 1..128 letters, digits, _, . or -")
        return value

    @staticmethod
    def _request(session_id, checkpoint_path, timeout):
        if not isinstance(session_id, str) or not _SESSION.fullmatch(session_id):
            raise ValueError("Desktop session_id is invalid")
        if not isinstance(checkpoint_path, (str, Path)) or not str(checkpoint_path).strip():
            raise ValueError("A saved checkpoint path is required")
        if type(timeout) is not int or not 1 <= timeout <= 86400:
            raise ValueError("continuation_timeout_seconds must be an integer from 1 to 86400")
        path = os.path.normcase(str(Path(checkpoint_path).expanduser().resolve()))
        return {"session_id": session_id, "checkpoint_path": path,
                "continuation_timeout_seconds": timeout}

    @staticmethod
    def _request_hash(request):
        return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _path(self, operation_id, suffix=".json"):
        return self.directory / (hashlib.sha256(operation_id.encode()).hexdigest() + suffix)

    def _load(self):
        for path in sorted(self.directory.glob("*.cancelled")):
            if not _DIGEST.fullmatch(path.stem):
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                operation = self._validate_id(value["operation_id"])
                if value.get("cancelled") is not True or path != self._path(operation, ".cancelled"):
                    raise ValueError("Invalid cancellation receipt")
                self.cancelled_ids.add(operation)
            except (OSError, ValueError, KeyError, TypeError):
                self.blocked_reason = "invalid_saved_cancellation"
        for path in sorted(self.directory.glob("*.json")):
            if not _DIGEST.fullmatch(path.stem):
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                operation = self._validate_id(value["operation_id"])
                request = value["request"]
                if (value.get("version") != 1 or value.get("state") not in _STATES
                        or path != self._path(operation) or not isinstance(request, dict)
                        or request != self._request(request.get("session_id"), request.get("checkpoint_path"),
                                                    request.get("continuation_timeout_seconds"))
                        or value.get("request_hash") != self._request_hash(request)
                        or not isinstance(value.get("nonce"), str) or not _NONCE.fullmatch(value["nonce"])):
                    raise ValueError("Invalid Desktop receipt")
                if operation in self.cancelled_ids:
                    value["cancelled"] = True
                self.records[operation] = value
                interrupted = value["state"] not in _TERMINAL
                completed = value.get("continuation_result", {})
                invalid_ready = value["state"] == "ready" and (
                    value.get("acknowledged") is not True or value.get("cancelled") is True
                    or not self._continuation_succeeded(completed)
                    or value.get("handoff_completed") is not True)
                if interrupted or invalid_ready:
                    value = {**value, "state": "needs_attention", "handoff_completed": False,
                             "task_completion": "not_asserted", "persistence_confirmed": True,
                             "error_code": "owner_interrupted" if interrupted else "invalid_completion_receipt"}
                    self.records[operation] = value
                    self.publish(path, value)
            except (OSError, ValueError, KeyError, TypeError):
                self.blocked_reason = "invalid_or_unwritable_saved_receipt"

    def _public(self, value):
        request = value.get("request", {})
        result = {key: value[key] for key in (
            "operation_id", "state", "cancelled", "acknowledged", "error_code",
            "persistence_confirmed", "continuation_result") if key in value}
        result.update({key: request[key] for key in ("session_id", "checkpoint_path") if key in request})
        result["handoff_completed"] = (value.get("state") == "ready"
            and value.get("acknowledged") is True and value.get("handoff_completed") is True
            and self._continuation_succeeded(value.get("continuation_result")))
        result["task_completion"] = "not_asserted"
        if self.blocked_reason:
            result["controller_error"] = self.blocked_reason
        return deepcopy(result)

    def _save_locked(self, operation, **changes):
        value = {**self.records[operation], **changes, "persistence_confirmed": True}
        value["task_completion"] = "not_asserted"
        try:
            self.publish(self._path(operation), value)
        except (OSError, ValueError, TypeError):
            self.storage_failed.add(operation)
            self.blocked_reason = "receipt_persistence_failed"
            self.records[operation] = {**self.records[operation], "state": "needs_attention",
                "error_code": "receipt_persistence_failed", "handoff_completed": False,
                "persistence_confirmed": False, "task_completion": "not_asserted"}
            self.events.get(operation, threading.Event()).set()
            raise
        self.records[operation] = value
        return value

    def _save(self, operation, **changes):
        with self.lock:
            return self._save_locked(operation, **changes)

    def prepare(self, operation_id, session_id, checkpoint_path, caller_pid,
                continuation_timeout_seconds=86400):
        operation = self._validate_id(operation_id)
        request = self._request(session_id, checkpoint_path, continuation_timeout_seconds)
        if type(caller_pid) is not int or caller_pid <= 0:
            raise ValueError("caller_pid must identify the live requesting Code process")
        digest = self._request_hash(request)
        with self.lock:
            previous = self.records.get(operation)
            if previous is not None:
                if previous["request_hash"] != digest:
                    raise ValueError("operation_id already belongs to another Desktop handoff request")
                return self._public(previous)
            if operation in self.cancelled_ids:
                raise ValueError("This Desktop operation was cancelled before submission")
            if self.closed or self.blocked_reason:
                raise ValueError("Desktop controller is closed or needs receipt inspection")
            if self.active_id is not None:
                raise ValueError("Another Desktop handoff transaction is active")

            binding = self.runtime.prepare_binding(session_id, request["checkpoint_path"], caller_pid)
            if not isinstance(binding, dict):
                raise ValueError("Desktop runtime binding must be a verified object")
            encoded = json.dumps(binding, ensure_ascii=False)
            if len(encoded.encode("utf-8")) > 128 * 1024:
                raise ValueError("Desktop runtime binding exceeded 128 KiB")
            value = {"version": 1, "operation_id": operation, "request": request,
                     "request_hash": digest, "binding": json.loads(encoded),
                     "nonce": secrets.token_hex(16), "state": "queued", "cancelled": False,
                     "acknowledged": False, "handoff_completed": False,
                     "task_completion": "not_asserted", "persistence_confirmed": True}
            try:
                self.publish(self._path(operation), value)
            except (OSError, ValueError, TypeError):
                self.blocked_reason = "receipt_persistence_failed"
                raise
            self.records[operation] = value
            self.events[operation] = threading.Event()
            self.active_id = operation
            accepted = {**self._public(value), "accepted": True}
            self.worker = threading.Thread(target=self._run, args=(operation,), daemon=True)
            try:
                self.worker.start()
            except RuntimeError:
                self.worker = None
                self.active_id = None
                self._save_locked(operation, state="failed", error_code="worker_start_failed")
                raise ValueError("Desktop worker could not start; the app was not changed") from None
            return accepted

    def status(self, operation_id):
        operation = self._validate_id(operation_id)
        with self.lock:
            if operation in self.records:
                return self._public(self.records[operation])
            if operation in self.cancelled_ids:
                return {"operation_id": operation, "state": "cancelled", "cancelled": True,
                        "handoff_completed": False, "task_completion": "not_asserted"}
            result = {"operation_id": operation, "state": "unknown", "handoff_completed": False,
                      "task_completion": "not_asserted"}
            if self.blocked_reason:
                result["controller_error"] = self.blocked_reason
            return result

    def cancel(self, operation_id):
        operation = self._validate_id(operation_id)
        with self.lock:
            value = self.records.get(operation)
            if value is not None and value["state"] in _TERMINAL:
                return self._public(value)
            event = self.events.get(operation)
            if event is not None:
                event.set()
            try:
                self.publish(self._path(operation, ".cancelled"),
                             {"operation_id": operation, "cancelled": True})
            except (OSError, ValueError, TypeError):
                self.blocked_reason = "receipt_persistence_failed"
                if value is not None:
                    self.storage_failed.add(operation)
                raise
            self.cancelled_ids.add(operation)
            if value is not None:
                self._save_locked(operation, cancelled=True)
                return self._public(self.records[operation])
            return self.status(operation)

    def acknowledge(self, operation_id, nonce, session_id):
        operation = self._validate_id(operation_id)
        with self.lock:
            value = self.records.get(operation)
            if (value is None or not isinstance(nonce, str) or not _NONCE.fullmatch(nonce)
                    or not secrets.compare_digest(value["nonce"], nonce)
                    or value["request"]["session_id"] != session_id):
                raise ValueError("Desktop acknowledgement does not match this handoff")
            if value.get("cancelled") or value["state"] in {"queued", "waiting_for_handoff", "quitting", "cancelled", "failed"}:
                raise ValueError("Desktop handoff is not accepting a resume acknowledgement")
            if not value.get("acknowledged"):
                self._save_locked(operation, acknowledged=True)
            return self._public(self.records[operation])

    def _check(self, operation, deadline):
        with self.lock:
            if operation in self.storage_failed:
                raise _Abort("needs_attention", "receipt_persistence_failed")
            if self.records[operation].get("cancelled"):
                raise _Abort("cancelled")
            if self.clock() >= deadline:
                raise _Abort("needs_attention", "deadline_exceeded")

    @staticmethod
    def _continuation_succeeded(value):
        return (isinstance(value, dict) and type(value.get("exit_code")) is int
                and value["exit_code"] == 0 and value.get("is_error") is False
                and value.get("subtype") == "success")

    @staticmethod
    def _result_metadata(value):
        if not isinstance(value, dict) or type(value.get("exit_code")) is not int:
            raise _Abort("needs_attention", "invalid_continuation_result")
        result = {"exit_code": value["exit_code"]}
        if type(value.get("is_error")) is bool:
            result["is_error"] = value["is_error"]
        subtype = value.get("subtype")
        if isinstance(subtype, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", subtype):
            result["subtype"] = subtype
        duration = value.get("duration_ms")
        if type(duration) in (int, float) and 0 <= duration <= 86400 * 1000:
            result["duration_ms"] = round(duration, 1)
        return result

    def _run(self, operation):
        with self.lock:
            value = self.records[operation]
            binding = deepcopy(value["binding"])
            binding["operation_id"] = operation
            nonce = value["nonce"]
            deadline = self.clock() + value["request"]["continuation_timeout_seconds"]
            event = self.events[operation]
        quit_attempted = False
        result = None
        terminal, error = "needs_attention", "handoff_did_not_settle"
        phase = "waiting_for_handoff"
        try:
            self._save(operation, state=phase)
            self._check(operation, deadline)
            self.runtime.wait_for_handoff(binding, event, deadline)
            self._check(operation, deadline)
            phase = "quitting"
            self._save(operation, state=phase)
            self._check(operation, deadline)
            quit_attempted = True
            self.runtime.quit(binding)
            self._check(operation, deadline)
            phase = "continuing"
            self._save(operation, state=phase)
            self._check(operation, deadline)
            result = self._result_metadata(self.runtime.continue_session(
                binding, operation, nonce, event, deadline))
            self._check(operation, deadline)
            if not self._continuation_succeeded(result):
                terminal, error = "failed", "continuation_failed"
            elif not self.records[operation].get("acknowledged"):
                terminal, error = "needs_attention", "resume_acknowledgement_missing"
            else:
                terminal, error = "ready", None
        except _Abort as exc:
            terminal, error = exc.state, exc.code
        except Exception as exc:
            # Runtime errors can contain private paths, text or credentials. Keep
            # a fixed category and leave detailed diagnosis to the runtime owner.
            terminal = "needs_attention" if quit_attempted else "failed"
            error = getattr(exc, "handoff_code", None) or {
                "waiting_for_handoff": "handoff_failed", "quitting": "quit_failed",
                "continuing": "continuation_failed"}.get(phase, "handoff_failed")
        finally:
            if quit_attempted:
                try:
                    changes = {"state": "reopening"}
                    if result is not None:
                        changes["continuation_result"] = result
                    self._save(operation, **changes)
                except Exception:
                    terminal, error = "needs_attention", "receipt_persistence_failed"
                try:
                    self.runtime.reopen(binding)
                except Exception:
                    terminal, error = "needs_attention", "reopen_failed"
            with self.lock:
                if operation in self.storage_failed:
                    terminal, error = "needs_attention", "receipt_persistence_failed"
                elif operation in self.shutdown_timed_out:
                    terminal, error = "needs_attention", "owner_shutdown_timeout"
                elif self.records[operation].get("cancelled") and error != "reopen_failed":
                    terminal, error = "cancelled", None
                changes = {"state": terminal, "handoff_completed": terminal == "ready"}
                if error is not None:
                    changes["error_code"] = error
                if result is not None:
                    changes["continuation_result"] = result
                try:
                    self._save_locked(operation, **changes)
                except Exception:
                    pass  # The in-memory status already reports failed persistence.
                if self.active_id == operation:
                    self.active_id = None

    def close(self, *, timeout_seconds=110):
        """Cancel and settle explicit owner shutdown; never call this for MCP EOF.

        A timed-out owner must not silently exit while app recovery is running.
        The caller decides how to handle the raised error and preserve its host.
        """
        if type(timeout_seconds) not in (int, float) or not 0 <= timeout_seconds <= 600:
            raise ValueError("Desktop shutdown timeout must be between 0 and 600 seconds")
        with self.lock:
            self.closed = True
            operation, worker = self.active_id, self.worker
        if operation is not None:
            try:
                self.cancel(operation)
            except (OSError, ValueError, TypeError):
                self.events[operation].set()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=timeout_seconds)
            if worker.is_alive():
                with self.lock:
                    if operation is not None:
                        self.shutdown_timed_out.add(operation)
                        try:
                            self._save_locked(operation, state="needs_attention",
                                error_code="owner_shutdown_timeout", handoff_completed=False)
                        except Exception:
                            pass  # Failed persistence is separately visible in status.
                raise RuntimeError("Desktop handoff did not settle before owner shutdown; inspect its receipt")
