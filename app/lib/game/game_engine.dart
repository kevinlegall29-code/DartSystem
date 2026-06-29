import 'package:flutter/foundation.dart';

enum GameType { x01, cricket, cutthroat }

class Player {
  String name;
  int score;
  int start;
  int dartsThrown = 0;
  // Cricket : marques par cible (15..20, 25) → 0..3
  Map<int, int> marks = {for (final t in cricketTargets) t: 0};
  Player(this.name, this.score) : start = score;
  bool hasClosedAll() => cricketTargets.every((t) => (marks[t] ?? 0) >= 3);
}

class TurnDart {
  final String label;
  final int value;
  final bool bust;
  TurnDart(this.label, this.value, {this.bust = false});
}

const List<int> cricketTargets = [20, 19, 18, 17, 16, 15, 25];
const Map<String, int> kStartScores = {"501": 501, "301": 301, "701": 701};

/// Moteur de jeu : x01 (501/301/701), Cricket, Cut Throat.
class GameEngine extends ChangeNotifier {
  bool active = false;
  GameType type = GameType.x01;
  String mode = "501";
  bool doubleOut = true;
  List<Player> players = [];
  int current = 0;
  List<TurnDart> turnDarts = [];
  int turnStartScore = 0;
  String? winner;
  String message = "Aucune partie";

  bool get isCricket => type == GameType.cricket || type == GameType.cutthroat;

  void start(String mode, List<String> names, {bool doubleOut = true}) {
    this.mode = mode;
    type = switch (mode) {
      "Cricket" => GameType.cricket,
      "Cut Throat" => GameType.cutthroat,
      _ => GameType.x01,
    };
    this.doubleOut = doubleOut;
    final s = isCricket ? 0 : (kStartScores[mode] ?? 501);
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

  void registerDart(String label, int value, int multiplier) {
    if (!active || winner != null || turnDarts.length >= 3) return;
    if (isCricket) {
      _cricketDart(label, value, multiplier);
    } else {
      _x01Dart(label, value, multiplier);
    }
  }

  // ---------------- x01 ----------------
  void _x01Dart(String label, int value, int multiplier) {
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
        _win(p);
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

  // ---------------- Cricket / Cut Throat ----------------
  void _cricketDart(String label, int value, int multiplier) {
    final p = players[current];
    p.dartsThrown++;
    final base = baseFromLabel(label);

    if (!cricketTargets.contains(base)) {
      // hors cible cricket → pas de marque
      turnDarts.add(TurnDart(label, value));
      message = "${p.name}";
      notifyListeners();
      return;
    }

    final prev = p.marks[base] ?? 0;
    final closingMarks = (3 - prev).clamp(0, multiplier);
    final scoringMarks = multiplier - closingMarks;
    p.marks[base] = prev + closingMarks;

    if (scoringMarks > 0) {
      final closedByAll = players.where((o) => o != p)
          .every((o) => (o.marks[base] ?? 0) >= 3);
      if (!closedByAll) {
        final pts = base * scoringMarks;
        if (type == GameType.cutthroat) {
          // Les points vont aux ADVERSAIRES qui n'ont pas fermé
          for (final o in players) {
            if (o != p && (o.marks[base] ?? 0) < 3) o.score += pts;
          }
        } else {
          p.score += pts;
        }
      }
    }

    turnDarts.add(TurnDart(label, value));
    message = "${p.name}";
    notifyListeners();
    _checkCricketWin(p);
  }

  void _checkCricketWin(Player p) {
    if (!p.hasClosedAll()) return;
    final others = players.where((o) => o != p).map((o) => o.score);
    final ok = type == GameType.cutthroat
        ? others.every((s) => p.score <= s)   // cut throat : le plus bas gagne
        : others.every((s) => p.score >= s);  // cricket : le plus haut gagne
    if (ok) _win(p);
  }

  void _win(Player p) {
    winner = p.name;
    active = false;
    message = "🏆 ${p.name} a gagné !";
    notifyListeners();
  }

  void correctDart(int index, String label, int value, int multiplier) {
    if (index >= turnDarts.length) return;
    // Correction supportée pour x01 (recalcul simple du tour).
    // Pour le cricket (marques/points cumulés), correction non supportée pour l'instant.
    if (isCricket) return;
    final darts = List<TurnDart>.from(turnDarts);
    darts[index] = TurnDart(label, value);
    final p = players[current];
    p.score = turnStartScore;
    turnDarts = [];
    final saved = winner;
    winner = null;
    active = true;
    for (final d in darts) {
      _x01Dart(d.label, d.value, multFromLabel(d.label));
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

  void onTakeout() => nextPlayer();

  int get turnTotal =>
      turnDarts.where((d) => !d.bust).fold(0, (s, d) => s + d.value);
}

// Helpers labels
int multFromLabel(String label) {
  final l = label.toUpperCase();
  if (l == "DBULL") return 2;
  if (l.startsWith("T")) return 3;
  if (l.startsWith("D")) return 2;
  return 1;
}

int baseFromLabel(String label) {
  final l = label.toUpperCase();
  if (l == "DBULL" || l == "BULL") return 25;
  if (l == "MISS") return 0;
  return int.tryParse(l.substring(1)) ?? 0;
}

int valueFromLabel(String label) {
  final l = label.toUpperCase();
  if (l == "DBULL") return 50;
  if (l == "BULL") return 25;
  if (l == "MISS") return 0;
  return baseFromLabel(l) * multFromLabel(l);
}
