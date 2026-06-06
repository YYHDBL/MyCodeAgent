from runtime.input_preprocess import extract_file_mentions, preprocess_input


def test_preprocess_leaves_plain_input_unchanged():
    result = preprocess_input("Hello world")

    assert result.processed_input == "Hello world"
    assert result.mentioned_files == []
    assert result.truncated_count == 0


def test_preprocess_adds_reminder_for_file_mention():
    result = preprocess_input("Please read @src/main.py")

    assert result.mentioned_files == ["src/main.py"]
    assert "system-reminder" in result.processed_input
    assert "this file" in result.processed_input


def test_preprocess_deduplicates_multiple_mentions():
    result = preprocess_input("Check @a.py and @b.ts and @a.py again")

    assert result.mentioned_files == ["a.py", "b.ts"]
    assert result.truncated_count == 0
    assert "these files" in result.processed_input


def test_preprocess_limits_mentions_to_five():
    result = preprocess_input("@a @b @c @d @e @f @g")

    assert len(result.mentioned_files) == 5
    assert result.truncated_count == 2
    assert "2 more" in result.processed_input


def test_extract_file_mentions_without_injecting_reminder():
    assert extract_file_mentions("@test.py is important") == ["test.py"]


def test_preprocess_supports_nested_and_punctuated_paths():
    nested = preprocess_input("Look at @src/utils/auth.ts")
    punctuated = preprocess_input("Check @my_file-name.py")

    assert nested.mentioned_files == ["src/utils/auth.ts"]
    assert punctuated.mentioned_files == ["my_file-name.py"]
