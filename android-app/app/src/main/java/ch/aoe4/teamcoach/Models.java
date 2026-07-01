package ch.aoe4.teamcoach;

import java.util.ArrayList;
import java.util.List;

final class Models {
    static final class Player {
        long id;
        String name = "Unbekannt";
        String civ = "Unbekannt";
        String result = "";
        Integer rating;
    }

    static final class Match {
        long gameId;
        String map = "Unbekannte Karte";
        String kind = "";
        Player me;
        List<Player> allies = new ArrayList<>();
        List<Player> enemies = new ArrayList<>();

        List<Player> ownTeam() {
            List<Player> result = new ArrayList<>();
            result.add(me);
            result.addAll(allies);
            return result;
        }
    }

    static final class EnemyInfo {
        Player player;
        String rank = "Rang unbekannt";
        List<String> mainCivs = new ArrayList<>();
        int gamesAnalyzed;
    }

    static final class LoadResult {
        long profileId;
        String profileName;
        Match match;
        List<EnemyInfo> enemies = new ArrayList<>();
        SelfStats selfStats = new SelfStats();
        CivGlossary civGlossary = new CivGlossary();
    }

    static final class CivOverview {
        String name;
        double winRate;
        double pickRate;
        int wins;
        int games;
        int medianDurationSeconds;
    }

    static final class CivGlossary {
        String patch = "unbekannt";
        List<CivOverview> civilizations = new ArrayList<>();
    }

    static final class CivDetail {
        String name;
        String description = "";
        String classes = "";
        List<String> specialUnits = new ArrayList<>();
        List<String> specialBuildings = new ArrayList<>();
        List<String> mechanics = new ArrayList<>();
    }

    static final class CivStat {
        String civ;
        int games;
        int wins;

        int winRate() { return games == 0 ? 0 : Math.round(wins * 100f / games); }
    }

    static final class SelfStats {
        int games;
        int wins;
        int recentWins;
        int recentGames;
        Integer currentRating;
        String rank = "Rang unbekannt";
        List<CivStat> civilizations = new ArrayList<>();

        int winRate() { return games == 0 ? 0 : Math.round(wins * 100f / games); }
    }
}
