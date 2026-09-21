"""Model discovery (`/ai/models/sync`) pulls every id a provider lists — Google alone returns TTS, image, video, music,
embedding, transcription and agent models. Only chat/text models may enter the catalog, otherwise the auto router
tries them for articles and trips the provider's circuit breaker on 400/404s."""
from seo_brain.ai.gateway.catalog import is_chat_model


def test_chat_models_pass():
    for mid in ("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-pro-preview", "gemini-flash-latest",
                "grok-4", "claude-sonnet-5", "gpt-4o", "llama-3.3-70b-versatile", "gemma-4-31b-it"):
        assert is_chat_model(mid), mid


def test_non_chat_models_are_filtered():
    for mid in ("gemini-2.5-flash-preview-tts", "gemini-3-pro-image", "veo-3.1-generate-preview", "lyria-3.5", "gemini-embedding-2",
                "gemini-3.5-transcribe", "gemini-robotics-er-2-preview", "gemini-2.5-computer-use-preview-10-2025",
                "deep-research-pro-preview-12-2025", "antigravity-preview-09-2026", "aqa", "gemini-omni-1.1-flash", "nano-banana-pro-preview",
                "gemini-2.5-flash-native-audio-latest", "gemini-3.5-transcribe-live", "gemini-3.1-pro-preview-customtools", "text-moderation-latest"):
        assert not is_chat_model(mid), mid
