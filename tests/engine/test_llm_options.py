from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from nexaql.config import LLMConfig
from nexaql.chat import llm


@pytest.mark.parametrize("effort", [None, "low"])
def test_reasoning_is_opt_in(monkeypatch, effort):
    create = Mock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="{}"))]
        )
    )
    monkeypatch.setattr(
        llm, "_get_client", lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    )
    config = LLMConfig(provider="meta", model="example", reasoning_effort=effort)
    assert llm.chat_completion(config, messages=[]) == "{}"
    if effort is None:
        assert "reasoning_effort" not in create.call_args.kwargs
    else:
        assert create.call_args.kwargs["reasoning_effort"] == effort


def test_truncated_model_output_is_not_parsed_as_valid_text(monkeypatch):
    create = Mock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content='{"node":'))]
        )
    )
    monkeypatch.setattr(
        llm, "_get_client", lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    )
    with pytest.raises(RuntimeError, match="output limit"):
        llm.chat_completion(LLMConfig(provider="meta", model="example"), messages=[])
