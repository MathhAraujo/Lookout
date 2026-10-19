from pathlib import Path

import pytest
from lookout.kb import (
    KnowledgeBaseError,
    kb_to_prompt_text,
    load_knowledge_base,
)


def test_load_knowledge_base_reads_all_sections():
    kb = load_knowledge_base(Path("tests/fixtures/kb"))

    assert kb.identity.full_name == "Maria Silva"
    assert kb.experiences[0].id == "exp-acme"
    assert kb.experiences[0].tech == ["Python", "FastAPI"]
    assert kb.skills == ["Python", "FastAPI", "PostgreSQL"]
    assert kb.languages == ["English", "Portuguese"]
    assert kb.education == ["Bachelor of Computer Science"]


def test_load_knowledge_base_errors_on_missing_identity(tmp_path):
    with pytest.raises(KnowledgeBaseError):
        load_knowledge_base(tmp_path)


def test_kb_to_prompt_text_tags_facts_with_ids():
    text = kb_to_prompt_text(load_knowledge_base(Path("tests/fixtures/kb")))

    assert "[exp-acme]" in text and "[proj-lookout]" in text
