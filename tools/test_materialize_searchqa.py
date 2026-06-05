import pytest
from materialize_searchqa import build_split, coerce_answers, validate_counts


def test_build_split_maps_fields():
    key_to_row = {"a": {"key": "a", "question": "Q1", "context": "[DOC] C1", "answers": ["X"]}}
    out = build_split(["a"], key_to_row)
    assert out == [{"id": "a", "question": "Q1", "context": "[DOC] C1", "answers": ["X"]}]


def test_build_split_raises_on_missing_id():
    with pytest.raises(KeyError):
        build_split(["missing"], {"a": {"question": "Q", "context": "C", "answers": ["X"]}})


def test_coerce_answers_handles_str_list_none():
    assert coerce_answers("hello") == ["hello"]
    assert coerce_answers(["a", "b"]) == ["a", "b"]
    assert coerce_answers(None) == []


def test_validate_counts_mismatch_raises():
    with pytest.raises(ValueError):
        validate_counts("train", [{"id": "1"}])  # train 期望 400
