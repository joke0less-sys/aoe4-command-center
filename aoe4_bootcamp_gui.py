#!/usr/bin/env python3
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import aoe4_team_analyzer as analyzer


POLL_SECONDS = 45


class CommandCenterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AoE4 Command Center")
        self.root.geometry("980x760")
        self.root.minsize(850, 620)
        self.message_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.scan_stop = threading.Event()
        self.scan_thread: threading.Thread | None = None
        self.last_plan_game_id: int | None = None
        self.last_seen_ongoing_id: int | None = None

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

        output_frame = ttk.LabelFrame(outer, text="Kurzfazit / Spielplan", padding=8)
        output_frame.pack(fill=tk.BOTH, expand=True)
        self.output = tk.Text(output_frame, wrap=tk.WORD, height=28)
        self.output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(output_frame, command=self.output.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.output.configure(yscrollcommand=scroll.set)

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

    def send_message(self, kind: str, text: str) -> None:
        self.message_queue.put((kind, text))

    def drain_messages(self) -> None:
        while True:
            try:
                kind, text = self.message_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.scan_status.set(text)
            elif kind == "clear":
                self.append_output(text, clear=True)
            else:
                self.append_output(text)
        self.root.after(200, self.drain_messages)

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
                out_dir = Path("reports")
                out_dir.mkdir(exist_ok=True)
                base = f"{analyzer.safe_slug(player_name)}_{profile_id}"
                short_path = out_dir / f"{base}_kurzbericht.md"
                detail_path = out_dir / f"{base}_details.md"
                short_text = analyzer.build_short_report(player_name, profile_id, games)
                short_path.write_text(short_text, encoding="utf-8")
                detail_path.write_text(analyzer.build_detail_report(player_name, profile_id, games), encoding="utf-8")
                self.send_message("clear", short_text)
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
                out_dir = Path("reports")
                out_dir.mkdir(exist_ok=True)
                path = out_dir / f"{analyzer.safe_slug(player_name)}_{profile_id}_spielplan.md"
                path.write_text(plan_text, encoding="utf-8")
                self.send_message("clear", plan_text)
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
        self.scan_thread = threading.Thread(target=self.scan_loop, daemon=True)
        self.scan_thread.start()

    def stop_scan(self) -> None:
        self.scan_stop.set()
        self.scan_status.set("Scan wird gestoppt...")

    def scan_loop(self) -> None:
        try:
            self.send_message("status", "Live-Scan gestartet.")
            while not self.scan_stop.is_set():
                profile_id, player_name, games, _ = self.load_games(limit=40)
                ongoing = next((game for game in games if game.ongoing), None)

                if ongoing and ongoing.game_id != self.last_plan_game_id:
                    self.last_plan_game_id = ongoing.game_id
                    self.last_seen_ongoing_id = ongoing.game_id
                    text = analyzer.build_pregame_plan(player_name, profile_id, ongoing)
                    self.send_message("clear", text)
                    self.send_message("status", f"Laufendes Spiel erkannt: {ongoing.game_id}. Strategie erzeugt.")
                elif self.last_seen_ongoing_id and not ongoing:
                    focused, found = analyzer.focus_games(games, self.last_seen_ongoing_id)
                    if found:
                        text = analyzer.build_short_report(player_name, profile_id, focused)
                        self.send_message("text", "Spiel beendet. Kurzauswertung:\n\n" + text)
                        self.send_message("status", "Spiel beendet. Kurzauswertung erstellt.")
                        self.last_seen_ongoing_id = None
                    else:
                        self.send_message("status", "Spiel nicht mehr laufend, warte auf fertige Matchdaten...")
                else:
                    self.send_message("status", "Kein laufendes Spiel gefunden. Scanne weiter...")

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
