import json
from pathlib import Path
import pytest

from app import (
    extract_text_from_content,
    fmt_dt,
    load_json_file,
    parse_conversation_messages,
    sanitize_filename,
    tokenize,
)


class TestSanitizeFilename:
    def test_clean_name(self):
        assert sanitize_filename("Normal Title") == "Normal Title"

    def test_replaces_illegal_characters(self):
        result = sanitize_filename(r"Test/File:Name*?<foo>|bar\baz")
        for ch in ["/", ":", "*", "?", "<", ">", "|", "\\"]:
            assert ch not in result

    def test_empty_fallback(self):
        assert sanitize_filename("", fallback="default") == "default"
        assert sanitize_filename("   ", fallback="custom_fallback") == "custom_fallback"

    def test_max_length_truncation(self):
        long_name = "a" * 200
        result = sanitize_filename(long_name)
        assert len(result) <= 120


class TestFmtDt:
    def test_none_and_empty(self):
        assert fmt_dt(None) == ""
        assert fmt_dt("") == ""

    def test_numeric_timestamp(self):
        ts = 1700000000.0
        formatted = fmt_dt(ts)
        assert "2023-11-14" in formatted
        assert "+00:00" in formatted or "Z" in formatted

    def test_string_passthrough(self):
        assert fmt_dt("2023-01-01") == "2023-01-01"


class TestExtractTextFromContent:
    def test_none(self):
        assert extract_text_from_content(None) == ""

    def test_string(self):
        assert extract_text_from_content("hello world") == "hello world"

    def test_list(self):
        assert extract_text_from_content(["line 1", "line 2"]) == "line 1\n\nline 2"

    def test_dict_parts(self):
        content = {"content_type": "text", "parts": ["part 1", "part 2"]}
        assert extract_text_from_content(content) == "part 1\n\npart 2"

    def test_dict_single_text(self):
        content = {"content_type": "text", "text": "solo text"}
        assert extract_text_from_content(content) == "solo text"

    def test_dict_structured_fallback(self):
        content = {"content_type": "code", "code": "print('hi')"}
        extracted = extract_text_from_content(content)
        assert "code" in extracted
        assert "print('hi')" in extracted


class TestParseConversationMessages:
    def test_tree_ordering_and_deduplication(self):
        conversation = {
            "mapping": {
                "root": {
                    "id": "root",
                    "parent": None,
                    "message": None,
                },
                "msg1": {
                    "id": "msg1",
                    "parent": "root",
                    "create_time": 100.0,
                    "message": {
                        "author": {"role": "user"},
                        "create_time": 100.0,
                        "content": {"parts": ["Hello assistant"]},
                    },
                },
                "msg2": {
                    "id": "msg2",
                    "parent": "msg1",
                    "create_time": 200.0,
                    "message": {
                        "author": {"role": "assistant"},
                        "create_time": 200.0,
                        "content": {"parts": ["Hello user"]},
                    },
                },
            }
        }
        messages = parse_conversation_messages(conversation)
        assert len(messages) == 2
        assert messages[0]["author"] == "user"
        assert messages[0]["content"] == "Hello assistant"
        assert messages[1]["author"] == "assistant"
        assert messages[1]["content"] == "Hello user"

    def test_skips_empty_messages(self):
        conversation = {
            "mapping": {
                "node1": {
                    "id": "node1",
                    "parent": None,
                    "message": {
                        "author": {"role": "system"},
                        "content": {"parts": ["   "]},
                    },
                }
            }
        }
        messages = parse_conversation_messages(conversation)
        assert len(messages) == 0


class TestTokenize:
    def test_filtering_and_stopwords(self):
        text = "Chciałbym użyć biblioteki python oraz pandas do analizy 12345"
        tokens = tokenize(text)
        assert "python" in tokens
        assert "pandas" in tokens
        assert "chciałbym" not in tokens  # stopword
        assert "oraz" not in tokens  # stopword
        assert "12345" not in tokens  # digit


class TestLoadJsonFile:
    def test_load_valid_json(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text(json.dumps([{"key": "value"}]), encoding="utf-8")
        data = load_json_file(p)
        assert data == [{"key": "value"}]

    def test_load_utf8_sig_json(self, tmp_path):
        p = tmp_path / "test_sig.json"
        p.write_bytes(json.dumps({"key": "sig_value"}).encode("utf-8-sig"))
        data = load_json_file(p)
        assert data == {"key": "sig_value"}
