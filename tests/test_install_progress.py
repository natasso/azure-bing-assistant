import io
import threading
from unittest.mock import Mock

import pytest

from azure_bing_assistant import install_progress
from azure_bing_assistant.install_progress import InstallProgress


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.mark.parametrize("tty", [False, True])
@pytest.mark.parametrize("language", ["it", "en"])
def test_immediate_start_elapsed_tick_and_final_status(monkeypatch, tty, language):
    stream = Terminal() if tty else io.StringIO()
    clock = Mock(return_value=0)
    monkeypatch.setattr(install_progress.time, "monotonic", clock)
    progress = InstallProgress("Provisioning Azure resources", 2, 5, language, stream=stream)
    with progress:
        assert ("in corso" if language == "it" else "in progress") in stream.getvalue()
        clock.return_value = 75
        progress._render("in progress")
        assert "01:15" in stream.getvalue()
    text = stream.getvalue()
    assert ("Fase 2/5" if language == "it" else "Phase 2/5") in text
    assert ("completata" if language == "it" else "completed") in text
    assert "%" not in text and "\x1b" not in text
    assert ("\r" in text) is tty
    assert text.endswith("\n")
    assert progress.stop.is_set() and not progress.thread.is_alive()


@pytest.mark.parametrize("tty,interval", [(True, 0.2), (False, 30)])
def test_worker_uses_event_wait_for_heartbeats_without_cloud_or_sleep(tty, interval):
    progress = InstallProgress("Saving the environment", 1, 5, "en", stream=io.StringIO())
    progress.tty = tty
    progress.stop = Mock()
    progress.stop.wait.side_effect = [False, True]
    progress._render = Mock()
    progress._animate()
    assert progress.stop.wait.call_args_list == [((interval,),), ((interval,),)]
    progress._render.assert_called_once_with("in progress")


@pytest.mark.parametrize("failure,status", [(RuntimeError("primary"), "failed"), (KeyboardInterrupt(), "interrupted")])
def test_exception_preserved_and_renderer_joined(failure, status):
    stream = Terminal()
    progress = InstallProgress("Provisioning Azure resources", 2, 5, "en", stream=stream)
    with pytest.raises(type(failure)) as caught:
        with progress:
            raise failure
    assert caught.value is failure
    assert status in stream.getvalue() and "completed" not in stream.getvalue()
    assert not progress.thread.is_alive()


def test_output_and_thread_start_failures_do_not_mask_operation(monkeypatch):
    stream = Mock()
    stream.isatty.return_value = True
    stream.write.side_effect = OSError("closed")
    failure = ValueError("primary")
    progress = InstallProgress("Saving the environment", 1, 5, "en", stream=stream)
    with pytest.raises(ValueError) as caught:
        with progress:
            raise failure
    assert caught.value is failure and progress.thread is None

    monkeypatch.setattr(threading.Thread, "start", Mock(side_effect=RuntimeError("unavailable")))
    with InstallProgress("Saving the environment", 1, 5, "en", stream=io.StringIO()) as progress:
        assert progress.thread is None


def test_ascii_terminal_uses_safe_fallback():
    class AsciiTerminal(Terminal):
        encoding = "ascii"

    stream = AsciiTerminal()
    with InstallProgress("Saving the environment", 1, 5, "it", stream=stream):
        pass
    assert stream.getvalue().isascii()
