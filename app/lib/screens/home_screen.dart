import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../ble/dart_ble.dart';
import '../game/game_engine.dart';

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
      appBar: AppBar(
        backgroundColor: theme.colorScheme.surface,
        title: Row(children: [
          if (clientLogo == null) const Text("🎯  "),
          Text(clientName, style: const TextStyle(fontWeight: FontWeight.bold)),
        ]),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 14),
            child: _BleIndicator(status: ble.status),
          ),
        ],
      ),
      body: SafeArea(
        child: ble.status != BleStatus.connected
            ? _ConnectView(ble: ble)
            : (game.active || game.winner != null
                ? _GameView(game: game)
                : _SetupView(game: game)),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _BleIndicator extends StatelessWidget {
  final BleStatus status;
  const _BleIndicator({required this.status});
  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (status) {
      BleStatus.connected => (Colors.green, "Connecté"),
      BleStatus.scanning => (Colors.orange, "Recherche…"),
      BleStatus.connecting => (Colors.orange, "Connexion…"),
      _ => (Colors.red, "Déconnecté"),
    };
    return Row(children: [
      Container(width: 11, height: 11, decoration: BoxDecoration(
        color: color, shape: BoxShape.circle,
        boxShadow: [BoxShadow(color: color.withValues(alpha: .6), blurRadius: 6)])),
      const SizedBox(width: 6),
      Text(label, style: const TextStyle(fontSize: 12)),
    ]);
  }
}

class _ConnectView extends StatelessWidget {
  final DartBle ble;
  const _ConnectView({required this.ble});
  @override
  Widget build(BuildContext context) {
    final scanning = ble.status == BleStatus.scanning || ble.status == BleStatus.connecting;
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.bluetooth_searching, size: 80, color: Theme.of(context).colorScheme.primary),
        const SizedBox(height: 20),
        Text(scanning ? "Recherche du DartSystem…" : "Non connecté",
            style: const TextStyle(fontSize: 18)),
        const SizedBox(height: 24),
        ElevatedButton.icon(
          onPressed: scanning ? null : ble.connect,
          icon: scanning
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.bluetooth),
          label: Text(scanning ? "Connexion…" : "Se connecter"),
        ),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------

class _SetupView extends StatefulWidget {
  final GameEngine game;
  const _SetupView({required this.game});
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(padding: const EdgeInsets.all(16), children: [
      Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(
        crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text("MODE", style: TextStyle(letterSpacing: 1, color: Colors.white54)),
          const SizedBox(height: 10),
          Row(children: ["501", "301", "701"].map((m) => Expanded(child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: OutlinedButton(
              onPressed: () => setState(() => mode = m),
              style: OutlinedButton.styleFrom(
                backgroundColor: mode == m ? theme.colorScheme.primary : null,
                padding: const EdgeInsets.symmetric(vertical: 16)),
              child: Text(m, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            )))).toList()),
          const SizedBox(height: 16),
          const Text("JOUEURS", style: TextStyle(letterSpacing: 1, color: Colors.white54)),
          const SizedBox(height: 10),
          ...players.asMap().entries.map((e) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(children: [
              Expanded(child: TextField(controller: e.value,
                decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true))),
              if (players.length > 1)
                IconButton(icon: const Icon(Icons.delete, color: Colors.redAccent),
                  onPressed: () => setState(() => players.removeAt(e.key))),
            ]))),
          TextButton.icon(onPressed: () => setState(() =>
            players.add(TextEditingController(text: "Joueur ${players.length + 1}"))),
            icon: const Icon(Icons.add), label: const Text("Ajouter un joueur")),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text("Finir sur un double (double-out)"),
            value: doubleOut, onChanged: (v) => setState(() => doubleOut = v)),
        ]))),
      const SizedBox(height: 12),
      ElevatedButton.icon(
        onPressed: () {
          final names = players.map((c) => c.text.trim()).where((s) => s.isNotEmpty).toList();
          if (names.isNotEmpty) widget.game.start(mode, names, doubleOut: doubleOut);
        },
        icon: const Icon(Icons.play_arrow),
        label: const Text("Démarrer la partie", style: TextStyle(fontSize: 16)),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.green, padding: const EdgeInsets.symmetric(vertical: 16)),
      ),
    ]);
  }
}

// ---------------------------------------------------------------------------

class _GameView extends StatelessWidget {
  final GameEngine game;
  const _GameView({required this.game});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(children: [
      // Joueurs
      Padding(padding: const EdgeInsets.all(12), child: Column(
        children: game.players.asMap().entries.map((e) {
          final p = e.value;
          final active = e.key == game.current && game.active;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: active ? theme.colorScheme.secondary : Colors.transparent, width: 2)),
            child: Row(children: [
              Expanded(child: Text(p.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600))),
              Text("${p.score}", style: TextStyle(fontSize: 30, fontWeight: FontWeight.w800,
                color: active ? theme.colorScheme.secondary : theme.colorScheme.primary)),
            ]));
        }).toList())),

      // Message
      Text(game.message, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600,
        color: game.message.contains("BUST") ? Colors.redAccent
          : game.winner != null ? Colors.green : null)),

      const Spacer(),

      // Volée en cours
      Row(mainAxisAlignment: MainAxisAlignment.center, children: List.generate(3, (i) {
        final d = i < game.turnDarts.length ? game.turnDarts[i] : null;
        return GestureDetector(
          onTap: () => _correct(context, i),
          child: Container(
            width: 95, height: 120, margin: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(
              color: d != null ? theme.colorScheme.primary.withValues(alpha: .15) : theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: d == null ? Colors.white12
                : d.bust ? Colors.redAccent : theme.colorScheme.primary, width: 2)),
            child: d == null
              ? const Center(child: Icon(Icons.add, color: Colors.white12, size: 30))
              : Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Text(d.label, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800)),
                  Text("${d.value} pts", style: const TextStyle(fontSize: 12, color: Colors.white60)),
                ])));
      })),
      const SizedBox(height: 8),
      if (game.turnTotal > 0)
        Text("Volée : ${game.turnTotal}", style: TextStyle(fontSize: 22,
          fontWeight: FontWeight.w800, color: theme.colorScheme.secondary)),

      const Spacer(),

      // Contrôles
      Padding(padding: const EdgeInsets.all(16), child: Row(children: [
        Expanded(child: OutlinedButton(
          onPressed: game.nextPlayer, child: const Text("Joueur suivant →"))),
        const SizedBox(width: 12),
        OutlinedButton(onPressed: game.stop, child: const Text("Quitter")),
      ])),
    ]);
  }

  void _correct(BuildContext context, int index) {
    if (index >= game.turnDarts.length) return;
    showModalBottomSheet(context: context, backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => _CorrectionSheet(onPick: (label) {
        game.correctDart(index, label, valueFromLabel(label), multFromLabel(label));
        Navigator.pop(context);
      }));
  }
}

class _CorrectionSheet extends StatefulWidget {
  final void Function(String label) onPick;
  const _CorrectionSheet({required this.onPick});
  @override
  State<_CorrectionSheet> createState() => _CorrectionSheetState();
}

class _CorrectionSheetState extends State<_CorrectionSheet> {
  String mult = "S";
  @override
  Widget build(BuildContext context) {
    return Padding(padding: const EdgeInsets.all(16), child: Column(
      mainAxisSize: MainAxisSize.min, children: [
        const Text("Corriger la fléchette", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        Row(children: [["S","Simple"],["D","Double"],["T","Triple"]].map((m) => Expanded(
          child: Padding(padding: const EdgeInsets.symmetric(horizontal: 4),
            child: OutlinedButton(
              onPressed: () => setState(() => mult = m[0]),
              style: OutlinedButton.styleFrom(backgroundColor: mult == m[0]
                ? Theme.of(context).colorScheme.primary : null),
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
