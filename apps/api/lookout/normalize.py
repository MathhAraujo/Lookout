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
