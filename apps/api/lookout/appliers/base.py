"""Shared applier contracts and the browser form engine used by the ATS adapters."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from lookout.browser_sessions import (
    BrowserSessionError,
    BrowserSessionInUseError,
    BrowserSessionManager,
)
from lookout.connector_health import (
    AUTH_TEXT_MARKERS,
    AUTH_URL_MARKERS,
    VERIFICATION_MARKERS,
)
from lookout.models import Application, Opening
from lookout.normalize import normalize_text
from lookout.screener import FormQuestion, ResolvedAnswer

SubmitStatus = Literal["submitted", "dry_run", "manual_assist"]

_CONFIRM_MARKERS = ("thank you", "application received", "application submitted")


@dataclass(frozen=True)
class ApplicationForm:
    """Screenable questions of an application form, parsed by an applier."""

    fields: list[FormQuestion]


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of an applier submit; detail is always a safe token, never page content."""

    status: SubmitStatus
    detail: str


class ApplierError(Exception):
    """Raised by inspect() when a form cannot be inspected; detail is a safe token."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class Applier(Protocol):
    def inspect(self, opening: Opening, *, resume_path: Path) -> ApplicationForm: ...

    def submit(
        self,
        application: Application,
        opening: Opening,
        *,
        resume_path: Path,
        answers: list[ResolvedAnswer],
        dry_run: bool,
        auto_submit_enabled: bool,
    ) -> ApplyResult: ...


def submission_guard(
    application: Application, *, dry_run: bool, auto_submit_enabled: bool
) -> ApplyResult | None:
    """Return a blocking ApplyResult, or None when a real submission may proceed.

    A dry run performs no side effect and is never blocked by the lane/status
    flags. A real submission requires auto-submit to be enabled, the auto-apply
    lane, and the submitting status committed before the external side effect.
    """

    if dry_run:
        return None
    if not auto_submit_enabled:
        return ApplyResult("manual_assist", "auto_submit_disabled")
    if application.lane != "auto_apply":
        return ApplyResult("manual_assist", "lane_not_auto_apply")
    if application.status != "submitting":
        return ApplyResult("manual_assist", "status_not_submitting")
    return None


class _ManualAssist(Exception):
    """Internal signal carrying a safe detail token for a manual-assist outcome."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class _Control:
    key: str
    label: str
    required: bool
    kind: Literal["text", "select", "file", "unsupported"]
    options: tuple[str, ...]
    selector: str


def _slug_key(label: str) -> str:
    return "_".join(normalize_text(label).split())


def _unsafe_page_marker(page) -> str | None:
    text = page.inner_text("body", timeout=5_000).casefold()
    if any(marker in text for marker in VERIFICATION_MARKERS):
        return "manual_verification_required"
    if any(marker in text for marker in AUTH_TEXT_MARKERS):
        return "browser_session_expired"
    url = page.url.casefold()
    if any(marker in url for marker in AUTH_URL_MARKERS):
        return "browser_session_expired"
    return None


def _option_match(answer_text: str, options: tuple[str, ...]) -> str | None:
    normalized = normalize_text(answer_text).casefold()
    return next(
        (option for option in options if normalize_text(option).casefold() == normalized),
        None,
    )


class _BrowserFormApplier:
    """Reusable Playwright flow for the Greenhouse and Lever adapters.

    The flow never crashes the worker: after the submission guard passes, every
    blocked or ambiguous condition degrades to a manual-assist result with a
    safe detail token, and an ambiguous real submission is never replayed.
    """

    platform: ClassVar[str]
    extraction_js: ClassVar[str]
    form_present_js: ClassVar[str]
    resume_selector: ClassVar[str]
    submit_selector: ClassVar[str]
    apply_route_selector: ClassVar[str]
    identity_names: ClassVar[frozenset[str]] = frozenset()
    name_mode: ClassVar[str] = "identity_only"
    needs_apply_route: ClassVar[bool] = False

    def __init__(self, sessions: BrowserSessionManager, *, headless: bool = True) -> None:
        self._sessions = sessions
        self._headless = headless

    def _key_for(self, node: dict) -> str:
        name = node.get("name") or ""
        label = node.get("label") or ""
        if self.name_mode == "always" and name and name.replace("_", "").isalnum():
            return name
        if self.name_mode == "identity_only" and name in self.identity_names:
            return name
        return _slug_key(label) or _slug_key(name)

    @contextmanager
    def _page_for(self, opening: Opening) -> Iterator:
        try:
            context_cm = self._sessions.open(self.platform, headless=self._headless)
        except BrowserSessionInUseError:
            raise _ManualAssist("browser_profile_in_use") from None
        except BrowserSessionError:
            raise _ManualAssist("browser_session_unavailable") from None

        with context_cm as context:
            try:
                page = context.new_page()
            except Exception as error:
                raise _ManualAssist("browser_session_unavailable") from error
            try:
                response = page.goto(opening.url, wait_until="domcontentloaded", timeout=20_000)
            except BrowserSessionError:
                raise _ManualAssist("browser_session_unavailable") from None
            except Exception as error:
                raise _ManualAssist("browser_platform_unavailable") from error
            status = response.status if response is not None else 0
            if status in {401, 403}:
                raise _ManualAssist("browser_session_expired")
            if response is None or status >= 400:
                raise _ManualAssist("browser_platform_unavailable")
            marker = _unsafe_page_marker(page)
            if marker is not None:
                raise _ManualAssist(marker)
            self._route_if_needed(page)
            yield page
            try:
                page.close()
            except Exception:  # noqa: BLE001, S110 - closing is best effort; teardown owns cleanup
                pass

    def _route_if_needed(self, page) -> None:
        if not self.needs_apply_route:
            return
        try:
            form_present = page.evaluate(self.form_present_js)
        except Exception as error:
            raise _ManualAssist("apply_form_unavailable") from error
        if form_present:
            return
        try:
            page.click(self.apply_route_selector, timeout=10_000)
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception as error:
            raise _ManualAssist("apply_form_unavailable") from error
        marker = _unsafe_page_marker(page)
        if marker is not None:
            raise _ManualAssist(marker)

    def _extract(self, page) -> list[_Control]:
        try:
            payload = page.evaluate(self.extraction_js)
        except Exception as error:
            raise _ManualAssist("apply_form_unavailable") from error
        if not isinstance(payload, list):
            raise _ManualAssist("apply_form_unavailable")

        controls: list[_Control] = []
        seen_keys: set[str] = set()
        seen_selectors: set[str] = set()
        for node in payload:
            kind = node.get("kind", "unsupported")
            if kind not in {"text", "select", "file", "unsupported"}:
                kind = "unsupported"
            selector = node.get("selector") or ""
            key = self._key_for(node)
            if kind in {"text", "select"}:
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
            else:
                if not selector or selector in seen_selectors:
                    continue
                seen_selectors.add(selector)
            controls.append(
                _Control(
                    key=key,
                    label=(node.get("label") or "").strip(),
                    required=bool(node.get("required")),
                    kind=kind,
                    options=tuple(node.get("options") or ()),
                    selector=selector,
                )
            )
        return controls

    def _fields(self, controls: list[_Control]) -> list[FormQuestion]:
        return [
            FormQuestion(
                key=control.key,
                label=control.label,
                required=control.required,
                options=control.options,
                disqualifying=False,
            )
            for control in controls
            if control.kind in {"text", "select"}
        ]

    def _fill(self, page, controls: list[_Control], answers: list[ResolvedAnswer]) -> None:
        for control in controls:
            if control.kind in {"file", "unsupported"}:
                # Unsupported and file controls are skipped: an unfulfillable
                # real form surfaces as submit_unconfirmed after the click
                # attempt, which is never retried.
                continue
            answer = next((item for item in answers if item.key == control.key), None)
            answer_text = answer.answer.strip() if answer and answer.status == "answered" else None
            if answer_text is None:
                if control.required:
                    raise _ManualAssist("required_answers_missing")
                continue
            if control.kind == "select":
                match = _option_match(answer_text, control.options)
                if match is None:
                    raise _ManualAssist("option_value_missing")
                page.select_option(control.selector, match, timeout=5_000)
            else:
                page.fill(control.selector, answer_text, timeout=5_000)

    def inspect(self, opening: Opening, *, resume_path: Path) -> ApplicationForm:
        try:
            with self._page_for(opening) as page:
                controls = self._extract(page)
        except _ManualAssist as blocked:
            raise ApplierError(blocked.detail) from None
        return ApplicationForm(fields=self._fields(controls))

    def submit(
        self,
        application: Application,
        opening: Opening,
        *,
        resume_path: Path,
        answers: list[ResolvedAnswer],
        dry_run: bool,
        auto_submit_enabled: bool,
    ) -> ApplyResult:
        guard = submission_guard(
            application, dry_run=dry_run, auto_submit_enabled=auto_submit_enabled
        )
        if guard is not None:
            return guard
        if not Path(resume_path).is_file():
            return ApplyResult("manual_assist", "resume_artifact_missing")

        try:
            with self._page_for(opening) as page:
                controls = self._extract(page)
                self._fill(page, controls, answers)
                page.set_input_files(self.resume_selector, str(resume_path), timeout=5_000)
                if dry_run:
                    return ApplyResult("dry_run", "dry_run_fill_succeeded")
                self._click_and_verify(page)
        except _ManualAssist as blocked:
            return ApplyResult("manual_assist", blocked.detail)
        except Exception:  # noqa: BLE001 - ambiguous outcomes must degrade, never crash the worker
            return ApplyResult("manual_assist", "submit_unconfirmed")
        return ApplyResult("submitted", "submission_confirmed")

    def _click_and_verify(self, page) -> None:
        try:
            page.click(self.submit_selector, timeout=10_000)
            try:
                page.wait_for_load_state("load", timeout=10_000)
            except Exception:  # noqa: BLE001, S110 - the POST may already be complete
                pass
            text = page.inner_text("body", timeout=5_000).casefold()
        except Exception:  # noqa: BLE001 - click ambiguities are never retried
            raise _ManualAssist("submit_unconfirmed") from None
        if not any(marker in text for marker in _CONFIRM_MARKERS):
            raise _ManualAssist("submit_unconfirmed")
