import 'dart:async';
import 'package:flutter/material.dart';
import '../services/board_service.dart';

class GameScreen extends StatefulWidget {
  final BoardService service;
  const GameScreen({super.key, required this.service});

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> {
  Map<String, dynamic> _gameState = {'active': false};
  final List<DartDetectedData> _lastDarts = [];
  StreamSubscription? _dartSub, _stateSub, _takeoutSub;

  @override
  void initState() {
    super.initState();
    _dartSub = widget.service.dartStream.listen((dart) {
      setState(() {
        _lastDarts.add(dart);
        if (_lastDarts.length > 3) _lastDarts.removeAt(0);
      });
    });
    _stateSub = widget.service.stateStream.listen((state) {
      setState(() => _gameState = state);
    });
    _takeoutSub = widget.service.takeoutStream.listen((_) {
      setState(() => _lastDarts.clear());
    });
  }

  @override
  void dispose() {
    _dartSub?.cancel();
    _stateSub?.cancel();
    _takeoutSub?.cancel();
    super.dispose();
  }

  int get _turnScore => _lastDarts.fold(0, (s, d) => s + d.score);

  Future<void> _startGame(String mode) async {
    await widget.service.startGame(mode, ['Joueur 1', 'Joueur 2']);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final active = _gameState['active'] == true;

    return Scaffold(
      appBar: AppBar(
        title: const Text('DartSystem'),
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: 'Recalibrer',
            onPressed: () {}, // TODO: navigation vers calibration
          ),
        ],
      ),
      body: active ? _GameBody(
        gameState: _gameState,
        lastDarts: _lastDarts,
        turnScore: _turnScore,
        onNextPlayer: () => widget.service.nextPlayer(),
        onManualScore: (label) => widget.service.manualScore(label),
        onStop: () => widget.service.stopGame(),
      ) : _LobbyBody(onStart: _startGame),
    );
  }
}

// ------------------------------------------------------------------
// Lobby (sélection du mode de jeu)
// ------------------------------------------------------------------

class _LobbyBody extends StatelessWidget {
  final void Function(String mode) onStart;
  const _LobbyBody({required this.onStart});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Choisir un jeu',
              style: theme.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold)),
          const SizedBox(height: 32),
          Wrap(
            spacing: 16, runSpacing: 16,
            children: [
              _ModeCard(label: '501', icon: Icons.filter_5, onTap: () => onStart('501')),
              _ModeCard(label: '301', icon: Icons.filter_3, onTap: () => onStart('301')),
              _ModeCard(label: 'Cricket', icon: Icons.sports_cricket, onTap: () => onStart('cricket')),
            ],
          ),
        ],
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  const _ModeCard({required this.label, required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        width: 140, height: 140,
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: theme.colorScheme.primary, width: 2),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 48, color: theme.colorScheme.primary),
            const SizedBox(height: 8),
            Text(label, style: theme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }
}

// ------------------------------------------------------------------
// Écran de jeu principal
// ------------------------------------------------------------------

class _GameBody extends StatelessWidget {
  final Map<String, dynamic> gameState;
  final List<DartDetectedData> lastDarts;
  final int turnScore;
  final VoidCallback onNextPlayer;
  final void Function(String) onManualScore;
  final VoidCallback onStop;

  const _GameBody({
    required this.gameState, required this.lastDarts,
    required this.turnScore, required this.onNextPlayer,
    required this.onManualScore, required this.onStop,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final players = List<String>.from(gameState['players'] ?? []);
    final scores  = Map<String, dynamic>.from(gameState['scores'] ?? {});
    final current = gameState['current_player'] as int? ?? 0;

    return Column(
      children: [
        // Scores joueurs
        Container(
          color: theme.colorScheme.surface,
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 24),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: players.asMap().entries.map((e) {
              final isActive = e.key == current;
              return _PlayerScore(
                name: e.value,
                score: scores[e.value]?.toString() ?? '—',
                isActive: isActive,
              );
            }).toList(),
          ),
        ),

        // Fléchettes du tour
        Expanded(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Tour en cours',
                    style: theme.textTheme.titleMedium?.copyWith(color: Colors.white54)),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: List.generate(3, (i) => _DartSlot(
                    dart: i < lastDarts.length ? lastDarts[i] : null,
                  )),
                ),
                const SizedBox(height: 24),
                if (lastDarts.isNotEmpty)
                  Text('= $turnScore pts',
                      style: theme.textTheme.headlineLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.secondary,
                      )),
              ],
            ),
          ),
        ),

        // Barre d'actions
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: onNextPlayer,
                    icon: const Icon(Icons.skip_next),
                    label: const Text('Joueur suivant'),
                  ),
                ),
                const SizedBox(width: 12),
                OutlinedButton(
                  onPressed: onStop,
                  child: const Text('Arrêter'),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _PlayerScore extends StatelessWidget {
  final String name, score;
  final bool isActive;
  const _PlayerScore({required this.name, required this.score, required this.isActive});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isActive ? theme.colorScheme.secondary : Colors.transparent,
          width: 2,
        ),
      ),
      child: Column(
        children: [
          Text(name, style: theme.textTheme.titleSmall?.copyWith(
              color: isActive ? theme.colorScheme.secondary : Colors.white54)),
          Text(score, style: theme.textTheme.displaySmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: isActive ? Colors.white : Colors.white60)),
        ],
      ),
    );
  }
}

class _DartSlot extends StatelessWidget {
  final DartDetectedData? dart;
  const _DartSlot({this.dart});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: 90, height: 90,
      margin: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: dart != null ? theme.colorScheme.primary.withOpacity(0.15) : theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: dart != null ? theme.colorScheme.primary : Colors.white12,
          width: 2,
        ),
      ),
      child: dart == null
          ? const Icon(Icons.add, color: Colors.white12, size: 32)
          : Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(dart!.label,
                    style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
                Text('${dart!.score} pts',
                    style: theme.textTheme.bodySmall?.copyWith(color: Colors.white60)),
              ],
            ),
    );
  }
}
