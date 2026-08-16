# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""auth_service.py — login throttling and audit trail that survive the session.

WHY THIS FILE EXISTS
The throttle added on 2026-08-01 lived in `st.session_state`. That stops an
ordinary brute-force loop and nothing else: session state is per-browser-session,
so an attacker clearing cookies, opening a private window, or driving the app
from a script with a fresh session gets a fresh counter every five attempts. The
audit noted this and scored security 7/10 for it.

This module moves the counter OUT of the session and into a small on-disk store
keyed by e-mail, so the limit follows the ACCOUNT rather than the browser. It
also records every authentication decision, because "who tried to get in, and
when" is a question a diagnostic laboratory will eventually be asked and cannot
answer from nothing.

WHAT THIS IS NOT
It is not a distributed rate limiter. A single JSON file under a lock is honest
for one Streamlit process; it does not coordinate across replicas. If the app is
ever scaled horizontally this must move to Redis or the database, and the shape
of the interface here is deliberately the shape that migration would keep.

It is also not a substitute for a strong password. Throttling buys time; it does
not make a six-character password safe.

DESIGN CHOICES WORTH KNOWING
  * FAIL-OPEN ON STORAGE ERROR. If the store cannot be read or written, the
    module logs loudly and allows the attempt. A laboratory locked out of its
    own CDSS because a disk filled up is a worse outcome than a slower brute
    force, and the failure is recorded either way.
  * LOCKOUT IS A DELAY, NOT A BAN. Attempts reset after the window expires. A
    permanent lock needs an administrator to unlock it, and there is no
    administrator at 2 a.m. in a hospital laboratory.
  * The store holds NO passwords and no hashes — only e-mail, counters and
    timestamps. Nothing in it is worth stealing.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_ATTEMPTS", "LOCKOUT_SECONDS", "ATTEMPT_WINDOW_SECONDS", "REASON_CODES",
    "check_lockout", "record_failure", "record_success",
    "recent_events", "store_path",
]

# Five attempts, then a five-minute delay. The window means the five have to
# happen within fifteen minutes to count together — a user who mistypes once a
# week never trips it.
MAX_ATTEMPTS: int = 5
LOCKOUT_SECONDS: int = 300
ATTEMPT_WINDOW_SECONDS: int = 900
MAX_EVENTS: int = 500          # ring buffer; the file must not grow unbounded


def store_path() -> str:
    """Where the throttle state lives.

    Honours ORANGE_AUTH_STORE so a deployment can point it at a writable volume;
    Streamlit Community Cloud gives the process a writable home directory but
    not a writable working directory, which is why this is not just "./".
    """
    env = os.environ.get("ORANGE_AUTH_STORE")
    if env:
        return env
    base = os.environ.get("HOME") or tempfile.gettempdir()
    return os.path.join(base, ".orange_cdss_auth.json")


def _load() -> Dict[str, Any]:
    p = store_path()
    try:
        if not os.path.exists(p):
            return {"accounts": {}, "events": []}
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("auth store is not an object")
        data.setdefault("accounts", {})
        data.setdefault("events", [])
        return data
    except Exception as exc:                       # corrupt file, bad perms, …
        logger.error("auth store unreadable (%s) — starting a fresh one", exc)
        return {"accounts": {}, "events": []}


def _save(data: Dict[str, Any]) -> bool:
    """Atomic write. Returns False on failure; callers FAIL OPEN."""
    p = store_path()
    try:
        data["events"] = list(data.get("events", []))[-MAX_EVENTS:]
        d = os.path.dirname(p) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".auth.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, p)           # atomic on POSIX and Windows
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        try:
            os.chmod(p, 0o600)           # the file is boring, but not public
        except OSError:
            pass
        return True
    except Exception as exc:
        logger.error("auth store unwritable (%s) — throttle degraded to "
                     "session-only for this attempt", exc)
        return False


def _key(email: str) -> str:
    return (email or "").strip().lower()


def _event(data: Dict[str, Any], email: str, kind: str, detail: str = "") -> None:
    data.setdefault("events", []).append({
        "t": int(time.time()), "email": _key(email), "kind": kind,
        "detail": detail[:200],
    })


def check_lockout(email: str) -> Tuple[bool, int, int]:
    """Is this account currently locked?

    Returns (locked, seconds_remaining, failures_so_far). Never raises.
    """
    try:
        data = _load()
        acc = data["accounts"].get(_key(email))
        if not acc:
            return False, 0, 0
        now = time.time()
        until = float(acc.get("locked_until") or 0)
        if until > now:
            return True, int(until - now), int(acc.get("failures") or 0)
        # Failures outside the window no longer count together.
        first = float(acc.get("first_failure") or 0)
        if first and now - first > ATTEMPT_WINDOW_SECONDS:
            return False, 0, 0
        return False, 0, int(acc.get("failures") or 0)
    except Exception as exc:
        logger.error("check_lockout failed open (%s)", exc)
        return False, 0, 0


# The audit trail records WHY an attempt failed, and `reason` is written to
# disk. A future caller passing user input there — the attempted password, a
# form field, an exception message containing a credential — would put it in a
# file that outlives the session. So the vocabulary is CLOSED: anything not in
# this set is recorded as "other" and the original is dropped.
REASON_CODES = frozenset({
    "bad password", "no password set", "not a subscriber",
    "subscription expired", "malformed email", "other",
})


def record_failure(email: str, reason: str = "bad password") -> Tuple[bool, int, int]:
    """Record one failed attempt.

    `reason` must be one of REASON_CODES; anything else is stored as "other".
    That is deliberate — this file is an audit trail, not a place for whatever
    string a caller happened to have. See the note above REASON_CODES.

    Returns (now_locked, seconds_remaining, attempts_left).
    """
    reason = reason if reason in REASON_CODES else "other"
    try:
        data = _load()
        k = _key(email)
        now = time.time()
        acc = data["accounts"].setdefault(k, {})
        first = float(acc.get("first_failure") or 0)
        if not first or now - first > ATTEMPT_WINDOW_SECONDS:
            acc["first_failure"] = now
            acc["failures"] = 0
        acc["failures"] = int(acc.get("failures") or 0) + 1
        acc["last_failure"] = now
        locked = False
        remaining = 0
        if acc["failures"] >= MAX_ATTEMPTS:
            acc["locked_until"] = now + LOCKOUT_SECONDS
            locked = True
            remaining = LOCKOUT_SECONDS
            _event(data, email, "lockout", f"{acc['failures']} failures")
            logger.error("auth lockout: %s after %d failures", k, acc["failures"])
        else:
            _event(data, email, "failure", reason)
            logger.warning("auth failure %d/%d: %s", acc["failures"],
                           MAX_ATTEMPTS, k)
        _save(data)
        return locked, remaining, max(0, MAX_ATTEMPTS - int(acc["failures"]))
    except Exception as exc:
        logger.error("record_failure failed open (%s)", exc)
        return False, 0, MAX_ATTEMPTS


def record_success(email: str) -> None:
    """Clear the counter and log the successful sign-in."""
    try:
        data = _load()
        k = _key(email)
        data["accounts"][k] = {"failures": 0, "first_failure": 0,
                               "locked_until": 0, "last_success": time.time()}
        _event(data, email, "success")
        _save(data)
        logger.info("auth success: %s", k)
    except Exception as exc:
        logger.error("record_success failed open (%s)", exc)


def recent_events(limit: int = 50) -> list:
    """Most recent authentication events, newest first. For the admin panel."""
    try:
        return list(reversed(_load().get("events", [])))[:limit]
    except Exception:
        return []
