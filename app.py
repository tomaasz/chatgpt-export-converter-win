import csv
import html as html_lib
import json
import os
import queue
import re
import shutil
import tempfile
import threading
import traceback
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "ChatGPT Export Converter v2"
BUNDLE_TARGET_CHARS = 2_000_000
MAX_FILENAME_LEN = 120
MAX_PROFILE_ITEMS = 20

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False
    DND_FILES = None
    TkinterDnD = None

try:
    import gdrive
    GDRIVE_AVAILABLE = True
except Exception:
    GDRIVE_AVAILABLE = False
    gdrive = None  # type: ignore


@dataclass
class ConversationMeta:
    title: str
    create_time: str
    update_time: str
    message_count: int
    file_name: str
    source_id: str
    source_file: str = ""


ROLE_MAP = {
    "user": "User",
    "assistant": "Assistant",
    "system": "System",
    "tool": "Tool",
}

SKILL_KEYWORDS = [
    "python", "sql", "javascript", "typescript", "java", "c#", "c++", "go", "rust",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "langchain", "llamaindex",
    "docker", "kubernetes", "git", "github", "gitlab", "linux", "windows", "powershell",
    "azure", "aws", "gcp", "bigquery", "airflow", "dbt", "spark", "hadoop", "snowflake",
    "postgresql", "mysql", "sqlite", "mongodb", "redis", "elasticsearch",
    "excel", "power bi", "tableau", "looker", "notion", "jira", "confluence",
    "chatgpt", "openai", "claude", "gemini", "ollama", "rag", "embeddings", "vector db",
    "playwright", "selenium", "fastapi", "flask", "django", "react", "node.js", "next.js",
    "bash", "ssh", "vscode", "google colab", "notebooklm", "qdrant", "chroma",
]

ROLE_HINTS = [
    "developer", "programista", "analityk danych", "data analyst", "data engineer", "data scientist",
    "devops", "ml engineer", "ai engineer", "backend", "frontend", "full stack", "team leader",
    "architekt", "konsultant", "specjalista", "administrator"
]

STOPWORDS = {
    "oraz", "który", "która", "które", "przez", "tego", "też", "jest", "było", "będzie", "chciałbym",
    "chcę", "możesz", "zrób", "jak", "czy", "dla", "oraz", "żeby", "bardzo", "bardziej", "tylko",
    "mam", "mieć", "jego", "jej", "ich", "nad", "pod", "ten", "ta", "to", "nie", "tak", "się",
    "with", "that", "this", "from", "have", "your", "about", "into", "using", "use", "used",
}


class SimpleHTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data)

    def get_text(self):
        text = " ".join(self.parts)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


def sanitize_filename(name: str, fallback: str = "conversation") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', '_', (name or '').strip())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ._')
    if not cleaned:
        cleaned = fallback
    return cleaned[:MAX_FILENAME_LEN]


def fmt_dt(value):
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            return dt.isoformat()
        return str(value)
    except Exception:
        return str(value)


def extract_text_from_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n\n".join(str(x) for x in content if x)
    if isinstance(content, dict):
        ctype = content.get("content_type")
        parts = content.get("parts")
        text = []
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, str):
                    text.append(p)
                elif isinstance(p, dict):
                    text.append(json.dumps(p, ensure_ascii=False, indent=2))
                else:
                    text.append(str(p))
        elif ctype == "text" and "text" in content:
            text.append(str(content.get("text", "")))
        elif ctype:
            text.append(json.dumps(content, ensure_ascii=False, indent=2))
        return "\n\n".join(t for t in text if t).strip()
    return str(content)


def parse_conversation_messages(conversation: dict):
    mapping = conversation.get("mapping") or {}
    nodes = {}
    children_by_parent = defaultdict(list)

    for node_id, node in mapping.items():
        parent = node.get("parent")
        if parent:
            children_by_parent[parent].append(node_id)
        message = node.get("message") or {}
        author = (message.get("author") or {}).get("role") or "unknown"
        content = extract_text_from_content(message.get("content"))
        create_time = message.get("create_time") or node.get("create_time")
        if content.strip():
            nodes[node_id] = {
                "author": author,
                "content": content.strip(),
                "create_time": create_time,
            }

    def sort_key(node_id):
        msg = nodes.get(node_id, {})
        ct = msg.get("create_time")
        if isinstance(ct, (int, float)):
            return (0, float(ct), node_id)
        return (1, 0, node_id)

    roots = [nid for nid, n in mapping.items() if not n.get("parent")]
    if not roots:
        roots = list(mapping.keys())

    ordered = []
    seen = set()

    def visit(nid):
        if nid in seen:
            return
        seen.add(nid)
        if nid in nodes:
            ordered.append(nodes[nid])
        for child in sorted(children_by_parent.get(nid, []), key=sort_key):
            visit(child)

    for r in sorted(roots, key=sort_key):
        visit(r)

    deduped = []
    last_key = None
    for m in ordered:
        key = (m["author"], m["content"])
        if key != last_key:
            deduped.append(m)
            last_key = key
    return deduped


def conversation_to_markdown(conversation: dict):
    title = conversation.get("title") or "Untitled conversation"
    conv_id = conversation.get("id") or ""
    create_time = fmt_dt(conversation.get("create_time"))
    update_time = fmt_dt(conversation.get("update_time"))
    messages = parse_conversation_messages(conversation)

    lines = [f"# {title}", ""]
    if conv_id:
        lines.append(f"- Conversation ID: `{conv_id}`")
    if create_time:
        lines.append(f"- Created: {create_time}")
    if update_time:
        lines.append(f"- Updated: {update_time}")
    lines.extend(["", "---", ""])

    for idx, msg in enumerate(messages, start=1):
        role = ROLE_MAP.get(msg["author"], msg["author"].capitalize())
        lines.append(f"## {idx}. {role}")
        lines.append("")
        lines.append(msg["content"])
        lines.append("")

    markdown = "\n".join(lines).rstrip() + "\n"
    meta = ConversationMeta(
        title=title,
        create_time=create_time,
        update_time=update_time,
        message_count=len(messages),
        file_name="",
        source_id=conv_id,
    )
    return markdown, meta


def find_relevant_files(path: Path):
    single_conversations = []
    split_conversations = []
    chat_html = []
    other_json = []
    for p in path.rglob('*'):
        if not p.is_file():
            continue
        low = p.name.lower()
        if low == 'conversations.json':
            single_conversations.append(p)
        elif re.fullmatch(r'conversations-\d+\.json', low):
            split_conversations.append(p)
        elif low == 'chat.html':
            chat_html.append(p)
        elif low.endswith('.json'):
            other_json.append(p)
    return single_conversations, split_conversations, chat_html, other_json


def parse_chat_html_to_conversation(chat_html_path: Path):
    raw = chat_html_path.read_text(encoding='utf-8', errors='ignore')
    parser = SimpleHTMLTextExtractor()
    parser.feed(raw)
    text = parser.get_text()
    if not text:
        raise ValueError('Plik chat.html jest pusty albo nie udało się odczytać treści.')

    paragraphs = [p.strip() for p in re.split(r'(?:(?:\r?\n){2,}|\s{4,})', text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    messages = []
    for part in paragraphs:
        messages.append({'author': 'unknown', 'content': part, 'create_time': None})

    conv = {'title': 'chat.html (fallback)', 'id': f'html::{chat_html_path.name}', 'create_time': '', 'update_time': '', 'mapping': {}}
    return conv, messages


def markdown_from_html_fallback(chat_html_path: Path):
    conv, messages = parse_chat_html_to_conversation(chat_html_path)
    title = conv['title']
    lines = [f'# {title}', '', f'- Source file: `{chat_html_path.name}`', '', '---', '']
    for idx, msg in enumerate(messages, start=1):
        lines.append(f'## {idx}. Fragment')
        lines.append('')
        lines.append(msg['content'])
        lines.append('')
    markdown = '\n'.join(lines).rstrip() + '\n'
    meta = ConversationMeta(title=title, create_time='', update_time='', message_count=len(messages), file_name='', source_id=conv['id'])
    return markdown, meta


def extract_zip_to_temp(zip_path: Path):
    temp_dir = Path(tempfile.mkdtemp(prefix='chatgpt_export_'))
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(temp_dir)
    return temp_dir


def load_json_file(json_path: Path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)


def load_conversations_from_path(input_path: Path):
    temp_dir = None
    path = input_path

    if input_path.is_file() and input_path.suffix.lower() == '.zip':
        temp_dir = extract_zip_to_temp(input_path)
        path = temp_dir

        single_conversations, split_conversations, chat_html, other_json = find_relevant_files(path)
        if not single_conversations and not split_conversations and not chat_html:
            nested_zips = [p for p in path.rglob('*.zip') if p.is_file()]
            if len(nested_zips) == 1:
                nested_temp = extract_zip_to_temp(nested_zips[0])
                shutil.rmtree(temp_dir, ignore_errors=True)
                temp_dir = nested_temp
                path = nested_temp

    if path.is_dir():
        single_conversations, split_conversations, chat_html, other_json = find_relevant_files(path)
        if single_conversations:
            json_path = sorted(single_conversations, key=lambda p: len(str(p)))[0]
            data = load_json_file(json_path)
            if not isinstance(data, list):
                raise ValueError('Plik conversations.json ma nieoczekiwany format.')
            return data, {'mode': 'single_json', 'source_path': json_path, 'temp_dir': temp_dir, 'files': [str(json_path)]}

        if split_conversations:
            split_conversations = sorted(split_conversations, key=lambda p: p.name)
            merged = []
            for p in split_conversations:
                data = load_json_file(p)
                if not isinstance(data, list):
                    raise ValueError(f'Plik {p.name} ma nieoczekiwany format.')
                merged.extend(data)
            return merged, {'mode': 'split_json', 'source_path': path, 'temp_dir': temp_dir, 'files': [str(p) for p in split_conversations]}

        if chat_html:
            html_path = sorted(chat_html, key=lambda p: len(str(p)))[0]
            markdown, meta = markdown_from_html_fallback(html_path)
            return None, {'mode': 'html_fallback', 'source_path': html_path, 'temp_dir': temp_dir, 'fallback': {'markdown': markdown, 'meta': meta}}

        diagnostic = []
        if other_json:
            preview = ', '.join(p.name for p in other_json[:15])
            diagnostic.append(f'Znalezione inne pliki JSON: {preview}')
        else:
            diagnostic.append('Nie znaleziono żadnych plików JSON ani chat.html.')
        raise FileNotFoundError('Nie znaleziono conversations.json, conversations-*.json ani chat.html.\n\n' + '\n'.join(diagnostic))

    if path.is_file() and path.name.lower() == 'conversations.json':
        data = load_json_file(path)
        if not isinstance(data, list):
            raise ValueError('Plik conversations.json ma nieoczekiwany format.')
        return data, {'mode': 'single_json', 'source_path': path, 'temp_dir': temp_dir, 'files': [str(path)]}

    if path.is_file() and re.fullmatch(r'conversations-\d+\.json', path.name.lower()):
        siblings = sorted(path.parent.glob('conversations-*.json'))
        merged = []
        for p in siblings:
            data = load_json_file(p)
            if not isinstance(data, list):
                raise ValueError(f'Plik {p.name} ma nieoczekiwany format.')
            merged.extend(data)
        return merged, {'mode': 'split_json', 'source_path': path.parent, 'temp_dir': temp_dir, 'files': [str(p) for p in siblings]}

    if path.is_file() and path.name.lower() == 'chat.html':
        markdown, meta = markdown_from_html_fallback(path)
        return None, {'mode': 'html_fallback', 'source_path': path, 'temp_dir': temp_dir, 'fallback': {'markdown': markdown, 'meta': meta}}

    raise FileNotFoundError('Wskaż plik ZIP z eksportem, folder eksportu, chat.html, conversations.json lub conversations-000.json.')


def tokenize(text: str):
    text = text.lower()
    tokens = re.findall(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9_+.#-]{3,}", text)
    return [t for t in tokens if t not in STOPWORDS and not t.isdigit()]


def extract_profile(conversations: list, metas: list):
    title_counter = Counter()
    token_counter = Counter()
    user_texts = []
    assistant_texts = 0
    user_messages = 0
    all_messages = 0
    date_values = []

    for conv in conversations:
        title = (conv.get('title') or '').strip()
        if title:
            title_counter[title] += 1
        ct = conv.get('create_time')
        if isinstance(ct, (int, float)):
            date_values.append(float(ct))
        ut = conv.get('update_time')
        if isinstance(ut, (int, float)):
            date_values.append(float(ut))
        for msg in parse_conversation_messages(conv):
            all_messages += 1
            if msg['author'] == 'user':
                user_messages += 1
                user_texts.append(msg['content'])
                token_counter.update(tokenize(msg['content']))
            elif msg['author'] == 'assistant':
                assistant_texts += 1

    full_user_text = "\n".join(user_texts).lower()
    found_skills = []
    for kw in SKILL_KEYWORDS:
        if kw.lower() in full_user_text:
            found_skills.append(kw)
    found_roles = []
    for kw in ROLE_HINTS:
        if kw.lower() in full_user_text:
            found_roles.append(kw)

    top_topics = [w for w, _ in token_counter.most_common(MAX_PROFILE_ITEMS) if len(w) >= 4]
    recent_titles = []
    metas_sorted = sorted(metas, key=lambda m: m.update_time or m.create_time, reverse=True)
    for m in metas_sorted[:10]:
        if m.title and m.title not in recent_titles:
            recent_titles.append(m.title)

    earliest = latest = ""
    if date_values:
        earliest = fmt_dt(min(date_values))
        latest = fmt_dt(max(date_values))

    lines = [
        "# Profil roboczy na podstawie historii ChatGPT",
        "",
        "## Szybka checklista",
        "",
        "- Analiza wszystkich rozmów i metadanych eksportu.",
        "- Ekstrakcja tytułów, dat, liczby wiadomości i najczęstszych tematów.",
        "- Wykrycie technologii, narzędzi i ról pojawiających się w treści pytań.",
        "- Oznaczenie danych wnioskowanych pośrednio jako roboczych.",
        "- Przygotowanie materiału wyjściowego do CV / LinkedIn / profilu zawodowego.",
        "",
        "## Statystyki zbioru",
        "",
        f"- Liczba rozmów: **{len(conversations)}**",
        f"- Liczba wiadomości po konwersji: **{all_messages}**",
        f"- Liczba wiadomości użytkownika: **{user_messages}**",
        f"- Liczba wiadomości asystenta: **{assistant_texts}**",
    ]
    if earliest:
        lines.append(f"- Zakres dat w metadanych: **{earliest}** → **{latest}**")

    lines.extend([
        "",
        "## Najczęściej wykryte technologie i narzędzia",
        "",
    ])
    if found_skills:
        for skill in sorted(found_skills)[:MAX_PROFILE_ITEMS]:
            lines.append(f"- {skill}")
    else:
        lines.append("- Nie wykryto jednoznacznych technologii na podstawie prostych reguł. Warto użyć dalszej analizy AI.")

    lines.extend([
        "",
        "## Wykryte role / konteksty zawodowe",
        "",
    ])
    if found_roles:
        for role in sorted(found_roles):
            lines.append(f"- {role} *(możliwe / wnioskowane z kontekstu)*")
    else:
        lines.append("- Brak jednoznacznych ról wykrytych regułowo.")

    lines.extend([
        "",
        "## Najczęstsze tematy w pytaniach użytkownika",
        "",
    ])
    for topic in top_topics[:MAX_PROFILE_ITEMS]:
        lines.append(f"- {topic}")

    lines.extend([
        "",
        "## Najnowsze tytuły rozmów",
        "",
    ])
    for title in recent_titles:
        lines.append(f"- {title}")

    lines.extend([
        "",
        "## Uwagi",
        "",
        "- Ten plik jest roboczym podsumowaniem lokalnym, opartym na heurystykach.",
        "- Do stworzenia finalnego profilu zawodowego warto użyć plików z `bundles/` lub `per_chat/` i zadać modelowi AI precyzyjny prompt analityczny.",
        "- Informacje z tej sekcji nie zastępują pełnej ekstrakcji faktów z całej historii rozmów.",
        "",
    ])
    return "\n".join(lines)


def write_outputs(conversations: list, output_dir: Path, source_mode: str, source_files: list, status_cb=None):
    per_chat_dir = output_dir / 'per_chat'
    bundles_dir = output_dir / 'bundles'
    per_chat_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir.mkdir(parents=True, exist_ok=True)

    metas = []
    bundle_parts = []
    current_bundle = []
    current_chars = 0
    bundle_index = 1
    total_messages = 0

    total = len(conversations)
    for i, conv in enumerate(conversations, start=1):
        title = conv.get('title') or f'conversation_{i}'
        if status_cb:
            status_cb(f'Przetwarzanie {i}/{total}: {title[:80]}')
        markdown, meta = conversation_to_markdown(conv)
        filename = f'{i:05d}_{sanitize_filename(title)}.md'
        meta.file_name = filename
        if source_mode == 'split_json':
            meta.source_file = 'multiple conversations-*.json'
        elif source_files:
            meta.source_file = Path(source_files[0]).name
        metas.append(meta)
        total_messages += meta.message_count

        with open(per_chat_dir / filename, 'w', encoding='utf-8') as f:
            f.write(markdown)

        if current_chars + len(markdown) > BUNDLE_TARGET_CHARS and current_bundle:
            bundle_name = f'chat_history_{bundle_index:03d}.md'
            with open(bundles_dir / bundle_name, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(current_bundle))
            bundle_parts.append(bundle_name)
            bundle_index += 1
            current_bundle = []
            current_chars = 0

        current_bundle.append(markdown)
        current_chars += len(markdown)

    if current_bundle:
        bundle_name = f'chat_history_{bundle_index:03d}.md'
        with open(bundles_dir / bundle_name, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(current_bundle))
        bundle_parts.append(bundle_name)

    with open(output_dir / 'index.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['title', 'create_time', 'update_time', 'message_count', 'file_name', 'source_id', 'source_file'])
        for m in metas:
            writer.writerow([m.title, m.create_time, m.update_time, m.message_count, m.file_name, m.source_id, m.source_file])

    profile_md = extract_profile(conversations, metas)
    with open(output_dir / 'career_profile_seed.md', 'w', encoding='utf-8') as f:
        f.write(profile_md)

    stats = [m.message_count for m in metas]
    avg_messages = round(sum(stats) / len(stats), 2) if stats else 0
    largest = sorted(metas, key=lambda m: m.message_count, reverse=True)[:10]
    with open(output_dir / 'stats.md', 'w', encoding='utf-8') as f:
        f.write('# Statystyki eksportu ChatGPT\n\n')
        f.write(f'- Format źródła: **{source_mode}**\n')
        f.write(f'- Liczba plików źródłowych: **{len(source_files)}**\n')
        f.write(f'- Liczba rozmów: **{len(conversations)}**\n')
        f.write(f'- Łączna liczba wiadomości: **{total_messages}**\n')
        f.write(f'- Średnia liczba wiadomości na rozmowę: **{avg_messages}**\n\n')
        f.write('## Największe rozmowy\n\n')
        for item in largest:
            f.write(f'- {item.title} — {item.message_count} wiadomości\n')

    with open(output_dir / 'README_GENERATED.md', 'w', encoding='utf-8') as f:
        f.write(
            '# Wynik konwersji eksportu ChatGPT\n\n'
            '## Zawartość\n\n'
            '- `per_chat/` — osobny plik Markdown dla każdej rozmowy\n'
            '- `bundles/` — większe pliki zbiorcze, wygodne do NotebookLM / AI\n'
            '- `index.csv` — indeks rozmów i metadanych\n'
            '- `stats.md` — statystyki zbioru\n'
            '- `career_profile_seed.md` — roboczy szkic profilu zawodowego na podstawie heurystyk\n\n'
            '## Jak użyć\n\n'
            '1. Do NotebookLM zwykle najlepiej wrzucić pliki z `bundles/`.\n'
            '2. Do dalszej analizy lokalnej użyj `per_chat/`, `index.csv` i `stats.md`.\n'
            '3. Do generowania profilu zawodowego użyj `career_profile_seed.md` jako punktu wyjścia i dołącz swój prompt analityczny.\n'
        )

    return {
        'conversations': len(conversations),
        'bundle_files': len(bundle_parts),
        'output_dir': str(output_dir),
        'mode': source_mode,
        'source_files': len(source_files),
        'message_count': total_messages,
    }


def write_html_fallback_output(markdown: str, meta: ConversationMeta, output_dir: Path):
    per_chat_dir = output_dir / 'per_chat'
    bundles_dir = output_dir / 'bundles'
    per_chat_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir.mkdir(parents=True, exist_ok=True)

    filename = '00001_chat_html_fallback.md'
    with open(per_chat_dir / filename, 'w', encoding='utf-8') as f:
        f.write(markdown)
    with open(bundles_dir / 'chat_history_001.md', 'w', encoding='utf-8') as f:
        f.write(markdown)
    with open(output_dir / 'index.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['title', 'create_time', 'update_time', 'message_count', 'file_name', 'source_id', 'source_file'])
        writer.writerow([meta.title, meta.create_time, meta.update_time, meta.message_count, filename, meta.source_id, 'chat.html'])
    with open(output_dir / 'stats.md', 'w', encoding='utf-8') as f:
        f.write('# Statystyki eksportu ChatGPT\n\n- Format źródła: **html_fallback**\n- Liczba rozmów: **1**\n')
    with open(output_dir / 'career_profile_seed.md', 'w', encoding='utf-8') as f:
        f.write('# Profil roboczy\n\nBrak pełnych danych strukturalnych. Wykryto tylko `chat.html`.\n')
    with open(output_dir / 'README_GENERATED.md', 'w', encoding='utf-8') as f:
        f.write(
            '# Wynik konwersji eksportu ChatGPT\n\n'
            'Wykryto tylko `chat.html`, bez strukturalnych plików `conversations*.json`.\n'
            'Utworzono awaryjny eksport do jednego pliku Markdown.\n'
        )
    return {'conversations': 1, 'bundle_files': 1, 'output_dir': str(output_dir), 'mode': 'html_fallback', 'source_files': 1, 'message_count': meta.message_count}


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry('820x680')
        self.root.minsize(760, 600)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value='Gotowe.')
        self.queue = queue.Queue()
        self.worker_running = False

        # Google Drive state
        self.drive_creds = None
        self.drive_service = None
        self.upload_to_drive_var = tk.BooleanVar(value=False)
        self._drive_temp_dir = None  # temp dir for Drive downloads

        self._build_ui()
        self.root.after(150, self._poll_queue)

        # Try to silently restore Drive session
        if GDRIVE_AVAILABLE:
            self._try_restore_drive()

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill='both', expand=True)

        ttk.Label(outer, text='Konwerter eksportu ChatGPT v2', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(
            outer,
            text='Obsługuje stary format `conversations.json`, nowy format `conversations-000.json ...`, folder eksportu, ZIP i awaryjnie `chat.html`. Konwersja odbywa się lokalnie.',
            wraplength=780,
        ).pack(anchor='w', pady=(6, 4))

        how_to = ttk.Label(
            outer,
            text='Jak pobrać eksport?  chatgpt.com \u2192 Ustawienia \u2192 Eksport danych \u2192 Potwierdź eksport. Link do pobrania ZIP przyjdzie e-mailem.',
            wraplength=780,
            foreground='#555555',
            font=('Segoe UI', 9),
        )
        how_to.pack(anchor='w', pady=(0, 6))

        # Google Drive connection bar
        drive_bar = ttk.Frame(outer)
        drive_bar.pack(fill='x', pady=(0, 10))
        self._drive_status_label = ttk.Label(drive_bar, text='Google Drive: niedostępne', foreground='#999999', font=('Segoe UI', 9))
        self._drive_status_label.pack(side='left')
        self._drive_btn = ttk.Button(drive_bar, text='Zaloguj do Google Drive', command=self._drive_sign_in, width=24)
        self._drive_btn.pack(side='right')
        if not GDRIVE_AVAILABLE:
            self._drive_btn.config(state='disabled')
            self._drive_status_label.config(text='Google Drive: brak bibliotek (pip install google-api-python-client google-auth-oauthlib)')
        elif not gdrive.is_configured():
            self._drive_btn.config(state='disabled')
            self._drive_status_label.config(text='Google Drive: brak client_config.json (szczegóły w README)')

        frm_input = ttk.LabelFrame(outer, text='Źródło')
        frm_input.pack(fill='x', pady=(0, 12))
        ttk.Entry(frm_input, textvariable=self.input_var).pack(side='left', fill='x', expand=True, padx=(10, 6), pady=10)
        ttk.Button(frm_input, text='Wybierz plik', command=self.pick_file).pack(side='left', padx=4, pady=10)
        ttk.Button(frm_input, text='Wybierz folder', command=self.pick_folder).pack(side='left', padx=4, pady=10)
        self._drive_import_btn = ttk.Button(frm_input, text='Importuj z Drive', command=self._drive_import, state='disabled')
        self._drive_import_btn.pack(side='left', padx=(4, 10), pady=10)

        frm_output = ttk.LabelFrame(outer, text='Folder docelowy')
        frm_output.pack(fill='x', pady=(0, 12))
        ttk.Entry(frm_output, textvariable=self.output_var).pack(side='left', fill='x', expand=True, padx=(10, 6), pady=10)
        ttk.Button(frm_output, text='Wybierz', command=self.pick_output).pack(side='left', padx=(4, 10), pady=10)

        drop_frame = ttk.LabelFrame(outer, text='Przeciągnij i upuść')
        drop_frame.pack(fill='both', expand=True, pady=(0, 12))

        self.drop_label = tk.Label(
            drop_frame,
            text=(
                'Upuść tutaj plik ZIP, folder eksportu, `conversations.json`, `conversations-000.json` lub `chat.html`\n\n'
                + ('Obsługa drag & drop aktywna.' if DND_AVAILABLE else 'Drag & drop wyłączone — użyj przycisków wyboru pliku/folderu.\nAby włączyć, zainstaluj: pip install tkinterdnd2')
            ),
            relief='groove', borderwidth=2, padx=16, pady=32, justify='center', bg='#fafafa'
        )
        self.drop_label.pack(fill='both', expand=True, padx=10, pady=10)
        if DND_AVAILABLE:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind('<<Drop>>', self.on_drop)

        options = ttk.Frame(outer)
        options.pack(fill='x')
        self.open_after_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text='Otwórz folder wynikowy po zakończeniu', variable=self.open_after_var).pack(side='left')
        self._drive_upload_chk = ttk.Checkbutton(options, text='Wyślij wynik na Google Drive', variable=self.upload_to_drive_var, state='disabled')
        self._drive_upload_chk.pack(side='left', padx=(16, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=(12, 8))
        self.convert_btn = ttk.Button(actions, text='Konwertuj lokalnie', command=self.start_conversion)
        self.convert_btn.pack(side='left')
        ttk.Button(actions, text='Wyczyść', command=self.clear_form).pack(side='left', padx=8)

        ttk.Label(outer, textvariable=self.status_var, wraplength=780).pack(anchor='w', pady=(6, 0))
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(8, 0))

    def set_status(self, text):
        self.status_var.set(text)

    def pick_file(self):
        path = filedialog.askopenfilename(
            title='Wybierz plik ZIP, JSON lub HTML',
            filetypes=[
                ('Eksport ChatGPT', '*.zip *.json *.html'), ('ZIP', '*.zip'), ('JSON', '*.json'), ('HTML', '*.html'), ('Wszystkie pliki', '*.*')
            ],
        )
        if path:
            self.input_var.set(path)
            self.ensure_default_output()

    def pick_folder(self):
        path = filedialog.askdirectory(title='Wybierz folder eksportu ChatGPT')
        if path:
            self.input_var.set(path)
            self.ensure_default_output()

    def pick_output(self):
        path = filedialog.askdirectory(title='Wybierz folder docelowy')
        if path:
            self.output_var.set(path)

    def ensure_default_output(self):
        if not self.output_var.get() and self.input_var.get():
            src = Path(self.input_var.get())
            base = src.parent if src.exists() else Path.cwd()
            self.output_var.set(str(base / 'chatgpt_converted'))

    def clear_form(self):
        if self.worker_running:
            return
        self.input_var.set('')
        self.output_var.set('')
        self.set_status('Gotowe.')

    def on_drop(self, event):
        raw = event.data.strip()
        paths = self.root.tk.splitlist(raw)
        if paths:
            self.input_var.set(paths[0])
            self.ensure_default_output()
            self.set_status(f'Wybrano: {paths[0]}')

    def start_conversion(self):
        if self.worker_running:
            return
        input_value = self.input_var.get().strip().strip('"')
        output_value = self.output_var.get().strip().strip('"')
        if not input_value:
            messagebox.showwarning(APP_TITLE, 'Wskaż plik ZIP, folder, chat.html, conversations.json lub conversations-000.json.')
            return
        if not output_value:
            messagebox.showwarning(APP_TITLE, 'Wskaż folder docelowy.')
            return
        self.worker_running = True
        self.convert_btn.config(state='disabled')
        self.progress.start(10)
        self.set_status('Rozpoczynam konwersję...')
        thread = threading.Thread(target=self._run_conversion, args=(input_value, output_value), daemon=True)
        thread.start()

    def _run_conversion(self, input_value, output_value):
        info = None
        try:
            input_path = Path(input_value)
            output_dir = Path(output_value)
            output_dir.mkdir(parents=True, exist_ok=True)
            conversations, info = load_conversations_from_path(input_path)
            mode = info['mode']
            if mode == 'html_fallback':
                fallback = info['fallback']
                self.queue.put(('status', f'Wykryto tylko {Path(info["source_path"]).name}. Uruchamiam tryb awaryjny.'))
                result = write_html_fallback_output(fallback['markdown'], fallback['meta'], output_dir)
            else:
                source_desc = f"tryb={mode}, pliki źródłowe={len(info['files'])}"
                self.queue.put(('status', f'Znaleziono {len(conversations)} rozmów ({source_desc}).'))
                result = write_outputs(conversations, output_dir, source_mode=mode, source_files=info['files'], status_cb=lambda txt: self.queue.put(('status', txt)))
            self.queue.put(('done', result))
        except Exception as e:
            self.queue.put(('error', f'{e}\n\n{traceback.format_exc()}'))
        finally:
            try:
                if info and info.get('temp_dir') and Path(info['temp_dir']).exists():
                    shutil.rmtree(info['temp_dir'], ignore_errors=True)
            except Exception:
                pass

    # -- Google Drive methods --

    def _try_restore_drive(self):
        """Try to silently load stored credentials on startup."""
        def _worker():
            creds = gdrive.load_credentials()
            if creds:
                self.queue.put(('drive_auth_ok', creds))
        threading.Thread(target=_worker, daemon=True).start()

    def _drive_sign_in(self):
        if self.drive_service:
            self._drive_sign_out()
            return
        self._drive_status_label.config(text='Google Drive: logowanie...', foreground='#CC8800')
        self._drive_btn.config(state='disabled')
        gdrive.authenticate_async(
            callback=lambda creds: self.queue.put(('drive_auth_ok', creds)),
            error_cb=lambda msg: self.queue.put(('drive_auth_fail', msg)),
        )

    def _drive_sign_out(self):
        gdrive.logout()
        self.drive_creds = None
        self.drive_service = None
        self._update_drive_ui(connected=False)

    def _on_drive_authenticated(self, creds):
        self.drive_creds = creds
        self.drive_service = gdrive.build_service(creds)
        email = gdrive.get_user_email(self.drive_service)
        self._update_drive_ui(connected=True, email=email)

    def _update_drive_ui(self, connected: bool, email: str = ''):
        if connected:
            label = f'Google Drive: {email}' if email else 'Google Drive: połączono'
            self._drive_status_label.config(text=label, foreground='#228B22')
            self._drive_btn.config(text='Wyloguj z Drive', state='normal')
            self._drive_import_btn.config(state='normal')
            self._drive_upload_chk.config(state='normal')
        else:
            self._drive_status_label.config(text='Google Drive: niepołączono', foreground='#999999')
            self._drive_btn.config(text='Zaloguj do Google Drive', state='normal')
            self._drive_import_btn.config(state='disabled')
            self._drive_upload_chk.config(state='disabled')
            self.upload_to_drive_var.set(False)

    def _drive_import(self):
        if not self.drive_service or self.worker_running:
            return
        result = gdrive.pick_file_from_drive(self.root, self.drive_service)
        if not result:
            return
        self.worker_running = True
        self.convert_btn.config(state='disabled')
        self.progress.start(10)
        self.set_status(f'Pobieranie z Google Drive: {result["name"]}...')
        threading.Thread(
            target=self._drive_download_worker, args=(result,), daemon=True
        ).start()

    def _drive_download_worker(self, file_info: dict):
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix='gdrive_dl_'))
            self._drive_temp_dir = temp_dir
            dest = temp_dir / file_info['name']
            gdrive.download_file(
                self.drive_service,
                file_info['id'],
                dest,
                progress_cb=lambda done, total: self.queue.put(('status', f'Pobieranie: {done // 1024} / {total // 1024} KB')),
            )
            self.queue.put(('drive_download_done', str(dest)))
        except Exception as exc:
            self.queue.put(('error', f'Błąd pobierania z Drive: {exc}'))

    def _drive_upload_result(self, output_dir: str):
        """Start upload of conversion results to Drive."""
        if not self.drive_service:
            return
        folder_info = gdrive.pick_folder_from_drive(self.root, self.drive_service)
        parent_id = folder_info['id'] if folder_info else 'root'
        self.worker_running = True
        self.convert_btn.config(state='disabled')
        self.progress.start(10)
        self.set_status('Wysyłanie wyniku na Google Drive...')
        threading.Thread(
            target=self._drive_upload_worker, args=(output_dir, parent_id), daemon=True
        ).start()

    def _drive_upload_worker(self, output_dir: str, parent_id: str):
        try:
            result = gdrive.upload_folder(
                self.drive_service,
                Path(output_dir),
                parent_id,
                status_cb=lambda txt: self.queue.put(('status', txt)),
            )
            self.queue.put(('drive_upload_done', result))
        except Exception as exc:
            self.queue.put(('error', f'Błąd uploadu na Drive: {exc}'))

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self.queue.get_nowait()
                if msg_type == 'status':
                    self.set_status(payload)
                elif msg_type == 'done':
                    self.worker_running = False
                    self.convert_btn.config(state='normal')
                    self.progress.stop()
                    out = payload['output_dir']
                    self.set_status(
                        f"Gotowe. Tryb: {payload['mode']}, rozmowy: {payload['conversations']}, wiadomości: {payload['message_count']}, pliki zbiorcze: {payload['bundle_files']}, wynik: {out}"
                    )
                    # Clean up Drive temp download
                    if self._drive_temp_dir and Path(self._drive_temp_dir).exists():
                        shutil.rmtree(self._drive_temp_dir, ignore_errors=True)
                        self._drive_temp_dir = None
                    if self.open_after_var.get():
                        try:
                            os.startfile(out)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    # Auto-trigger Drive upload if checkbox is checked
                    if self.upload_to_drive_var.get() and self.drive_service:
                        messagebox.showinfo(APP_TITLE, self.status_var.get())
                        self._drive_upload_result(out)
                    else:
                        messagebox.showinfo(APP_TITLE, self.status_var.get())
                elif msg_type == 'error':
                    self.worker_running = False
                    self.convert_btn.config(state='normal')
                    self.progress.stop()
                    self.set_status('Wystąpił błąd.')
                    if self._drive_temp_dir and Path(self._drive_temp_dir).exists():
                        shutil.rmtree(self._drive_temp_dir, ignore_errors=True)
                        self._drive_temp_dir = None
                    messagebox.showerror(APP_TITLE, payload[:7000])
                elif msg_type == 'drive_auth_ok':
                    self._on_drive_authenticated(payload)
                elif msg_type == 'drive_auth_fail':
                    self._update_drive_ui(connected=False)
                    messagebox.showerror(APP_TITLE, f'Logowanie do Google Drive nie powiodło się:\n{payload[:2000]}')
                elif msg_type == 'drive_download_done':
                    # File downloaded from Drive — set as input and start conversion
                    self.worker_running = False
                    self.input_var.set(payload)
                    self.ensure_default_output()
                    self.set_status(f'Pobrano z Drive: {Path(payload).name}. Rozpoczynam konwersję...')
                    self.start_conversion()
                elif msg_type == 'drive_upload_done':
                    self.worker_running = False
                    self.convert_btn.config(state='normal')
                    self.progress.stop()
                    url = payload.get('url', '')
                    count = payload.get('uploaded', 0)
                    self.set_status(f'Wysłano {count} plików na Google Drive: {url}')
                    messagebox.showinfo(APP_TITLE, f'Wysłano {count} plików na Google Drive.\n\n{url}')
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    try:
        root.iconname(APP_TITLE)
    except Exception:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use('vista')
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
