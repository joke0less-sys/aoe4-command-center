#!/usr/bin/env python3
from __future__ import annotations

import queue
import json
import os
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import aoe4_team_analyzer as analyzer


POLL_SECONDS = 45
APP_DIR = Path(__file__).resolve().parent
REPORTS_DIR = APP_DIR / "reports"
HISTORY_PATH = REPORTS_DIR / "verlauf.json"
HISTORY_LIMIT = 40


class CommandCenterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AoE4 Command Center")
        self.root.geometry("980x760")
        self.root.minsize(850, 620)
        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.scan_stop = threading.Event()
        self.scan_thread: threading.Thread | None = None
        self.last_plan_game_id: int | None = None
        self.last_seen_ongoing_id: int | None = None
        self.pending_review_game_ids: list[int] = []
        self.history_entries: list[dict[str, str]] = []

        self.url_var = tk.StringVar()
        self.match_type = tk.StringVar(value="ranked")
        self.scan_status = tk.StringVar(value="Bereit.")
        self.mode_vars: dict[str, tk.BooleanVar] = {}

        self.build_ui()
        self.root.after(200, self.drain_messages)

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(outer, text="Eingabe", padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="AoE4World Profil-URL, Spiel-URL, Profil-ID oder Name").pack(anchor=tk.W)
        entry_row = ttk.Frame(top)
        entry_row.pack(fill=tk.X, pady=(4, 8))
        ttk.Entry(entry_row, textvariable=self.url_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.build_mode_controls(top)

        actions = ttk.Frame(outer)
        actions.pack(fill=tk.X, pady=10)
        ttk.Button(actions, text="Vergangene Spiele auswerten", command=self.run_report).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Spielplan fuer aktuelles/letztes Spiel", command=self.run_plan_once).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Live-Scan starten", command=self.start_scan).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Scan stoppen", command=self.stop_scan).pack(side=tk.LEFT)

        ttk.Label(outer, textvariable=self.scan_status).pack(anchor=tk.W, pady=(0, 8))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)

        output_frame = ttk.Frame(notebook, padding=8)
        notebook.add(output_frame, text="Kurzfazit / Spielplan")
        self.output = tk.Text(output_frame, wrap=tk.WORD, height=28)
        self.output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(output_frame, command=self.output.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.output.configure(yscrollcommand=scroll.set)

        self.build_history_tab(notebook)
        self.load_history()
        if not self.history_entries:
            self.load_history_from_reports()
        self.refresh_history_list()

    def build_history_tab(self, notebook: ttk.Notebook) -> None:
        history_frame = ttk.Frame(notebook, padding=8)
        notebook.add(history_frame, text="Verlauf")

        left = ttk.Frame(history_frame)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        ttk.Label(left, text="Gespeicherte Auswertungen").pack(anchor=tk.W)
        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.Y, expand=True, pady=(4, 8))
        self.history_list = tk.Listbox(list_frame, width=42, height=22)
        self.history_list.pack(side=tk.LEFT, fill=tk.Y, expand=True)
        history_scroll = ttk.Scrollbar(list_frame, command=self.history_list.yview)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_list.configure(yscrollcommand=history_scroll.set)
        self.history_list.bind("<<ListboxSelect>>", self.show_selected_history)

        button_row = ttk.Frame(left)
        button_row.pack(fill=tk.X)
        ttk.Button(button_row, text="Anzeigen", command=self.show_selected_history).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(button_row, text="Ordner oeffnen", command=self.open_reports_folder).pack(side=tk.LEFT)

        right = ttk.Frame(history_frame)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.history_preview = tk.Text(right, wrap=tk.WORD, height=24)
        self.history_preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scroll = ttk.Scrollbar(right, command=self.history_preview.yview)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_preview.configure(yscrollcommand=preview_scroll.set)

    def build_mode_controls(self, parent: ttk.Frame) -> None:
        mode_box = ttk.LabelFrame(parent, text="Modus", padding=8)
        mode_box.pack(fill=tk.X)

        type_row = ttk.Frame(mode_box)
        type_row.pack(fill=tk.X, pady=(0, 6))
        for label, value in [("Ranked", "ranked"), ("Quick Match", "quick"), ("Beides", "both")]:
            ttk.Radiobutton(type_row, text=label, value=value, variable=self.match_type).pack(side=tk.LEFT, padx=(0, 14))

        sizes = ttk.Frame(mode_box)
        sizes.pack(fill=tk.X)
        defaults = {"3v3", "4v4"}
        for size in ["1v1", "2v2", "3v3", "4v4"]:
            var = tk.BooleanVar(value=size in defaults)
            self.mode_vars[size] = var
            ttk.Checkbutton(sizes, text=size, variable=var).pack(side=tk.LEFT, padx=(0, 14))

    def selected_modes(self) -> list[str]:
        prefixes = []
        if self.match_type.get() in ("ranked", "both"):
            prefixes.append("rm")
        if self.match_type.get() in ("quick", "both"):
            prefixes.append("qm")
        modes = []
        for size, var in self.mode_vars.items():
            if var.get():
                modes.extend(f"{prefix}_{size}" for prefix in prefixes)
        return modes or ["rm_3v3", "rm_4v4"]

    def append_output(self, text: str, clear: bool = False) -> None:
        if clear:
            self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text.rstrip() + "\n\n")
        self.output.see(tk.END)

    def send_message(self, kind: str, payload: object) -> None:
        self.message_queue.put((kind, payload))

    def drain_messages(self) -> None:
        while True:
            try:
                kind, payload = self.message_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.scan_status.set(str(payload))
            elif kind == "clear":
                self.append_output(str(payload), clear=True)
            elif kind == "history":
                self.add_history_entry(payload)
            else:
                self.append_output(str(payload))
        self.root.after(200, self.drain_messages)

    def load_history(self) -> None:
        try:
            if HISTORY_PATH.exists():
                loaded = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    self.history_entries = [entry for entry in loaded if isinstance(entry, dict)]
        except (OSError, json.JSONDecodeError):
            self.history_entries = []

    def load_history_from_reports(self) -> None:
        if not REPORTS_DIR.exists():
            return
        entries: list[dict[str, str]] = []
        for path in REPORTS_DIR.glob("*.md"):
            if path.name.endswith("_details.md"):
                continue
            kind = "Spielplan" if path.name.endswith("_spielplan.md") else "Auswertung"
            detail_path = Path(str(path).replace("_kurzbericht.md", "_details.md"))
            title_name = path.stem.replace("_kurzbericht", "").replace("_spielplan", "")
            entries.append(
                {
                    "created_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "title": f"{kind}: {title_name}",
                    "kind": kind,
                    "player_name": title_name,
                    "profile_id": "",
                    "preview_path": str(path),
                    "detail_path": str(detail_path) if detail_path.exists() else "",
                }
            )
        self.history_entries = sorted(entries, key=lambda entry: entry["created_at"], reverse=True)[:HISTORY_LIMIT]
        if self.history_entries:
            self.save_history()

    def save_history(self) -> None:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(
            json.dumps(self.history_entries[:HISTORY_LIMIT], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_history_entry(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        entry = {str(key): str(value) for key, value in payload.items()}
        self.history_entries = [entry, *self.history_entries]
        self.history_entries = self.history_entries[:HISTORY_LIMIT]
        self.save_history()
        self.refresh_history_list()
        self.history_list.selection_clear(0, tk.END)
        self.history_list.selection_set(0)
        self.show_history_entry(0)

    def refresh_history_list(self) -> None:
        self.history_list.delete(0, tk.END)
        for entry in self.history_entries:
            created_at = entry.get("created_at", "?")
            title = entry.get("title", "Auswertung")
            self.history_list.insert(tk.END, f"{created_at} - {title}")

    def selected_history_index(self) -> int | None:
        selection = self.history_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if index >= len(self.history_entries):
            return None
        return index

    def show_selected_history(self, _event: object | None = None) -> None:
        index = self.selected_history_index()
        if index is not None:
            self.show_history_entry(index)

    def show_history_entry(self, index: int) -> None:
        entry = self.history_entries[index]
        preview_path = self.report_path(entry.get("preview_path", ""))
        if preview_path.exists():
            text = preview_path.read_text(encoding="utf-8")
        else:
            text = "Die Datei zu diesem Verlaufseintrag wurde nicht gefunden."
        self.history_preview.delete("1.0", tk.END)
        self.history_preview.insert(tk.END, text)
        self.history_preview.see("1.0")

    def open_reports_folder(self) -> None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(REPORTS_DIR)

    def report_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else APP_DIR / path

    def history_payload(
        self,
        kind: str,
        player_name: str,
        profile_id: int,
        preview_path: Path,
        detail_path: Path | None = None,
    ) -> dict[str, str]:
        return {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": f"{kind}: {player_name}",
            "kind": kind,
            "player_name": player_name,
            "profile_id": str(profile_id),
            "preview_path": str(preview_path),
            "detail_path": str(detail_path or ""),
        }

    def report_base(self, player_name: str, profile_id: int, game_id: int | None = None) -> str:
        base = f"{analyzer.safe_slug(player_name)}_{profile_id}"
        return f"{base}_{game_id}" if game_id is not None else base

    def match_data_ready(self, game: analyzer.NormalizedGame) -> bool:
        return analyzer.is_review_ready(game)

    def input_value(self) -> str:
        value = self.url_var.get().strip()
        if not value:
            raise ValueError("Bitte AoE4World-URL, Profil-ID oder Namen eingeben.")
        return value

    def load_games(self, limit: int = 150) -> tuple[int, str, list[analyzer.NormalizedGame], analyzer.InputTarget]:
        value = self.input_value()
        target = analyzer.parse_input_target(value)
        profile_id, player_name = analyzer.resolve_profile_id(value)
        raw_games = analyzer.fetch_games(profile_id, self.selected_modes(), limit)
        if target.game_id is not None and not any(int(game.get("game_id", 0)) == target.game_id for game in raw_games):
            raw_games = analyzer.fetch_games(profile_id, self.selected_modes(), max(limit, 250))
        games = analyzer.normalize_games(raw_games, profile_id)
        games, _ = analyzer.focus_games(games, target.game_id)
        return profile_id, player_name, games, target

    def run_threaded(self, job) -> None:
        threading.Thread(target=job, daemon=True).start()

    def run_report(self) -> None:
        def job() -> None:
            try:
                self.send_message("status", "Erstelle Auswertung...")
                profile_id, player_name, games, _ = self.load_games()
                if not games:
                    self.send_message("clear", "Keine passenden Spiele gefunden.")
                    return
                if not self.match_data_ready(games[0]):
                    self.send_message(
                        "clear",
                        "Das neueste Spiel ist noch nicht vollstaendig bei AoE4World angekommen. "
                        "Bitte in 1-2 Minuten erneut auswerten.",
                    )
                    self.send_message("status", "Warte auf fertige Matchdaten.")
                    return
                short_text, short_path, detail_path = self.save_short_report(player_name, profile_id, games)
                self.send_message("clear", short_text)
                self.send_message(
                    "history",
                    self.history_payload("Auswertung", player_name, profile_id, short_path, detail_path),
                )
                self.send_message("status", f"Auswertung gespeichert: {short_path} und {detail_path}")
            except Exception as exc:
                self.send_message("status", "Fehler.")
                self.send_message("clear", f"Fehler: {exc}")

        self.run_threaded(job)

    def run_plan_once(self) -> None:
        def job() -> None:
            try:
                self.send_message("status", "Erstelle Spielplan...")
                profile_id, player_name, games, _ = self.load_games(limit=80)
                if not games:
                    self.send_message("clear", "Kein passendes Spiel gefunden.")
                    return
                plan_text = analyzer.build_pregame_plan(player_name, profile_id, games[0])
                out_dir = REPORTS_DIR
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"{self.report_base(player_name, profile_id)}_spielplan.md"
                path.write_text(plan_text, encoding="utf-8")
                self.send_message("clear", plan_text)
                self.send_message("history", self.history_payload("Spielplan", player_name, profile_id, path))
                self.send_message("status", f"Spielplan gespeichert: {path}")
            except Exception as exc:
                self.send_message("status", "Fehler.")
                self.send_message("clear", f"Fehler: {exc}")

        self.run_threaded(job)

    def start_scan(self) -> None:
        if self.scan_thread and self.scan_thread.is_alive():
            messagebox.showinfo("Live-Scan", "Der Scan laeuft bereits.")
            return
        self.scan_stop.clear()
        self.last_plan_game_id = None
        self.last_seen_ongoing_id = None
        self.pending_review_game_ids = []
        self.scan_thread = threading.Thread(target=self.scan_loop, daemon=True)
        self.scan_thread.start()

    def stop_scan(self) -> None:
        self.scan_stop.set()
        self.scan_status.set("Scan wird gestoppt...")

    def queue_pending_review(self, game_id: int | None) -> None:
        if game_id is None or game_id in self.pending_review_game_ids:
            return
        self.pending_review_game_ids.append(game_id)

    def save_short_report(
        self,
        player_name: str,
        profile_id: int,
        games: list[analyzer.NormalizedGame],
        game_id: int | None = None,
    ) -> tuple[str, Path, Path]:
        text = analyzer.build_short_report(player_name, profile_id, games)
        out_dir = REPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        base = self.report_base(player_name, profile_id, game_id)
        short_path = out_dir / f"{base}_kurzbericht.md"
        detail_path = out_dir / f"{base}_details.md"
        short_path.write_text(text, encoding="utf-8")
        detail_path.write_text(analyzer.build_detail_report(player_name, profile_id, games), encoding="utf-8")
        return text, short_path, detail_path

    def process_pending_reviews(
        self,
        player_name: str,
        profile_id: int,
        games: list[analyzer.NormalizedGame],
        quiet: bool = False,
    ) -> bool:
        if not self.pending_review_game_ids:
            return False

        completed: list[int] = []
        waiting = False
        for game_id in list(self.pending_review_game_ids):
            focused, found = analyzer.focus_games(games, game_id)
            if not found:
                waiting = True
                continue
            if not self.match_data_ready(focused[0]):
                waiting = True
                continue

            _, short_path, detail_path = self.save_short_report(player_name, profile_id, focused, game_id)
            self.send_message(
                "history",
                self.history_payload("Live-Kurzauswertung", player_name, profile_id, short_path, detail_path),
            )
            completed.append(game_id)

        for game_id in completed:
            self.pending_review_game_ids.remove(game_id)

        if completed and not quiet:
            self.send_message("status", "Kurzauswertung fuer beendetes Spiel im Verlauf gespeichert.")
        elif waiting and not quiet:
            self.send_message(
                "status",
                "Warte auf vollstaendige Matchdaten fuer beendete Spiele; Live-Scan laeuft weiter...",
            )
        return bool(completed)

    def scan_loop(self) -> None:
        try:
            self.send_message("status", "Live-Scan gestartet.")
            while not self.scan_stop.is_set():
                profile_id, player_name, games, _ = self.load_games(limit=40)
                ongoing = next((game for game in games if game.ongoing), None)

                if ongoing:
                    if self.last_seen_ongoing_id and ongoing.game_id != self.last_seen_ongoing_id:
                        self.queue_pending_review(self.last_seen_ongoing_id)
                    self.last_seen_ongoing_id = ongoing.game_id

                if ongoing and ongoing.game_id != self.last_plan_game_id:
                    self.last_plan_game_id = ongoing.game_id
                    text = analyzer.build_pregame_plan(player_name, profile_id, ongoing)
                    out_dir = REPORTS_DIR
                    out_dir.mkdir(parents=True, exist_ok=True)
                    plan_path = out_dir / f"{self.report_base(player_name, profile_id, ongoing.game_id)}_spielplan.md"
                    plan_path.write_text(text, encoding="utf-8")
                    self.send_message("clear", text)
                    self.send_message("history", self.history_payload("Live-Spielplan", player_name, profile_id, plan_path))
                    self.send_message("status", f"Laufendes Spiel erkannt: {ongoing.game_id}. Strategie erzeugt.")
                elif self.last_seen_ongoing_id and not ongoing:
                    self.queue_pending_review(self.last_seen_ongoing_id)
                    self.last_seen_ongoing_id = None
                else:
                    self.send_message("status", "Kein laufendes Spiel gefunden. Scanne weiter...")

                self.process_pending_reviews(player_name, profile_id, games, quiet=ongoing is not None)

                for _ in range(POLL_SECONDS):
                    if self.scan_stop.is_set():
                        break
                    time.sleep(1)
            self.send_message("status", "Scan gestoppt.")
        except Exception as exc:
            self.send_message("status", "Scan-Fehler.")
            self.send_message("text", f"Fehler im Live-Scan: {exc}")


def main() -> None:
    root = tk.Tk()
    app = CommandCenterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
