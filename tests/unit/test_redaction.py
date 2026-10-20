from lookout.redaction import PiiProfile, contains_pii, redact

PII = PiiProfile(
    full_name="Maria Silva",
    cpf="123.456.789-09",
    phone="+55 11 98765-4321",
    address="Rua das Flores, 123 - São Paulo/SP",
    email="maria.silva@example.com",
)


def test_redact_replaces_identity_fields():
    out = redact(
        "MARIA SILVA — maria.silva@example.com — Rua das Flores, 123 - São Paulo/SP",
        PII,
    )

    assert "Maria Silva" not in out and "maria.silva@example.com" not in out
    assert "[CANDIDATE_NAME]" in out and "[EMAIL]" in out and "[ADDRESS]" in out


def test_redact_catches_pii_inside_free_text():
    out = redact("Led migration; reach me at 11 98765-4321 or 987.654.321-00", PII)

    assert "98765-4321" not in out and "987.654.321-00" not in out


def test_redact_catches_international_phone_in_free_text():
    out = redact("Contact me at +44 20 7946 0958", PII)

    assert "+44 20 7946 0958" not in out
    assert "[PHONE]" in out


def test_redact_keeps_company_names():
    assert "Globex Corporation" in redact("Backend Engineer at Globex Corporation", PII)


def test_contains_pii():
    assert contains_pii("call 123.456.789-09", PII)
    assert not contains_pii("[CPF] available on request", PII)


def test_contains_pii_detects_international_phone():
    assert contains_pii("Contact me at +44 20 7946 0958", PII)
