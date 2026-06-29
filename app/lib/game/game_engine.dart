import 'package:flutter/foundation.dart';

class Player {
  String name;
  int score;
  int start;
  int dartsThrown = 0;
  Player(this.name, this.score) : start = score;
}

class TurnDart {
  final String label;
  final int value;
  final bool bust;
  TurnDart(this.label, this.value, {this.bust = false});
}

const Map<String, int> kStartScores = {"501": 501, "301": 301, "701": 701};

/// Moteur de jeu x01 (501/301/701) avec double-out optionnel.
/// Toute la logique est ici (l'app est le cerveau, le Pi n'envoie que les events).
class GameEngine extends ChangeNotifier {
  bool active = false;
  String mode = "501";
  bool doubleOut = true;
  List<Player> players = [];
  int current = 0;
  List<TurnDart> turnDarts = [];
  int turnStartScore = 0;
  String? winner;
  String message = "Aucune partie";

  void start(String mode, List<String> names, {bool doubleOut = true}) {
    final s = kStartScores[mode] ?? 501;
    this.mode = mode;
    this.doubleOut = doubleOut;
    players = names.map((n) => Player(n, s)).toList();
    current = 0;
    turnDarts = [];
    turnStartScore = s;
    active = true;
    winner = null;
    message = "Au tour de ${names.first}";
    notifyListeners();
  }

  void stop() {
    active = false;
    winner = null;
    message = "Aucune partie";
    notifyListeners();
  }

  /// Enregistre une fléchette (depuis le Pi ou correction manuelle).
  void registerDart(String label, int value, int multiplier) {
    if (!active || winner != null) return;
    if (turnDarts.length >= 3) return;

    final p = players[current];
    if (turnDarts.isEmpty) turnStartScore = p.score;
    p.dartsThrown++;

    final remaining = p.score - value;
    final isDouble = multiplier == 2;

    bool bust = false;
    if (remaining < 0) {
      bust = true;
    } else if (remaining == 0) {
      if (doubleOut && !isDouble) {
        bust = true;
      } else {
        p.score = 0;
        turnDarts.add(TurnDart(label, value));
        winner = p.name;
        active = false;
        message = "🏆 ${p.name} a gagné !";
        notifyListeners();
        return;
      }
    } else if (remaining == 1 && doubleOut) {
      bust = true;
    }

    if (bust) {
      turnDarts.add(TurnDart(label, value, bust: true));
      p.score = turnStartScore;
      message = "💥 BUST ! ${p.name}";
      notifyListeners();
      return;
    }

    p.score = remaining;
    turnDarts.add(TurnDart(label, value));
    message = turnDarts.length >= 3
        ? "${p.name} : retirez les fléchettes"
        : "${p.name} — ${p.score} restants";
    notifyListeners();
  }

  /// Corrige une fléchette du tour en cours et recalcule.
  void correctDart(int index, String label, int value, int multiplier) {
    if (index >= turnDarts.length) return;
    final p = players[current];
    final darts = List<TurnDart>.from(turnDarts);
    darts[index] = TurnDart(label, value);
    // Rejoue le tour depuis le début
    p.score = turnStartScore;
    turnDarts = [];
    final saved = winner;
    winner = null;
    active = true;
    for (final d in darts) {
      registerDart(d.label, d.value, _multFromLabel(d.label));
    }
    if (winner == null) winner = saved;
    notifyListeners();
  }

  void nextPlayer() {
    if (!active || winner != null) return;
    current = (current + 1) % players.length;
    turnDarts = [];
    turnStartScore = players[current].score;
    message = "Au tour de ${players[current].name}";
    notifyListeners();
  }

  /// Appelé sur un retrait (takeout) détecté par le Pi.
  void onTakeout() => nextPlayer();

  int get turnTotal =>
      turnDarts.where((d) => !d.bust).fold(0, (s, d) => s + d.value);
}

int multFromLabel(String label) => _multFromLabel(label);
int _multFromLabel(String label) {
  final l = label.toUpperCase();
  if (l == "DBULL") return 2;
  if (l.startsWith("T")) return 3;
  if (l.startsWith("D")) return 2;
  return 1;
}

int valueFromLabel(String label) {
  final l = label.toUpperCase();
  if (l == "DBULL") return 50;
  if (l == "BULL") return 25;
  if (l == "MISS") return 0;
  final n = int.tryParse(l.substring(1)) ?? 0;
  return n * _multFromLabel(l);
}
