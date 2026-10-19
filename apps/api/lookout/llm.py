import json

import httpx


class LLMError(Exception):
    pass


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=30.0)

    def complete_json(self, *, system: str, user: str) -> dict:
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            if not isinstance(result, dict):
                raise LLMError("OpenRouter returned JSON that is not an object")
            return result
        except LLMError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
            raise LLMError(f"OpenRouter request failed: {exc}") from exc
