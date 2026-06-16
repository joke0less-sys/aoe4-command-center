#!/usr/bin/env python3
"""
AoE4 3v3/4v4 team game analyzer using the public AoE4World API.

The tool focuses on patterns that are visible from match history:
maps, civilizations, match length, rating/MMR movement, team size, teammates,
opponent civilizations, and recent form.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://aoe4world.com/api/v0"
USER_AGENT = "AoE4CommandCenter/0.1 contact: local-user"
TEAM_MODES = (
    "rm_1v1",
    "rm_2v2",
    "rm_3v3",
    "rm_4v4",
    "qm_1v1",
    "qm_2v2",
    "qm_3v3",
    "qm_4v4",
)

MAP_GUIDES = {
    "lipany": ("grosse Karte", "Mitte/Relikte kontrollieren, gegnerische Boomer nicht frei skalieren lassen."),
    "hill and dale": ("grosse Boom-Karte", "Mitte halten, eigene Eco absichern, nicht in unnoetige All-Ins laufen."),
    "canal": ("grosse Karte", "zwei Spieler Druck, zwei Spieler Boom; Trade-Routen frueh scouten."),
    "gorge": ("kleine Kampfkarte", "Feudal-Armee und Team-Timing zwischen Minute 10-15 priorisieren."),
    "mountain pass": ("kleine Kampfkarte", "frueh Armee sammeln, Engstellen sichern, keinen isolierten Fight nehmen."),
    "cliffside": ("kleine Kampfkarte", "Tempo hochhalten und fruehe Kaempfe gemeinsam nehmen."),
    "dry arabia": ("offene Karte", "Flanken scouten, Raids vorbereiten und Boomer ueber Gold/Aussenressourcen stoeren."),
    "flankwoods": ("flankige Karte", "Vision und Wall-Spots frueh klaeren, sonst werden Teamkaempfe unkoordiniert."),
}

CIV_GUIDES = {
    "English": ("Map-Control-Spieler", "Longbows ab ca. Minute 7-8, Mitte/Relikte sichern, auf grossen Karten 2 TC pruefen."),
    "House Of Lancaster": ("Map-Control-Spieler", "fruehe Praesenz halten, Mitte sichern und Teamkaempfe vorbereiten."),
    "Japanese": ("Scaling-Carry", "Fast Castle, Relikte und Imperial-Timing priorisieren."),
    "Sengoku Daimyo": ("Scaling-Carry", "Castle/Imperial-Timing vorbereiten und nicht zu frueh isoliert kaempfen."),
    "Abbasid Dynasty": ("Eco-/Support-Spieler", "2 TC/Eco-Vorteil aufbauen, spaeter Trade oder grosse Armee vorbereiten."),
    "Malians": ("Eco-/Trade-Spieler", "Wirtschaft sichern, Goldquellen schuetzen und spaeter in Armee/Trade umwandeln."),
    "Ottomans": ("Support-/Produktionsspieler", "Militaerschulen frueh nutzen und konstant Druck unterstuetzen."),
    "French": ("Aggressionsspieler", "fruehe Ritter, Gold deny, Villager-Raids und Map-Control."),
    "Ayyubids": ("flexibler Tempo-Spieler", "schnelle Map-Praesenz, Gold/Relikte angreifen, Castle-Timing nutzen."),
    "Knights Templar": ("Aggressionsspieler", "fruehe Power in Druck uebersetzen und Boomer stoeren."),
    "Delhi Sultanate": ("Map-Control-/Sacred-Sites-Spieler", "Sacred Sites, Relikte und fruehe Praesenz erzwingen."),
    "Holy Roman Empire": ("Relikt-/Castle-Spieler", "Relikte sichern und den Castle-Powerspike vorbereiten."),
    "Rus": ("Map-Control-/Eco-Spieler", "Bounty, Holz/Eco und fruehe Map-Kontrolle sauber verbinden."),
}

BOOM_CIVS = {
    "Abbasid Dynasty",
    "Chinese",
    "Zhu Xis Legacy",
    "Jin Dynasty",
    "Holy Roman Empire",
    "Japanese",
    "Sengoku Daimyo",
    "Malians",
}

AGGRESSION_CIVS = {
    "French",
    "Ayyubids",
    "Knights Templar",
    "Mongols",
    "Rus",
    "Delhi Sultanate",
    "Order Of The Dragon",
}

KNOWN_PLAYER_ROLES = {
    "joko": "Map-Control",
    "burbleb": "Aggression/Raids",
    "taronimo": "Scaling-Carry",
    "teledubee": "Eco/Support",
    "dubee": "Eco/Support",
}

SCOUT_STATES = {
    "2tc": "2 TC/Eco",
    "fc": "Fast Castle",
    "army": "Fruehe Army",
    "trade": "Trade/Boom",
    "feudal": "Feudal",
    "castle": "Castle",
    "imperial": "Imperial",
    "unclear": "Unklar",
}

GLOSSARY = {
    "Tempo": (
        "Spielweise, bei der du die Initiative haeltst: frueh Druck machen, Timing-Fenster nutzen "
        "und den Gegner zu Reaktionen zwingen, statt passiv nur zu boomen."
    ),
    "Boom": "Starker Wirtschaftsaufbau, oft mit 2 TC, Trade oder Eco-Upgrades; kurzfristig schwach, spaeter stark.",
    "2 TC": "Zweites Dorfzentrum. Mehr Dorfbewohner und Eco, aber anfangs weniger Armee und anfaelliger gegen Druck.",
    "Fast Castle": "Schnell in Age III gehen, um Relikte, starke Techs oder Castle-Units frueh zu nutzen.",
    "Feudal-Army": "Armee in Age II. Ziel: Druck, Defense oder Map-Control bevor Castle-Timings kommen.",
    "Map-Control": "Wichtige Orte halten: Mitte, Relikte, Sacred Sites, Gold, Trade-Route oder Engstellen.",
    "Timing": "Kurzes Fenster, in dem dein Team staerker ist, z. B. neue Age, neue Tech oder erste grosse Army.",
    "Power-Spike": "Moment, in dem eine Civ/Army ploetzlich deutlich staerker wird.",
    "All-in": "Sehr harter Angriff mit wenig Eco-Backup. Wenn er scheitert, faellt man oft stark zurueck.",
    "Trade": "Haendler-Wirtschaft. Sehr stark spaeter, aber Route muss frueh gescoutet und geschuetzt werden.",
    "Relikte": "Goldquelle ab Castle Age. Besonders wichtig fuer HRE/Japanese/Relikt-Civs.",
    "Sacred Sites": "Heilige Staetten. Geben Gold und koennen mit Delhi/Map-Control viel Druck erzeugen.",
    "Scout": "Fruehe Information sammeln: Gold, Produktion, 2 TC, Fast Castle, Army, Trade und offene Flanken.",
    "Push": "Gemeinsamer Angriff auf ein Ziel, idealerweise mit vorherigem Sammeln statt einzelnem Reinlaufen.",
    "Tech": "Technologien oder Age-Up priorisieren statt sofort mehr Armee zu bauen.",
    "Eco": "Wirtschaft: Dorfbewohner, Nahrung, Holz, Gold, Stein, Upgrades, 2 TC, Trade.",
    "Support": "Teamrolle, die Druckspieler deckt, Vision gibt, Defense stellt oder spaeter Army-Masse liefert.",
}

CIV_PLAYBOOK = {
    "English": {
        "focus": "Feudal-Armee",
        "build": "Ratshalle/Longbows, 1 TC Druck; 2 TC nur wenn Gegner passiv.",
        "scout": "Gold, Range, Barracks, zweites TC.",
        "react": "Gegen Ritter Speere mischen; gegen Boom Longbow-Druck auf Gold.",
        "timing": "Minute 7-10 erster Longbow/Speer-Druck.",
    },
    "House Of Lancaster": {
        "focus": "Feudal-Armee",
        "build": "Fruehe Praesenz, 1 TC Druck; 2 TC nur bei sicherer Karte.",
        "scout": "Gold, Produktion, Wall-Spots.",
        "react": "Mitte halten und Druckspieler absichern.",
        "timing": "Minute 8-12 Longbow/Infanterie zum Teamziel.",
    },
    "French": {
        "focus": "Fruehe Army",
        "build": "1 TC Royal Knights; kein greediger 2 TC Start.",
        "scout": "Gegner-Gold, Speere, zweite Produktion.",
        "react": "Gold/Beeren raiden, Speere umgehen, Boomer stoeren.",
        "timing": "Minute 5-9 Ritterdruck, danach Teamziel festnageln.",
    },
    "Mongols": {
        "focus": "Fruehe Army",
        "build": "Tower/Feudal-Druck oder schnelle Kav; kein klassisches 2 TC.",
        "scout": "Ovoo-Position, Gegner-Gold, offene Holzlinien.",
        "react": "Tempo nutzen, aber nicht alleine all-in.",
        "timing": "Minute 5-10 Druck/Vision, Minute 10+ Teamfight vorbereiten.",
    },
    "Ottomans": {
        "focus": "Produktion/Support",
        "build": "Militaerschulen frueh setzen, 1 TC stabile Army; 2 TC nur wenn Team dich deckt.",
        "scout": "Raidgefahr, gegnerische Stables, Boomer-Gold.",
        "react": "Gratis-Produktion konstant sammeln, Mehter/Army zum Teamfight.",
        "timing": "Minute 8-12 Masse sammeln, nicht einzeln traden.",
    },
    "Abbasid Dynasty": {
        "focus": "2 TC/Eco",
        "build": "Eco Wing -> 2 TC, wenn Scout keine harte Feudal-Army sieht.",
        "scout": "Fruehe Stables/Ranges, Tower-Rush, freie Expansion.",
        "react": "Bei Druck 1 TC bleiben, Army zuerst; bei Ruhe 2 TC skalieren.",
        "timing": "Minute 7-9 2 TC oder Defense-Call, Minute 14+ Army nachziehen.",
    },
    "Malians": {
        "focus": "Eco/Trade",
        "build": "Pit Mines sichern, defensiv skalieren; Trade nur mit Teamdeckung.",
        "scout": "Raidgefahr auf Gold/Pit Mines, gegnerische Kav.",
        "react": "Walls/Outposts frueh, danach in Army oder Trade umwandeln.",
        "timing": "Minute 8 Defense-Check, Minute 14+ Power-Spike nutzen.",
    },
    "Japanese": {
        "focus": "Fast Castle",
        "build": "Fast Castle/Relikte, 1 TC; Feudal-Army nur gegen Druck.",
        "scout": "Kommt Feudal-All-in? Stables/Ranges und gegnerisches Gold.",
        "react": "Bei wenig Druck Castle; bei Druck Speere/Defense und Teamhilfe.",
        "timing": "Minute 8-10 Castle vorbereiten, Minute 12-15 Relikte/Push.",
    },
    "Sengoku Daimyo": {
        "focus": "Fast Castle",
        "build": "Castle/Imperial-Timing vorbereiten; nicht in Feudal verheizen.",
        "scout": "Feudal-Druck, offene Goldwege, Relikte.",
        "react": "Nur verteidigen bis Tech-Timing, dann gesammelt kaempfen.",
        "timing": "Minute 12-16 Castle-Power mit Team sichern.",
    },
    "Holy Roman Empire": {
        "focus": "Fast Castle",
        "build": "Aachen-Eco -> Fast Castle/Relikte; 2 TC selten vor Sicherheit.",
        "scout": "Wird dein Gold getowert/geraided? Relikte und Gegnerdruck.",
        "react": "Bei Druck defensiv sammeln; bei Ruhe Castle und Relikte.",
        "timing": "Minute 8-10 Castle, Minute 11-14 Relikte sichern.",
    },
    "Delhi Sultanate": {
        "focus": "Map-Control",
        "build": "Sacred Sites + Feudal-Army, 1 TC Tempo.",
        "scout": "Sacred-Site Wege, gegnerische Army, Wall-Spots.",
        "react": "Sites nehmen, Gegner zum Reagieren zwingen, Teamfight vorbereiten.",
        "timing": "Minute 6-9 Sites/Army, Minute 10-14 Teamdruck.",
    },
    "Ayyubids": {
        "focus": "Tempo/Tech",
        "build": "Flex: schnelle Map-Praesenz oder Castle-Timing nach Scout.",
        "scout": "Kannst du Gold/Relikte bestrafen oder musst du verteidigen?",
        "react": "Schwachen Gegner aktiv stoeren, sonst Castle-Power vorbereiten.",
        "timing": "Minute 8-12 Druck oder Tech-Call klar ansagen.",
    },
    "Knights Templar": {
        "focus": "Fruehe Army",
        "build": "Fruehe Power in Druck uebersetzen, 1 TC Tempo.",
        "scout": "Gold, Speere, isolierte Eco.",
        "react": "Boom verzoegern, aber Team nicht ohne dich fighten lassen.",
        "timing": "Minute 7-12 Druck auf erstes Ziel.",
    },
    "Rus": {
        "focus": "Map-Control/Eco",
        "build": "Bounty + Holz/Eco, dann Feudal-Kav oder Castle nach Scout.",
        "scout": "Hunt/Bounty, Gegner-Gold, Raidgefahr.",
        "react": "Map-Kontrolle nutzen, Boomer stoeren oder Castle sichern.",
        "timing": "Minute 6-10 Map-Control, Minute 12+ gemeinsamer Druck.",
    },
    "Golden Horde": {
        "focus": "Fruehe Army",
        "build": "Tempo und mobile Army; Druck statt greediger Eco.",
        "scout": "Offene Eco, gegnerische Speere, Goldwege.",
        "react": "Raids setzen und Teamfight nicht verpassen.",
        "timing": "Minute 6-11 Druck, danach Teamziel halten.",
    },
    "Tughlaq Dynasty": {
        "focus": "Flex/Support",
        "build": "Scout entscheidet: Defense gegen Druck, sonst Tech/Eco absichern.",
        "scout": "Feudal-Army, gegnerisches Gold, freie Expansion.",
        "react": "Teamluecke fuellen: Schutz fuer Boomer oder zweiter Druckspieler.",
        "timing": "Minute 8 Rollenentscheidung, Minute 12 Teamfight vorbereiten.",
    },
    "Macedonian Dynasty": {
        "focus": "Tech/Timing",
        "build": "Saubere Eco in Timing-Army; 2 TC nur bei sicherem Scout.",
        "scout": "Raidgefahr, gegnerisches Tech, offene Ressourcen.",
        "react": "Nicht isoliert boomen; Power-Spike mit Team callen.",
        "timing": "Minute 10-15 erster koordinierter Spike.",
    },
    "Jin Dynasty": {
        "focus": "2 TC/Eco",
        "build": "Eco skalieren, aber gegen Feudal-Druck 1 TC Defense.",
        "scout": "Stables/Ranges, zweites TC, Golddruck.",
        "react": "Greed nur mit Walls/Vision; sonst Army zuerst.",
        "timing": "Minute 8 Eco-Entscheid, Minute 14 Army nachziehen.",
    },
    "Chinese": {
        "focus": "2 TC/Eco",
        "build": "Song/Eco oder 2 TC, wenn kein harter Druck kommt.",
        "scout": "Fruehe Aggression, Tower, gegnerisches zweites TC.",
        "react": "Bei Ruhe boomen; bei Druck Defense/Units vor Tech.",
        "timing": "Minute 8 Eco-Call, Minute 15+ skalierte Army.",
    },
    "Zhu Xis Legacy": {
        "focus": "2 TC/Eco",
        "build": "Eco/Tech skalieren; 2 TC nur mit sicherer Front.",
        "scout": "Golddruck, fruehe Army, Expansionsfenster.",
        "react": "Nicht frei raiden lassen, danach starkes Timing callen.",
        "timing": "Minute 10-15 Tech/Eco in Army uebersetzen.",
    },
    "Byzantines": {
        "focus": "Flex/Support",
        "build": "Mercenary/Army nach Scout; Eco nur wenn Druck gering ist.",
        "scout": "Welche Gegnerseite ist offen? Gold, Stables, Range.",
        "react": "Team braucht entweder Defense oder Zusatzdruck, nicht beides halb.",
        "timing": "Minute 8-12 Rolle festlegen und mit Team sammeln.",
    },
    "Order Of The Dragon": {
        "focus": "Fruehe Army",
        "build": "Wenige starke Units, 1 TC Druck/Map-Control.",
        "scout": "Kann Gegner Masse bauen? Gold und Produktion pruefen.",
        "react": "Nicht in schlechte Trades laufen; hochwertige Units erhalten.",
        "timing": "Minute 8-12 kleine starke Army zum Teamziel.",
    },
    "Jeanne Darc": {
        "focus": "Fruehe Army",
        "build": "Jeanne leveln, 1 TC Tempo, Druck auf Gold/Beeren.",
        "scout": "Speere, Wall-Spots, isolierte Villager.",
        "react": "XP und Map-Control holen, nicht in TC-Feuer verlieren.",
        "timing": "Minute 5-10 Druck, Jeanne-Level sichern.",
    },
}


@dataclass
class PlayerInGame:
    profile_id: int
    name: str
    civilization: str
    result: str
    rating: int | None
    rating_diff: int | None
    mmr: int | None
    mmr_diff: int | None


@dataclass
class NormalizedGame:
    game_id: int
    started_at: str
    duration: int
    map_name: str
    kind: str
    average_rating: int | None
    average_mmr: int | None
    ongoing: bool
    just_finished: bool
    player: PlayerInGame
    allies: list[PlayerInGame]
    enemies: list[PlayerInGame]

    @property
    def won(self) -> bool:
        return self.player.result == "win"

    @property
    def team_size(self) -> int:
        return len(self.allies) + 1

    @property
    def duration_minutes(self) -> float:
        return self.duration / 60


@dataclass
class InputTarget:
    raw: str
    profile_hint: str
    game_id: int | None = None


def api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    query = ""
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        query = "?" + urllib.parse.urlencode(clean)
    url = f"{BASE_URL}{path}{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"API-Fehler {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Netzwerkfehler beim Abruf von AoE4World: {exc}") from exc


def parse_input_target(value: str) -> InputTarget:
    value = value.strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.netloc and "aoe4world.com" in parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "players":
            game_id: int | None = None
            if "games" in parts:
                game_index = parts.index("games")
                if len(parts) > game_index + 1 and parts[game_index + 1].isdigit():
                    game_id = int(parts[game_index + 1])
            return InputTarget(raw=value, profile_hint=parts[1], game_id=game_id)

    return InputTarget(raw=value, profile_hint=value)


def resolve_profile_id(value: str) -> tuple[int, str]:
    target = parse_input_target(value)
    value = target.profile_hint

    leading_id = re.match(r"^(\d+)", value)
    if leading_id:
        value = leading_id.group(1)

    if value.isdigit():
        data = api_get(f"/players/{value}")
        return int(value), data.get("name", value)

    data = api_get("/players/search", {"query": value, "exact": "true"})
    players = data.get("players", [])
    if not players:
        data = api_get("/players/search", {"query": value})
        players = data.get("players", [])

    if not players:
        raise SystemExit(f"Kein AoE4World-Profil fuer '{value}' gefunden.")

    player = players[0]
    return int(player["profile_id"]), player.get("name", value)


def fetch_games(profile_id: int, modes: list[str], limit: int) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    per_mode = max(limit, 10)

    for mode in modes:
        page = 1
        collected_for_mode = 0
        while collected_for_mode < limit:
            data = api_get(
                f"/players/{profile_id}/games",
                {"leaderboard": mode, "limit": min(50, per_mode - collected_for_mode), "page": page},
            )
            batch = data.get("games", [])
            if not batch:
                break
            games.extend(batch)
            collected_for_mode += len(batch)
            if len(batch) < min(50, per_mode - collected_for_mode + len(batch)):
                break
            page += 1
            time.sleep(0.15)

    unique = {game["game_id"]: game for game in games}
    return sorted(unique.values(), key=lambda item: item.get("started_at", ""), reverse=True)


def extract_player(entry: dict[str, Any]) -> PlayerInGame:
    raw = entry.get("player", entry)
    return PlayerInGame(
        profile_id=int(raw.get("profile_id", 0)),
        name=raw.get("name", "Unbekannt"),
        civilization=pretty(raw.get("civilization", "unknown")),
        result=raw.get("result", "unknown"),
        rating=raw.get("rating"),
        rating_diff=raw.get("rating_diff"),
        mmr=raw.get("mmr"),
        mmr_diff=raw.get("mmr_diff"),
    )


def normalize_games(raw_games: list[dict[str, Any]], profile_id: int) -> list[NormalizedGame]:
    normalized: list[NormalizedGame] = []
    for game in raw_games:
        teams = game.get("teams", [])
        own_team: list[PlayerInGame] | None = None
        enemy_team: list[PlayerInGame] | None = None
        player: PlayerInGame | None = None

        parsed_teams = [[extract_player(entry) for entry in team] for team in teams]
        for team in parsed_teams:
            for candidate in team:
                if candidate.profile_id == profile_id:
                    player = candidate
                    own_team = team
                    break
            if player:
                break

        if not player or not own_team:
            continue

        for team in parsed_teams:
            if team is not own_team:
                enemy_team = team
                break

        if not enemy_team:
            continue

        normalized.append(
            NormalizedGame(
                game_id=int(game["game_id"]),
                started_at=game.get("started_at", ""),
                duration=int(game.get("duration") or 0),
                map_name=game.get("map", "Unbekannte Map"),
                kind=game.get("kind", "unknown"),
                average_rating=game.get("average_rating"),
                average_mmr=game.get("average_mmr"),
                ongoing=bool(game.get("ongoing")),
                just_finished=bool(game.get("just_finished")),
                player=player,
                allies=[ally for ally in own_team if ally.profile_id != profile_id],
                enemies=enemy_team,
            )
        )
    return normalized


def focus_games(games: list[NormalizedGame], target_game_id: int | None) -> tuple[list[NormalizedGame], bool]:
    sorted_games = sorted(games, key=lambda game: game.started_at, reverse=True)
    if target_game_id is None:
        return sorted_games, True

    focus = next((game for game in sorted_games if game.game_id == target_game_id), None)
    if not focus:
        return sorted_games, False

    older = [game for game in sorted_games if game.game_id != target_game_id and game.started_at <= focus.started_at]
    newer = [game for game in sorted_games if game.game_id != target_game_id and game.started_at > focus.started_at]
    return [focus, *older, *newer], True


def pct(wins: int, total: int) -> float:
    return (wins / total * 100) if total else 0.0


def pretty(value: str) -> str:
    return value.replace("_", " ").title() if value else "Unbekannt"


def safe_slug(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    slug = "".join(ch if ch in allowed else "_" for ch in value)
    slug = "_".join(part for part in slug.split("_") if part)
    return slug[:40] or "player"


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def date_short(value: str) -> str:
    if not value:
        return "?"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return value[:10]


def winrate_by(games: list[NormalizedGame], key_fn) -> list[tuple[str, int, int, float]]:
    totals: dict[str, int] = Counter()
    wins: dict[str, int] = Counter()
    for game in games:
        key = key_fn(game)
        totals[key] += 1
        if game.won:
            wins[key] += 1
    rows = [(key, wins[key], total, pct(wins[key], total)) for key, total in totals.items()]
    return sorted(rows, key=lambda row: (-row[2], row[3], row[0]))


def duration_bucket(game: NormalizedGame) -> str:
    minutes = game.duration_minutes
    if minutes < 16:
        return "kurze Spiele <16 min"
    if minutes < 26:
        return "Midgame 16-26 min"
    if minutes < 38:
        return "lange Spiele 26-38 min"
    return "sehr lange Spiele >38 min"


def team_rating_delta(game: NormalizedGame) -> float | None:
    own = [p.rating for p in [game.player, *game.allies] if p.rating is not None]
    enemy = [p.rating for p in game.enemies if p.rating is not None]
    if not own or not enemy:
        return None
    return mean([float(v) for v in own]) - mean([float(v) for v in enemy])


def low_sample_note(count: int) -> str:
    return " (kleine Stichprobe)" if count < 5 else ""


def ally_signature(game: NormalizedGame) -> tuple[int, ...]:
    return tuple(sorted(ally.profile_id for ally in game.allies))


def ally_names(game: NormalizedGame) -> str:
    return " + ".join(ally.name for ally in sorted(game.allies, key=lambda ally: ally.name.lower()))


def civ_names(players: list[PlayerInGame]) -> str:
    return ", ".join(player.civilization for player in players)


def best_and_worst(
    games: list[NormalizedGame], key_fn, min_games: int = 2
) -> tuple[tuple[str, int, int, float] | None, tuple[str, int, int, float] | None]:
    rows = [row for row in winrate_by(games, key_fn) if row[2] >= min_games]
    if not rows:
        return None, None
    return max(rows, key=lambda row: row[3]), min(rows, key=lambda row: row[3])


def short_team_fazit(games: list[NormalizedGame], overall_wr: float) -> tuple[str, str]:
    wins = sum(1 for game in games if game.won)
    wr = pct(wins, len(games))
    best_map, worst_map = best_and_worst(games, lambda game: game.map_name)
    best_duration, worst_duration = best_and_worst(games, duration_bucket)

    good_parts: list[str] = []
    bad_parts: list[str] = []

    if wr >= overall_wr + 8:
        good_parts.append(f"ueber Schnitt ({wr:.0f}%)")
    elif wr >= 55:
        good_parts.append(f"positive Quote ({wr:.0f}%)")

    if best_map and best_map[3] >= 65:
        good_parts.append(f"stark auf {best_map[0]}")
    if best_duration and best_duration[3] >= 65:
        good_parts.append(f"stark in {best_duration[0]}")

    if wr <= overall_wr - 10 and wr < 55:
        bad_parts.append(f"unter Schnitt ({wr:.0f}%)")
    elif wr < 45:
        bad_parts.append(f"niedrige Quote ({wr:.0f}%)")

    if worst_map and worst_map[3] <= 40:
        bad_parts.append(f"schwach auf {worst_map[0]}")
    if worst_duration and worst_duration[3] <= 40:
        bad_parts.append(f"Probleme in {worst_duration[0]}")

    if not good_parts:
        good_parts.append("solide, aber keine klare Staerke sichtbar")
    if not bad_parts:
        bad_parts.append("keine klare Schwachstelle in den Daten")

    return "; ".join(good_parts[:2]), "; ".join(bad_parts[:2])


def build_team_composition_rows(games: list[NormalizedGame]) -> list[list[str]]:
    groups: dict[tuple[int, ...], list[NormalizedGame]] = defaultdict(list)
    for game in games:
        groups[ally_signature(game)].append(game)

    rows: list[list[str]] = []
    for group_games in groups.values():
        if len(group_games) < 2:
            continue
        wins = sum(1 for game in group_games if game.won)
        best_map, worst_map = best_and_worst(group_games, lambda game: game.map_name)
        good = f"gut auf {best_map[0]}" if best_map and best_map[3] >= 60 else "-"
        focus = f"Fokus {worst_map[0]}" if worst_map and worst_map[3] <= 45 else "-"
        rows.append(
            [
                ally_names(group_games[0]),
                str(len(group_games)),
                f"{wins}/{len(group_games)}",
                f"{pct(wins, len(group_games)):.0f}%",
                date_short(group_games[0].started_at),
                good,
                focus,
            ]
        )
    return sorted(rows, key=lambda row: (-int(row[1]), row[0]))[:12]


def build_latest_team_section(games: list[NormalizedGame]) -> tuple[str, list[list[str]], list[str]]:
    if not games:
        return "_Keine Daten._", [], []

    latest = games[0]
    if not latest.allies:
        return "Dieses Spiel ist ein 1v1; es gibt keine Teammitglieder fuer diese Auswertung.", [], []

    same_team_games = [game for game in games if ally_signature(game) == ally_signature(latest)]
    wins = sum(1 for game in same_team_games if game.won)
    latest_team = ", ".join(f"{ally.name} ({ally.civilization})" for ally in latest.allies)
    summary = (
        f"Im letzten Spiel hattest du **{latest_team}** im Team. "
        f"Diese genaue Mitspieler-Gruppe kommt in den ausgewerteten Daten **{len(same_team_games)}x** vor "
        f"und steht bei **{wins}/{len(same_team_games)} Siegen** ({pct(wins, len(same_team_games)):.0f}%)."
    )

    rows = [
        [
            date_short(game.started_at),
            game.kind,
            game.map_name,
            "Sieg" if game.won else "Niederlage",
            f"{game.duration_minutes:.1f}",
            game.player.civilization,
            civ_names(game.allies),
        ]
        for game in same_team_games[:10]
    ]

    overall_wr = pct(sum(1 for game in games if game.won), len(games))
    good, bad = short_team_fazit(same_team_games, overall_wr)
    insights = [f"Gut: {good}.", f"Schlecht/Fokus: {bad}."]

    if len(same_team_games) == 1:
        insights.append(
            "Noch keine echte Vergleichsbasis fuer genau diese Gruppe. Nach 3-5 gemeinsamen Spielen wird das Fazit deutlich besser."
        )
    else:
        by_player_civ = winrate_by(same_team_games, lambda game: game.player.civilization)
        if by_player_civ:
            top_civ = max(by_player_civ, key=lambda row: (row[3], row[2]))
            if top_civ[2] >= 2:
                insights.append(
                    f"Deine beste erkennbare Rolle in dieser Gruppe: {top_civ[0]} mit {top_civ[1]}/{top_civ[2]} Siegen."
                )

    return summary, rows, insights


def build_teammate_fazit_rows(games: list[NormalizedGame]) -> list[list[str]]:
    overall_wr = pct(sum(1 for game in games if game.won), len(games))
    teammate_games: dict[int, list[NormalizedGame]] = defaultdict(list)
    teammate_names: dict[int, str] = {}
    teammate_civs: dict[int, Counter[str]] = defaultdict(Counter)

    for game in games:
        for ally in game.allies:
            teammate_games[ally.profile_id].append(game)
            teammate_names[ally.profile_id] = ally.name
            teammate_civs[ally.profile_id][ally.civilization] += 1

    rows: list[list[str]] = []
    for profile_id, ally_games in teammate_games.items():
        if len(ally_games) < 2:
            continue
        wins = sum(1 for game in ally_games if game.won)
        good, bad = short_team_fazit(ally_games, overall_wr)
        common_civ = teammate_civs[profile_id].most_common(1)[0][0]
        rows.append(
            [
                teammate_names[profile_id],
                str(len(ally_games)),
                f"{wins}/{len(ally_games)}",
                f"{pct(wins, len(ally_games)):.0f}%",
                common_civ,
                good,
                bad,
            ]
        )

    return sorted(rows, key=lambda row: (-int(row[1]), row[0]))[:16]


def game_result_text(game: NormalizedGame) -> str:
    if game.ongoing:
        return "Laufend"
    if not is_review_ready(game):
        return "Daten noch nicht final"
    return "Sieg" if game.won else "Niederlage"


def is_review_ready(game: NormalizedGame) -> bool:
    return not game.ongoing and game.duration > 0 and game.player.result in {"win", "loss"}


def signed(value: int | None) -> str:
    return f"{value:+d}" if value is not None else "-"


def teammate_in_game(game: NormalizedGame, profile_id: int) -> PlayerInGame | None:
    for ally in game.allies:
        if ally.profile_id == profile_id:
            return ally
    return None


def role_focus_for_ally(ally: PlayerInGame, latest: NormalizedGame, previous: list[NormalizedGame]) -> tuple[str, str]:
    role, hint = guide_for_civ(ally.civilization)
    map_type, _ = guide_for_map(latest.map_name)
    wins = sum(1 for game in previous if game.won)
    wr = pct(wins, len(previous))

    strengths: list[str] = []
    focus: list[str] = []

    if previous:
        if wr >= 60:
            strengths.append(f"gute Synergie bisher ({wr:.0f}%)")
        elif wr <= 40:
            focus.append(f"Synergie niedrig ({wr:.0f}%)")
        else:
            strengths.append(f"solide Vergleichsbasis ({wr:.0f}%)")

    if "Aggressionsspieler" in role or "Tempo" in role:
        strengths.append("kann Druck/Raids setzen")
        focus.append("erstes Ziel frueh callen")
    elif "Scaling" in role or "Eco" in role or "Trade" in role:
        strengths.append("skaliert gut ins Mid/Late")
        focus.append("bis Castle/Trade schuetzen")
    elif "Map-Control" in role or "Support" in role:
        strengths.append("hilft bei Vision/Map-Control")
        focus.append("mit deiner Armee zusammen spielen")
    else:
        strengths.append(role)
        focus.append(hint)

    if "kleine" in map_type and ("Scaling" in role or "Eco" in role or "Trade" in role):
        focus.insert(0, "auf kleiner Map frueher Armee")
    elif "grosse" in map_type and ("Aggressionsspieler" in role or "Tempo" in role):
        focus.insert(0, "Boomer stoeren, nicht all-in gehen")

    same_map_previous = [game for game in previous if game.map_name == latest.map_name]
    if same_map_previous:
        map_wins = sum(1 for game in same_map_previous if game.won)
        map_wr = pct(map_wins, len(same_map_previous))
        if map_wr >= 60:
            strengths.append(f"{latest.map_name} funktioniert")
        elif map_wr <= 40:
            focus.append(f"{latest.map_name} vereinfachen")

    return "; ".join(strengths[:2]), "; ".join(focus[:2])


def latest_teammate_review_rows(games: list[NormalizedGame]) -> list[list[str]]:
    if not games:
        return []

    latest = games[0]
    rows: list[list[str]] = []

    for ally in latest.allies:
        previous = [
            game
            for game in games[1:]
            if teammate_in_game(game, ally.profile_id) is not None
        ][:10]
        previous_wins = sum(1 for game in previous if game.won)
        previous_wr = pct(previous_wins, len(previous))
        role, _ = guide_for_civ(ally.civilization)
        strength, focus = role_focus_for_ally(ally, latest, previous)

        rows.append(
            [
                ally.name,
                ally.civilization,
                role,
                f"{previous_wins}/{len(previous)}" if previous else "0/0",
                f"{previous_wr:.0f}%" if previous else "-",
                strength,
                focus,
            ]
        )

    return rows


def latest_team_trend(games: list[NormalizedGame]) -> list[str]:
    if not games:
        return ["Keine Spiele gefunden."]

    latest = games[0]
    exact_previous = [game for game in games[1:] if ally_signature(game) == ally_signature(latest)][:10]
    related_previous = [
        game
        for game in games[1:]
        if any(teammate_in_game(game, ally.profile_id) for ally in latest.allies)
    ][:10]
    baseline = exact_previous or related_previous
    source = "genau diesem Team" if exact_previous else "mindestens einem dieser Teamkameraden"

    if not baseline:
        return [
            "Noch kein Vergleich moeglich: In den geladenen Daten gibt es keine frueheren Spiele mit diesen Teamkameraden."
        ]

    prev_wins = sum(1 for game in baseline if game.won)
    prev_wr = pct(prev_wins, len(baseline))
    prev_rating = mean([float(game.player.rating_diff or 0) for game in baseline])
    latest_rating = latest.player.rating_diff or 0
    latest_bucket = duration_bucket(latest)
    prev_same_bucket = [game for game in baseline if duration_bucket(game) == latest_bucket]
    prev_bucket_wr = pct(sum(1 for game in prev_same_bucket if game.won), len(prev_same_bucket))

    lines = [
        f"Vergleichsbasis: vorherige {len(baseline)} Spiele mit {source}: {prev_wins}/{len(baseline)} Siege ({prev_wr:.0f}%).",
    ]

    if latest.won and prev_wr < 50:
        lines.append("Besser geworden: Das letzte Spiel war ein Sieg, obwohl die Vergleichsspiele eher schwach waren.")
    elif not latest.won and prev_wr >= 55:
        lines.append("Schlechter als zuletzt: Das letzte Spiel war eine Niederlage, obwohl die Vergleichsspiele positiv waren.")
    elif latest.won:
        lines.append("Stabil positiv: Das letzte Spiel bestaetigt den bisherigen Trend.")
    else:
        lines.append("Fokus noetig: Das letzte Spiel bestaetigt oder verstaerkt einen wackligen Trend.")

    if latest_rating > prev_rating + 8:
        lines.append(f"Rating-Trend besser: letztes Spiel {latest_rating:+d}, vorher im Schnitt {prev_rating:+.1f}.")
    elif latest_rating < prev_rating - 8:
        lines.append(f"Rating-Trend schlechter: letztes Spiel {latest_rating:+d}, vorher im Schnitt {prev_rating:+.1f}.")

    if prev_same_bucket:
        if latest.won and prev_bucket_wr < 50:
            lines.append(f"Besser in dieser Matchlaenge: {latest_bucket} war vorher nur {prev_bucket_wr:.0f}% Winrate.")
        elif not latest.won and prev_bucket_wr >= 60:
            lines.append(f"Schlechter in dieser Matchlaenge: {latest_bucket} war vorher {prev_bucket_wr:.0f}% Winrate.")

    lines.append(
        "Team-Fokus fuer naechstes Spiel: gleiche Rollen vor Minute 5 festlegen und nach dem ersten gemeinsamen Fight entscheiden, ob Boom, Trade oder zweiter Push folgt."
    )
    return lines


def latest_game_summary(games: list[NormalizedGame]) -> str:
    if not games:
        return "_Keine Daten._"
    latest = games[0]
    allies = ", ".join(f"{ally.name} ({ally.civilization})" for ally in latest.allies)
    enemies = ", ".join(f"{enemy.name} ({enemy.civilization})" for enemy in latest.enemies)
    return (
        f"**{game_result_text(latest)}** auf **{latest.map_name}** ({latest.kind}, {latest.duration_minutes:.1f} min). "
        f"Du: **{latest.player.civilization}**, Team: **{allies}**. "
        f"Gegner: {enemies}. Rating: **{signed(latest.player.rating_diff)}**, MMR: **{signed(latest.player.mmr_diff)}**."
    )


def guide_for_map(map_name: str) -> tuple[str, str]:
    return MAP_GUIDES.get(map_name.lower(), ("Map ohne Spezialregel", "Standardplan: scouten, Rollen klaeren, ersten Teamfight gemeinsam nehmen."))


def guide_for_civ(civilization: str) -> tuple[str, str]:
    return CIV_GUIDES.get(
        civilization,
        ("flexible Rolle", "Pruefe im Replay vor allem: saubere Eco, keine Produktionsluecken, rechtzeitiger Teamfight."),
    )


def latest_player_focus(games: list[NormalizedGame]) -> list[str]:
    if not games:
        return ["Keine Spiele gefunden."]

    latest = games[0]
    role, civ_hint = guide_for_civ(latest.player.civilization)
    map_type, map_hint = guide_for_map(latest.map_name)
    enemy_boomers = [enemy for enemy in latest.enemies if enemy.civilization in BOOM_CIVS]
    previous_same_civ = [game for game in games[1:] if game.player.civilization == latest.player.civilization][:10]
    previous_same_map = [game for game in games[1:] if game.map_name == latest.map_name][:10]

    lines = [
        f"Deine Rolle im letzten Spiel: **{role}** mit **{latest.player.civilization}**.",
        f"Map-Plan fuer **{latest.map_name}** ({map_type}): {map_hint}",
        f"Build-Order-Check: {civ_hint}",
    ]

    if enemy_boomers:
        names = ", ".join(f"{enemy.name} ({enemy.civilization})" for enemy in enemy_boomers[:3])
        lines.append(f"Anti-Boom-Fokus: {names} durfte nicht frei bis Minute 20-25 skalieren.")
    else:
        lines.append("Gegner-Fokus: Kein klarer Boom-Spieler erkannt; wichtiger ist gemeinsamer erster Fight und Map-Vision.")

    if previous_same_civ:
        civ_wins = sum(1 for game in previous_same_civ if game.won)
        civ_wr = pct(civ_wins, len(previous_same_civ))
        if latest.won and civ_wr < 50:
            lines.append(f"Verbesserung: Mit dieser Civ warst du zuletzt nur bei {civ_wr:.0f}%, dieses Spiel war besser.")
        elif not latest.won and civ_wr >= 55:
            lines.append(f"Warnsignal: Mit dieser Civ warst du zuletzt bei {civ_wr:.0f}%, dieses Spiel fiel darunter.")
        else:
            lines.append(f"Civ-Vergleich: letzte {len(previous_same_civ)} Spiele mit dieser Civ: {civ_wins}/{len(previous_same_civ)} Siege.")

    if previous_same_map:
        map_wins = sum(1 for game in previous_same_map if game.won)
        map_wr = pct(map_wins, len(previous_same_map))
        lines.append(f"Map-Vergleich: letzte {len(previous_same_map)} Spiele auf dieser Map: {map_wins}/{len(previous_same_map)} Siege ({map_wr:.0f}%).")

    if latest.won:
        lines.append("Naechster Fokus: Erfolgsplan wiederholen, aber im Replay pruefen, ob der erste Druck wirklich den staerksten Gegner getroffen hat.")
    else:
        lines.append("Naechster Fokus: Replay bis Minute 12 pruefen - Scoutinfo, erster Druck, Produktion und ob der gefaehrlichste Gegner gestoert wurde.")

    return lines[:7]


def compact_ai_style_review(games: list[NormalizedGame]) -> list[str]:
    if not games:
        return ["Keine Spiele gefunden."]

    latest = games[0]
    _, map_hint = guide_for_map(latest.map_name)
    role, civ_hint = guide_for_civ(latest.player.civilization)
    enemy_boomers = [enemy for enemy in latest.enemies if enemy.civilization in BOOM_CIVS]
    previous_same_team = [game for game in games[1:] if ally_signature(game) == ally_signature(latest)][:10]
    previous_same_map = [game for game in games[1:] if game.map_name == latest.map_name][:10]

    missed = "Ersten Teamplan frueher festlegen: Scoutinfo -> Ziel -> gemeinsamer Fight."
    if enemy_boomers:
        target = enemy_boomers[0]
        missed = f"Moegliche verpasste Chance: {target.name} ({target.civilization}) frueher ueber Gold/Relikte stoeren."
    elif latest.duration_minutes > 30:
        missed = "Moegliche verpasste Chance: Nach gewonnenem Fight schneller Trade/Boom/Imperial absichern."
    elif latest.duration_minutes < 18 and not latest.won:
        missed = "Moegliche verpasste Chance: Fruehe Armee/Defense vor dem ersten grossen Fight stabilisieren."

    if previous_same_team:
        team_wins = sum(1 for game in previous_same_team if game.won)
        team_line = f"Gleiches Team vorher: {team_wins}/{len(previous_same_team)} Siege."
    else:
        team_line = "Gleiches Team vorher: zu wenig Daten fuer einen sicheren Vergleich."

    if previous_same_map:
        map_wins = sum(1 for game in previous_same_map if game.won)
        map_line = f"Gleiche Map vorher: {map_wins}/{len(previous_same_map)} Siege."
    else:
        map_line = "Gleiche Map vorher: zu wenig Daten."

    likely_issue = "Team-Timing und Zielauswahl"
    if latest.duration_minutes < 18 and not latest.won:
        likely_issue = "fruehe Stabilitaet und erster Fight"
    elif latest.duration_minutes >= 26 and not latest.won:
        likely_issue = "Midgame-Uebergang, Eco-Schutz und gemeinsamer Push"
    elif latest.won:
        likely_issue = "Siegplan wiederholen und sauberer ausbauen"

    return [
        f"Wahrscheinlich wichtigster Punkt: **{likely_issue}**.",
        missed,
        f"Rollencheck: Du warst **{role}**. {civ_hint}",
        f"Mapcheck: {map_hint}",
        f"{team_line} {map_line}",
    ]


def short_coaching_review(games: list[NormalizedGame]) -> list[str]:
    if not games:
        return ["Keine Spiele gefunden."]

    latest = games[0]
    role, civ_hint = guide_for_civ(latest.player.civilization)
    _, map_hint = guide_for_map(latest.map_name)
    enemy_boomers = [enemy for enemy in latest.enemies if enemy.civilization in BOOM_CIVS]
    previous_same_team = [game for game in games[1:] if ally_signature(game) == ally_signature(latest)][:10]
    previous_same_map = [game for game in games[1:] if game.map_name == latest.map_name][:10]

    if latest.duration_minutes < 18:
        phase = "fruehes Spiel"
        problem = "Der wichtigste Check ist, ob ihr vor dem ersten grossen Fight genug Armee, Scoutinfo und ein klares Ziel hattet."
        improve = "Naechstes Mal bis Minute 8 klaeren: Wer drueckt, wer sichert, welches Gold/Relikt wird angegriffen?"
    elif latest.duration_minutes < 28:
        phase = "Midgame"
        problem = "Der wichtigste Check ist, ob Eco und Tech schnell genug in gemeinsame Armee und Map-Kontrolle umgewandelt wurden."
        improve = "Naechstes Mal nach dem ersten Castle-/Midgame-Spike sofort sammeln und nicht einzeln traden."
    else:
        phase = "Late Game"
        problem = "Der wichtigste Check ist, ob eure starke Eco in saubere Re-Maxes, Siege-Schutz und eine klare Komposition ging."
        improve = "Naechstes Mal vor grossen Fights Produktion und Rallypunkte setzen, damit Verluste sofort ersetzt werden."

    if latest.won:
        summary = (
            f"Ihr habt das {phase} auf {latest.map_name} gewonnen. Der Fokus ist jetzt nicht ein grosser Fehler, "
            "sondern den Siegplan reproduzierbar zu machen: gleiche Rollen, gleiches erstes Ziel, gleicher Timing-Fight."
        )
    else:
        summary = (
            f"Ihr habt auf {latest.map_name} nach {latest.duration_minutes:.1f} Minuten verloren. "
            f"Der wahrscheinlich wichtigste Hebel war {phase}: {problem}"
        )

    wrong_points = []
    if enemy_boomers:
        target = enemy_boomers[0]
        wrong_points.append(f"{target.name} ({target.civilization}) war das klare Anti-Boom-Ziel und musste frueh gestoert werden.")
    else:
        wrong_points.append("Es gab kein eindeutiges Boom-Ziel; dadurch zaehlt euer erster gemeinsamer Fight noch mehr.")
    if previous_same_team:
        team_wins = sum(1 for game in previous_same_team if game.won)
        team_wr = pct(team_wins, len(previous_same_team))
        if latest.won and team_wr < 50:
            wrong_points.append(f"Mit diesem Team wart ihr vorher nur bei {team_wr:.0f}% - dieses Spiel war ein besserer Plan.")
        elif not latest.won and team_wr >= 50:
            wrong_points.append(f"Mit diesem Team wart ihr vorher bei {team_wr:.0f}% - das Spiel fiel unter euer normales Niveau.")
        else:
            wrong_points.append(f"Gleiches Team vorher: {team_wins}/{len(previous_same_team)} Siege.")
    if previous_same_map:
        map_wins = sum(1 for game in previous_same_map if game.won)
        map_wr = pct(map_wins, len(previous_same_map))
        if not latest.won and map_wr >= 60:
            wrong_points.append(f"{latest.map_name} war sonst besser ({map_wr:.0f}%) - Replay auf ersten Fight und Map-Kontrolle pruefen.")
        elif latest.won and map_wr <= 40:
            wrong_points.append(f"{latest.map_name} war sonst schwach ({map_wr:.0f}%) - diesen Plan als Vorlage speichern.")

    improve_points = [
        improve,
        f"Dein Rollencheck mit {latest.player.civilization}: {civ_hint}",
        f"Map-Regel: {map_hint}",
    ]

    return [
        f"**Summary:** {summary}",
        "**Was wahrscheinlich schief lief:** " + " ".join(wrong_points[:2]),
        "**Wie du es konkret verbesserst:** " + " ".join(improve_points[:2]),
    ]


def previous_context(games: list[NormalizedGame]) -> list[str]:
    if not games:
        return ["Keine Spiele gefunden."]

    latest = games[0]
    previous_team = [game for game in games[1:] if ally_signature(game) == ally_signature(latest)][:10]
    previous_map = [game for game in games[1:] if game.map_name == latest.map_name][:10]
    previous_civ = [game for game in games[1:] if game.player.civilization == latest.player.civilization][:10]
    lines: list[str] = []

    if previous_team:
        wins = sum(1 for game in previous_team if game.won)
        wr = pct(wins, len(previous_team))
        direction = "besser" if latest.won and wr < 50 else "schlechter" if not latest.won and wr >= 50 else "aehnlich"
        comparison = "wie" if direction == "aehnlich" else "als"
        lines.append(f"Gleiches Team: dieses Spiel war **{direction}** {comparison} die letzten {len(previous_team)} Spiele ({wins}/{len(previous_team)} Siege).")

    if previous_map:
        wins = sum(1 for game in previous_map if game.won)
        wr = pct(wins, len(previous_map))
        direction = "besser" if latest.won and wr < 50 else "schlechter" if not latest.won and wr >= 50 else "aehnlich"
        comparison = "wie" if direction == "aehnlich" else "als"
        lines.append(f"Gleiche Map: **{direction}** {comparison} zuletzt auf {latest.map_name} ({wins}/{len(previous_map)} Siege).")

    if previous_civ:
        wins = sum(1 for game in previous_civ if game.won)
        wr = pct(wins, len(previous_civ))
        direction = "besser" if latest.won and wr < 50 else "schlechter" if not latest.won and wr >= 50 else "aehnlich"
        comparison = "wie" if direction == "aehnlich" else "als"
        lines.append(f"Gleiche Civ: **{direction}** {comparison} zuletzt mit {latest.player.civilization} ({wins}/{len(previous_civ)} Siege).")

    if not lines:
        lines.append("Zu wenig passende Vergleichsspiele gefunden; Details stehen im Detailbericht.")

    return lines[:3]


def next_match_focus(games: list[NormalizedGame]) -> list[str]:
    if not games:
        return ["Keine Spiele gefunden."]

    latest = games[0]
    role, civ_hint = guide_for_civ(latest.player.civilization)
    _, map_hint = guide_for_map(latest.map_name)
    enemy_boomers = [enemy for enemy in latest.enemies if enemy.civilization in BOOM_CIVS]

    if latest.duration_minutes < 18:
        timing_focus = "Bis Minute 8 muss klar sein: erstes Ziel, wer drueckt, wer sichert."
    elif latest.duration_minutes < 28:
        timing_focus = "Nach dem ersten Castle-/Midgame-Spike sofort gemeinsam sammeln statt einzeln traden."
    else:
        timing_focus = "Vor grossen Fights Produktion, Rallypunkte und Re-Max vorbereiten."

    target_focus = (
        f"Anti-Boom-Ziel: {enemy_boomers[0].name} ({enemy_boomers[0].civilization}) frueh stoeren."
        if enemy_boomers
        else "Kein klares Boom-Ziel: ersten gemeinsamen Fight und Vision priorisieren."
    )

    return [
        timing_focus,
        target_focus,
        f"Deine Rolle: {role}. {civ_hint}",
        f"Map-Regel: {map_hint}",
    ][:3]


def player_label(player: PlayerInGame) -> str:
    return f"{player.name} ({player.civilization})"


def civ_key(civilization: str) -> str:
    return civilization.lower().replace(" ", "_").replace("'", "")


def civ_playbook(civilization: str) -> dict[str, str]:
    role, hint = guide_for_civ(civilization)
    return CIV_PLAYBOOK.get(
        civilization,
        {
            "focus": role,
            "build": "Scout entscheidet: 1 TC Army gegen Druck, Eco/Tech nur wenn sicher.",
            "scout": "Gold, zweites TC, fruehe Produktion, offene Flanken.",
            "react": hint,
            "timing": "Minute 8 Rollenentscheidung, Minute 12-15 gemeinsam sammeln.",
        },
    )


def threat_score(player: PlayerInGame) -> int:
    score = 0
    if player.civilization in BOOM_CIVS:
        score += 3
    if player.civilization in AGGRESSION_CIVS:
        score += 2
    if player.rating:
        score += max(0, min(3, (player.rating - 1000) // 250))
    return score


def choose_primary_target(game: NormalizedGame) -> PlayerInGame | None:
    if not game.enemies:
        return None
    return max(game.enemies, key=threat_score)


def pregame_role_rows(game: NormalizedGame) -> list[list[str]]:
    rows: list[list[str]] = []
    for player in [game.player, *game.allies]:
        role, hint = guide_for_civ(player.civilization)
        if player.profile_id == game.player.profile_id:
            name = f"{player.name} (du)"
        else:
            name = player.name
        rows.append([name, player.civilization, role, hint])
    return rows


def known_role(player: PlayerInGame) -> str | None:
    role = KNOWN_PLAYER_ROLES.get(player.name.strip().lower())
    if not role:
        return None
    if player.name.strip().lower() == "joko" and player.civilization not in {"English", "House Of Lancaster"}:
        return None
    if player.name.strip().lower() == "burbleb" and player.civilization not in {"French", "Ayyubids", "Knights Templar"}:
        return None
    if player.name.strip().lower() == "taronimo" and player.civilization not in {"Japanese", "Sengoku Daimyo"}:
        return None
    return role


def short_player_plan(player: PlayerInGame, game: NormalizedGame, is_requester: bool = False) -> str:
    role, _ = guide_for_civ(player.civilization)
    custom_role = known_role(player)
    shown_role = custom_role or role
    prefix = f"{player.name}{' (du)' if is_requester else ''}: {player.civilization} -> {shown_role}"

    book = civ_playbook(player.civilization)
    action = f"{book['focus']}: {book['build']} {book['timing']}"

    if game.team_size >= 4 and custom_role in {"Eco/Support", "Scaling-Carry"}:
        action += " Team muss dich bis Castle/Imperial schuetzen."
    if game.team_size >= 4 and custom_role == "Aggression/Raids":
        action += " Nicht alleine all-in, nur Boom verzoegern."

    return f"- {prefix}: {action}"


def team_focus_cards(game: NormalizedGame) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for player in [game.player, *game.allies]:
        role, _ = guide_for_civ(player.civilization)
        book = civ_playbook(player.civilization)
        cards.append(
            {
                "name": f"{player.name} (du)" if player.profile_id == game.player.profile_id else player.name,
                "civ": player.civilization,
                "role": known_role(player) or role,
                "focus": book["focus"],
                "build": book["build"],
                "timing": book["timing"],
            }
        )
    return cards


def scout_reaction(enemy: PlayerInGame, state: str) -> str:
    if state == "2tc":
        return f"{enemy.name} boomt: Druck auf Gold/2. TC, nicht bis Minute 18 frei lassen."
    if state == "fc":
        return f"{enemy.name} techt: Gold/Relikte stoeren oder vor Castle gemeinsam pushen."
    if state == "army":
        return f"{enemy.name} baut Army: defensiv sammeln, Counter bauen, nicht einzeln fighten."
    if state == "trade":
        return f"{enemy.name} will Trade/Boom: Route scouten, Markt/Trader frueh bestrafen."
    if state == "feudal":
        return f"{enemy.name} bleibt Feudal: Army erwarten, erst halten und dann gemeinsam kontern."
    if state == "castle":
        return f"{enemy.name} ist/geht Castle: Relikte und Gold stoeren, vor dem Power-Spike sammeln."
    if state == "imperial":
        return f"{enemy.name} geht Imperial: sofort Druck auf Eco/Trade, kein langes Warten."
    if state == "unclear":
        return f"{enemy.name} unklar: Scout nochmal Gold, Produktion, TC und Markt."
    book = civ_playbook(enemy.civilization)
    return f"Erwartung: {book['focus']}. Scout prueft: {book['scout']}"


def enemy_scout_cards(game: NormalizedGame, scout_states: dict[int, str] | None = None) -> list[dict[str, str]]:
    scout_states = scout_states or {}
    cards: list[dict[str, str]] = []
    for enemy in game.enemies:
        state = scout_states.get(enemy.profile_id, "")
        book = civ_playbook(enemy.civilization)
        cards.append(
            {
                "profile_id": str(enemy.profile_id),
                "name": enemy.name,
                "civ": enemy.civilization,
                "expected": book["focus"],
                "scout": book["scout"],
                "state": SCOUT_STATES.get(state, ""),
                "reaction": scout_reaction(enemy, state),
            }
        )
    return cards


def combined_reaction_plan(game: NormalizedGame, scout_states: dict[int, str] | None = None) -> list[str]:
    scout_states = scout_states or {}
    enemies_by_id = {enemy.profile_id: enemy for enemy in game.enemies}

    army = [enemies_by_id[pid] for pid, state in scout_states.items() if state in {"army", "feudal"} and pid in enemies_by_id]
    tech = [enemies_by_id[pid] for pid, state in scout_states.items() if state in {"fc", "castle", "imperial"} and pid in enemies_by_id]
    eco = [enemies_by_id[pid] for pid, state in scout_states.items() if state in {"2tc", "trade"} and pid in enemies_by_id]
    unclear = [enemies_by_id[pid] for pid, state in scout_states.items() if state == "unclear" and pid in enemies_by_id]

    if not any([army, tech, eco, unclear]):
        return concise_enemy_plan(game) or ["Noch kein Scout-Input: Gold, 2. TC, Stables/Ranges und Trade-Route pruefen."]

    lines: list[str] = []
    if army:
        names = ", ".join(player_label(enemy) for enemy in army[:2])
        lines.append(f"Prioritaet 1: {names} baut Druck. Erst defensiv sammeln, Counter bauen, keinen Solo-Fight nehmen.")
    if tech:
        names = ", ".join(player_label(enemy) for enemy in tech[:2])
        prefix = "Prioritaet 2" if army else "Prioritaet 1"
        lines.append(f"{prefix}: {names} techt. Gold/Relikte stoeren oder vor dem Power-Spike gemeinsam pushen.")
    if eco:
        names = ", ".join(player_label(enemy) for enemy in eco[:2])
        prefix = "Danach" if army or tech else "Prioritaet 1"
        lines.append(f"{prefix}: {names} boomt/tradet. Druck auf Gold, 2. TC oder Trade-Route.")
    if unclear:
        names = ", ".join(player_label(enemy) for enemy in unclear[:2])
        lines.append(f"Unklar: {names} nochmal scouten: Gold, Produktion, TC, Markt.")

    return lines[:4]


def tactical_steps(game: NormalizedGame, scout_states: dict[int, str] | None = None) -> dict[str, list[str]]:
    scout_states = scout_states or {}
    target = choose_primary_target(game)
    reactions = combined_reaction_plan(game, scout_states)
    has_enemy_army = any(state in {"army", "feudal"} for state in scout_states.values())
    first_push = (
        "9-12: Erst gegnerischen Druck halten, dann gemeinsam kontern."
        if has_enemy_army
        else f"9-12: {pressure_player_names(game)} geht auf {player_label(target) if target else 'das gescoutete Ziel'}, Team sichert nach."
    )
    return {
        "scout_now": [
            "0-2: Gegner-Gold und erste Produktion ansehen.",
            "2-4: Check: 2. TC? Stables/Ranges? Fast-Castle-Gold? Markt/Trade?",
            "4-6: Teamcall: wer drueckt, wer deckt, wer darf boomen.",
        ],
        "after_scout": reactions[:4],
        "push": [
            first_push,
            "12-16: Kein Solo-Fight; erst sammeln, dann Gold/TC/Trade angreifen.",
            "16-20: Wenn Druck nicht endet: Relikte/Mitte/zweite Front sichern.",
        ],
    }


def fetch_current_matchup_stats(
    own_civs: list[str],
    enemy_civs: list[str],
    rating: str | None = None,
    rank_level: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if rating:
        params["rating"] = rating
    if rank_level:
        params["rank_level"] = rank_level
    data = api_get("/stats/rm_solo/matchups", params)
    rows = data.get("data", [])
    lookup = {
        (row.get("civilization"), row.get("other_civilization")): row
        for row in rows
        if isinstance(row, dict)
    }
    pair_rows = []
    for own in own_civs:
        for enemy in enemy_civs:
            row = lookup.get((civ_key(own), civ_key(enemy)))
            if row:
                pair_rows.append(row)
    games = sum(int(row.get("games_count") or 0) for row in pair_rows)
    if not pair_rows or games <= 0:
        return {"available": False, "patch": str(data.get("patch", "?")), "summary": "Keine Matchup-Daten gefunden."}
    weighted = sum(float(row.get("win_rate") or 0) * int(row.get("games_count") or 0) for row in pair_rows) / games
    return {
        "available": True,
        "patch": str(data.get("patch", "?")),
        "win_rate": weighted,
        "games": games,
        "summary": f"AoE4World Patch {data.get('patch', '?')}: Team-Civ-Matchup ca. {weighted:.1f}% aus {games} 1v1-Paarungen.",
    }


def build_live_cockpit_data(
    player_name: str,
    profile_id: int,
    game: NormalizedGame,
    scout_states: dict[int, str] | None = None,
    include_online_stats: bool = False,
) -> dict[str, Any]:
    own_civs = [player.civilization for player in [game.player, *game.allies]]
    enemy_civs = [enemy.civilization for enemy in game.enemies]
    stats = {"available": False, "summary": "Online-Matchup noch nicht geladen."}
    if include_online_stats:
        try:
            stats = fetch_current_matchup_stats(own_civs, enemy_civs)
        except Exception as exc:
            stats = {"available": False, "summary": f"Online-Matchup nicht verfuegbar: {exc}"}
    return {
        "player": player_name,
        "profile_id": profile_id,
        "game_id": game.game_id,
        "map": game.map_name,
        "kind": game.kind,
        "team": team_focus_cards(game),
        "enemies": enemy_scout_cards(game, scout_states),
        "steps": tactical_steps(game, scout_states),
        "matchup_stats": stats,
    }


def timing_role_summary(game: NormalizedGame) -> str:
    roles: list[str] = []
    for player in [game.player, *game.allies]:
        role, _ = guide_for_civ(player.civilization)
        shown_role = known_role(player) or role
        name = f"{player.name} (du)" if player.profile_id == game.player.profile_id else player.name
        roles.append(f"{name}={shown_role}")
    return "; ".join(roles)


def pressure_player_names(game: NormalizedGame) -> str:
    pressure_players = [
        player
        for player in [game.player, *game.allies]
        if player.civilization in AGGRESSION_CIVS or known_role(player) == "Aggression/Raids"
    ]
    if not pressure_players:
        pressure_players = [
            player
            for player in [game.player, *game.allies]
            if "Map-Control" in (known_role(player) or guide_for_civ(player.civilization)[0])
        ]
    if not pressure_players:
        return "Druckspieler"
    return " + ".join(player.name for player in pressure_players[:2])


def map_specific_plan(game: NormalizedGame) -> list[str]:
    name = game.map_name.lower()
    if "lipany" in name:
        return [
            "Mitte ist wichtig: Relikte/Sacred/Mitte frueh scouten.",
            "Kein blindes All-in: Druck setzen, waehrend Eco-Spieler skalieren.",
        ]
    if "dry arabia" in name:
        return [
            "Offene Flanken: frueh scouten und Raids erwarten.",
            "Erstes Ziel meist Gold/Aussenressourcen vom Boomer oder Tempo-Spieler.",
        ]
    if "gorge" in name:
        return [
            "Kleine Kampfkarte: fruehe Armee zaehlt mehr als greedy Boom.",
            "Minute 10-15 gemeinsam pushen oder Engstelle sichern.",
        ]
    if "canal" in name or "water" in name:
        return [
            "Wasser/Trade frueh klaeren: Wer contestet, wer boomt?",
            "Nicht alle Spieler auf Wasser ziehen; Landdruck gegen Boomer behalten.",
        ]
    if "hill and dale" in name:
        return [
            "Boom-Karte: eigene Eco schuetzen, gegnerische Eco nicht frei lassen.",
            "Mitte halten und vor Minute 20 Teamfight vorbereiten.",
        ]
    return [
        "Scout zuerst Flanken, Gold und moegliche Boom-Spieler.",
        "Vor Minute 8 ein gemeinsames erstes Ziel festlegen.",
    ]


def concise_enemy_plan(game: NormalizedGame) -> list[str]:
    boomers = [enemy for enemy in game.enemies if enemy.civilization in BOOM_CIVS]
    aggressors = [enemy for enemy in game.enemies if enemy.civilization in AGGRESSION_CIVS]
    lines: list[str] = []
    if boomers:
        lines.append("Boom-Ziel: " + ", ".join(player_label(enemy) for enemy in boomers[:2]))
    if aggressors:
        lines.append("Frueher Druck moeglich von: " + ", ".join(player_label(enemy) for enemy in aggressors[:2]))
    if not lines:
        target = choose_primary_target(game)
        if target:
            lines.append(f"Kein klares Boom/Aggro-Matchup. Erstes Ziel nach Scout: {player_label(target)}.")
    return lines


def shotcaller_calls(game: NormalizedGame) -> list[str]:
    boomers = [enemy for enemy in game.enemies if enemy.civilization in BOOM_CIVS]
    aggressors = [enemy for enemy in game.enemies if enemy.civilization in AGGRESSION_CIVS]
    pressure_players = [
        player
        for player in [game.player, *game.allies]
        if player.civilization in AGGRESSION_CIVS or known_role(player) == "Aggression/Raids"
    ]
    scaling_players = [
        player
        for player in [game.player, *game.allies]
        if player.civilization in BOOM_CIVS or known_role(player) in {"Scaling-Carry", "Eco/Support"}
    ]
    map_control_players = [
        player
        for player in [game.player, *game.allies]
        if "Map-Control" in (known_role(player) or guide_for_civ(player.civilization)[0])
    ]

    pressure = pressure_players[0] if pressure_players else game.player
    scaler = scaling_players[0] if scaling_players else None
    map_control = map_control_players[0] if map_control_players else game.player
    boom_target = max(boomers, key=threat_score) if boomers else None
    aggro_target = max(aggressors, key=threat_score) if aggressors else None
    fallback_target = choose_primary_target(game)

    lines: list[str] = []
    if boom_target and pressure:
        lines.append(
            f"CALL 1: Wenn {player_label(boom_target)} frei boomt, dann {pressure.name} auf Gold/Beeren/Relikte schicken."
        )
    if aggro_target:
        defender = map_control or game.player
        lines.append(
            f"CALL 2: Wenn {player_label(aggro_target)} frueh drueckt, dann {defender.name} defensiv sammeln und erst halten."
        )
    if scaler and pressure and scaler.profile_id != pressure.profile_id:
        lines.append(
            f"CALL 3: {scaler.name} darf boomen, solange {pressure.name} Vision/Druck macht. Bei Angriff sofort pingen und zurueckziehen."
        )
    if fallback_target:
        lines.append(
            f"CALL 4: Wenn kein klarer Druck kommt, erstes Teamziel: {player_label(fallback_target)}."
        )
    if game.team_size >= 3:
        lines.append("CALL 5: Kein Solo-Fight nach Minute 10. Erst sammeln, dann pushen.")
    else:
        lines.append("CALL 5: Nicht planlos wechseln: Scoutinfo entscheidet zwischen Druck, 2 TC oder Fast Castle.")

    return lines[:5]


def build_pregame_plan(player_name: str, profile_id: int, game: NormalizedGame) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    map_type, map_hint = guide_for_map(game.map_name)
    target = choose_primary_target(game)
    enemy_boomers = [enemy for enemy in game.enemies if enemy.civilization in BOOM_CIVS]
    enemy_aggressors = [enemy for enemy in game.enemies if enemy.civilization in AGGRESSION_CIVS]

    boom_target = max(enemy_boomers, key=threat_score) if enemy_boomers else None
    aggression_target = max(enemy_aggressors, key=threat_score) if enemy_aggressors else None

    if boom_target and aggression_target:
        target_line = (
            f"Erst Druck von **{player_label(aggression_target)}** scouten/abfangen, "
            f"danach **{player_label(boom_target)}** ueber Gold, Relikte oder TC/Trade stoeren."
        )
    elif target:
        target_line = f"Primaeres Ziel: **{player_label(target)}**. "
        if target.civilization in BOOM_CIVS:
            target_line += "Nicht frei boomen lassen: Gold, Relikte, zweites TC oder Trade frueh stoeren."
        elif target.civilization in AGGRESSION_CIVS:
            target_line += "Fruehe Aggression erwarten: Scouten, Speere/Defense rechtzeitig vorbereiten."
        else:
            target_line += "Als staerksten Gegner scouten und ersten Druck auf ihn ausrichten."
    else:
        target_line = "Primaeres Ziel: noch nicht bestimmbar."

    if enemy_boomers and enemy_aggressors:
        matchup_line = "Gegner haben Boom + Druck. Erst Aggression abfangen, dann den Boomer stoeren."
    elif enemy_boomers:
        matchup_line = "Gegner wirken boomlastig. Frueh Vision holen und Gold/Relikte/Trade bestrafen."
    elif enemy_aggressors:
        matchup_line = "Gegner wirken aggressiv. Erste Minuten sauber verteidigen, dann gemeinsam kontern."
    else:
        matchup_line = "Kein extremes Matchup erkannt. Der erste koordinierte Fight und Map-Kontrolle sind entscheidend."

    timing_lines = ["0-4: Scout: Flanken, Gold, Boomer, Raidgefahr."]
    if game.team_size >= 3:
        timing_lines.append(f"5-8: Rollen callen: {timing_role_summary(game)}.")
        timing_lines.append(f"9-12: {pressure_player_names(game)} geht auf Ziel, Team sichert nach.")
    else:
        timing_lines.append("5-8: Entscheiden: Druck, 2 TC oder Fast Castle.")
        timing_lines.append("9-12: Map-Control oder gegnerischen Push abfangen.")
    timing_lines.append("16-20: Gemeinsam fighten, Relikte/Mitte/Trade sichern.")

    lines = [
        f"# Spielplan: {player_name}",
        "",
        f"Erstellt: {generated_at}",
        "",
        "## Match",
        "",
        f"{game.kind} auf **{game.map_name}** ({map_type}) - {'laufend' if game.ongoing else 'nicht laufend / zuletzt gefunden'}",
        "",
        "## Sofortplan",
        "",
    ]
    lines.extend(f"- {line}" for line in map_specific_plan(game))
    lines.extend(f"- {line}" for line in concise_enemy_plan(game))
    lines.extend([f"- {matchup_line}", f"- {target_line}", "", "## Dein Team", ""])
    lines.extend(short_player_plan(player, game, player.profile_id == game.player.profile_id) for player in [game.player, *game.allies])
    lines.extend(["", "## Shotcaller Calls", ""])
    lines.extend(f"- {line}" for line in shotcaller_calls(game))
    lines.extend(
        [
            "",
            "## Gegner",
            "",
        ]
    )
    lines.extend(f"- {player_label(enemy)}" for enemy in game.enemies)
    lines.extend(
        [
            "",
            "## Timing",
            "",
        ]
    )
    lines.extend(f"- {line}" for line in timing_lines)
    lines.extend(
        [
            "",
            "## Call Vor Minute 5",
            "",
            "- Was ist das erste Ziel?",
            "- Wer verteidigt gegen Raids?" if game.allies else "- Welche fruehe Aggression muss ich scouten?",
            "- Wer darf boomen und wer muss Druck machen?" if game.allies else "- Spiele ich 1 TC Druck, 2 TC oder Fast Castle?",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_recommendations(games: list[NormalizedGame]) -> list[str]:
    recs: list[str] = []
    if not games:
        return ["Noch keine 3v3/4v4-Spiele gefunden. Pruefe Profil-ID, Datenschutz und Modus-Auswahl."]

    total = len(games)
    wins = sum(1 for game in games if game.won)
    wr = pct(wins, total)

    if wr < 45:
        recs.append(
            "Grundplan stabilisieren: Waehle fuer die naechsten 10 Teamspiele nur 1-2 Civs und nutze pro Map einen festen ersten Gameplan."
        )
    elif wr > 58:
        recs.append(
            "Staerke ausbauen: Deine Gesamt-Winrate ist gut. Suche gezielt nach den 1-2 Maps oder Matchlaengen, die darunter liegen."
        )
    else:
        recs.append(
            "Du liegst im Bereich, in dem kleine Team-Absprachen viel bringen: vor Minute 5 Rollen klaeren, erstes Ziel pingen, ersten Push timen."
        )

    by_duration = winrate_by(games, duration_bucket)
    weak_duration = min(by_duration, key=lambda row: row[3])
    if weak_duration[2] >= 3 and weak_duration[3] < wr - 8:
        recs.append(
            f"Matchlaenge trainieren: In '{weak_duration[0]}' liegst du bei {weak_duration[3]:.0f}% Winrate{low_sample_note(weak_duration[2])}. "
            "Replay dort zuerst auf Eco-Uebergang, zweite TC/Tech-Entscheidung und gemeinsame Armee-Sammlung pruefen."
        )

    by_map = [row for row in winrate_by(games, lambda game: game.map_name) if row[2] >= 3]
    if by_map:
        weak_map = min(by_map, key=lambda row: row[3])
        strong_map = max(by_map, key=lambda row: row[3])
        if weak_map[3] < 45:
            recs.append(
                f"Map-Fokus: '{weak_map[0]}' ist auffaellig schwach ({weak_map[1]}/{weak_map[2]} Siege). "
                "Lege dafuer einen klaren Teamplan fest: wer scoutet Flanken, wer haelt Mitte/Relics, wer reagiert auf Raids."
            )
        if strong_map[2] >= 4 and strong_map[3] >= 65:
            recs.append(
                f"Uebertrage Erfolgsrezepte von '{strong_map[0]}' ({strong_map[3]:.0f}% Winrate): gleiche Rollenverteilung und Timing-Idee auf aehnliche Maps testen."
            )

    by_civ = [row for row in winrate_by(games, lambda game: game.player.civilization) if row[2] >= 3]
    if by_civ:
        weak_civ = min(by_civ, key=lambda row: row[3])
        best_civ = max(by_civ, key=lambda row: row[3])
        if weak_civ[3] <= 45:
            recs.append(
                f"Civ-Fokus: Mit {weak_civ[0]} ist die Quote niedrig ({weak_civ[1]}/{weak_civ[2]}). "
                "Entscheide, ob du sie pausierst oder nur auf passenden Maps spielst."
            )
        if best_civ[3] >= 60 and best_civ[2] >= 5:
            recs.append(
                f"Main-Civ-Kandidat: {best_civ[0]} performt stabil ({best_civ[3]:.0f}% aus {best_civ[2]} Spielen). "
                "Nutze sie als Referenz fuer Build-Order, Map-Kontrolle und Team-Timing."
            )

    deltas = [team_rating_delta(game) for game in games]
    valid_deltas = [delta for delta in deltas if delta is not None]
    if valid_deltas:
        underdog_losses = [game for game in games if not game.won and (team_rating_delta(game) or 0) < -75]
        favored_losses = [game for game in games if not game.won and (team_rating_delta(game) or 0) > 75]
        if favored_losses:
            recs.append(
                f"{len(favored_losses)} Niederlagen trotz Rating-Vorteil: Prioritaet ist sauberes Schliessen von Spielen, nicht riskante Solo-Pushes."
            )
        if underdog_losses and len(underdog_losses) >= max(2, math.ceil(total * 0.15)):
            recs.append(
                "Gegen staerkere Teams frueh vereinfachen: defensive Wall-Spots, sichere Trade-/Boom-Route und ein gemeinsamer erster Fight statt verstreuter Kaempfe."
            )

    recent = games[:10]
    recent_wr = pct(sum(1 for game in recent if game.won), len(recent))
    if len(recent) >= 6 and recent_wr + 15 < wr:
        recs.append(
            f"Aktuelle Form faellt ab: letzte {len(recent)} Spiele {recent_wr:.0f}% vs. gesamt {wr:.0f}%. "
            "Eine kurze Review-Session der letzten drei Niederlagen lohnt sich mehr als direkt weiter zu grinden."
        )

    if len(recs) < 5:
        recs.append(
            "Replay-Checkliste fuer jede Niederlage: 1. erster Scout-Fehler, 2. erste ungenutzte Armee, 3. erster unkoordinierter Fight, 4. Zeitpunkt fuer Trade/Boom/Imperial."
        )

    return recs[:8]


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_Keine Daten._"
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))
    lines = [
        "| " + " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)) + " |",
        "| " + " | ".join("-" * widths[idx] for idx in range(len(headers))) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row)) + " |")
    return "\n".join(lines)


def collect_report_data(games: list[NormalizedGame]) -> dict[str, Any]:
    total = len(games)
    wins = sum(1 for game in games if game.won)
    losses = total - wins
    durations = [game.duration_minutes for game in games]
    rating_diff = sum((game.player.rating_diff or 0) for game in games)
    mmr_diff = sum((game.player.mmr_diff or 0) for game in games)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    recent_rows = [
        [
            date_short(game.started_at),
            game.kind,
            game.map_name,
            game.player.civilization,
            "Sieg" if game.won else "Niederlage",
            f"{game.duration_minutes:.1f}",
            str(game.player.rating_diff or ""),
        ]
        for game in games[:12]
    ]

    mode_rows = [
        [mode, f"{wins}/{count}", f"{wr:.0f}%"]
        for mode, wins, count, wr in winrate_by(games, lambda game: game.kind)
    ]
    map_rows = [
        [name, f"{wins}/{count}", f"{wr:.0f}%"]
        for name, wins, count, wr in winrate_by(games, lambda game: game.map_name)[:10]
    ]
    civ_rows = [
        [name, f"{wins}/{count}", f"{wr:.0f}%"]
        for name, wins, count, wr in winrate_by(games, lambda game: game.player.civilization)[:10]
    ]
    duration_rows = [
        [name, f"{wins}/{count}", f"{wr:.0f}%"]
        for name, wins, count, wr in winrate_by(games, duration_bucket)
    ]

    ally_counts: Counter[str] = Counter()
    ally_wins: Counter[str] = Counter()
    enemy_civs_on_losses: Counter[str] = Counter()
    for game in games:
        for ally in game.allies:
            ally_counts[ally.name] += 1
            if game.won:
                ally_wins[ally.name] += 1
        if not game.won:
            for enemy in game.enemies:
                enemy_civs_on_losses[enemy.civilization] += 1

    ally_rows = [
        [name, f"{ally_wins[name]}/{count}", f"{pct(ally_wins[name], count):.0f}%"]
        for name, count in ally_counts.most_common(10)
    ]
    enemy_rows = [[civ, str(count)] for civ, count in enemy_civs_on_losses.most_common(10)]

    recommendations = generate_recommendations(games)
    latest_team_summary, latest_team_rows, latest_team_insights = build_latest_team_section(games)
    latest_review_rows = latest_teammate_review_rows(games)
    latest_trend_lines = latest_team_trend(games)
    team_comp_rows = build_team_composition_rows(games)
    teammate_fazit_rows = build_teammate_fazit_rows(games)

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "durations": durations,
        "rating_diff": rating_diff,
        "mmr_diff": mmr_diff,
        "generated_at": generated_at,
        "recent_rows": recent_rows,
        "mode_rows": mode_rows,
        "map_rows": map_rows,
        "civ_rows": civ_rows,
        "duration_rows": duration_rows,
        "ally_rows": ally_rows,
        "enemy_rows": enemy_rows,
        "recommendations": recommendations,
        "latest_team_summary": latest_team_summary,
        "latest_team_rows": latest_team_rows,
        "latest_team_insights": latest_team_insights,
        "latest_review_rows": latest_review_rows,
        "latest_trend_lines": latest_trend_lines,
        "team_comp_rows": team_comp_rows,
        "teammate_fazit_rows": teammate_fazit_rows,
    }


def build_short_report(player_name: str, profile_id: int, games: list[NormalizedGame]) -> str:
    data = collect_report_data(games)
    lines = [
        f"# Kurz-Auswertung: {player_name}",
        "",
        f"Erstellt: {data['generated_at']}",
        "",
        "## Spiel",
        "",
        latest_game_summary(games),
        "",
        "## Kurzreview",
        "",
    ]
    lines.extend(f"- {line}" for line in short_coaching_review(games))
    lines.extend(
        [
            "",
            "## Vergleich Zu Vorher",
            "",
        ]
    )
    lines.extend(f"- {line}" for line in previous_context(games))
    lines.extend(
        [
            "",
            "## Naechstes Mal",
            "",
        ]
    )
    lines.extend(f"{idx}. {line}" for idx, line in enumerate(next_match_focus(games), start=1))
    lines.extend(
        [
            "",
            "_Alle Tabellen, Referenzspiele und Gesamtstatistiken stehen im Detailbericht._",
        ]
    )
    return "\n".join(lines) + "\n"


def build_detail_report(player_name: str, profile_id: int, games: list[NormalizedGame]) -> str:
    data = collect_report_data(games)
    lines = [
        f"# Detail-Auswertung: {player_name}",
        "",
        f"Profil-ID: `{profile_id}`",
        f"Erstellt: {data['generated_at']}",
        "",
        "## Kurzfazit",
        "",
        f"- Ausgewertete 3v3/4v4-Spiele: **{data['total']}**",
        f"- Ergebnis: **{data['wins']} Siege / {data['losses']} Niederlagen** ({pct(data['wins'], data['total']):.1f}% Winrate)",
        f"- Durchschnittliche Spieldauer: **{mean(data['durations']):.1f} min**, Median: **{median(data['durations']):.1f} min**",
        f"- Rating-Differenz in diesen Spielen: **{data['rating_diff']:+d}**, MMR-Differenz: **{data['mmr_diff']:+d}**",
        "",
        "## Letztes Spiel Review",
        "",
        latest_game_summary(games),
        "",
        "### Teammitglieder Im Letzten Spiel",
        "",
        format_table(
            ["Mitspieler", "Civ", "Rolle", "Letzte 10", "Winrate", "Staerke", "Fokus"],
            data["latest_review_rows"],
        ),
        "",
        "### Teamtrend",
        "",
    ]
    lines.extend(f"- {line}" for line in data["latest_trend_lines"])
    lines.extend(
        [
            "",
        "## Verbesserungsvorschlaege",
        "",
        ]
    )
    lines.extend(f"{idx}. {rec}" for idx, rec in enumerate(data["recommendations"], start=1))
    lines.extend(
        [
            "",
            "## Letztes Team",
            "",
            data["latest_team_summary"],
            "",
        ]
    )
    lines.extend(f"- {insight}" for insight in data["latest_team_insights"])
    lines.extend(
        [
            "",
            format_table(["Datum", "Modus", "Map", "Resultat", "Min", "Deine Civ", "Team-Civs"], data["latest_team_rows"]),
            "",
            "## Wiederkehrende Team-Konstellationen",
            "",
            format_table(["Mitspieler-Gruppe", "Spiele", "Siege", "Winrate", "Letztes", "Gut", "Fokus"], data["team_comp_rows"]),
            "",
            "## Fazit Pro Mitspieler",
            "",
            format_table(
                ["Mitspieler", "Spiele", "Siege", "Winrate", "Haefige Civ", "Gut", "Schlecht/Fokus"],
                data["teammate_fazit_rows"],
            ),
            "",
            "## Nach Modus",
            "",
            format_table(["Modus", "Siege", "Winrate"], data["mode_rows"]),
            "",
            "## Maps",
            "",
            format_table(["Map", "Siege", "Winrate"], data["map_rows"]),
            "",
            "## Eigene Civs",
            "",
            format_table(["Civ", "Siege", "Winrate"], data["civ_rows"]),
            "",
            "## Matchlaenge",
            "",
            format_table(["Bereich", "Siege", "Winrate"], data["duration_rows"]),
            "",
            "## Haefige Mitspieler",
            "",
            format_table(["Mitspieler", "Siege", "Winrate"], data["ally_rows"]),
            "",
            "## Gegner-Civs in Niederlagen",
            "",
            format_table(["Civ", "Niederlagen"], data["enemy_rows"]),
            "",
            "## Letzte Spiele",
            "",
            format_table(["Datum", "Modus", "Map", "Civ", "Resultat", "Min", "Rating"], data["recent_rows"]),
            "",
            "## Replay-Notizen",
            "",
            "Ergaenze hier nach dem Anschauen einzelner Replays:",
            "",
            "- Spiel-ID:",
            "- Erster grosser Fehler:",
            "- Verpasster Team-Timing-Moment:",
            "- Naechstes konkretes Training:",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analysiert AoE4 3v3/4v4 Match-History und erstellt Verbesserungsvorschlaege."
    )
    parser.add_argument("player", help="AoE4World Profil-ID, Spielername, Profil-URL oder Game-URL")
    parser.add_argument("--limit", type=int, default=50, help="Spiele pro Modus abrufen, Standard: 50")
    parser.add_argument(
        "--modes",
        default="rm_3v3,rm_4v4,qm_3v3,qm_4v4",
        help="Kommagetrennte Modi, Standard: rm_3v3,rm_4v4,qm_3v3,qm_4v4",
    )
    parser.add_argument("--out", default="reports", help="Ausgabeordner, Standard: reports")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Erstellt statt der Auswertung einen Early-Game-Spielplan fuer das laufende/angegebene Spiel.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    unknown_modes = [mode for mode in modes if mode not in TEAM_MODES]
    if unknown_modes:
        print(f"Unbekannte Modi: {', '.join(unknown_modes)}", file=sys.stderr)
        print(f"Erlaubt: {', '.join(TEAM_MODES)}", file=sys.stderr)
        return 2

    target = parse_input_target(args.player)
    profile_id, player_name = resolve_profile_id(args.player)
    effective_limit = max(args.limit, 1)
    raw_games = fetch_games(profile_id, modes, effective_limit)
    if target.game_id is not None and not any(int(game.get("game_id", 0)) == target.game_id for game in raw_games):
        raw_games = fetch_games(profile_id, modes, max(effective_limit, 250))
    games = normalize_games(raw_games, profile_id)
    games, found_target = focus_games(games, target.game_id)
    if target.game_id is not None and not found_target:
        print(
            f"Warnung: Spiel {target.game_id} wurde in den geladenen 3v3/4v4-Spielen nicht gefunden. "
            "Der Bericht nutzt stattdessen das neueste gefundene Teamspiel.",
            file=sys.stderr,
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{safe_slug(player_name)}_{profile_id}"
    if args.plan:
        plan_output = out_dir / f"{base_name}_spielplan.md"
        if not games:
            raise SystemExit("Kein passendes 3v3/4v4-Spiel fuer den Spielplan gefunden.")
        plan_output.write_text(build_pregame_plan(player_name, profile_id, games[0]), encoding="utf-8")
        print(f"Spielplan erstellt: {plan_output}")
        return 0

    short_output = out_dir / f"{base_name}_kurzbericht.md"
    detail_output = out_dir / f"{base_name}_details.md"
    short_output.write_text(build_short_report(player_name, profile_id, games), encoding="utf-8")
    detail_output.write_text(build_detail_report(player_name, profile_id, games), encoding="utf-8")

    print(f"Kurzbericht erstellt: {short_output}")
    print(f"Detailbericht erstellt: {detail_output}")
    print(f"Ausgewertete Spiele: {len(games)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
