import csv
import json
from pathlib import Path
import zipfile
import pytest

from app import (
    conversation_to_markdown,
    extract_profile,
    load_conversations_from_path,
    write_outputs,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestConversationToMarkdown:
    def test_markdown_generation(self):
        fixture_path = FIXTURES_DIR / "conversations.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        conv = data[0]
        markdown, meta = conversation_to_markdown(conv)

        assert "# Python Data Analysis with Pandas" in markdown
        assert "Conversation ID: `conv-test-001`" in markdown
        assert "## 1. User" in markdown
        assert "Cześć, jak analizować dane w python przy użyciu pandas" in markdown
        assert "## 2. Assistant" in markdown
        assert "Możesz wykorzystać bibliotekę pandas" in markdown

        assert meta.title == "Python Data Analysis with Pandas"
        assert meta.message_count == 2
        assert meta.source_id == "conv-test-001"


class TestLoadConversationsFromPath:
    def test_single_conversations_json(self):
        fixture_path = FIXTURES_DIR / "conversations.json"
        data, info = load_conversations_from_path(fixture_path)

        assert isinstance(data, list)
        assert len(data) == 2
        assert info["mode"] == "single_json"
        assert fixture_path.name in info["files"][0]

    def test_directory_with_single_json(self):
        data, info = load_conversations_from_path(FIXTURES_DIR)
        assert isinstance(data, list)
        assert len(data) == 2
        assert info["mode"] == "single_json"

    def test_split_conversations_json(self, tmp_path):
        split_dir = tmp_path / "split_export"
        split_dir.mkdir()

        c1 = [{"id": "c1", "title": "Part 1", "mapping": {}}]
        c2 = [{"id": "c2", "title": "Part 2", "mapping": {}}]

        (split_dir / "conversations-001.json").write_text(json.dumps(c1), encoding="utf-8")
        (split_dir / "conversations-002.json").write_text(json.dumps(c2), encoding="utf-8")

        data, info = load_conversations_from_path(split_dir)
        assert isinstance(data, list)
        assert len(data) == 2
        assert info["mode"] == "split_json"
        assert len(info["files"]) == 2

    def test_zip_archive_loading(self, tmp_path):
        fixture_path = FIXTURES_DIR / "conversations.json"
        zip_file = tmp_path / "export.zip"
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.write(fixture_path, arcname="conversations.json")

        data, info = load_conversations_from_path(zip_file)
        assert isinstance(data, list)
        assert len(data) == 2
        assert info["mode"] == "single_json"


class TestExtractProfile:
    def test_skill_and_role_detection(self):
        fixture_path = FIXTURES_DIR / "conversations.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        metas = []
        for conv in data:
            _, meta = conversation_to_markdown(conv)
            metas.append(meta)

        profile_md = extract_profile(data, metas)

        assert "# Profil roboczy na podstawie historii ChatGPT" in profile_md
        assert "Liczba rozmów: **2**" in profile_md
        # Skills from the fixture texts
        assert "python" in profile_md.lower()
        assert "pandas" in profile_md.lower()
        assert "docker" in profile_md.lower()
        assert "fastapi" in profile_md.lower()
        # Role hint from fixture
        assert "data analyst" in profile_md.lower()


class TestWriteOutputs:
    def test_full_pipeline_writing(self, tmp_path):
        fixture_path = FIXTURES_DIR / "conversations.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        output_dir = tmp_path / "converted_output"
        res = write_outputs(data, output_dir, "single_json", [str(fixture_path)])

        assert res["conversations"] == 2
        assert res["message_count"] == 4
        assert res["mode"] == "single_json"

        # Check per_chat files
        per_chat_files = list((output_dir / "per_chat").glob("*.md"))
        assert len(per_chat_files) == 2

        # Check bundles
        bundle_files = list((output_dir / "bundles").glob("*.md"))
        assert len(bundle_files) >= 1

        # Check index.csv
        index_file = output_dir / "index.csv"
        assert index_file.exists()
        with open(index_file, "r", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
            assert rows[0] == ["title", "create_time", "update_time", "message_count", "file_name", "source_id", "source_file"]
            assert len(rows) == 3  # Header + 2 rows

        # Check stats.md
        stats_file = output_dir / "stats.md"
        assert stats_file.exists()
        stats_content = stats_file.read_text(encoding="utf-8")
        assert "Liczba rozmów: **2**" in stats_content
        assert "Łączna liczba wiadomości: **4**" in stats_content

        # Check career_profile_seed.md
        profile_file = output_dir / "career_profile_seed.md"
        assert profile_file.exists()

        # Check README_GENERATED.md
        readme_file = output_dir / "README_GENERATED.md"
        assert readme_file.exists()
