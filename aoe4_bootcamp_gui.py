#!/usr/bin/env python3
from __future__ import annotations

import queue
import json
import os
import socket
import threading
import time
import urllib.parse
import tkinter as tk
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import messagebox, ttk

import aoe4_team_analyzer as analyzer


POLL_SECONDS = 25
APP_DIR = Path(__file__).resolve().parent
REPORTS_DIR = APP_DIR / "reports"
HISTORY_PATH = REPORTS_DIR / "verlauf.json"
HISTORY_LIMIT = 40
TABLET_PORT = 8765


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
        self.current_cockpit_context: tuple[str, int, analyzer.NormalizedGame] | None = None
        self.current_cockpit_stats: dict[str, object] | None = None
        self.scout_states: dict[int, str] = {}
        self.strategy_window: tk.Toplevel | None = None
        self.strategy_text: tk.Text | None = None
        self.touch_window: tk.Toplevel | None = None
        self.touch_frame: ttk.Frame | None = None
        self.tablet_server: ThreadingHTTPServer | None = None
        self.tablet_thread: threading.Thread | None = None
        self.current_cockpit_data: dict[str, object] | None = None
        self.latest_output_text = ""

        self.url_var = tk.StringVar()
        self.match_type = tk.StringVar(value="ranked")
        self.scan_status = tk.StringVar(value="Bereit.")
        self.mode_vars: dict[str, tk.BooleanVar] = {}

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(200, self.drain_messages)

    def on_close(self) -> None:
        self.scan_stop.set()
        if self.tablet_server:
            self.tablet_server.shutdown()
            self.tablet_server.server_close()
        self.root.destroy()

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
        analysis_actions = ttk.LabelFrame(actions, text="Analyse", padding=6)
        analysis_actions.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(analysis_actions, text="Vergangene Spiele auswerten", command=self.run_report).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(analysis_actions, text="Spielplan erzeugen", command=self.run_plan_once).pack(side=tk.LEFT)

        live_actions = ttk.LabelFrame(actions, text="Live", padding=6)
        live_actions.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(live_actions, text="Live-Scan starten", command=self.start_scan).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(live_actions, text="Scan stoppen", command=self.stop_scan).pack(side=tk.LEFT)

        window_actions = ttk.LabelFrame(actions, text="Fenster/Ansicht", padding=6)
        window_actions.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(window_actions, text="Strategie-Fenster", command=self.open_strategy_window).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(window_actions, text="Touch-/Cockpit-Fenster", command=self.open_touch_window).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(window_actions, text="Tablet-Browser", command=self.start_tablet_server).pack(side=tk.LEFT)

        ttk.Label(outer, textvariable=self.scan_status).pack(anchor=tk.W, pady=(0, 8))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)

        output_frame = ttk.Frame(notebook, padding=8)
        notebook.add(output_frame, text="Kurzfazit / Spielplan")
        self.cockpit_frame = ttk.Frame(output_frame)
        self.cockpit_frame.pack(fill=tk.X, pady=(0, 8))
        self.output = tk.Text(output_frame, wrap=tk.WORD, height=28)
        self.output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(output_frame, command=self.output.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.output.configure(yscrollcommand=scroll.set)

        self.build_history_tab(notebook)
        self.build_glossary_tab(notebook)
        self.load_history()
        if not self.history_entries:
            self.load_history_from_reports()
        self.refresh_history_list()

    def build_glossary_tab(self, notebook: ttk.Notebook) -> None:
        glossary_frame = ttk.Frame(notebook, padding=8)
        notebook.add(glossary_frame, text="Glossar")

        glossary_text = tk.Text(glossary_frame, wrap=tk.WORD, height=24)
        glossary_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(glossary_frame, command=glossary_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        glossary_text.configure(yscrollcommand=scroll.set)

        for term, description in analyzer.GLOSSARY.items():
            glossary_text.insert(tk.END, f"{term}\n", "term")
            glossary_text.insert(tk.END, f"{description}\n\n")
        glossary_text.tag_configure("term", font=("Segoe UI", 10, "bold"))
        glossary_text.configure(state=tk.DISABLED)

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
            self.latest_output_text = text.rstrip() + "\n\n"
        else:
            self.latest_output_text += text.rstrip() + "\n\n"
        self.output.insert(tk.END, text.rstrip() + "\n\n")
        self.output.see(tk.END)
        self.refresh_strategy_window()

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
            elif kind == "cockpit":
                self.show_cockpit(payload)
            elif kind == "scout":
                self.apply_scout_payload(payload)
            elif kind == "refresh_cockpit":
                self.update_cockpit_from_scout()
            else:
                self.append_output(str(payload))
        self.root.after(200, self.drain_messages)

    def clear_cockpit(self) -> None:
        for child in self.cockpit_frame.winfo_children():
            child.destroy()

    def show_cockpit(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        context = payload.get("context")
        data = payload.get("data")
        if isinstance(context, tuple) and len(context) == 3:
            player_name, profile_id, game = context
            self.current_cockpit_context = (str(player_name), int(profile_id), game)
            self.scout_states = {}
        if isinstance(data, dict):
            self.current_cockpit_stats = data.get("matchup_stats") if isinstance(data.get("matchup_stats"), dict) else None
            self.render_cockpit(data)

    def update_cockpit_from_scout(self) -> None:
        if not self.current_cockpit_context:
            return
        player_name, profile_id, game = self.current_cockpit_context
        data = analyzer.build_live_cockpit_data(player_name, profile_id, game, self.scout_states)
        if self.current_cockpit_stats is not None:
            data["matchup_stats"] = self.current_cockpit_stats
        self.render_cockpit(data)

    def set_enemy_scout(self, profile_id: int, state: str) -> None:
        self.toggle_scout_state(profile_id, state)
        self.update_cockpit_from_scout()

    def toggle_scout_state(self, profile_id: int, state: str) -> None:
        if self.scout_states.get(profile_id) == state:
            self.scout_states.pop(profile_id, None)
        else:
            self.scout_states[profile_id] = state

    def apply_scout_payload(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        try:
            profile_id = int(str(payload.get("profile_id", "0")))
        except ValueError:
            return
        state = str(payload.get("state", ""))
        if not state:
            return
        self.set_enemy_scout(profile_id, state)

    def matchup_summary(self, stats: object, detail: bool = False) -> str:
        if not isinstance(stats, dict):
            return ""
        if stats.get("available") and stats.get("win_rate") is not None:
            if detail:
                return f"AoE4World Patch {stats.get('patch', '?')}, Durchschnitt aus {stats.get('games', '?')} Vergleichsdaten."
            return f"Team-Matchup: {float(stats.get('win_rate')):.1f}% Winrate"
        return str(stats.get("summary", ""))

    def open_strategy_window(self) -> None:
        if self.strategy_window and self.strategy_window.winfo_exists():
            self.strategy_window.lift()
            return
        self.strategy_window = tk.Toplevel(self.root)
        self.strategy_window.title("Strategie")
        self.strategy_window.geometry("760x700")
        self.strategy_text = tk.Text(self.strategy_window, wrap=tk.WORD, font=("Segoe UI", 12))
        self.strategy_text.pack(fill=tk.BOTH, expand=True)
        self.strategy_window.protocol("WM_DELETE_WINDOW", self.close_strategy_window)
        self.refresh_strategy_window()

    def close_strategy_window(self) -> None:
        if self.strategy_window:
            self.strategy_window.destroy()
        self.strategy_window = None
        self.strategy_text = None

    def refresh_strategy_window(self) -> None:
        if not self.strategy_text or not self.strategy_window or not self.strategy_window.winfo_exists():
            return
        self.strategy_text.configure(state=tk.NORMAL)
        self.strategy_text.delete("1.0", tk.END)
        self.strategy_text.insert(tk.END, self.latest_output_text)
        self.strategy_text.configure(state=tk.DISABLED)

    def open_touch_window(self) -> None:
        if self.touch_window and self.touch_window.winfo_exists():
            self.touch_window.lift()
            return
        self.touch_window = tk.Toplevel(self.root)
        self.touch_window.title("Touch-Cockpit")
        self.touch_window.geometry("900x720")
        self.touch_frame = ttk.Frame(self.touch_window, padding=10)
        self.touch_frame.pack(fill=tk.BOTH, expand=True)
        self.touch_window.protocol("WM_DELETE_WINDOW", self.close_touch_window)
        self.update_cockpit_from_scout()

    def close_touch_window(self) -> None:
        if self.touch_window:
            self.touch_window.destroy()
        self.touch_window = None
        self.touch_frame = None

    def local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def tablet_state(self) -> dict[str, object]:
        return {
            "cockpit": self.current_cockpit_data or {},
            "scout_states": {str(key): value for key, value in self.scout_states.items()},
        }

    def tablet_html(self) -> str:
        return """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AoE4 Touch-Cockpit</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f5f5;color:#111}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:12px;z-index:2}
h1{font-size:20px;margin:0 0 4px}
.meta{font-size:14px;color:#444}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;padding:10px}
.card,.panel{background:#fff;border:1px solid #ccc;border-radius:6px;padding:10px}
.name{font-weight:700;font-size:17px}.civ{color:#333;margin-bottom:6px}.expected{font-weight:700;margin:6px 0}
.reaction{min-height:42px;font-size:14px}
.buttons{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}
button{font-size:16px;padding:12px 6px;border:1px solid #999;border-radius:6px;background:#fafafa}
button.active{background:#1f6feb;color:#fff;border-color:#1f6feb}
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;padding:0 10px 10px}
ul{padding-left:18px;margin:6px 0}li{margin:5px 0}
</style>
</head>
<body>
<header><h1 id="title">AoE4 Touch-Cockpit</h1><div class="meta" id="meta">Warte auf Spielplan...</div></header>
<main><section class="grid" id="enemies"></section><section class="panels" id="panels"></section></main>
<script>
const buttons=[['2tc','2 TC'],['fc','Fast Castle'],['trade','Trade'],['army','Army'],['feudal','Feudal'],['castle','Castle'],['imperial','Imperial'],['unclear','Unklar']];
async function setScout(pid,state){await fetch('/set?pid='+encodeURIComponent(pid)+'&state='+encodeURIComponent(state)); await load();}
function list(lines){return '<ul>'+((lines||[]).map(x=>'<li>'+escapeHtml(x)+'</li>').join(''))+'</ul>'}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
async function load(){
 const res=await fetch('/state',{cache:'no-store'}); const state=await res.json(); const data=state.cockpit||{}; const scouts=state.scout_states||{};
 document.getElementById('title').textContent=(data.kind||'?')+' | '+(data.map||'?')+' | Game '+(data.game_id||'?');
 let stats=data.matchup_stats||{}; document.getElementById('meta').textContent=stats.available&&stats.win_rate!=null?'Team-Matchup: '+Number(stats.win_rate).toFixed(1)+'% Winrate':'';
 const enemies=document.getElementById('enemies'); enemies.innerHTML='';
 (data.enemies||[]).forEach(e=>{
   const pid=e.profile_id; const active=scouts[String(pid)]||'';
   const card=document.createElement('div'); card.className='card';
   card.innerHTML='<div class="name">'+escapeHtml(e.name||'?')+'</div><div class="civ">'+escapeHtml(e.civ||'?')+'</div><div class="expected">'+escapeHtml(e.expected||'')+'</div><div class="reaction">'+escapeHtml(e.reaction||'')+'</div><div class="buttons"></div>';
   const wrap=card.querySelector('.buttons');
   buttons.forEach(([key,label])=>{const b=document.createElement('button'); b.textContent=label; if(active===key)b.className='active'; b.onclick=()=>setScout(pid,key); wrap.appendChild(b);});
   enemies.appendChild(card);
 });
 const steps=data.steps||{}; document.getElementById('panels').innerHTML='<div class="panel"><b>Reaktionsplan</b>'+list(steps.after_scout)+'</div><div class="panel"><b>Push-Timing</b>'+list(steps.push)+'</div><div class="panel"><b>Scout-Check</b>'+list(steps.scout_now)+'</div>';
}
load(); setInterval(load,2000);
</script>
</body>
</html>"""

    def start_tablet_server(self) -> None:
        if self.tablet_server:
            url = f"http://{self.local_ip()}:{TABLET_PORT}/"
            self.scan_status.set(f"Tablet-Browser: {url}")
            return

        app = self

        class TabletHandler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def send_text(self, text: str, content_type: str) -> None:
                raw = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/":
                    self.send_text(app.tablet_html(), "text/html; charset=utf-8")
                    return
                if parsed.path == "/state":
                    self.send_text(json.dumps(app.tablet_state(), ensure_ascii=False), "application/json; charset=utf-8")
                    return
                if parsed.path == "/set":
                    params = urllib.parse.parse_qs(parsed.query)
                    pid = params.get("pid", [""])[0]
                    state = params.get("state", [""])[0]
                    try:
                        app.toggle_scout_state(int(pid), state)
                        app.send_message("refresh_cockpit", "")
                    except ValueError:
                        pass
                    self.send_text('{"ok":true}', "application/json; charset=utf-8")
                    return
                self.send_error(404)

        try:
            self.tablet_server = ThreadingHTTPServer(("0.0.0.0", TABLET_PORT), TabletHandler)
        except OSError as exc:
            messagebox.showerror("Tablet-Browser", f"Tablet-Server konnte nicht starten: {exc}")
            return

        self.tablet_thread = threading.Thread(target=self.tablet_server.serve_forever, daemon=True)
        self.tablet_thread.start()
        url = f"http://{self.local_ip()}:{TABLET_PORT}/"
        self.scan_status.set(f"Tablet-Browser: {url}")
        messagebox.showinfo("Tablet-Browser", f"Oeffne diese Adresse am Tablet:\n\n{url}")

    def render_cockpit(self, data: dict[str, object]) -> None:
        self.current_cockpit_data = data
        self.clear_cockpit()

        header = ttk.Frame(self.cockpit_frame)
        header.pack(fill=tk.X, pady=(0, 6))
        title = f"{data.get('kind', '?')} auf {data.get('map', '?')}"
        ttk.Label(header, text=title, font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        stats = data.get("matchup_stats")
        summary = self.matchup_summary(stats)
        if summary:
            ttk.Label(header, text=summary).pack(side=tk.RIGHT)

        top = ttk.Frame(self.cockpit_frame)
        top.pack(fill=tk.X)
        team_box = ttk.LabelFrame(top, text="Team-Aufgaben", padding=6)
        team_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        team = data.get("team", [])
        if isinstance(team, list):
            for idx, raw_card in enumerate(team):
                if not isinstance(raw_card, dict):
                    continue
                card = ttk.LabelFrame(team_box, text=str(raw_card.get("name", "?")), padding=6)
                card.grid(row=0, column=idx, sticky="nsew", padx=3)
                team_box.columnconfigure(idx, weight=1, uniform="team")
                ttk.Label(card, text=str(raw_card.get("focus", "?")), font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
                ttk.Label(card, text=str(raw_card.get("civ", ""))).pack(anchor=tk.W)
                ttk.Label(card, text=str(raw_card.get("build", "")), wraplength=210).pack(anchor=tk.W, pady=(3, 0))
                ttk.Label(card, text=str(raw_card.get("timing", "")), wraplength=210).pack(anchor=tk.W, pady=(3, 0))

        steps = data.get("steps", {})
        step_row = ttk.Frame(self.cockpit_frame)
        step_row.pack(fill=tk.X, pady=(8, 0))
        if isinstance(steps, dict):
            for idx, (key, title_text) in enumerate(
                [("scout_now", "1 Scout jetzt"), ("after_scout", "2 Reaktion"), ("push", "3 Push-Timing")]
            ):
                box = ttk.LabelFrame(step_row, text=title_text, padding=6)
                box.grid(row=0, column=idx, sticky="nsew", padx=3)
                step_row.columnconfigure(idx, weight=1, uniform="steps")
                lines = steps.get(key, [])
                if isinstance(lines, list):
                    for line in lines[:4]:
                        ttk.Label(box, text=f"- {line}", wraplength=320).pack(anchor=tk.W)

        self.render_touch_cockpit(data)

    def render_touch_cockpit(self, data: dict[str, object]) -> None:
        if not self.touch_frame or not self.touch_window or not self.touch_window.winfo_exists():
            return
        for child in self.touch_frame.winfo_children():
            child.destroy()

        header = ttk.Frame(self.touch_frame)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            header,
            text=f"{data.get('kind', '?')} | {data.get('map', '?')} | Game {data.get('game_id', '?')}",
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)
        detail = self.matchup_summary(data.get("matchup_stats"), detail=True)
        if detail:
            ttk.Label(header, text=detail).pack(side=tk.RIGHT)

        enemy_grid = ttk.Frame(self.touch_frame)
        enemy_grid.pack(fill=tk.X)
        enemies = data.get("enemies", [])
        button_defs = [
            ("2tc", "2 TC"),
            ("fc", "Fast Castle"),
            ("trade", "Trade"),
            ("army", "Army"),
            ("feudal", "Feudal"),
            ("castle", "Castle"),
            ("imperial", "Imperial"),
            ("unclear", "Unklar"),
        ]
        if isinstance(enemies, list):
            for idx, raw_enemy in enumerate(enemies):
                if not isinstance(raw_enemy, dict):
                    continue
                pid = int(str(raw_enemy.get("profile_id", "0")) or 0)
                card = ttk.LabelFrame(enemy_grid, text=f"{raw_enemy.get('name', '?')} - {raw_enemy.get('civ', '?')}", padding=8)
                card.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=4, pady=4)
                enemy_grid.columnconfigure(idx % 2, weight=1, uniform="enemy")
                ttk.Label(card, text=str(raw_enemy.get("expected", "")), font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
                ttk.Label(card, text=str(raw_enemy.get("reaction", "")), wraplength=380).pack(anchor=tk.W, pady=(2, 6))
                buttons = ttk.Frame(card)
                buttons.pack(fill=tk.X)
                for b_idx, (state, label) in enumerate(button_defs):
                    text = f"[{label}]" if self.scout_states.get(pid) == state else label
                    ttk.Button(buttons, text=text, command=lambda p=pid, s=state: self.set_enemy_scout(p, s)).grid(
                        row=b_idx // 4, column=b_idx % 4, sticky="ew", padx=2, pady=2
                    )
                    buttons.columnconfigure(b_idx % 4, weight=1)

        steps = data.get("steps", {})
        if isinstance(steps, dict):
            lower = ttk.Frame(self.touch_frame)
            lower.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            for idx, (key, title_text) in enumerate(
                [("after_scout", "Reaktionsplan"), ("push", "Push-Timing"), ("scout_now", "Scout-Check")]
            ):
                box = ttk.LabelFrame(lower, text=title_text, padding=8)
                box.grid(row=0, column=idx, sticky="nsew", padx=4)
                lower.columnconfigure(idx, weight=1, uniform="lower")
                lines = steps.get(key, [])
                if isinstance(lines, list):
                    for line in lines[:4]:
                        ttk.Label(box, text=f"- {line}", wraplength=260).pack(anchor=tk.W)

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
                game = games[0]
                plan_text = analyzer.build_pregame_plan(player_name, profile_id, game)
                cockpit = analyzer.build_live_cockpit_data(player_name, profile_id, game, include_online_stats=True)
                out_dir = REPORTS_DIR
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"{self.report_base(player_name, profile_id)}_spielplan.md"
                path.write_text(plan_text, encoding="utf-8")
                self.send_message("clear", plan_text)
                self.send_message("cockpit", {"context": (player_name, profile_id, game), "data": cockpit})
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
                    cockpit = analyzer.build_live_cockpit_data(player_name, profile_id, ongoing, include_online_stats=True)
                    out_dir = REPORTS_DIR
                    out_dir.mkdir(parents=True, exist_ok=True)
                    plan_path = out_dir / f"{self.report_base(player_name, profile_id, ongoing.game_id)}_spielplan.md"
                    plan_path.write_text(text, encoding="utf-8")
                    self.send_message("clear", text)
                    self.send_message("cockpit", {"context": (player_name, profile_id, ongoing), "data": cockpit})
                    self.send_message("history", self.history_payload("Live-Spielplan", player_name, profile_id, plan_path))
                    size = f"{ongoing.team_size}v{ongoing.team_size}"
                    self.send_message(
                        "status",
                        f"AoE4World: {size} erkannt. Strategie erzeugt.",
                    )
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
