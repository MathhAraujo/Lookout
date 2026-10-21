import multiprocessing
from pathlib import Path
from queue import Empty

import pytest
from lookout.browser_sessions import (
    BrowserSessionError,
    BrowserSessionInUseError,
    BrowserSessionManager,
)


class FakeBrowserContext:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeBrowserType:
    def __init__(self, launches, *, error=None):
        self.launches = launches
        self.error = error
        self.contexts = []

    def launch_persistent_context(self, user_data_dir, *, headless):
        self.launches.append((user_data_dir, headless))
        if self.error is not None:
            raise self.error
        context = FakeBrowserContext()
        self.contexts.append(context)
        return context


class FakePlaywrightRuntime:
    def __init__(self, browser_type):
        self.chromium = browser_type
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


def make_playwright_factory(*, error=None):
    launches = []
    browser_type = FakeBrowserType(launches, error=error)
    runtimes = []

    def factory():
        runtime = FakePlaywrightRuntime(browser_type)
        runtimes.append(runtime)
        return runtime

    return factory, launches, browser_type, runtimes


def _try_open_profile_in_child(profile_root: str, result_queue) -> None:
    try:
        with BrowserSessionManager(Path(profile_root)).open("greenhouse", headless=True):
            result_queue.put("opened")
    except BrowserSessionInUseError:
        result_queue.put("busy")


def test_manager_uses_separate_persistent_profiles_and_closes_contexts(tmp_path):
    factory, launches, _, runtimes = make_playwright_factory()
    manager = BrowserSessionManager(tmp_path / "browser-profiles", playwright_factory=factory)

    with manager.open("greenhouse", headless=True) as greenhouse_context:
        assert not greenhouse_context.closed
    with manager.open("lever", headless=False) as lever_context:
        assert not lever_context.closed

    assert launches == [
        (str(tmp_path / "browser-profiles" / "greenhouse"), True),
        (str(tmp_path / "browser-profiles" / "lever"), False),
    ]
    assert greenhouse_context.closed
    assert lever_context.closed
    assert all(runtime.closed for runtime in runtimes)
    assert (tmp_path / "browser-profiles" / "greenhouse").is_dir()
    assert (tmp_path / "browser-profiles" / "lever").is_dir()


def test_manager_rejects_simultaneous_profile_use_in_another_process(tmp_path):
    factory, _, _, _ = make_playwright_factory()
    manager = BrowserSessionManager(tmp_path / "browser-profiles", playwright_factory=factory)
    process_context = multiprocessing.get_context("spawn")
    result_queue = process_context.Queue()

    with manager.open("greenhouse", headless=True):
        process = process_context.Process(
            target=_try_open_profile_in_child,
            args=(str(tmp_path / "browser-profiles"), result_queue),
        )
        process.start()
        try:
            assert result_queue.get(timeout=10) == "busy"
        except Empty:
            process.terminate()
            raise AssertionError("the second process was not rejected")
        finally:
            process.join(timeout=10)
        assert process.exitcode == 0


def test_manager_releases_profile_lock_when_browser_launch_fails(tmp_path):
    failed_factory, _, _, _ = make_playwright_factory(error=RuntimeError("fictional launch error"))
    manager = BrowserSessionManager(
        tmp_path / "browser-profiles", playwright_factory=failed_factory
    )

    with (
        pytest.raises(BrowserSessionError, match="could not launch persistent browser"),
        manager.open("greenhouse", headless=True),
    ):
        pytest.fail("a failed browser launch must not yield a context")

    working_factory, _, _, _ = make_playwright_factory()
    with BrowserSessionManager(
        tmp_path / "browser-profiles",
        playwright_factory=working_factory,
    ).open("greenhouse", headless=True):
        pass


def test_manager_rejects_unsupported_platform(tmp_path):
    manager = BrowserSessionManager(tmp_path / "browser-profiles")

    with (
        pytest.raises(ValueError, match="unsupported browser platform"),
        manager.open("linkedin", headless=True),
    ):
        pytest.fail("unsupported platform must not launch a browser")
