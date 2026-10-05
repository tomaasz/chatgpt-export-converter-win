import csv
from pathlib import Path
import pytest

from app import (
    ConversationMeta,
    SimpleHTMLTextExtractor,
    load_conversations_from_path,
    markdown_from_html_fallback,
    parse_chat_html_to_conversation,
    write_html_fallback_output,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSimpleHTMLTextExtractor:
    def test_extract_and_unescape(self):
        parser = SimpleHTMLTextExtractor()
        parser.feed("<div><p>Hello &amp; welcome</p><span>to Python</span></div>")
        text = parser.get_text()
        assert text == "Hello & welcome to Python"


class TestHtmlFallbackParsing:
    def test_parse_chat_html_to_conversation(self):
        html_file = FIXTURES_DIR / "chat.html"
        conv, messages = parse_chat_html_to_conversation(html_file)
        assert conv["title"] == "chat.html (fallback)"
        assert len(messages) >= 1
        assert "przykładowa historia" in messages[0]["content"]

    def test_markdown_from_html_fallback(self):
        html_file = FIXTURES_DIR / "chat.html"
        markdown, meta = markdown_from_html_fallback(html_file)
        assert "# chat.html (fallback)" in markdown
        assert "## 1. Fragment" in markdown
        assert meta.message_count >= 1
        assert meta.source_id == f"html::{html_file.name}"

    def test_load_conversations_from_path_html(self):
        html_file = FIXTURES_DIR / "chat.html"
        data, info = load_conversations_from_path(html_file)
        assert data is None
        assert info["mode"] == "html_fallback"
        assert "fallback" in info

    def test_write_html_fallback_output(self, tmp_path):
        html_file = FIXTURES_DIR / "chat.html"
        markdown, meta = markdown_from_html_fallback(html_file)
        output_dir = tmp_path / "html_fallback_output"

        res = write_html_fallback_output(markdown, meta, output_dir)
        assert res["conversations"] == 1
        assert res["mode"] == "html_fallback"

        per_chat_file = output_dir / "per_chat" / "00001_chat_html_fallback.md"
        assert per_chat_file.exists()
        assert "# chat.html (fallback)" in per_chat_file.read_text(encoding="utf-8")

        bundle_file = output_dir / "bundles" / "chat_history_001.md"
        assert bundle_file.exists()

        index_file = output_dir / "index.csv"
        assert index_file.exists()
        with open(index_file, "r", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
            assert len(rows) == 2
