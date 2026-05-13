from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from question_api.domain.ask_graph import _msg_content, _msg_role, _turn_id_from_message


def test_msg_role_human_message_instance() -> None:
    assert _msg_role(HumanMessage(content="hi")) == "human"


def test_msg_role_ai_message_instance() -> None:
    assert _msg_role(AIMessage(content="yo")) == "ai"


def test_msg_role_lc_constructor_envelope() -> None:
    """JsonPlus checkpoints store messages as lc+constructor blobs (not flat type: human)."""
    human_ctor = {
        "lc": 1,
        "type": "constructor",
        "id": ["langchain", "schema", "messages", "HumanMessage"],
        "kwargs": {
            "content": "Tell me cybersecurity requirements?",
            "additional_kwargs": {"turn_id": "turn-1"},
        },
    }
    assert _msg_role(human_ctor) == "human"
    assert _msg_content(human_ctor) == "Tell me cybersecurity requirements?"
    assert _turn_id_from_message(human_ctor) == "turn-1"

    ai_ctor = {
        "lc": 1,
        "type": "constructor",
        "id": ["langchain", "schema", "messages", "AIMessage"],
        "kwargs": {"content": "Based on the provided context…"},
    }
    assert _msg_role(ai_ctor) == "ai"
    assert "context" in _msg_content(ai_ctor).lower()


def test_msg_role_flat_dict_shapes() -> None:
    """Some serde paths use simple type + content dicts."""
    assert _msg_role({"type": "human", "content": "same?"}) == "human"
    assert _msg_role({"type": "ai", "content": "answer"}) == "ai"
    assert _msg_role({"type": "HumanMessage", "content": "x"}) == "human"
    assert _msg_role({"type": "AIMessage", "content": "y"}) == "ai"


def test_msg_content_dict() -> None:
    assert _msg_content({"type": "human", "content": "  x  "}) == "x"
