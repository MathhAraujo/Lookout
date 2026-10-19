from lookout.normalize import dedup_key, normalize_company, normalize_text, normalize_title


def test_normalize_text_strips_accents_case_and_punctuation():
    assert normalize_text("Sênior Dev, Remoto!") == "senior dev remoto"


def test_normalize_company_strips_legal_suffixes():
    assert normalize_company("Acme, Inc.") == "acme"
    assert normalize_company("Globex Corporation") == "globex"


def test_normalize_company_strips_punctuated_legal_suffixes():
    assert normalize_company("Acme S.A.") == "acme"
    assert normalize_company("Globex L.L.C.") == "globex"


def test_normalize_title_strips_remote_tokens():
    assert normalize_title("Backend Engineer (Remote)") == "backend engineer"


def test_dedup_key_format():
    assert dedup_key("Acme, Inc.", "Backend Engineer (Remote)") == "acme|backend engineer"
