"""Google Gemini provider.

Free tier is generous enough to be the practical default for a student, and the
model is strong enough to avoid the invented-detail problem a local 7B has on
summarisation. Get a key at https://aistudio.google.com/apikey.
"""

from ...config import settings
from .base import LLMProvider

# Gemini 2.5 and later spend output tokens on internal reasoning before writing
# anything, and max_output_tokens caps reasoning + answer together. Asking for
# exactly the caller's budget can therefore return an empty response that hit
# the cap while still thinking, so give the reasoning its own room on top.
THINKING_HEADROOM = 2048


class GeminiProvider(LLMProvider):
    name = "gemini"

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)

        # Gemini names the assistant role "model", and takes the system prompt
        # out of band rather than as a message.
        contents = [
            types.Content(
                role="model" if message["role"] == "assistant" else "user",
                parts=[types.Part(text=message["content"])],
            )
            for message in messages
        ]

        response = client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system or None,
                max_output_tokens=max_tokens + THINKING_HEADROOM,
                temperature=temperature,
                # We never pass tools, and leaving this on makes the SDK warn
                # about automatic function calling on every single request.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )

        text = response.text or ""
        if not text:
            raise RuntimeError(f"Gemini returned no text ({_why_empty(response)})")
        return text


    def available(self) -> bool:
        return bool(settings.gemini_api_key)


def _why_empty(response) -> str:
    """Gemini answers an empty string for several unrelated reasons — a safety
    block, a token cap, a bad model name — so surface which one it was."""
    candidates = getattr(response, "candidates", None) or []
    if candidates and getattr(candidates[0], "finish_reason", None):
        return f"finish_reason={candidates[0].finish_reason}"
    feedback = getattr(response, "prompt_feedback", None)
    if feedback and getattr(feedback, "block_reason", None):
        return f"prompt blocked: {feedback.block_reason}"
    return "no candidates returned"
