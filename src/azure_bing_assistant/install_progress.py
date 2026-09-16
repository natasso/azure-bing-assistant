"""Best-effort terminal activity for synchronous installer operations."""

from __future__ import annotations

import sys
import threading
import time
from types import TracebackType
from typing import TextIO

from .installer_messages import InstallerMessages


class InstallProgress:
    """Render only; never poll Azure or interrupt the operation being observed."""

    def __init__(
        self, phase: str, number: int, total: int, language: str,
        *, stream: TextIO | None = None,
    ) -> None:
        self.stream = sys.stderr if stream is None else stream
        self.tr = InstallerMessages(language)
        self.phase = self.tr(phase)
        self.number, self.total = number, total
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.started = 0.0
        self.frame = 0
        self.width = 0
        try:
            self.tty = self.stream.isatty()
        except Exception:
            self.tty = False

    def _render(self, status: str, *, final: bool = False) -> None:
        try:
            elapsed = max(0, int(time.monotonic() - self.started))
            text = self.tr(
                "Phase {number}/{total} · {phase} · {status} · {elapsed}",
                number=self.number, total=self.total, phase=self.phase,
                status=self.tr(status), elapsed=f"{elapsed // 60:02}:{elapsed % 60:02}",
            )
            if self.tty and not final:
                text += " " + "|/-\\"[self.frame % 4]
                self.frame += 1
            encoding = getattr(self.stream, "encoding", None) or "utf-8"
            text = text.encode(encoding, errors="replace").decode(encoding)
            if self.tty:
                padded = text.ljust(self.width)
                self.width = len(text)
                self.stream.write("\r" + padded + ("\n" if final else ""))
            else:
                self.stream.write(text + "\n")
            self.stream.flush()
        except Exception:
            # A closed/redirected terminal must not change deployment semantics.
            self.stop.set()

    def _animate(self) -> None:
        while not self.stop.wait(0.2 if self.tty else 30):
            self._render("in progress")

    def __enter__(self) -> InstallProgress:
        self.started = time.monotonic()
        self._render("in progress")
        if not self.stop.is_set():
            self.thread = threading.Thread(
                target=self._animate, name="installer-progress", daemon=True,
            )
            try:
                self.thread.start()
            except Exception:
                self.thread = None
            except BaseException:
                self.stop.set()
                if self.thread.is_alive():
                    self.thread.join()
                self._render("interrupted", final=True)
                raise
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None,
        _exc: BaseException | None, _tb: TracebackType | None,
    ) -> None:
        self.stop.set()
        if self.thread is not None:
            try:
                self.thread.join()
            except Exception:
                pass
        status = "completed" if exc_type is None else (
            "interrupted" if issubclass(exc_type, KeyboardInterrupt) else "failed"
        )
        self._render(status, final=True)
