"""Windows foreground application and title monitoring."""

from __future__ import annotations

import ctypes
import ntpath
import platform
import re
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
_UNSET = object()


def clean_window_title(value: str, maximum_length: int) -> Optional[str]:
    """Remove control characters, normalize whitespace, and limit a title."""
    cleaned = _CONTROL_CHARACTERS.sub(" ", value)
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned[:maximum_length]
    return cleaned or None


def _foreground_window(
    report_application: bool,
    report_title: bool,
    maximum_title_length: int,
) -> tuple[Optional[str], Optional[str]]:
    if platform.system().lower() != "windows":
        return None, None

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    window = user32.GetForegroundWindow()
    if not window:
        return None, None

    application = None
    if report_application:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if process:
            try:
                buffer = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(buffer))
                if kernel32.QueryFullProcessImageNameW(
                    process, 0, buffer, ctypes.byref(size)
                ):
                    application = ntpath.basename(buffer.value)[:255] or None
            finally:
                kernel32.CloseHandle(process)

    title = None
    if report_title:
        length = min(max(0, user32.GetWindowTextLengthW(window)), 32767)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            if user32.GetWindowTextW(window, buffer, len(buffer)):
                title = clean_window_title(buffer.value, maximum_title_length)
    return application, title


class ForegroundMonitor:
    """Poll foreground context and report only changes."""

    def __init__(
        self,
        report_application: bool,
        report_title: bool,
        maximum_title_length: int,
        on_change: Callable[[Optional[str], Optional[str]], None],
        poll_seconds: float = 1.0,
    ) -> None:
        self.report_application = report_application
        self.report_title = report_title
        self.maximum_title_length = maximum_title_length
        self._on_change = on_change
        self._poll_seconds = poll_seconds
        self._last_sample = _UNSET
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running or not (self.report_application or self.report_title):
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._watch,
            name="AYONPresenceForegroundWatcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _poll_once(self) -> None:
        sample = _foreground_window(
            self.report_application,
            self.report_title,
            self.maximum_title_length,
        )
        if sample == self._last_sample:
            return
        self._last_sample = sample
        self._on_change(*sample)

    def _watch(self) -> None:
        while self._running:
            try:
                self._poll_once()
            except Exception:
                # Foreground inspection is optional and must never stop the tray.
                pass
            time.sleep(self._poll_seconds)
