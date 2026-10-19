import httpx
import pytest
from lookout.llm import LLMError, OpenRouterClient


def test_complete_json_posts_to_openrouter_and_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenRouterClient(api_key="test-key", model="test-model", client=client)

    assert llm.complete_json(system="s", user="u") == {"ok": True}


def test_complete_json_raises_on_http_error():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, json={}))
    )
    llm = OpenRouterClient(api_key="k", model="m", client=client)

    with pytest.raises(LLMError):
        llm.complete_json(system="s", user="u")
