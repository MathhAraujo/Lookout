from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from filelock import FileLock, Timeout
from playwright.sync_api import BrowserContext, sync_playwright

BrowserPlatform = Literal["greenhouse", "lever"]


class BrowserSessionError(Exception):
    """Raised when a persistent browser profile cannot be used safely."""


class BrowserSessionInUseError(BrowserSessionError):
    """Raised when another process already owns a browser profile."""


class BrowserSessionManager:
    def __init__(
        self,
        profiles_root: Path = Path("data/browser-profiles"),
        *,
        playwright_factory=sync_playwright,
    ) -> None:
        self.profiles_root = Path(profiles_root)
        self._playwright_factory = playwright_factory

    @contextmanager
    def open(self, platform: BrowserPlatform, *, headless: bool) -> Iterator[BrowserContext]:
        if platform not in {"greenhouse", "lever"}:
            raise ValueError("unsupported browser platform")

        try:
            self.profiles_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise BrowserSessionError("browser profile storage is unavailable") from None

        profile_path = self.profiles_root / platform
        lock = FileLock(str(self.profiles_root / f"{platform}.lock"))
        try:
            lock.acquire(blocking=False)
        except Timeout:
            raise BrowserSessionInUseError("browser profile is already in use") from None

        try:
            try:
                profile_path.mkdir(parents=True, exist_ok=True)
                runtime = self._playwright_factory()
                playwright = runtime.__enter__()
            except Exception:  # noqa: BLE001 - any runtime failure must become a sanitized BrowserSessionError
                raise BrowserSessionError("could not start persistent browser") from None

            try:
                try:
                    context = playwright.chromium.launch_persistent_context(
                        str(profile_path),
                        headless=headless,
                    )
                except Exception:  # noqa: BLE001 - sanitized launch failure; do not leak Playwright internals
                    raise BrowserSessionError("could not launch persistent browser") from None

                try:
                    yield context
                finally:
                    try:
                        context.close()
                    except Exception:  # noqa: BLE001 - cleanup failures are surfaced as sanitized errors
                        raise BrowserSessionError("could not close persistent browser") from None
            finally:
                try:
                    runtime.__exit__(None, None, None)
                except Exception:  # noqa: BLE001 - cleanup failures are surfaced as sanitized errors
                    raise BrowserSessionError("could not stop browser runtime") from None
        finally:
            lock.release()
