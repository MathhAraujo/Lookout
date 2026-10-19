import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiProfile:
    full_name: str
    cpf: str
    phone: str
    address: str
    email: str


_CPF_PATTERN = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_PHONE_PATTERN = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}")


def _profile_literals(pii: PiiProfile) -> list[tuple[str, str]]:
    literals = [
        (pii.full_name, "[CANDIDATE_NAME]"),
        (pii.cpf, "[CPF]"),
        (pii.phone, "[PHONE]"),
        (pii.address, "[ADDRESS]"),
        (pii.email, "[EMAIL]"),
    ]
    return sorted(
        ((value, placeholder) for value, placeholder in literals if value),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )


def redact(text: str, pii: PiiProfile) -> str:
    redacted = text
    for literal, placeholder in _profile_literals(pii):
        redacted = re.sub(re.escape(literal), placeholder, redacted, flags=re.IGNORECASE)

    redacted = _CPF_PATTERN.sub("[CPF]", redacted)
    return _PHONE_PATTERN.sub("[PHONE]", redacted)


def contains_pii(text: str, pii: PiiProfile) -> bool:
    if any(re.search(re.escape(literal), text, flags=re.IGNORECASE) for literal, _ in _profile_literals(pii)):
        return True
    return bool(_CPF_PATTERN.search(text) or _PHONE_PATTERN.search(text))
