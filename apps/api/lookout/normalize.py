import re
import unicodedata

_LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "ltda",
    "corp",
    "corporation",
    "company",
    "co",
    "gmbh",
    "sarl",
    "sa",
}
_REMOTE_TITLE_TOKENS = {"remote", "hybrid", "onsite"}

_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_MAILTO_ANCHOR_PATTERN = re.compile(
    r"<a\b[^>]*href=(?P<quote>[\"'])mailto:(?P<address>[^\"'?]+)(?:\?[^\"']*)?(?P=quote)[^>]*>(?P<text>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_APPLY_HINT = re.compile(r"\bapply\b", re.IGNORECASE)


def _decode_minimal_html(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )


def extract_application_email(payload_html: str | None, *, apply_email_field=None) -> str | None:
    """Return an explicit application email, or None when the target is not explicit.

    Only two sources count as explicit: an apply-email field in the payload and
    a ``mailto:`` anchor whose link text is an application link. Arbitrary
    recruiter or contact addresses are never treated as application targets.
    """

    if isinstance(apply_email_field, str):
        candidate = apply_email_field.strip().strip("<>")
        if candidate and _EMAIL_PATTERN.fullmatch(candidate):
            return candidate
    if not isinstance(payload_html, str) or not payload_html.strip():
        return None
    unique_addresses: dict[str, str] = {}
    for match in _MAILTO_ANCHOR_PATTERN.finditer(payload_html):
        address = _decode_minimal_html(match.group("address")).strip()
        anchor_text = _decode_minimal_html(re.sub(r"<[^>]+>", " ", match.group("text")))
        if not address or not _EMAIL_PATTERN.fullmatch(address):
            continue
        if not _APPLY_HINT.search(anchor_text):
            continue
        unique_addresses.setdefault(address.casefold(), address)
    if len(unique_addresses) != 1:
        return None
    return next(iter(unique_addresses.values()))


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    characters = (
        character.lower() if character.isalnum() or character.isspace() else " "
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join("".join(characters).split())


def normalize_company(name: str) -> str:
    tokens = normalize_text(name).split()
    while tokens:
        if tokens[-1] in _LEGAL_SUFFIXES:
            tokens.pop()
            continue

        punctuated_suffix_length = next(
            (
                len(suffix)
                for suffix in sorted(_LEGAL_SUFFIXES, key=len, reverse=True)
                if len(tokens) >= len(suffix)
                and all(len(token) == 1 for token in tokens[-len(suffix) :])
                and "".join(tokens[-len(suffix) :]) == suffix
            ),
            None,
        )
        if punctuated_suffix_length is None:
            break
        del tokens[-punctuated_suffix_length:]

    return " ".join(tokens)


def normalize_title(title: str) -> str:
    tokens = normalize_text(title).split()
    return " ".join(token for token in tokens if token not in _REMOTE_TITLE_TOKENS)


def dedup_key(company: str, title: str) -> str:
    return f"{normalize_company(company)}|{normalize_title(title)}"
