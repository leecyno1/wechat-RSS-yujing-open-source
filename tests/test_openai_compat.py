def test_openai_compat_chat_url_join():
    from core.llm.openai_compat import _chat_completions_url

    assert _chat_completions_url("https://api.example.com/v1") == "https://api.example.com/v1/chat/completions"
    assert _chat_completions_url("https://api.example.com/v1/") == "https://api.example.com/v1/chat/completions"
    assert _chat_completions_url("https://api.example.com") == "https://api.example.com/chat/completions"

