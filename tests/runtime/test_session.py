import json


def test_legacy_snapshot_import_is_transcript_only_and_idempotent(tmp_path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    snapshot = tmp_path / "session-latest.json"
    snapshot.write_text(
        json.dumps(
            {
                "history_messages": [
                    {"role": "user", "content": "restore this", "metadata": {}},
                    {"role": "assistant", "content": "restored", "metadata": {}},
                ],
                "read_cache": {"README.md": "cached"},
            }
        ),
        encoding="utf-8",
    )
    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")

    assert store.import_legacy_snapshot(snapshot) is True
    assert store.import_legacy_snapshot(snapshot) is False

    resume = ResumeLoader(store).load_session()

    assert [message["content"] for message in resume.history_messages] == ["restore this", "restored"]
    assert resume.runtime_state["read_cache"] == {"README.md": "cached"}
    assert len(store.read_events()) == 3
