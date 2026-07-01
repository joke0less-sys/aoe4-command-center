package ch.aoe4.teamcoach;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class StrategyEngine {
    private static final Set<String> FC = new HashSet<>(Arrays.asList(
            "Holy Roman Empire", "Japanese", "Sengoku Daimyo", "Ayyubids", "Malians"));
    private static final Set<String> TWO_TC = new HashSet<>(Arrays.asList(
            "Abbasid Dynasty", "Chinese", "Zhu Xis Legacy", "Jin Dynasty", "English"));
    private static final Set<String> AGGRO = new HashSet<>(Arrays.asList(
            "French", "Jeanne Darc", "Mongols", "Delhi Sultanate", "Knights Templar",
            "Order Of The Dragon", "Ottomans", "Golden Horde"));

    static List<String> teamPlan(Models.Match match) {
        List<Models.Player> team = match.ownTeam();
        if (team.size() == 1) return soloPlan(match, team.get(0));
        int ecoSlots = team.size() / 2; // abgerundet maximal 50 Prozent
        List<Models.Player> candidates = new ArrayList<>(team);
        candidates.sort(Comparator.comparingInt(StrategyEngine::ecoFit).reversed()
                .thenComparing(player -> player.name.toLowerCase()));
        Set<Long> selected = new HashSet<>();
        for (Models.Player player : candidates) {
            if (selected.size() >= ecoSlots || ecoFit(player) <= 0) break;
            selected.add(player.id);
        }

        List<String> rows = new ArrayList<>();
        for (Models.Player player : team) {
            String who = player.name + (player.id == match.me.id ? " (du)" : "");
            if (selected.contains(player.id)) {
                String role = FC.contains(player.civ) ? "FAST CASTLE / TECH" : "2 TC / ECO";
                rows.add(who + " · " + player.civ + "\n" + role + " – " + ecoAdvice(player.civ));
            } else {
                rows.add(who + " · " + player.civ + "\nAGGRO / MAP CONTROL – " + aggroAdvice(player.civ));
            }
        }
        rows.add(0, "Teamregel: " + selected.size() + " von " + team.size()
                + " Spielern erhält eine Boom-/Tech-Rolle. Das Limit liegt bei " + ecoSlots
                + " (maximal 50 %, abgerundet).\n"
                + mapAdvice(match.map));
        return rows;
    }

    private static List<String> soloPlan(Models.Match match, Models.Player player) {
        List<String> rows = new ArrayList<>();
        rows.add("1v1: Die Teambegrenzung entfällt. Der Plan richtet sich nach deiner Civ, der Karte und dem gegnerischen Opening.\n"
                + mapAdvice(match.map));
        if (FC.contains(player.civ)) {
            rows.add(player.name + " (du) · " + player.civ + "\nFAST CASTLE – " + ecoAdvice(player.civ)
                    + " Scoute früh die gegnerische Produktion und sichere dein Gold. Bei einem Feudal-All-in wechselst du rechtzeitig auf Verteidigung.");
        } else if (TWO_TC.contains(player.civ)) {
            rows.add(player.name + " (du) · " + player.civ + "\n2 TC / ECO – " + ecoAdvice(player.civ)
                    + " Spiele den zweiten TC nur, wenn dein Scout keinen starken frühen Druck erkennt.");
        } else if (AGGRO.contains(player.civ)) {
            rows.add(player.name + " (du) · " + player.civ + "\nAGGRO / MAP CONTROL – " + aggroAdvice(player.civ));
        } else {
            rows.add(player.name + " (du) · " + player.civ
                    + "\nFLEXIBEL – Fast Castle ist möglich, wenn dein Gold sicher ist und kein Feudal-All-in droht. Andernfalls bleibst du auf einem TC und baust zuerst Armee.");
        }
        return rows;
    }

    static String enemyThreat(Models.Player enemy) {
        if (AGGRO.contains(enemy.civ)) return "Früher Druck ist wahrscheinlich. Scoute Gold und Produktionsgebäude, verteidige kompakt und kontere nach dem ersten Angriff.";
        if (FC.contains(enemy.civ)) return "Fast Castle ist wahrscheinlich. Störe Gold und Relikte, damit das Castle-Timing nicht unbestraft bleibt.";
        if (TWO_TC.contains(enemy.civ)) return "Ein früher zweiter TC ist möglich. Finde die Expansion und setze die zusätzliche Wirtschaft vor Minute 15 unter Druck.";
        return "Diese Civ kann mehrere Openings spielen. Scoute Gold, frühe Produktion und eine mögliche Expansion, bevor du dein Angriffsziel festlegst.";
    }

    private static int ecoFit(Models.Player player) {
        if (player.civ.equals("Holy Roman Empire")) return 8;
        if (player.civ.equals("Japanese") || player.civ.equals("Sengoku Daimyo")) return 7;
        if (player.civ.equals("Abbasid Dynasty")) return 6;
        if (player.civ.equals("Chinese") || player.civ.equals("Zhu Xis Legacy") || player.civ.equals("Jin Dynasty")) return 5;
        if (FC.contains(player.civ)) return 4;
        if (TWO_TC.contains(player.civ)) return 3;
        if (AGGRO.contains(player.civ)) return 0;
        return 1;
    }

    private static String ecoAdvice(String civ) {
        if (civ.equals("Holy Roman Empire")) return "Nutze die Aachen-Wirtschaft für ein schnelles Castle-Timing und sichere anschließend die Relikte.";
        if (civ.equals("Japanese") || civ.equals("Sengoku Daimyo")) return "Bereite ein sicheres Castle-Timing vor und übernimm danach die Kontrolle über die Relikte.";
        if (civ.equals("Abbasid Dynasty")) return "Öffne mit dem Wirtschaftsflügel und setze den zweiten TC, solange deine Mitspieler den nötigen Raum schaffen.";
        if (civ.equals("Chinese") || civ.equals("Zhu Xis Legacy") || civ.equals("Jin Dynasty")) return "Skaliere deine Wirtschaft, aber wechsle bei frühem Druck sofort in Verteidigungseinheiten.";
        return "Baue einen Wirtschafts- oder Technologievorteil auf und kündige deinen nächsten Machtanstieg frühzeitig an.";
    }

    private static String aggroAdvice(String civ) {
        if (civ.equals("French") || civ.equals("Jeanne Darc")) return "Schicke frühe Ritter auf Gold und ungeschützte Wirtschaftslinien.";
        if (civ.equals("English")) return "Übe mit Langbögen und Speeren Druck auf den gegnerischen Boom-Spieler aus.";
        if (civ.equals("Delhi Sultanate")) return "Kontrolliere die Heiligen Stätten und die Kartenmitte mit deiner Feudalarmee.";
        if (civ.equals("Mongols")) return "Nutze Mobilität, Sicht und Raids, ohne dich in einen unkoordinierten All-in zu zwingen.";
        if (civ.equals("Knights Templar")) return "Nutze deine starken frühen Einheiten, um Gold und Expansionen zu bedrohen.";
        return "Bleibe zunächst auf einem TC, baue früh Armee und halte den Druck vom Boom-Spieler fern.";
    }

    private static String mapAdvice(String map) {
        String lower = map.toLowerCase();
        if (lower.contains("arabia")) return "Offene Karte: Scoute früh die Flanken und bedrohe ungeschütztes Gold.";
        if (lower.contains("hill") || lower.contains("dale")) return "Boom-Karte: Sichere die Mitte, ohne die gegnerische Wirtschaft ungestört skalieren zu lassen.";
        if (lower.contains("mountain") || lower.contains("gorge")) return "Karte mit Engstellen: Sammelt eure Armeen, bevor ihr einen Kampf beginnt.";
        return "Auf " + map + " solltest du zuerst Flanken, Gold, mögliche Expansionen und Handelsrouten scouten.";
    }
}
