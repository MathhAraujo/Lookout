from __future__ import annotations

import base64
import re
from email.header import decode_header, make_header
from html.parser import HTMLParser
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from lookout.collectors.base import CollectorError, RawOpening
from lookout.config import Settings

_GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_JOB_URL_PATTERN = re.compile(r"https://www\.linkedin\.com/(?:comm/)?jobs/view/(\d+)")
_VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}


class _Element:
    def __init__(
        self,
        tag: str,
        attributes: dict[str, str],
        parent: _Element | None = None,
    ):
        self.tag = tag
        self.attributes = attributes
        self.parent = parent
        self.children: list[_Element | str] = []


class _HTMLTreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        element = _Element(tag, attributes, self.stack[-1])
        self.stack[-1].children.append(element)
        if tag not in _VOID_ELEMENTS:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        self.stack[-1].children.append(_Element(tag, attributes, self.stack[-1]))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _descendants(element: _Element):
    for child in element.children:
        if isinstance(child, _Element):
            yield child
            yield from _descendants(child)


def _text(element: _Element) -> str:
    parts = [child if isinstance(child, str) else _text(child) for child in element.children]
    return " ".join(" ".join(parts).split())


def _has_class(element: _Element, fragment: str) -> bool:
    return any(fragment in token.lower() for token in element.attributes.get("class", "").split())


def _card_container(anchor: _Element) -> _Element | None:
    element = anchor.parent
    while element is not None and element.tag != "root":
        if (_has_class(element, "job") and _has_class(element, "card")) or element.tag in {
            "article",
            "li",
            "tr",
            "td",
        }:
            return element
        element = element.parent
    return None


def _matching_text(container: _Element, *class_fragments: str) -> str:
    for element in _descendants(container):
        if any(_has_class(element, fragment) for fragment in class_fragments):
            value = _text(element)
            if value:
                return value
    return ""


def parse_linkedin_alert(subject: str, html_body: str) -> list[RawOpening]:
    parser = _HTMLTreeBuilder()
    parser.feed(html_body)

    jobs = []
    seen_ids: set[str] = set()
    for anchor in _descendants(parser.root):
        if anchor.tag != "a":
            continue
        match = _JOB_URL_PATTERN.search(anchor.attributes.get("href", ""))
        if match is None:
            continue

        external_id = match.group(1)
        if external_id in seen_ids:
            continue
        container = _card_container(anchor)
        if container is None:
            continue

        title = _text(anchor) or _matching_text(container, "title")
        company = _matching_text(container, "company", "employer")
        if not title or not company:
            continue

        location = _matching_text(container, "location") or None
        jobs.append(
            RawOpening(
                source="linkedin_email",
                external_id=external_id,
                company=company,
                title=title,
                location=location,
                url=f"https://www.linkedin.com/jobs/view/{external_id}",
                description=_text(container),
                posted_at=None,
                raw={"subject": subject},
            )
        )
        seen_ids.add(external_id)

    return jobs


def load_gmail_credentials(settings: Settings) -> Credentials:
    token_path = settings.gmail_token_file
    if not token_path.is_file():
        raise CollectorError(
            f"Gmail token file not found at {token_path}; run `python -m lookout.cli gmail-auth`"
        )

    try:
        credentials = Credentials.from_authorized_user_file(
            str(token_path), scopes=[_GMAIL_READONLY_SCOPE]
        )
    except (OSError, ValueError) as exc:
        raise CollectorError(
            f"Unable to load Gmail credentials from {token_path}; run `python -m lookout.cli gmail-auth`"
        ) from exc

    if credentials.expired:
        if not credentials.refresh_token:
            raise CollectorError(
                "Gmail credentials expired without a refresh token; run `python -m lookout.cli gmail-auth`"
            )
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            raise CollectorError(
                "Unable to refresh Gmail credentials; run `python -m lookout.cli gmail-auth`"
            ) from exc
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    return credentials


def run_gmail_auth(settings: Settings) -> None:
    if not settings.gmail_credentials_file.is_file():
        raise CollectorError(f"Gmail client secrets not found at {settings.gmail_credentials_file}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(settings.gmail_credentials_file), scopes=[_GMAIL_READONLY_SCOPE]
    )
    credentials = flow.run_local_server(port=0)
    settings.gmail_token_file.parent.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_file.write_text(credentials.to_json(), encoding="utf-8")


def _decode_header(value: str) -> str:
    return str(make_header(decode_header(value)))


def _decode_body(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")


def _find_html_body(payload: dict[str, Any]) -> str | None:
    if payload.get("mimeType") == "text/html":
        body = payload.get("body")
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, str):
            return _decode_body(data)

    parts = payload.get("parts")
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict):
                body = _find_html_body(part)
                if body is not None:
                    return body
    return None


class LinkedInEmailCollector:
    name = "linkedin_email"

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self) -> list[RawOpening]:
        credentials = load_gmail_credentials(self.settings)
        service = build("gmail", "v1", credentials=credentials)
        query = f"label:{self.settings.gmail_label} from:jobs-noreply@linkedin.com newer_than:7d"
        response = service.users().messages().list(userId="me", q=query).execute()
        messages = response.get("messages", [])

        jobs = []
        for message in messages:
            message_id = message.get("id")
            if not message_id:
                continue
            message_data = (
                service.users().messages().get(userId="me", id=message_id, format="full").execute()
            )
            payload = message_data.get("payload", {})
            headers = payload.get("headers", [])
            subject = next(
                (
                    _decode_header(header["value"])
                    for header in headers
                    if header.get("name", "").lower() == "subject"
                    and isinstance(header.get("value"), str)
                ),
                "",
            )
            html_body = _find_html_body(payload) if isinstance(payload, dict) else None
            if html_body:
                jobs.extend(parse_linkedin_alert(subject, html_body))

        return jobs
