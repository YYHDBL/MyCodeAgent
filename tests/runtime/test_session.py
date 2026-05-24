from runtime.session import SessionStore


def test_session_store_roundtrip(tmp_path):
    store = SessionStore()
    snapshot = store.build_snapshot(
        system_messages=[{"role": "system", "content": "sys"}],
        history_messages=[{"role": "user", "content": "hi"}],
        tool_schema=[],
        project_root=str(tmp_path),
    )

    path = tmp_path / "session.json"
    store.save(path, snapshot)
    loaded = store.load(path)

    assert loaded["system_messages"][0]["content"] == "sys"
    assert loaded["history_messages"][0]["content"] == "hi"
