"""Google Drive integration for ChatGPT Export Converter.

OAuth2 authentication, file browsing, download and upload via Google Drive API v3.
"""

import io
import json
import os
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from google.auth.transport.requests import Request  # type: ignore
from google.oauth2.credentials import Credentials  # type: ignore
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload  # type: ignore

import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# OAuth2 configuration
# ---------------------------------------------------------------------------
# Client config is loaded from an external file — NEVER hardcoded.
# Search order:
#   1. client_config.json next to this script (bundled with EXE)
#   2. ~/.chatgpt-converter/client_config.json (user-provided)
#
# Users can create their own Google Cloud project:
#   1. Go to https://console.cloud.google.com/
#   2. Create a project, enable Google Drive API
#   3. Create OAuth 2.0 Client ID (type: Desktop app)
#   4. Download the JSON and save as client_config.json
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]
TOKEN_DIR = Path.home() / ".chatgpt-converter"
TOKEN_PATH = TOKEN_DIR / "gdrive_token.json"
# PyInstaller sets sys._MEIPASS for bundled apps; otherwise use script dir
import sys as _sys
_APP_DIR = Path(getattr(_sys, '_MEIPASS', Path(__file__).resolve().parent))

FOLDER_MIME = "application/vnd.google-apps.folder"


def _find_client_config() -> Optional[Path]:
    """Find client_config.json in known locations."""
    candidates = [
        _APP_DIR / "client_config.json",
        TOKEN_DIR / "client_config.json",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _load_client_config() -> dict:
    """Load and validate client_config.json. Raises FileNotFoundError if missing."""
    path = _find_client_config()
    if not path:
        raise FileNotFoundError(
            "Brak pliku client_config.json.\n\n"
            "Umieść plik obok aplikacji lub w:\n"
            f"  {TOKEN_DIR / 'client_config.json'}\n\n"
            "Aby go uzyskać:\n"
            "1. Wejdź na https://console.cloud.google.com/\n"
            "2. Utwórz projekt i włącz Google Drive API\n"
            "3. Utwórz dane logowania OAuth 2.0 (typ: Aplikacja na komputer)\n"
            "4. Pobierz plik JSON i zapisz jako client_config.json"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    # Google's downloaded JSON has an "installed" or "web" key
    if "installed" not in data and "web" not in data:
        raise ValueError(
            f"Plik {path} nie wygląda na poprawny client_config.json od Google.\n"
            "Powinien zawierać klucz 'installed' z client_id i client_secret."
        )
    return data


def is_configured() -> bool:
    """Check if client_config.json exists (Drive can be used)."""
    return _find_client_config() is not None


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def load_credentials() -> Optional[Credentials]:
    """Try to load stored credentials and refresh if needed. Returns None on failure."""
    if not TOKEN_PATH.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_credentials(creds)
            return creds
    except Exception:
        TOKEN_PATH.unlink(missing_ok=True)
    return None


def save_credentials(creds: Credentials) -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")


def authenticate_blocking() -> Credentials:
    """Run the full browser-based OAuth2 flow (blocking)."""
    client_config = _load_client_config()
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    save_credentials(creds)
    return creds


def authenticate_async(
    callback: Callable[[Credentials], None],
    error_cb: Callable[[str], None],
) -> threading.Thread:
    """Run OAuth flow in a background thread."""
    def _worker():
        try:
            creds = authenticate_blocking()
            callback(creds)
        except Exception as exc:
            error_cb(str(exc))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def logout() -> None:
    TOKEN_PATH.unlink(missing_ok=True)


def build_service(creds: Credentials):
    return build("drive", "v3", credentials=creds, static_discovery=False)


def get_user_email(service) -> str:
    """Get the email of the authenticated user."""
    try:
        about = service.about().get(fields="user(emailAddress)").execute()
        return about.get("user", {}).get("emailAddress", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Drive API operations
# ---------------------------------------------------------------------------

def list_folder(service, folder_id: str = "root", query_extra: str = "") -> list[dict]:
    """List files in a Drive folder. Returns list of dicts with id, name, mimeType, size, modifiedTime."""
    q_parts = [f"'{folder_id}' in parents", "trashed=false"]
    if query_extra:
        q_parts.append(query_extra)
    q = " and ".join(q_parts)

    results = []
    page_token = None
    while True:
        resp = service.files().list(
            q=q,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
            orderBy="folder,name",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def download_file(
    service,
    file_id: str,
    dest_path: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """Download a file from Drive to dest_path."""
    request = service.files().get_media(fileId=file_id)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if progress_cb and status:
                progress_cb(
                    int(status.resumable_progress),
                    int(status.total_size or 0),
                )
    return dest_path


def create_folder(service, name: str, parent_id: str = "root") -> str:
    """Create a folder on Drive. Returns the new folder's ID."""
    meta = {
        "name": name,
        "mimeType": FOLDER_MIME,
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def upload_file(
    service,
    local_path: Path,
    parent_id: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Upload a single file. Returns file ID."""
    file_meta = {"name": local_path.name, "parents": [parent_id]}
    media = MediaFileUpload(str(local_path), resumable=True)
    request = service.files().create(body=file_meta, media_body=media, fields="id")

    response = None
    while response is None:
        status, response = request.next_chunk()
        if progress_cb and status:
            progress_cb(
                int(status.resumable_progress),
                int(status.total_size or 0),
            )
    return response["id"]


def upload_folder(
    service,
    local_dir: Path,
    parent_id: str = "root",
    status_cb: Optional[Callable[[str], None]] = None,
) -> dict:
    """Recursively upload a directory to Drive. Returns summary dict."""
    folder_name = local_dir.name
    drive_folder_id = create_folder(service, folder_name, parent_id)
    uploaded = 0

    for item in sorted(local_dir.iterdir()):
        if item.is_dir():
            sub = upload_folder(service, item, drive_folder_id, status_cb)
            uploaded += sub["uploaded"]
        elif item.is_file():
            if status_cb:
                status_cb(f"Upload: {item.name}")
            upload_file(service, item, drive_folder_id)
            uploaded += 1

    return {
        "uploaded": uploaded,
        "folder_id": drive_folder_id,
        "folder_name": folder_name,
        "url": f"https://drive.google.com/drive/folders/{drive_folder_id}",
    }


# ---------------------------------------------------------------------------
# Drive File Picker Dialog (Tkinter Toplevel)
# ---------------------------------------------------------------------------

class DrivePickerDialog(tk.Toplevel):
    """Modal dialog for browsing and selecting files/folders on Google Drive."""

    def __init__(
        self,
        parent: tk.Tk,
        service,
        mode: str = "file",
        title: str = "Google Drive",
        file_filter: str = "",
    ):
        """
        Args:
            parent: root Tk window
            service: googleapiclient Resource for Drive v3
            mode: 'file' to pick a file, 'folder' to pick a folder
            title: window title
            file_filter: Drive query filter for files, e.g. "(name contains '.zip' or name contains '.json')"
        """
        super().__init__(parent)
        self.service = service
        self.mode = mode
        self.file_filter = file_filter
        self.result: Optional[dict] = None

        self.title(title)
        self.geometry("700x480")
        self.minsize(500, 350)
        self.transient(parent)
        self.grab_set()

        self._nav_stack: list[str] = []
        self._current_folder_id = "root"
        self._current_folder_name = "My Drive"
        self._items: list[dict] = []

        self._build_ui()
        self._load_folder("root", "My Drive")

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="\u2190 Wstecz", command=self._go_back, width=10).pack(side="left")
        ttk.Button(top, text="\u2302 Home", command=self._go_home, width=10).pack(side="left", padx=4)
        ttk.Button(top, text="\u21BB Odśwież", command=self._refresh, width=10).pack(side="left")

        self._path_label = ttk.Label(top, text="My Drive", font=("Segoe UI", 9))
        self._path_label.pack(side="left", padx=(12, 0))

        # Treeview
        tree_frame = ttk.Frame(self, padding=(8, 0, 8, 0))
        tree_frame.pack(fill="both", expand=True)

        cols = ("size", "modified")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Nazwa", anchor="w")
        self.tree.heading("size", text="Rozmiar", anchor="e")
        self.tree.heading("modified", text="Zmodyfikowany", anchor="w")
        self.tree.column("#0", width=360, minwidth=200)
        self.tree.column("size", width=100, minwidth=60, anchor="e")
        self.tree.column("modified", width=160, minwidth=100)
        self.tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.bind("<Double-1>", self._on_double_click)

        # Status / loading
        self._status_var = tk.StringVar(value="Ładowanie...")
        ttk.Label(self, textvariable=self._status_var).pack(anchor="w", padx=8, pady=(4, 0))

        # Buttons
        btn_frame = ttk.Frame(self, padding=8)
        btn_frame.pack(fill="x")

        self._select_btn = ttk.Button(btn_frame, text="Wybierz", command=self._on_select)
        self._select_btn.pack(side="right")
        ttk.Button(btn_frame, text="Anuluj", command=self._on_cancel).pack(side="right", padx=(0, 8))

    # -- Navigation --

    def _go_back(self):
        if self._nav_stack:
            folder_id = self._nav_stack.pop()
            self._load_folder(folder_id)

    def _go_home(self):
        self._nav_stack.clear()
        self._load_folder("root", "My Drive")

    def _refresh(self):
        self._load_folder(self._current_folder_id, self._current_folder_name)

    def _load_folder(self, folder_id: str, folder_name: str = ""):
        if folder_name:
            self._current_folder_name = folder_name
        self._current_folder_id = folder_id
        self._path_label.config(text=self._current_folder_name)
        self._status_var.set("Ładowanie...")
        self.tree.delete(*self.tree.get_children())

        threading.Thread(
            target=self._fetch_folder, args=(folder_id,), daemon=True
        ).start()

    def _fetch_folder(self, folder_id: str):
        try:
            items = list_folder(self.service, folder_id, self.file_filter)
            self.after(0, self._populate, items)
        except Exception as exc:
            self.after(0, self._show_error, str(exc))

    def _populate(self, items: list[dict]):
        self._items = items
        self.tree.delete(*self.tree.get_children())

        folders = [f for f in items if f.get("mimeType") == FOLDER_MIME]
        files = [f for f in items if f.get("mimeType") != FOLDER_MIME]

        for f in folders:
            self.tree.insert("", "end", iid=f["id"], text=f"\U0001F4C1 {f['name']}", values=("", self._fmt_date(f)))
        for f in files:
            self.tree.insert("", "end", iid=f["id"], text=f"\U0001F4C4 {f['name']}", values=(self._fmt_size(f), self._fmt_date(f)))

        count = len(folders) + len(files)
        self._status_var.set(f"{count} element{'ów' if count != 1 else ''}")

    def _show_error(self, msg: str):
        self._status_var.set(f"Błąd: {msg[:200]}")

    # -- Actions --

    def _on_double_click(self, event):
        sel = self.tree.focus()
        if not sel:
            return
        item = next((f for f in self._items if f["id"] == sel), None)
        if item and item.get("mimeType") == FOLDER_MIME:
            self._nav_stack.append(self._current_folder_id)
            self._load_folder(item["id"], item["name"])
        elif item and self.mode == "file":
            self.result = item
            self.destroy()

    def _on_select(self):
        sel = self.tree.focus()
        if not sel:
            return
        item = next((f for f in self._items if f["id"] == sel), None)
        if not item:
            return
        if self.mode == "folder":
            if item.get("mimeType") == FOLDER_MIME:
                self.result = item
                self.destroy()
            else:
                self._status_var.set("Wybierz folder, nie plik.")
        else:
            if item.get("mimeType") == FOLDER_MIME:
                self._nav_stack.append(self._current_folder_id)
                self._load_folder(item["id"], item["name"])
            else:
                self.result = item
                self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

    # -- Formatting helpers --

    @staticmethod
    def _fmt_size(item: dict) -> str:
        size = item.get("size")
        if not size:
            return ""
        n = int(size)
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        if n < 1024 * 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} MB"
        return f"{n / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def _fmt_date(item: dict) -> str:
        raw = item.get("modifiedTime", "")
        if not raw:
            return ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return raw[:16]


def pick_file_from_drive(parent: tk.Tk, service) -> Optional[dict]:
    """Open the Drive file picker and return the selected file dict or None."""
    dlg = DrivePickerDialog(
        parent,
        service,
        mode="file",
        title="Google Drive — Wybierz plik źródłowy",
        file_filter="(name contains '.zip' or name contains '.json' or name contains '.html')",
    )
    parent.wait_window(dlg)
    return dlg.result


def pick_folder_from_drive(parent: tk.Tk, service) -> Optional[dict]:
    """Open the Drive folder picker and return the selected folder dict or None."""
    dlg = DrivePickerDialog(
        parent,
        service,
        mode="folder",
        title="Google Drive — Wybierz folder docelowy",
    )
    parent.wait_window(dlg)
    return dlg.result
