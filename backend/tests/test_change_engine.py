import pytest
from app.services.change_engine import apply_changes, ChangeError


def _change(text: str, replacement: str, occurrence=None):
    return {"target": {"text": text, "occurrence": occurrence}, "replacement": replacement}


class TestSingleReplace:
    def test_replace_first_occurrence(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog")])
        assert result.content == "the dog sat on the cat mat"
        assert result.changes_applied == 1

    def test_replace_second_occurrence(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog", occurrence=2)])
        assert result.content == "the cat sat on the dog mat"

    def test_replace_all_occurrences(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog", occurrence="all")])
        assert result.content == "the dog sat on the dog mat"
        assert result.changes_applied == 1

    def test_replace_all_with_zero(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog", occurrence=0)])
        assert result.content == "the dog sat on the dog mat"

    def test_target_not_found_raises(self):
        with pytest.raises(ChangeError, match="not found"):
            apply_changes("hello world", [_change("xyz", "abc")])

    def test_occurrence_out_of_range_raises(self):
        with pytest.raises(ChangeError, match="only 2 occurrences"):
            apply_changes("cat cat", [_change("cat", "dog", occurrence=5)])


class TestBulkReplace:
    def test_multiple_changes_applied_sequentially(self):
        content = "hello world foo bar"
        changes = [
            _change("hello", "hi"),
            _change("foo", "baz"),
        ]
        result = apply_changes(content, changes)
        assert result.content == "hi world baz bar"
        assert result.changes_applied == 2

    def test_replacement_text_is_target_of_next_change(self):
        content = "aaa bbb"
        changes = [
            _change("aaa", "bbb"),
            _change("bbb", "ccc", occurrence="all"),
        ]
        result = apply_changes(content, changes)
        assert result.content == "ccc ccc"

    def test_empty_replacement(self):
        content = "remove this word"
        result = apply_changes(content, [_change("this ", "")])
        assert result.content == "remove word"


class TestLargeFile:
    def test_10mb_document_100_changes(self):
        import time
        # Build a 10MB document
        word = "lorem ipsum dolor sit amet "
        repeats = (10 * 1024 * 1024) // len(word)
        content = word * repeats

        # Create 100 distinct changes
        changes = [_change("lorem", "LOREM", occurrence=i + 1) for i in range(100)]

        start = time.perf_counter()
        result = apply_changes(content, changes)
        elapsed = time.perf_counter() - start

        assert result.changes_applied == 100
        assert elapsed < 5.0, f"Took {elapsed:.2f}s, expected < 5s"
