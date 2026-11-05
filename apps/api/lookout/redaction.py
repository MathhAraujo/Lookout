import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiProfile:
    full_name: str
    cpf: str
    phone: str
    address: str
    email: str


_INTERNATIONAL_PHONE_PATTERN = re.compile(r"(?<!\w)\+\d(?:[ .()-]*\d){6,14}(?!\w)")
_CPF_PATTERN = re.compile(r"(?<!\d)\d{3}[ .]?\d{3}[ .]?\d{3}[- .]?\d{2}(?!\d)")
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?55[ .()-]*)?\(?\d{2}\)?[ .-]*9?\d{4}[ .-]*\d{4}(?!\w)")
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
_GENERIC_PATTERNS = (
    (_EMAIL_PATTERN, "[EMAIL]"),
    (_CPF_PATTERN, "[CPF]"),
    (_INTERNATIONAL_PHONE_PATTERN, "[PHONE]"),
    (_PHONE_PATTERN, "[PHONE]"),
)


def _fold(text: str) -> tuple[str, list[int]]:
    """Normalize accents and separators while retaining original character offsets."""
    letters, offsets = [], []
    for index, character in enumerate(text):
        for folded in unicodedata.normalize("NFKD", character.casefold()):
            if unicodedata.combining(folded):
                continue
            value = folded if folded.isalnum() else " "
            if value == " " and (not letters or letters[-1] == " "):
                continue
            letters.append(value)
            offsets.append(index)
    return "".join(letters), offsets


def _profile_literals(pii: PiiProfile) -> list[tuple[str, str]]:
    literals = [
        (pii.full_name, "[CANDIDATE_NAME]"),
        (pii.cpf, "[CPF]"),
        (pii.phone, "[PHONE]"),
        (pii.address, "[ADDRESS]"),
        (pii.email, "[EMAIL]"),
    ]
    # A free-text copy often omits middle names or the city/state suffix.
    names = pii.full_name.split()
    if len(names) > 2:
        literals.append((f"{names[0]} {names[-1]}", "[CANDIDATE_NAME]"))
    street = re.split(r"\s[-–—]\s", pii.address, maxsplit=1)[0]
    if street and street != pii.address:
        literals.append((street, "[ADDRESS]"))
    return [(value, placeholder) for value, placeholder in literals if value.strip()]


def _profile_spans(text: str, pii: PiiProfile) -> list[tuple[int, int, str]]:
    folded, offsets = _fold(text)
    spans = []
    for literal, placeholder in _profile_literals(pii):
        normalized = _fold(literal)[0].strip()
        if not normalized:
            continue
        for match in re.finditer(rf"(?<!\w){re.escape(normalized)}(?!\w)", folded):
            spans.append((offsets[match.start()], offsets[match.end() - 1] + 1, placeholder))
    return spans


def redact(text: str, pii: PiiProfile) -> str:
    spans = sorted(_profile_spans(text, pii), key=lambda span: (span[0], -span[1]))
    parts, cursor = [], 0
    for start, end, placeholder in spans:
        if start < cursor:
            continue
        parts.extend([text[cursor:start], placeholder])
        cursor = end
    parts.append(text[cursor:])
    redacted = "".join(parts)
    for pattern, placeholder in _GENERIC_PATTERNS:
        redacted = pattern.sub(placeholder, redacted)
    return redacted


def contains_pii(text: str, pii: PiiProfile) -> bool:
    return bool(_profile_spans(text, pii)) or any(
        pattern.search(text) for pattern, _ in _GENERIC_PATTERNS
    )
