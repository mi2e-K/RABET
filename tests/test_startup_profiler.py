"""StartupProfiler (PR-STARTUP-01): milestone recording + opt-in logging."""

from __future__ import annotations

import logging

from utils.startup_profiler import StartupProfiler


def test_marks_record_monotonic_cumulative():
    p = StartupProfiler(enabled=False)
    p.mark("a")
    p.mark("b")
    p.mark("c")
    marks = p.marks
    assert [m[0] for m in marks] == ["a", "b", "c"]
    cums = [cum for _label, cum, _delta in marks]
    assert cums == sorted(cums)  # cumulative is monotonic non-decreasing
    assert all(delta >= 0 for _label, _cum, delta in marks)


def test_summary_emits_one_line(caplog):
    p = StartupProfiler(enabled=False)
    p.mark("logger")
    p.mark("config")
    with caplog.at_level(logging.INFO):
        p.summary()
    assert "[startup] total" in caplog.text
    assert "logger=" in caplog.text and "config=" in caplog.text


def test_disabled_does_not_log_per_mark(caplog):
    p = StartupProfiler(enabled=False)
    with caplog.at_level(logging.INFO):
        p.mark("a")
    assert "[startup] a @" not in caplog.text


def test_enabled_logs_per_mark(caplog):
    p = StartupProfiler(enabled=True)
    with caplog.at_level(logging.INFO):
        p.mark("a")
    assert "[startup] a @" in caplog.text


def test_env_var_enables(monkeypatch):
    monkeypatch.setenv("RABET_STARTUP_PROFILE", "1")
    assert StartupProfiler().enabled is True  # enabled=None -> reads env
    monkeypatch.setenv("RABET_STARTUP_PROFILE", "0")
    assert StartupProfiler().enabled is False
    monkeypatch.delenv("RABET_STARTUP_PROFILE", raising=False)
    assert StartupProfiler().enabled is False


def test_summary_with_no_marks_is_safe(caplog):
    p = StartupProfiler(enabled=False)
    with caplog.at_level(logging.INFO):
        p.summary()  # no marks -> no crash, no summary line
    assert "[startup] total" not in caplog.text
