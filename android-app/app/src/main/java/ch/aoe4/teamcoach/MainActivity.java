package ch.aoe4.teamcoach;

import android.app.Activity;
import android.app.Dialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import android.text.Editable;
import android.text.TextWatcher;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int BG = Color.rgb(6, 18, 28);
    private static final int SURFACE = Color.rgb(11, 29, 42);
    private static final int SURFACE_2 = Color.rgb(15, 38, 54);
    private static final int GOLD = Color.rgb(220, 174, 83);
    private static final int GOLD_DARK = Color.rgb(121, 88, 38);
    private static final int TEXT = Color.rgb(239, 235, 222);
    private static final int MUTED = Color.rgb(164, 174, 181);
    private static final int BLUE = Color.rgb(54, 159, 229);
    private static final int RED = Color.rgb(231, 75, 60);
    private static final int GREEN = Color.rgb(91, 195, 91);
    private static final int PURPLE = Color.rgb(184, 112, 223);
    private static final int ORANGE = Color.rgb(238, 151, 47);

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private LinearLayout content;
    private EditText profileInput;
    private ProgressBar progress;
    private TextView matchupTab;
    private TextView enemyTab;
    private TextView statsTab;
    private TextView civsTab;
    private Models.LoadResult current;
    private int selectedTab;
    private final Map<String, Models.CivDetail> civDetailCache = new HashMap<>();

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        buildUi();
        SharedPreferences prefs = getPreferences(MODE_PRIVATE);
        String saved = prefs.getString("aoe4world_profile", "");
        profileInput.setText(saved);
        if (!saved.isEmpty()) loadProfile();
    }

    private void buildUi() {
        LinearLayout root = column();
        root.setBackgroundColor(BG);

        root.addView(buildHeader());
        root.addView(buildProfileBar());

        progress = new ProgressBar(this);
        progress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(GOLD));
        progress.setVisibility(View.GONE);
        root.addView(progress, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(3)));

        content = column();
        content.setPadding(dp(14), dp(8), dp(14), dp(22));
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setClipToPadding(false);
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        root.addView(buildBottomNavigation());
        setContentView(root);
        showWelcome();
    }

    private View buildHeader() {
        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(16), dp(14), dp(12), dp(8));
        TextView crest = text("♜", 27, GOLD, true);
        crest.setGravity(Gravity.CENTER);
        header.addView(crest, new LinearLayout.LayoutParams(dp(42), dp(44)));
        LinearLayout titles = column();
        titles.addView(text("AGE OF EMPIRES 4", 21, GOLD, true));
        titles.addView(text("MATCHUP & STRATEGIE", 10, MUTED, true));
        header.addView(titles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        TextView refresh = text("↻", 29, GOLD, false);
        refresh.setGravity(Gravity.CENTER);
        refresh.setOnClickListener(v -> loadProfile());
        header.addView(refresh, new LinearLayout.LayoutParams(dp(52), dp(48)));
        return header;
    }

    private View buildProfileBar() {
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(14), dp(4), dp(14), dp(10));
        profileInput = new EditText(this);
        profileInput.setHint("AoE4World-Name, ID oder Profil-Link");
        profileInput.setSingleLine(true);
        profileInput.setTextSize(14);
        profileInput.setTextColor(TEXT);
        profileInput.setHintTextColor(MUTED);
        profileInput.setPadding(dp(13), 0, dp(13), 0);
        profileInput.setBackground(outline(SURFACE, GOLD_DARK, 1, 8));
        bar.addView(profileInput, new LinearLayout.LayoutParams(0, dp(48), 1));

        Button load = new Button(this);
        load.setText("LADEN");
        load.setTextColor(BG);
        load.setTextSize(12);
        load.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        load.setBackground(outline(GOLD, GOLD, 1, 8));
        load.setOnClickListener(v -> loadProfile());
        LinearLayout.LayoutParams loadParams = new LinearLayout.LayoutParams(dp(82), dp(48));
        loadParams.setMargins(dp(8), 0, 0, 0);
        bar.addView(load, loadParams);
        return bar;
    }

    private View buildBottomNavigation() {
        LinearLayout nav = new LinearLayout(this);
        nav.setPadding(dp(5), dp(2), dp(5), dp(5));
        nav.setBackground(outline(Color.rgb(5, 15, 23), GOLD_DARK, 1, 0));
        matchupTab = navItem("⚔\nMATCHUP", 0);
        enemyTab = navItem("♜\nGEGNER", 1);
        statsTab = navItem("▥\nMEINE STATS", 2);
        civsTab = navItem("♛\nCIVS", 3);
        nav.addView(matchupTab, new LinearLayout.LayoutParams(0, dp(65), 1));
        nav.addView(enemyTab, new LinearLayout.LayoutParams(0, dp(65), 1));
        nav.addView(statsTab, new LinearLayout.LayoutParams(0, dp(65), 1));
        nav.addView(civsTab, new LinearLayout.LayoutParams(0, dp(65), 1));
        updateNavigation();
        return nav;
    }

    private TextView navItem(String label, int tab) {
        TextView item = text(label, 12, MUTED, true);
        item.setGravity(Gravity.CENTER);
        item.setOnClickListener(v -> { selectedTab = tab; render(); });
        return item;
    }

    private void updateNavigation() {
        TextView[] tabs = {matchupTab, enemyTab, statsTab, civsTab};
        for (int i = 0; i < tabs.length; i++) {
            if (tabs[i] == null) continue;
            tabs[i].setTextColor(i == selectedTab ? GOLD : MUTED);
            tabs[i].setBackground(i == selectedTab ? outline(Color.rgb(18, 31, 39), GOLD, 2, 5) : null);
        }
    }

    private void loadProfile() {
        String input = profileInput.getText().toString().trim();
        if (input.length() < 3) { toast("Bitte AoE4World-Name, ID oder Profil-Link eingeben."); return; }
        getPreferences(MODE_PRIVATE).edit().putString("aoe4world_profile", input).apply();
        progress.setVisibility(View.VISIBLE);
        content.removeAllViews();
        content.addView(statusCard("AOE4WORLD", "Daten werden geladen …", GOLD));
        executor.execute(() -> {
            try {
                Models.LoadResult result = new Aoe4WorldClient().load(input);
                runOnUiThread(() -> { current = result; progress.setVisibility(View.GONE); render(); });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    progress.setVisibility(View.GONE);
                    content.removeAllViews();
                    content.addView(statusCard("LADEN FEHLGESCHLAGEN", e.getMessage(), RED));
                });
            }
        });
    }

    private void render() {
        updateNavigation();
        if (current == null) { showWelcome(); return; }
        content.removeAllViews();
        if (selectedTab == 1) renderEnemies();
        else if (selectedTab == 2) renderStats();
        else if (selectedTab == 3) renderCivGlossary();
        else renderMatchup();
    }

    private void renderMatchup() {
        Models.Match match = current.match;
        content.addView(screenTitle("⚔", "MATCHUP", match.map.toUpperCase(Locale.GERMAN) + " · " + teamMode(match)));
        content.addView(teamPanel("♜  DEIN TEAM", match.ownTeam(), BLUE, true));
        content.addView(teamPanel("⚔  GEGNER", match.enemies, RED, false));

        List<String> plan = StrategyEngine.teamPlan(match);
        if (!plan.isEmpty()) {
            content.addView(ruleBanner(plan.get(0)));
            content.addView(sectionTitle("♞", "EMPFOHLENER TEAMPLAN"));
            for (int i = 1; i < plan.size(); i++) content.addView(strategyCard(plan.get(i), strategyColor(i - 1)));
        }

        if (!match.enemies.isEmpty()) {
            Models.Player target = primaryTarget(match.enemies);
            content.addView(sectionTitle("◎", "PRIMÄRES ZIEL"));
            content.addView(targetCard(target));
        }
        content.addView(sectionTitle("⌛", "TIMING"));
        content.addView(timingRow());
    }

    private View teamPanel(String title, List<Models.Player> players, int accent, boolean own) {
        LinearLayout panel = column();
        panel.setPadding(dp(11), dp(10), dp(11), dp(11));
        panel.setBackground(outline(SURFACE, accent, 1, 9));
        panel.addView(text(title, 15, accent, true), bottom(8));
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        LinearLayout row = new LinearLayout(this);
        for (int i = 0; i < players.size(); i++) {
            Models.Player player = players.get(i);
            View card = playerCard(player, accent, own && player.id == current.profileId);
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(142), dp(142));
            if (i > 0) params.setMargins(dp(8), 0, 0, 0);
            row.addView(card, params);
        }
        scroll.addView(row);
        panel.addView(scroll);
        LinearLayout.LayoutParams params = bottom(10);
        panel.setLayoutParams(params);
        return panel;
    }

    private View playerCard(Models.Player player, int accent, boolean me) {
        LinearLayout card = column();
        card.setGravity(Gravity.CENTER_HORIZONTAL);
        card.setPadding(dp(7), dp(9), dp(7), dp(8));
        card.setBackground(outline(SURFACE_2, me ? GOLD : accent, me ? 2 : 1, 8));
        card.addView(text(me ? "DU" : shortName(player.name), 10, me ? GOLD : accent, true));
        TextView emblem = text(civSymbol(player.civ), 28, GOLD, true);
        emblem.setGravity(Gravity.CENTER);
        emblem.setBackground(outline(Color.rgb(20, 43, 58), GOLD, 2, 40));
        LinearLayout.LayoutParams emblemParams = new LinearLayout.LayoutParams(dp(62), dp(62));
        emblemParams.setMargins(0, dp(7), 0, dp(7));
        card.addView(emblem, emblemParams);
        TextView civ = text(shortCiv(player.civ).toUpperCase(Locale.GERMAN), 12, accent, true);
        civ.setGravity(Gravity.CENTER);
        civ.setMaxLines(2);
        card.addView(civ);
        return card;
    }

    private View ruleBanner(String rule) {
        String clean = rule.split("\n")[0].replace("Teamregel:", "TEAMREGEL ·").replace("1v1-Regel:", "1V1 ·");
        TextView banner = text("⚖  " + clean.toUpperCase(Locale.GERMAN), 13, GOLD, true);
        banner.setGravity(Gravity.CENTER_VERTICAL);
        banner.setPadding(dp(13), dp(12), dp(13), dp(12));
        banner.setBackground(outline(Color.rgb(18, 29, 36), GOLD, 2, 8));
        banner.setLayoutParams(bottom(8));
        return banner;
    }

    private View strategyCard(String raw, int accent) {
        String[] parts = raw.split("\n", 2);
        String title = parts[0].replace(" · ", "  ·  ");
        String body = parts.length > 1 ? parts[1] : "";
        LinearLayout card = new LinearLayout(this);
        card.setGravity(Gravity.CENTER_VERTICAL);
        card.setPadding(dp(11), dp(11), dp(10), dp(11));
        card.setBackground(outline(SURFACE, accent, 1, 9));
        TextView icon = text(roleSymbol(title), 23, accent, true);
        icon.setGravity(Gravity.CENTER);
        icon.setBackground(outline(Color.rgb(19, 40, 52), accent, 1, 35));
        card.addView(icon, new LinearLayout.LayoutParams(dp(54), dp(54)));
        LinearLayout copy = column();
        copy.addView(text(title.toUpperCase(Locale.GERMAN), 14, accent, true));
        TextView bodyView = text(body, 13, TEXT, false);
        bodyView.setLineSpacing(dp(2), 1f);
        copy.addView(bodyView, top(5));
        LinearLayout.LayoutParams copyParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        copyParams.setMargins(dp(11), 0, dp(4), 0);
        card.addView(copy, copyParams);
        card.addView(text("›", 28, accent, false));
        card.setLayoutParams(bottom(9));
        return card;
    }

    private View targetCard(Models.Player enemy) {
        LinearLayout card = column();
        card.setPadding(dp(13), dp(12), dp(13), dp(12));
        card.setBackground(outline(Color.rgb(35, 24, 27), RED, 1, 9));
        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        TextView emblem = text(civSymbol(enemy.civ), 24, GOLD, true);
        emblem.setGravity(Gravity.CENTER);
        emblem.setBackground(outline(Color.rgb(64, 31, 29), RED, 1, 30));
        top.addView(emblem, new LinearLayout.LayoutParams(dp(52), dp(52)));
        LinearLayout copy = column();
        copy.addView(text(shortCiv(enemy.civ).toUpperCase(Locale.GERMAN), 16, RED, true));
        copy.addView(text(likelyRole(enemy.civ), 12, MUTED, true), top(2));
        LinearLayout.LayoutParams copyParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        copyParams.setMargins(dp(10), 0, 0, 0);
        top.addView(copy, copyParams);
        card.addView(top);
        card.addView(text(StrategyEngine.enemyThreat(enemy), 13, TEXT, false), top(9));
        LinearLayout chips = new LinearLayout(this);
        chips.setGravity(Gravity.CENTER_VERTICAL);
        chips.addView(chip("Gold scouten", RED), weightedChip());
        chips.addView(chip("Eco finden", RED), weightedChip());
        chips.addView(chip("Timing callen", RED), weightedChip());
        card.addView(chips, top(10));
        card.setLayoutParams(bottom(10));
        return card;
    }

    private View timingRow() {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(timingBox("0–4", "SCOUT", BLUE), new LinearLayout.LayoutParams(0, dp(83), 1));
        row.addView(arrow());
        row.addView(timingBox("7–10", "DRUCK", GREEN), new LinearLayout.LayoutParams(0, dp(83), 1));
        row.addView(arrow());
        row.addView(timingBox("12–15", "SAMMELN", PURPLE), new LinearLayout.LayoutParams(0, dp(83), 1));
        row.setLayoutParams(bottom(14));
        return row;
    }

    private View timingBox(String time, String action, int accent) {
        LinearLayout box = column();
        box.setGravity(Gravity.CENTER);
        box.setBackground(outline(SURFACE, accent, 1, 7));
        box.addView(text(time, 20, accent, true));
        box.addView(text(action, 11, TEXT, true), top(2));
        return box;
    }

    private View arrow() {
        TextView arrow = text("›", 24, GOLD, true);
        arrow.setGravity(Gravity.CENTER);
        arrow.setLayoutParams(new LinearLayout.LayoutParams(dp(20), dp(50)));
        return arrow;
    }

    private void renderEnemies() {
        content.addView(screenTitle("⚔", "GEGNER-ÜBERSICHT", current.enemies.size() + " SPIELER ANALYSIERT"));
        int high = 0;
        for (Models.EnemyInfo info : current.enemies) {
            int danger = dangerLevel(info.player);
            if (danger >= 4) high++;
            content.addView(enemyDetailCard(info, danger));
        }
        content.addView(sectionTitle("◈", "GEGNER-GESAMTÜBERSICHT"));
        String summary = "Zivilisationen: " + civList(current.match.enemies)
                + "\nHohe Gefahr: " + high + " · Mittel/Niedrig: " + Math.max(0, current.enemies.size() - high)
                + "\n\nPasse den Teamplan nach dem Scout an. Prüfe zuerst Wirtschaft, Militärproduktion und Tech-Timing.";
        content.addView(statusCard("ZUSAMMENFASSUNG", summary, GOLD));
        content.addView(scoutingPanel());
    }

    private View enemyDetailCard(Models.EnemyInfo info, int danger) {
        LinearLayout card = column();
        card.setPadding(dp(13), dp(12), dp(13), dp(13));
        card.setBackground(outline(SURFACE, dangerColor(danger), 1, 9));

        LinearLayout identity = new LinearLayout(this);
        identity.setGravity(Gravity.CENTER_VERTICAL);
        TextView emblem = text(civSymbol(info.player.civ), 27, GOLD, true);
        emblem.setGravity(Gravity.CENTER);
        emblem.setBackground(outline(Color.rgb(48, 28, 29), GOLD, 2, 38));
        identity.addView(emblem, new LinearLayout.LayoutParams(dp(66), dp(66)));
        LinearLayout names = column();
        names.addView(text(shortCiv(info.player.civ).toUpperCase(Locale.GERMAN), 17, RED, true));
        names.addView(text(info.player.name, 13, TEXT, false), top(2));
        names.addView(text(info.rank, 12, BLUE, true), top(5));
        LinearLayout.LayoutParams nameParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        nameParams.setMargins(dp(12), 0, 0, 0);
        identity.addView(names, nameParams);
        card.addView(identity);

        card.addView(divider(), topBottom(11, 10));
        card.addView(labelValue("HÄUFIG GESPIELT", String.join("  ·  ", info.mainCivs), GREEN));
        card.addView(labelValue("WAHRSCHEINLICHE STRATEGIE", likelyRole(info.player.civ), GOLD), top(9));
        card.addView(text(StrategyEngine.enemyThreat(info.player), 13, TEXT, false), top(6));

        LinearLayout dangerRow = new LinearLayout(this);
        dangerRow.setGravity(Gravity.CENTER_VERTICAL);
        dangerRow.addView(text("GEFÄHRDUNG", 11, GOLD, true), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        dangerRow.addView(text(dangerName(danger), 13, dangerColor(danger), true));
        card.addView(dangerRow, top(12));
        card.addView(dangerMeter(danger), top(6));
        card.setLayoutParams(bottom(10));
        return card;
    }

    private View dangerMeter(int danger) {
        LinearLayout meter = new LinearLayout(this);
        for (int i = 1; i <= 5; i++) {
            View segment = new View(this);
            segment.setBackground(outline(i <= danger ? dangerColor(danger) : Color.rgb(38, 48, 54), Color.TRANSPARENT, 0, 2));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(7), 1);
            if (i > 1) params.setMargins(dp(4), 0, 0, 0);
            meter.addView(segment, params);
        }
        return meter;
    }

    private View scoutingPanel() {
        LinearLayout panel = column();
        panel.setPadding(dp(13), dp(12), dp(13), dp(13));
        panel.setBackground(outline(Color.rgb(21, 31, 37), GOLD_DARK, 1, 9));
        panel.addView(text("⚠  SCOUTING EMPFOHLEN", 14, GOLD, true));
        panel.addView(text("WIRTSCHAFT  ·  Ressourcen und Arbeiter prüfen\nMILITÄR  ·  Armee und Produktionsgebäude scouten\nTECHNOLOGIE  ·  Zeitalter, Relikte und Upgrades beobachten", 13, TEXT, false), top(8));
        panel.setLayoutParams(bottom(14));
        return panel;
    }

    private void renderStats() {
        Models.SelfStats stats = current.selfStats;
        content.addView(screenTitle("▥", "MEINE STATS", "LETZTE " + stats.games + " ÖFFENTLICHE SPIELE"));
        if (stats.games == 0) {
            content.addView(statusCard("NOCH KEINE STATISTIK", "Es konnten keine abgeschlossenen öffentlichen Spiele ausgewertet werden.", GOLD));
            return;
        }

        content.addView(statsHero(stats));
        Models.CivStat most = stats.civilizations.isEmpty() ? null : stats.civilizations.get(0);
        Models.CivStat best = qualified(stats.civilizations, true);
        Models.CivStat worst = qualified(stats.civilizations, false);
        content.addView(sectionTitle("♛", "CIV-AUSWERTUNG"));
        LinearLayout highlights = new LinearLayout(this);
        highlights.setGravity(Gravity.TOP);
        highlights.addView(statHighlight("BESTE", best, GREEN), highlightParams(0));
        highlights.addView(statHighlight("MEIST", most, BLUE), highlightParams(7));
        highlights.addView(statHighlight("SCHWÄCHSTE", worst, RED), highlightParams(7));
        content.addView(highlights, bottom(12));

        content.addView(sectionTitle("◫", "ALLE ZIVILISATIONEN"));
        for (Models.CivStat civ : stats.civilizations) content.addView(civStatRow(civ));
        content.addView(statusCard("DATENBASIS", "Beste und schwächste Civ werden erst ab mindestens 3 Spielen gewertet.", GOLD));
    }

    private void renderCivGlossary() {
        Models.CivGlossary glossary = current.civGlossary;
        content.addView(screenTitle("♛", "CIV-LEXIKON", "EINHEITEN · GEBÄUDE · BESONDERHEITEN"));
        content.addView(statusCard("SO FUNKTIONIERT ES", "Wähle eine Zivilisation aus. Die App zeigt ihre einzigartigen Einheiten, besonderen Gebäude und wichtigsten Mechaniken aus den AoE4World-Explorer-Daten.", GOLD));

        EditText search = new EditText(this);
        search.setHint("Zivilisation suchen …");
        search.setSingleLine(true);
        search.setTextSize(14);
        search.setTextColor(TEXT);
        search.setHintTextColor(MUTED);
        search.setPadding(dp(13), 0, dp(13), 0);
        search.setBackground(outline(SURFACE, GOLD_DARK, 1, 8));
        content.addView(search, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)));

        TextView count = text("", 11, MUTED, true);
        count.setPadding(dp(3), dp(9), 0, dp(7));
        content.addView(count);
        LinearLayout list = column();
        content.addView(list);

        Runnable refresh = () -> renderCivGlossaryRows(list, count, glossary.civilizations, search.getText().toString());
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) { refresh.run(); }
            @Override public void afterTextChanged(Editable s) { }
        });
        refresh.run();
    }

    private void renderCivGlossaryRows(LinearLayout list, TextView count, List<Models.CivOverview> civilizations, String query) {
        list.removeAllViews();
        String needle = query.trim().toLowerCase(Locale.GERMAN);
        int shown = 0;
        for (int i = 0; i < civilizations.size(); i++) {
            Models.CivOverview civ = civilizations.get(i);
            if (!needle.isEmpty() && !civ.name.toLowerCase(Locale.GERMAN).contains(needle)) continue;
            list.addView(civGlossaryCard(civ, i + 1));
            shown++;
        }
        count.setText(shown + " ZIVILISATIONEN · ANTIPPEN FÜR DETAILS");
        if (shown == 0) list.addView(statusCard("NICHT GEFUNDEN", "Keine Zivilisation passt zu deiner Suche.", RED));
    }

    private View civGlossaryCard(Models.CivOverview civ, int position) {
        int accent = strategyColor(position - 1);
        LinearLayout card = column();
        card.setPadding(dp(13), dp(12), dp(13), dp(12));
        card.setBackground(outline(SURFACE, accent, 1, 9));

        LinearLayout heading = new LinearLayout(this);
        heading.setGravity(Gravity.CENTER_VERTICAL);
        TextView emblem = text(civSymbol(civ.name), 25, GOLD, true);
        emblem.setGravity(Gravity.CENTER);
        emblem.setBackground(outline(Color.rgb(20, 43, 58), GOLD, 2, 34));
        heading.addView(emblem, new LinearLayout.LayoutParams(dp(58), dp(58)));
        LinearLayout title = column();
        title.addView(text(civ.name.toUpperCase(Locale.GERMAN), 16, accent, true));
        title.addView(text(likelyRole(civ.name), 11, MUTED, true), top(3));
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        titleParams.setMargins(dp(11), 0, 0, 0);
        heading.addView(title, titleParams);
        TextView open = text("›", 28, GOLD, true);
        open.setGravity(Gravity.CENTER);
        heading.addView(open, new LinearLayout.LayoutParams(dp(42), dp(42)));
        card.addView(heading);

        card.addView(divider(), topBottom(10, 9));
        card.addView(text("⚔  Besondere Einheiten\n♜  Gebäude und Landmarks\n✦  Civ-Boni und Mechaniken", 12, TEXT, false));
        card.setOnClickListener(v -> openCivDetail(civ.name));
        card.setLayoutParams(bottom(9));
        return card;
    }

    private void openCivDetail(String civilization) {
        Models.CivDetail cached = civDetailCache.get(civilization);
        if (cached != null) { showCivDetail(cached); return; }
        progress.setVisibility(View.VISIBLE);
        executor.execute(() -> {
            try {
                Models.CivDetail detail = new Aoe4WorldClient().loadCivDetail(civilization);
                civDetailCache.put(civilization, detail);
                runOnUiThread(() -> { progress.setVisibility(View.GONE); showCivDetail(detail); });
            } catch (Exception error) {
                runOnUiThread(() -> { progress.setVisibility(View.GONE); toast("Civ-Daten konnten nicht geladen werden: " + error.getMessage()); });
            }
        });
    }

    private void showCivDetail(Models.CivDetail detail) {
        Dialog dialog = new Dialog(this);
        LinearLayout page = column();
        page.setPadding(dp(16), dp(15), dp(16), dp(18));
        page.setBackground(outline(BG, GOLD, 2, 10));
        page.addView(text(civSymbol(detail.name) + "  " + detail.name.toUpperCase(Locale.GERMAN), 20, GOLD, true));
        if (!detail.classes.isEmpty()) page.addView(text(detail.classes.toUpperCase(Locale.GERMAN), 11, BLUE, true), top(4));
        if (!detail.description.isEmpty()) page.addView(text(detail.description, 13, TEXT, false), top(10));
        page.addView(detailSection("⚔  BESONDERE EINHEITEN", detail.specialUnits, GREEN), top(13));
        page.addView(detailSection("♜  GEBÄUDE & LANDMARKS", detail.specialBuildings, ORANGE), top(10));
        page.addView(detailSection("✦  WAS IST SPEZIELL?", detail.mechanics, PURPLE), top(10));
        TextView source = text("Quelle: AoE4World Explorer Data", 10, MUTED, false);
        page.addView(source, top(12));
        TextView close = text("SCHLIESSEN", 13, BG, true);
        close.setGravity(Gravity.CENTER);
        close.setBackground(outline(GOLD, GOLD, 1, 7));
        close.setOnClickListener(v -> dialog.dismiss());
        page.addView(close, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(page);
        dialog.setContentView(scroll);
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawableResource(android.R.color.transparent);
            dialog.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        }
        dialog.setOnShowListener(v -> {
            if (dialog.getWindow() != null) dialog.getWindow().setLayout((int) (getResources().getDisplayMetrics().widthPixels * .94f), (int) (getResources().getDisplayMetrics().heightPixels * .9f));
        });
        dialog.show();
    }

    private View detailSection(String title, List<String> entries, int accent) {
        LinearLayout section = column();
        section.setPadding(dp(12), dp(11), dp(12), dp(11));
        section.setBackground(outline(SURFACE, accent, 1, 8));
        section.addView(text(title, 13, accent, true));
        if (entries.isEmpty()) {
            section.addView(text("Keine besonderen Einträge in den verfügbaren Daten gefunden.", 12, MUTED, false), top(6));
        } else {
            for (String entry : entries) section.addView(text("•  " + entry, 12, TEXT, false), top(6));
        }
        return section;
    }


    private View statsHero(Models.SelfStats stats) {
        LinearLayout panel = new LinearLayout(this);
        panel.setGravity(Gravity.CENTER_VERTICAL);
        panel.setPadding(dp(14), dp(14), dp(14), dp(14));
        panel.setBackground(outline(SURFACE, GOLD, 1, 10));
        TextView rate = text(stats.winRate() + "%\nWINRATE", 18, stats.winRate() >= 50 ? GREEN : RED, true);
        rate.setGravity(Gravity.CENTER);
        rate.setBackground(outline(Color.rgb(15, 35, 47), GOLD, 3, 60));
        panel.addView(rate, new LinearLayout.LayoutParams(dp(105), dp(105)));
        LinearLayout copy = column();
        copy.addView(text(current.profileName.toUpperCase(Locale.GERMAN), 18, GOLD, true));
        copy.addView(text(stats.rank, 13, BLUE, true), top(4));
        copy.addView(text(stats.games + " Spiele  ·  " + stats.wins + " Siege", 14, TEXT, false), top(9));
        int recentRate = stats.recentGames == 0 ? 0 : Math.round(stats.recentWins * 100f / stats.recentGames);
        copy.addView(text("LETZTE FORM  " + stats.recentWins + "/" + stats.recentGames + "  ·  " + recentRate + "%", 12, recentRate >= 50 ? GREEN : ORANGE, true), top(7));
        LinearLayout.LayoutParams copyParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        copyParams.setMargins(dp(14), 0, 0, 0);
        panel.addView(copy, copyParams);
        panel.setLayoutParams(bottom(10));
        return panel;
    }

    private View statHighlight(String label, Models.CivStat civ, int accent) {
        LinearLayout box = column();
        box.setGravity(Gravity.CENTER_HORIZONTAL);
        box.setPadding(dp(6), dp(10), dp(6), dp(10));
        box.setBackground(outline(SURFACE, accent, 1, 8));
        box.addView(text(label, 9, accent, true));
        TextView emblem = text(civ == null ? "?" : civSymbol(civ.civ), 22, GOLD, true);
        emblem.setGravity(Gravity.CENTER);
        box.addView(emblem, new LinearLayout.LayoutParams(dp(44), dp(44)));
        TextView name = text(civ == null ? "ZU WENIG DATEN" : shortCiv(civ.civ).toUpperCase(Locale.GERMAN), 10, TEXT, true);
        name.setGravity(Gravity.CENTER);
        name.setMaxLines(2);
        box.addView(name);
        box.addView(text(civ == null ? "–" : civ.winRate() + "% · " + civ.games + " Sp.", 10, accent, true), top(5));
        return box;
    }

    private View civStatRow(Models.CivStat civ) {
        LinearLayout row = column();
        row.setPadding(dp(12), dp(10), dp(12), dp(10));
        row.setBackground(outline(SURFACE, GOLD_DARK, 1, 7));
        LinearLayout labels = new LinearLayout(this);
        labels.setGravity(Gravity.CENTER_VERTICAL);
        labels.addView(text(civSymbol(civ.civ) + "  " + civ.civ, 13, TEXT, true), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        labels.addView(text(civ.winRate() + "%", 14, civ.winRate() >= 50 ? GREEN : RED, true));
        row.addView(labels);
        row.addView(progressBar(civ.winRate(), civ.winRate() >= 50 ? GREEN : RED), top(7));
        row.addView(text(civ.games + " Spiele · " + civ.wins + " Siege", 11, MUTED, false), top(5));
        row.setLayoutParams(bottom(7));
        return row;
    }

    private View progressBar(int percent, int accent) {
        FrameLayout track = new FrameLayout(this);
        track.setBackground(outline(Color.rgb(35, 47, 54), Color.TRANSPARENT, 0, 3));
        View fill = new View(this);
        fill.setBackground(outline(accent, Color.TRANSPARENT, 0, 3));
        track.addView(fill, new FrameLayout.LayoutParams(0, dp(7)));
        track.post(() -> {
            FrameLayout.LayoutParams params = (FrameLayout.LayoutParams) fill.getLayoutParams();
            params.width = Math.max(dp(3), track.getWidth() * percent / 100);
            fill.setLayoutParams(params);
        });
        track.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(7)));
        return track;
    }

    private void showWelcome() {
        content.removeAllViews();
        content.addView(screenTitle("♜", "BEREIT FÜR DEN TEAMFIGHT", "AOE4WORLD VERBINDEN"));
        content.addView(statusCard("PROFIL LADEN", "Gib oben deinen AoE4World-Namen, deine Profil-ID oder den Profil-Link ein. Die App speichert die Eingabe und lädt sie beim nächsten Start automatisch.", GOLD));
        content.addView(statusCard("VIER BEREICHE", "MATCHUP · Rollen, Teamregel und Timing\nGEGNER · Rang, Civ-Historie und Gefährdung\nMEINE STATS · Winrate, Form und Civ-Auswertung\nCIVS · durchsuchbares Glossar mit AoE4World-Metadaten", BLUE));
    }

    private View screenTitle(String icon, String title, String subtitle) {
        LinearLayout block = column();
        TextView heading = text(icon + "  " + title, 20, GOLD, true);
        block.addView(heading);
        block.addView(text(subtitle, 11, MUTED, true), top(3));
        block.setPadding(dp(2), dp(7), dp(2), dp(12));
        return block;
    }

    private TextView sectionTitle(String icon, String title) {
        TextView view = text(icon + "  " + title, 15, GOLD, true);
        view.setPadding(dp(3), dp(11), 0, dp(9));
        return view;
    }

    private View statusCard(String title, String body, int accent) {
        LinearLayout card = column();
        card.setPadding(dp(14), dp(13), dp(14), dp(13));
        card.setBackground(outline(SURFACE, accent, 1, 9));
        card.addView(text(title, 14, accent, true));
        TextView bodyView = text(body == null ? "Unbekannter Fehler" : body, 13, TEXT, false);
        bodyView.setLineSpacing(dp(3), 1f);
        card.addView(bodyView, top(7));
        card.setLayoutParams(bottom(10));
        return card;
    }

    private View labelValue(String label, String value, int accent) {
        LinearLayout block = column();
        block.addView(text(label, 10, accent, true));
        block.addView(text(value, 13, TEXT, false), top(4));
        return block;
    }

    private View divider() {
        View line = new View(this);
        line.setBackgroundColor(Color.rgb(49, 62, 69));
        line.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)));
        return line;
    }

    private TextView chip(String value, int accent) {
        TextView chip = text(value, 10, TEXT, true);
        chip.setGravity(Gravity.CENTER);
        chip.setPadding(dp(4), dp(6), dp(4), dp(6));
        chip.setBackground(outline(Color.rgb(25, 29, 34), accent, 1, 5));
        return chip;
    }

    private LinearLayout.LayoutParams weightedChip() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        params.setMargins(dp(3), 0, dp(3), 0);
        return params;
    }

    private LinearLayout.LayoutParams highlightParams(int left) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(135), 1);
        params.setMargins(dp(left), 0, 0, 0);
        return params;
    }

    private Models.CivStat qualified(List<Models.CivStat> civs, boolean best) {
        List<Models.CivStat> qualified = new ArrayList<>();
        for (Models.CivStat civ : civs) if (civ.games >= 3) qualified.add(civ);
        if (qualified.isEmpty()) return null;
        qualified.sort((a, b) -> best ? Integer.compare(b.winRate(), a.winRate()) : Integer.compare(a.winRate(), b.winRate()));
        return qualified.get(0);
    }

    private Models.Player primaryTarget(List<Models.Player> enemies) {
        return enemies.stream().max(Comparator.comparingInt(this::dangerLevel)).orElse(enemies.get(0));
    }

    private int dangerLevel(Models.Player player) {
        int danger = 2;
        if (player.rating != null && player.rating >= 1400) danger++;
        String role = likelyRole(player.civ);
        if (role.contains("AGGRO") || role.contains("FAST CASTLE")) danger++;
        return Math.min(5, danger);
    }

    private int dangerColor(int danger) {
        if (danger >= 4) return RED;
        if (danger == 3) return ORANGE;
        return GREEN;
    }

    private String dangerName(int danger) {
        if (danger >= 5) return "HOCH";
        if (danger == 4) return "MITTEL–HOCH";
        if (danger == 3) return "MITTEL";
        return "NIEDRIG";
    }

    private String likelyRole(String civ) {
        if (contains(civ, "French", "Jeanne", "Mongol", "Delhi", "Templar", "Ottoman", "Golden Horde")) return "AGGRO / MAP CONTROL";
        if (contains(civ, "Holy Roman", "Japanese", "Sengoku", "Ayyubid", "Malians")) return "FAST CASTLE / TECH";
        if (contains(civ, "Abbasid", "Chinese", "Zhu Xi", "Jin Dynasty", "English")) return "2 TC / ECO";
        return "FLEXIBEL / SCOUT-ABHÄNGIG";
    }

    private boolean contains(String value, String... needles) {
        for (String needle : needles) if (value.toLowerCase(Locale.ROOT).contains(needle.toLowerCase(Locale.ROOT))) return true;
        return false;
    }

    private String roleSymbol(String title) {
        if (title.contains("FAST CASTLE") || title.contains("TECH")) return "♜";
        if (title.contains("2 TC") || title.contains("ECO")) return "♛";
        if (title.contains("MAP")) return "◎";
        return "♞";
    }

    private int strategyColor(int index) {
        int[] colors = {BLUE, GREEN, PURPLE, ORANGE};
        return colors[index % colors.length];
    }

    private String civSymbol(String civ) {
        String clean = shortCiv(civ).replaceAll("[^A-Za-zÄÖÜäöü]", "");
        if (clean.isEmpty()) return "?";
        return clean.substring(0, 1).toUpperCase(Locale.GERMAN);
    }

    private String shortName(String name) {
        if (name == null || name.isEmpty()) return "ALLY";
        return name.length() > 13 ? name.substring(0, 12) + "…" : name;
    }

    private String shortCiv(String civ) {
        if (civ == null) return "Unbekannt";
        return civ.replace("Holy Roman Empire", "HRE")
                .replace("Abbasid Dynasty", "Abbasiden")
                .replace("Delhi Sultanate", "Delhi")
                .replace("Order Of The Dragon", "Orden des Drachen")
                .replace("Zhu Xis Legacy", "Zhu Xi");
    }

    private String teamMode(Models.Match match) {
        int size = match.ownTeam().size();
        return size + "v" + match.enemies.size();
    }

    private GradientDrawable outline(int fill, int stroke, int strokeWidth, int radius) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{lighten(fill, 7), fill});
        drawable.setCornerRadius(dp(radius));
        if (strokeWidth > 0 && stroke != Color.TRANSPARENT) drawable.setStroke(dp(strokeWidth), stroke);
        return drawable;
    }

    private int lighten(int color, int amount) {
        return Color.rgb(Math.min(255, Color.red(color) + amount), Math.min(255, Color.green(color) + amount), Math.min(255, Color.blue(color) + amount));
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.create("serif", Typeface.BOLD));
        else view.setTypeface(Typeface.create("sans", Typeface.NORMAL));
        return view;
    }

    private LinearLayout column() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.VERTICAL);
        return view;
    }

    private LinearLayout.LayoutParams bottom(int value) {
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, 0, 0, dp(value));
        return params;
    }

    private LinearLayout.LayoutParams top(int value) {
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, dp(value), 0, 0);
        return params;
    }

    private LinearLayout.LayoutParams topBottom(int top, int bottom) {
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, dp(top), 0, dp(bottom));
        return params;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private String civList(List<Models.Player> players) {
        StringBuilder result = new StringBuilder();
        for (Models.Player player : players) {
            if (result.length() > 0) result.append(" · ");
            result.append(shortCiv(player.civ));
        }
        return result.toString();
    }
    private void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_LONG).show(); }
    @Override protected void onDestroy() { super.onDestroy(); executor.shutdownNow(); }
}
