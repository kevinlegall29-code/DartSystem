import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../ble/dart_ble.dart';
import '../game/game_engine.dart';
import '../widgets/neon.dart';
import '../widgets/dartboard.dart';

class HomeScreen extends StatelessWidget {
  final String clientName;
  final String? clientLogo;
  const HomeScreen({super.key, required this.clientName, this.clientLogo});

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<DartBle>();
    final game = context.watch<GameEngine>();
    final theme = Theme.of(context);

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: const Alignment(0, -0.6),
            radius: 1.2,
            colors: [
              theme.colorScheme.surface,
              theme.scaffoldBackgroundColor,
            ],
          ),
        ),
        child: SafeArea(
          child: ble.status != BleStatus.connected
              ? _ConnectView(ble: ble, title: clientName)
              : Column(children: [
                  Expanded(
                    child: (game.active || game.winner != null)
                        ? _GameView(game: game)
                        : _SetupView(game: game, title: clientName),
                  ),
                  _BottomBar(ble: ble),
                ]),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _BottomBar extends StatelessWidget {
  final DartBle ble;
  const _BottomBar({required this.ble});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final connected = ble.status == BleStatus.connected;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: Colors.white.withValues(alpha: .06))),
      ),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
        _navIcon(Icons.bluetooth,
            color: connected ? theme.colorScheme.primary : Colors.redAccent,
            onTap: connected ? null : ble.connect),
        _navIcon(Icons.settings, color: Colors.white54, onTap: () {
          ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text("Réglages — bientôt")));
        }),
        _navIcon(Icons.bar_chart, color: Colors.white54, onTap: () {
          ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text("Statistiques — bientôt")));
        }),
      ]),
    );
  }

  Widget _navIcon(IconData icon, {required Color color, VoidCallback? onTap}) =>
      IconButton(
        onPressed: onTap,
        icon: Icon(icon, color: color, size: 26),
        splashRadius: 24,
      );
}

// ---------------------------------------------------------------------------

class _ConnectView extends StatelessWidget {
  final DartBle ble;
  final String title;
  const _ConnectView({required this.ble, required this.title});
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scanning = ble.status == BleStatus.scanning || ble.status == BleStatus.connecting;
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        NeonTitle(title, size: 34, color: theme.colorScheme.primary),
        const SizedBox(height: 40),
        Icon(Icons.bluetooth_searching, size: 70, color: theme.colorScheme.primary),
        const SizedBox(height: 18),
        Text(scanning ? "Recherche du DartSystem…" : "Non connecté",
            style: const TextStyle(fontSize: 18)),
        const SizedBox(height: 28),
        NeonButton(
          color: theme.colorScheme.primary,
          selected: true,
          padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 16),
          onTap: scanning ? null : ble.connect,
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            scanning
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.bluetooth),
            const SizedBox(width: 10),
            Text(scanning ? "Connexion…" : "Se connecter",
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ]),
        ),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------

class _GameDef {
  final String mode;
  final String label;
  final IconData icon;
  const _GameDef(this.mode, this.label, this.icon);
}

const _games = [
  _GameDef("501", "X01", Icons.tag),
  _GameDef("Cricket", "Cricket", Icons.grid_4x4),
  _GameDef("Cut Throat", "Cut Throat", Icons.content_cut),
  _GameDef("Around the Clock", "Around\nthe Clock", Icons.schedule),
  _GameDef("Shanghai", "Shanghai", Icons.location_city),
  _GameDef("Count Up", "Count Up", Icons.exposure_plus_1),
  _GameDef("Football", "Football", Icons.sports_soccer),
];

class _SetupView extends StatefulWidget {
  final GameEngine game;
  final String title;
  const _SetupView({required this.game, required this.title});
  @override
  State<_SetupView> createState() => _SetupViewState();
}

class _SetupViewState extends State<_SetupView> {
  String mode = "501";
  bool doubleOut = true;
  final players = <TextEditingController>[
    TextEditingController(text: "Joueur 1"),
    TextEditingController(text: "Joueur 2"),
  ];

  bool get isX01 => mode == "501" || mode == "301" || mode == "701";

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cyan = theme.colorScheme.primary;
    final purple = theme.colorScheme.secondary;

    return ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 8), children: [
      NeonTitle(widget.title, size: 30, color: cyan),
      const SizedBox(height: 4),
      Text("Sélectionne un jeu",
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white54, letterSpacing: 1.5)),
      const SizedBox(height: 20),

      // Grille de jeux (2 colonnes)
      LayoutBuilder(builder: (context, c) {
        const cols = 2;
        const gap = 12.0;
        final w = (c.maxWidth - gap) / cols;
        return Wrap(spacing: gap, runSpacing: gap, children: [
          for (final g in _games)
            SizedBox(
              width: g.mode == "Football" ? c.maxWidth : w,
              child: NeonButton(
                color: cyan,
                selected: mode == g.mode || (g.mode == "501" && isX01),
                onTap: () => setState(() => mode = g.mode),
                child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Icon(g.icon, color: cyan, size: 22),
                  const SizedBox(width: 10),
                  Flexible(
                    child: Text(g.label,
                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  ),
                ]),
              ),
            ),
        ]);
      }),

      // Sous-choix X01
      if (isX01) ...[
        const SizedBox(height: 14),
        Row(children: ["501", "301", "701"].map((m) => Expanded(
          child: Padding(padding: const EdgeInsets.symmetric(horizontal: 4),
            child: NeonButton(
              color: purple,
              selected: mode == m,
              padding: const EdgeInsets.symmetric(vertical: 12),
              onTap: () => setState(() => mode = m),
              child: Center(child: Text(m,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold))),
            )))).toList()),
        const SizedBox(height: 6),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          activeColor: cyan,
          title: const Text("Finir sur un double", style: TextStyle(fontSize: 14)),
          value: doubleOut, onChanged: (v) => setState(() => doubleOut = v)),
      ],

      const SizedBox(height: 18),
      Row(children: [
        const Icon(Icons.people, size: 18, color: Colors.white54),
        const SizedBox(width: 8),
        const Text("JOUEURS", style: TextStyle(letterSpacing: 1.5, color: Colors.white54)),
        const Spacer(),
        TextButton.icon(
          onPressed: () => setState(() =>
            players.add(TextEditingController(text: "Joueur ${players.length + 1}"))),
          icon: Icon(Icons.add, color: cyan, size: 18),
          label: Text("Ajouter", style: TextStyle(color: cyan)),
        ),
      ]),
      const SizedBox(height: 6),
      ...players.asMap().entries.map((e) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(children: [
          Expanded(child: TextField(controller: e.value,
            decoration: InputDecoration(
              isDense: true,
              filled: true,
              fillColor: Colors.white.withValues(alpha: .04),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: cyan.withValues(alpha: .3))),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: cyan.withValues(alpha: .3))),
            ))),
          if (players.length > 1)
            IconButton(icon: const Icon(Icons.close, color: Colors.white38),
              onPressed: () => setState(() => players.removeAt(e.key))),
        ]))),

      const SizedBox(height: 16),
      Center(child: NeonCircleButton(
        color: purple,
        icon: Icons.play_arrow,
        label: "Start",
        onTap: () {
          final names = players.map((c) => c.text.trim()).where((s) => s.isNotEmpty).toList();
          if (names.isNotEmpty) widget.game.start(mode, names, doubleOut: doubleOut);
        },
      )),
      const SizedBox(height: 12),
    ]);
  }
}

// ---------------------------------------------------------------------------

class _GameView extends StatelessWidget {
  final GameEngine game;
  const _GameView({required this.game});

  List<Impact> get _impacts {
    // Ignore les fléchettes ajoutées à la main (position inconnue → pas de croix)
    final shown = [for (final d in game.turnDarts) if (!d.manual) d];
    return [
      for (int i = 0; i < shown.length; i++)
        Impact(shown[i].x, shown[i].y, shown[i].label, latest: i == shown.length - 1),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cyan = theme.colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Column(children: [
        const SizedBox(height: 6),
        // Scoreboard compact
        game.isCricket ? _CricketBoard(game: game) : _X01Scores(game: game),

        if (game.contextLine.isNotEmpty)
          Padding(padding: const EdgeInsets.only(top: 4),
            child: Text(game.contextLine,
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600,
                letterSpacing: .5, color: theme.colorScheme.secondary))),

        // Cible avec impacts
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: DartboardView(impacts: _impacts, glow: cyan),
          ),
        ),

        // Message
        Text(game.message, textAlign: TextAlign.center,
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700,
            color: game.message.contains("BUST") ? Colors.redAccent
              : game.winner != null ? cyan : Colors.white)),
        const SizedBox(height: 8),

        // Volée précédente (plus petite, corrigeable même après retrait)
        if (game.type == GameType.x01 && game.prevTurnDarts.isNotEmpty) ...[
          Text("Volée précédente — ${game.players[game.prevTurnPlayer].name}",
            style: const TextStyle(fontSize: 11, color: Colors.white38)),
          const SizedBox(height: 4),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            for (int i = 0; i < game.prevTurnDarts.length; i++)
              GestureDetector(
                onTap: () => _correctPrev(context, i),
                child: Container(
                  width: 60, height: 38, margin: const EdgeInsets.symmetric(horizontal: 5),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: .03),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.white24)),
                  child: Text(game.prevTurnDarts[i].label,
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700,
                      color: game.prevTurnDarts[i].bust ? Colors.redAccent : Colors.white70)),
                )),
          ]),
          const SizedBox(height: 10),
        ],

        // Volée en cours (3 fléchettes)
        Row(mainAxisAlignment: MainAxisAlignment.center, children: List.generate(3, (i) {
          final d = i < game.turnDarts.length ? game.turnDarts[i] : null;
          return GestureDetector(
            onTap: () => _correct(context, i),
            child: Container(
              width: 86, height: 70, margin: const EdgeInsets.symmetric(horizontal: 6),
              decoration: BoxDecoration(
                color: d != null ? cyan.withValues(alpha: .12) : Colors.white.withValues(alpha: .02),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: d == null ? Colors.white12
                    : d.bust ? Colors.redAccent : cyan.withValues(alpha: .8), width: 1.5),
                boxShadow: d != null && !d.bust
                  ? [BoxShadow(color: cyan.withValues(alpha: .25), blurRadius: 8)] : null),
              child: d == null
                ? const Center(child: Icon(Icons.add, color: Colors.white12, size: 26))
                : Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Text(d.label, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
                    Text("${d.value} pts", style: const TextStyle(fontSize: 11, color: Colors.white60)),
                  ])));
        })),
        const SizedBox(height: 10),

        // Contrôles
        Row(children: [
          Expanded(child: NeonButton(
            color: cyan,
            onTap: game.nextPlayer,
            padding: const EdgeInsets.symmetric(vertical: 13),
            child: const Center(child: Text("Joueur suivant  →",
                style: TextStyle(fontWeight: FontWeight.w700))))),
          const SizedBox(width: 10),
          NeonButton(
            color: Colors.redAccent,
            onTap: game.stop,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
            child: const Text("Quitter")),
        ]),
        const SizedBox(height: 6),
      ]),
    );
  }

  void _correct(BuildContext context, int index) {
    final isEmpty = index >= game.turnDarts.length;
    showModalBottomSheet(context: context, backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => _CorrectionSheet(
        title: isEmpty ? "Ajouter une fléchette non détectée" : "Corriger la fléchette",
        onPick: (label) {
          if (isEmpty) {
            // Fléchette manquée par la détection → on l'ajoute à la main
            game.registerDart(label, valueFromLabel(label), multFromLabel(label), manual: true);
          } else {
            game.correctDart(index, label, valueFromLabel(label), multFromLabel(label));
          }
          Navigator.pop(context);
        }));
  }

  void _correctPrev(BuildContext context, int index) {
    showModalBottomSheet(context: context, backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => _CorrectionSheet(
        title: "Corriger la volée précédente",
        onPick: (label) {
          game.correctPrevDart(index, label, valueFromLabel(label), multFromLabel(label));
          Navigator.pop(context);
        }));
  }
}

class _X01Scores extends StatelessWidget {
  final GameEngine game;
  const _X01Scores({required this.game});
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(children: game.players.asMap().entries.map((e) {
      final p = e.value;
      final active = e.key == game.current && game.active;
      final col = active ? theme.colorScheme.primary : Colors.white;
      return Expanded(child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: NeonPanel(
          color: theme.colorScheme.primary,
          highlight: active,
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
          child: Column(children: [
            Text(p.name, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13, color: active ? col : Colors.white70)),
            Text("${p.score}", style: TextStyle(fontSize: 30, fontWeight: FontWeight.w800,
              color: col, shadows: active
                ? [Shadow(color: col.withValues(alpha: .7), blurRadius: 10)] : null)),
          ]),
        ),
      ));
    }).toList());
  }
}

class _CricketBoard extends StatelessWidget {
  final GameEngine game;
  const _CricketBoard({required this.game});

  String _marksSymbol(int m) => switch (m) { 1 => "/", 2 => "✕", >= 3 => "Ⓧ", _ => "" };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cell = const TextStyle(fontSize: 16, fontWeight: FontWeight.bold);
    return NeonPanel(
      color: theme.colorScheme.primary,
      padding: const EdgeInsets.all(8),
      child: Table(
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        columnWidths: const {0: FixedColumnWidth(48)},
        children: [
          TableRow(children: [
            const SizedBox(),
            ...game.players.asMap().entries.map((e) {
              final active = e.key == game.current && game.active;
              return Column(children: [
                Text(e.value.name, overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontWeight: FontWeight.w600,
                    color: active ? theme.colorScheme.primary : null)),
                Text("${e.value.score}", style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800,
                  color: active ? theme.colorScheme.primary : Colors.white)),
              ]);
            }),
          ]),
          ...cricketTargets.map((t) => TableRow(
            decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white12))),
            children: [
              Padding(padding: const EdgeInsets.symmetric(vertical: 6),
                child: Text(t == 25 ? "Bull" : "$t",
                  textAlign: TextAlign.center, style: cell.copyWith(color: theme.colorScheme.secondary))),
              ...game.players.map((p) {
                final m = p.marks[t] ?? 0;
                return Center(child: Text(_marksSymbol(m),
                  style: cell.copyWith(color: m >= 3 ? Colors.white38 : Colors.white)));
              }),
            ])),
        ]),
    );
  }
}

class _CorrectionSheet extends StatefulWidget {
  final void Function(String label) onPick;
  final String title;
  const _CorrectionSheet({required this.onPick, this.title = "Corriger la fléchette"});
  @override
  State<_CorrectionSheet> createState() => _CorrectionSheetState();
}

class _CorrectionSheetState extends State<_CorrectionSheet> {
  String mult = "S";
  @override
  Widget build(BuildContext context) {
    final cyan = Theme.of(context).colorScheme.primary;
    return Padding(padding: const EdgeInsets.all(16), child: Column(
      mainAxisSize: MainAxisSize.min, children: [
        Text(widget.title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        Row(children: [["S","Simple"],["D","Double"],["T","Triple"]].map((m) => Expanded(
          child: Padding(padding: const EdgeInsets.symmetric(horizontal: 4),
            child: OutlinedButton(
              onPressed: () => setState(() => mult = m[0]),
              style: OutlinedButton.styleFrom(backgroundColor: mult == m[0]
                ? cyan.withValues(alpha: .2) : null,
                side: BorderSide(color: cyan.withValues(alpha: .5))),
              child: Text(m[1]))))).toList()),
        const SizedBox(height: 10),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (int n = 1; n <= 20; n++)
            SizedBox(width: 56, child: OutlinedButton(
              style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 10)),
              onPressed: () => widget.onPick("$mult$n"), child: Text("$n"))),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: OutlinedButton(onPressed: () => widget.onPick("MISS"), child: const Text("MISS"))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton(onPressed: () => widget.onPick("BULL"), child: const Text("Bull 25"))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton(onPressed: () => widget.onPick("DBULL"), child: const Text("Bull 50"))),
        ]),
      ]));
  }
}
