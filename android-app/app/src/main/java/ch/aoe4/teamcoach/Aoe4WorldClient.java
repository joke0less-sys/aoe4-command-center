package ch.aoe4.teamcoach;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;

final class Aoe4WorldClient {
    private static final String API = "https://aoe4world.com/api/v0";
    private static final String DATA = "https://data.aoe4world.com";
    private static final String USER_AGENT = "AoE4TeamCoach/1.0 Android";

    Models.LoadResult load(String input) throws Exception {
        Models.LoadResult result = new Models.LoadResult();
        result.profileId = resolveProfileId(input);
        JSONObject profile = get("/players/" + result.profileId);
        result.profileName = profile.optString("name", String.valueOf(result.profileId));
        result.selfStats = loadSelfStats(result.profileId, profile);
        result.civGlossary = loadCivilizationGlossary();
        result.match = loadLatestMatch(result.profileId);
        for (Models.Player enemy : result.match.enemies) {
            result.enemies.add(loadEnemyInfo(enemy));
        }
        return result;
    }

    private Models.CivGlossary loadCivilizationGlossary() {
        Models.CivGlossary glossary = new Models.CivGlossary();
        try {
            JSONObject data = get("/stats/rm_solo/civilizations");
            glossary.patch = data.optString("patch", "unbekannt");
            JSONArray rows = data.optJSONArray("data");
            if (rows == null) return glossary;
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row == null) continue;
                Models.CivOverview civ = new Models.CivOverview();
                civ.name = pretty(row.optString("civilization", "unknown"));
                civ.winRate = row.optDouble("win_rate", 0);
                civ.pickRate = row.optDouble("pick_rate", 0);
                civ.wins = row.optInt("win_count", 0);
                civ.games = row.optInt("games_count", 0);
                civ.medianDurationSeconds = row.optInt("duration_median", 0);
                glossary.civilizations.add(civ);
            }
            glossary.civilizations.sort(Comparator.comparing(civ -> civ.name));
        } catch (Exception ignored) { }
        return glossary;
    }

    Models.CivDetail loadCivDetail(String civilization) throws Exception {
        String slug = civDataSlug(civilization);
        Models.CivDetail detail = new Models.CivDetail();
        JSONObject civ = new JSONObject(readUrl(DATA + "/civilizations/" + slug + ".json"));
        detail.name = civ.optString("name", civilization);
        detail.description = civ.optString("description", "");
        detail.classes = civ.optString("classes", "");

        JSONArray overview = civ.optJSONArray("overview");
        if (overview != null) for (int i = 0; i < overview.length(); i++) {
            JSONObject item = overview.optJSONObject(i);
            if (item == null) continue;
            String title = item.optString("title", "Besonderheit");
            if (title.toLowerCase(Locale.ROOT).contains("unique unit")) continue;
            JSONArray list = item.optJSONArray("list");
            if (list != null) {
                for (int n = 0; n < list.length() && detail.mechanics.size() < 8; n++) {
                    String value = list.optString(n, "").trim();
                    if (!value.isEmpty()) detail.mechanics.add(value);
                }
            } else if (detail.mechanics.size() < 8) {
                String description = item.optString("description", "").replace('\n', ' ').trim();
                if (!description.isEmpty()) detail.mechanics.add(title + ": " + description);
            }
        }

        try {
            detail.specialUnits.addAll(loadUniqueNames(DATA + "/units/" + slug + ".json", 12));
        } catch (Exception ignored) { }
        try {
            detail.specialBuildings.addAll(loadUniqueNames(DATA + "/buildings/" + slug + ".json", 12));
        } catch (Exception ignored) { }
        return detail;
    }

    private List<String> loadUniqueNames(String url, int limit) throws Exception {
        String raw = readUrl(url);
        JSONArray rows = raw.trim().startsWith("[")
                ? new JSONArray(raw)
                : new JSONObject(raw).optJSONArray("data");
        if (rows == null) return new ArrayList<>();
        LinkedHashSet<String> names = new LinkedHashSet<>();
        LinkedHashSet<String> baseIds = new LinkedHashSet<>();
        for (int i = 0; i < rows.length() && names.size() < limit; i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null || !row.optBoolean("unique", false)) continue;
            String name = row.optString("name", "").trim();
            String baseId = row.optString("baseId", name);
            if (!name.isEmpty() && baseIds.add(baseId)) names.add(name);
        }
        return new ArrayList<>(names);
    }

    private String civDataSlug(String civilization) {
        String key = civilization.toLowerCase(Locale.ROOT).replace("'", "").replace(" ", "_");
        Map<String, String> slugs = new HashMap<>();
        slugs.put("abbasid_dynasty", "abbasid");
        slugs.put("golden_horde", "goldenhorde");
        slugs.put("holy_roman_empire", "hre");
        slugs.put("house_of_lancaster", "lancaster");
        slugs.put("jeanne_darc", "jeannedarc");
        slugs.put("jin_dynasty", "jindynasty");
        slugs.put("knights_templar", "templar");
        slugs.put("macedonian_dynasty", "macedonian");
        slugs.put("order_of_the_dragon", "orderofthedragon");
        slugs.put("sengoku_daimyo", "sengoku");
        slugs.put("tughlaq_dynasty", "tughlaq");
        slugs.put("zhu_xis_legacy", "zhuxi");
        slugs.put("delhi_sultanate", "delhi");
        return slugs.getOrDefault(key, key);
    }

    private Models.SelfStats loadSelfStats(long profileId, JSONObject profile) {
        Models.SelfStats stats = new Models.SelfStats();
        String rank = findTeamRank(profile);
        if (!rank.isEmpty()) stats.rank = rank;
        try {
            JSONObject data = get("/players/" + profileId + "/games?limit=50");
            JSONArray games = data.optJSONArray("games");
            Map<String, Models.CivStat> byCiv = new HashMap<>();
            if (games != null) for (int i = 0; i < games.length(); i++) {
                Models.Player me = findPlayer(games.optJSONObject(i), profileId);
                if (me == null || (!"win".equals(me.result) && !"loss".equals(me.result))) continue;
                stats.games++;
                boolean won = "win".equals(me.result);
                if (won) stats.wins++;
                if (stats.recentGames < 10) {
                    stats.recentGames++;
                    if (won) stats.recentWins++;
                }
                if (me.rating != null) {
                    if (stats.currentRating == null) stats.currentRating = me.rating;
                }
                Models.CivStat civ = byCiv.get(me.civ);
                if (civ == null) { civ = new Models.CivStat(); civ.civ = me.civ; byCiv.put(me.civ, civ); }
                civ.games++;
                if (won) civ.wins++;
            }
            stats.civilizations.addAll(byCiv.values());
            stats.civilizations.sort(Comparator.comparingInt((Models.CivStat c) -> c.games).reversed());
        } catch (Exception ignored) { }
        return stats;
    }

    private Models.Player findPlayer(JSONObject game, long profileId) {
        if (game == null) return null;
        JSONArray teams = game.optJSONArray("teams");
        if (teams == null) return null;
        for (int t = 0; t < teams.length(); t++) {
            JSONArray team = teams.optJSONArray(t);
            if (team == null) continue;
            for (int p = 0; p < team.length(); p++) {
                Models.Player player = parsePlayer(team.optJSONObject(p));
                if (player.id == profileId) return player;
            }
        }
        return null;
    }

    private long resolveProfileId(String raw) throws Exception {
        String value = raw.trim();
        if (value.contains("aoe4world.com/players/")) {
            value = value.substring(value.indexOf("/players/") + 9).split("[/?#-]")[0];
        }
        if (value.matches("\\d+")) return Long.parseLong(value);
        JSONObject search = get("/players/search?query=" + enc(value));
        JSONArray players = search.optJSONArray("players");
        if (players == null || players.length() == 0) throw new Exception("Kein AoE4World-Profil gefunden.");
        return players.getJSONObject(0).getLong("profile_id");
    }

    private Models.Match loadLatestMatch(long profileId) throws Exception {
        JSONObject data = get("/players/" + profileId + "/games?limit=10");
        JSONArray games = data.optJSONArray("games");
        if (games == null || games.length() == 0) throw new Exception("Keine öffentlichen Spiele gefunden.");
        for (int i = 0; i < games.length(); i++) {
            Models.Match match = parseMatch(games.getJSONObject(i), profileId);
            if (match != null && match.enemies.size() >= 1) return match;
        }
        throw new Exception("Kein Teamspiel in den letzten Spielen gefunden.");
    }

    private Models.Match parseMatch(JSONObject game, long profileId) {
        JSONArray teams = game.optJSONArray("teams");
        if (teams == null) return null;
        List<List<Models.Player>> parsed = new ArrayList<>();
        int own = -1;
        for (int t = 0; t < teams.length(); t++) {
            JSONArray team = teams.optJSONArray(t);
            if (team == null) continue;
            List<Models.Player> players = new ArrayList<>();
            for (int p = 0; p < team.length(); p++) {
                Models.Player player = parsePlayer(team.optJSONObject(p));
                players.add(player);
                if (player.id == profileId) own = parsed.size();
            }
            parsed.add(players);
        }
        if (own < 0 || parsed.size() < 2) return null;
        Models.Match match = new Models.Match();
        match.gameId = game.optLong("game_id");
        match.map = game.optString("map", "Unbekannte Karte");
        match.kind = game.optString("kind", "");
        for (Models.Player player : parsed.get(own)) {
            if (player.id == profileId) match.me = player; else match.allies.add(player);
        }
        for (int i = 0; i < parsed.size(); i++) if (i != own) match.enemies.addAll(parsed.get(i));
        return match;
    }

    private Models.Player parsePlayer(JSONObject entry) {
        if (entry == null) entry = new JSONObject();
        JSONObject raw = entry.optJSONObject("player");
        if (raw == null) raw = entry;
        Models.Player p = new Models.Player();
        p.id = raw.optLong("profile_id");
        p.name = raw.optString("name", "Unbekannt");
        p.civ = pretty(raw.optString("civilization", "Unbekannt"));
        p.result = raw.optString("result", "");
        if (!raw.isNull("rating")) p.rating = raw.optInt("rating");
        return p;
    }

    private Models.EnemyInfo loadEnemyInfo(Models.Player enemy) {
        Models.EnemyInfo info = new Models.EnemyInfo();
        info.player = enemy;
        info.rank = enemy.rating == null ? "Rang unbekannt" : "Team-Rating " + enemy.rating;
        try {
            JSONObject profile = get("/players/" + enemy.id);
            String betterRank = findTeamRank(profile);
            if (!betterRank.isEmpty()) info.rank = betterRank;
            JSONObject data = get("/players/" + enemy.id + "/games?limit=30");
            JSONArray games = data.optJSONArray("games");
            Map<String, Integer> civs = new HashMap<>();
            if (games != null) for (int i = 0; i < games.length(); i++) {
                Models.Match match = parseMatch(games.optJSONObject(i), enemy.id);
                if (match != null && match.me != null) {
                    civs.put(match.me.civ, civs.getOrDefault(match.me.civ, 0) + 1);
                    info.gamesAnalyzed++;
                }
            }
            civs.entrySet().stream().sorted(Map.Entry.<String,Integer>comparingByValue(Comparator.reverseOrder()))
                    .limit(3).forEach(e -> info.mainCivs.add(e.getKey() + " · " + e.getValue() + "×"));
        } catch (Exception ignored) { }
        if (info.mainCivs.isEmpty()) info.mainCivs.add(enemy.civ + " · aktuelles Spiel");
        return info;
    }

    private String findTeamRank(JSONObject profile) {
        Object raw = profile.opt("leaderboards");
        if (raw instanceof JSONArray) {
            JSONArray boards = (JSONArray) raw;
            for (int i = 0; i < boards.length(); i++) {
                JSONObject board = boards.optJSONObject(i);
                if (board == null) continue;
                String key = board.optString("short_name", board.optString("leaderboard", ""));
                if (key.equals("rm_team") || key.matches("rm_[234]v[234]")) {
                    String label = rankLabel(board);
                    if (!label.isEmpty()) return label;
                }
            }
            for (int i = 0; i < boards.length(); i++) {
                JSONObject board = boards.optJSONObject(i);
                if (board == null) continue;
                String key = board.optString("short_name", board.optString("leaderboard", ""));
                if (key.equals("rm_solo") || key.equals("rm_1v1")) {
                    String label = rankLabel(board);
                    if (!label.isEmpty()) return label;
                }
            }
        } else if (raw instanceof JSONObject) {
            JSONObject boards = (JSONObject) raw;
            for (String key : new String[]{"rm_team", "rm_4v4", "rm_3v3", "rm_2v2"}) {
                JSONObject board = boards.optJSONObject(key);
                String label = rankLabel(board);
                if (!label.isEmpty()) return label;
            }
            String solo = rankLabel(boards.optJSONObject("rm_solo"));
            if (!solo.isEmpty()) return solo;
        }
        return "";
    }

    private String rankLabel(JSONObject board) {
        if (board == null) return "";
        int rating = board.optInt("rating", 0);
        int rank = board.optInt("rank", 0);
        String level = pretty(board.optString("rank_level", ""));
        return rating <= 0 ? "" : (level.isEmpty() ? "Team" : level) + " · " + rating + (rank > 0 ? " · #" + rank : "");
    }

    private JSONObject get(String path) throws Exception {
        return new JSONObject(readUrl(API + path));
    }

    private String readUrl(String url) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestProperty("User-Agent", USER_AGENT);
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(20000);
        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) throw new Exception("AoE4World antwortet mit Fehler " + code + ".");
        StringBuilder text = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            String line; while ((line = reader.readLine()) != null) text.append(line);
        } finally { connection.disconnect(); }
        return text.toString();
    }

    private static String enc(String value) { return URLEncoder.encode(value, StandardCharsets.UTF_8); }
    private static String pretty(String value) {
        String[] parts = value.replace('_', ' ').split(" ");
        StringBuilder out = new StringBuilder();
        for (String p : parts) if (!p.isEmpty()) out.append(Character.toUpperCase(p.charAt(0))).append(p.substring(1)).append(' ');
        return out.toString().trim();
    }
}
