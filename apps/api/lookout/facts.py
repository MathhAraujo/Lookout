from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ApprovedFact:
    key: str
    value: str
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApprovedFacts:
    facts: dict[str, ApprovedFact]


class FactsError(Exception):
    """Raised when the local approved-facts file is missing or invalid."""


def load_facts(path: Path) -> ApprovedFacts:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        raise FactsError("unable to load approved facts") from None

    if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
        raise FactsError("invalid approved facts")

    facts: dict[str, ApprovedFact] = {}
    for entry in data["facts"]:
        if not isinstance(entry, dict) or set(entry) - {"key", "value", "allowed_values"}:
            raise FactsError("invalid approved facts")

        key = entry.get("key")
        value = entry.get("value")
        allowed_values = entry.get("allowed_values", [])
        if allowed_values is None:
            allowed_values = []
        if (
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
            or not isinstance(allowed_values, list)
            or any(not isinstance(option, str) or not option.strip() for option in allowed_values)
        ):
            raise FactsError("invalid approved facts")

        normalized_key = key.strip()
        normalized_value = value.strip()
        options = tuple(option.strip() for option in allowed_values)
        if options and normalized_value.casefold() not in {option.casefold() for option in options}:
            raise FactsError("invalid approved facts")
        if normalized_key in facts:
            raise FactsError("invalid approved facts")

        facts[normalized_key] = ApprovedFact(
            key=normalized_key,
            value=normalized_value,
            allowed_values=options,
        )

    return ApprovedFacts(facts=facts)
