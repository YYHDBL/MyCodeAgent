from runtime.messages import HistoryManager, Message


def test_runtime_history_module_exposes_history_public_objects():
    from runtime.history import HistoryManager as CanonicalHistoryManager
    from runtime.history import Message as CanonicalMessage

    assert CanonicalHistoryManager is HistoryManager
    assert CanonicalMessage is Message


def test_message_to_dict_returns_openai_shape():
    msg = Message(content="hello", role="user")

    assert msg.to_dict() == {"role": "user", "content": "hello"}


def test_history_manager_serialization_roundtrip_preserves_metadata():
    history = HistoryManager()
    history.append_user("question")
    history.append_assistant("answer", metadata={"step": 1})

    payload = history.serialize_messages()

    restored = HistoryManager()
    restored.load_messages(payload)

    assert restored.get_message_count() == 2
    assert restored.get_messages()[1].metadata["step"] == 1
