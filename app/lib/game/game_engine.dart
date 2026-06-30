import 'package:flutter/foundation.dart';

enum GameType { x01, cricket, cutthroat, clock, countup, shanghai, football }

class Player {
  String name;
  int score;
  int start;
  int dartsThrown = 0;
  Map<int, int> marks = {for (final t in cricketTargets) t: 0}; // cricket
  int target = 1;            // around the clock (1..20)
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

class GameEngine extends ChangeNotifier {
  bool active = false;
  GameType type = GameType.x01;
  String mode = "501";
  bool doubleOut = true;
  List<Player> players = [];
  int current = 0;
  List<TurnDart> turnDarts = [];
  int turnStartScore = 0;
  int round = 1;
  int maxRounds = 0;          // 0 = illimité
  int possession = -1;        // football
  String? winner;
  String message = "Aucune partie";

  bool get isCricket => type == GameType.cricket || type == GameType.cutthroat;

  void start(String mode, List<String> names, {bool doubleOut = true}) {
    this.mode = mode;
    this.doubleOut = doubleOut;
    type = switch (mode) {
      "Cricket" => GameType.cricket,
      "Cut Throat" => GameType.cutthroat,
      "Around the Clock" => GameType.clock,
      "Count Up" => GameType.countup,
      "Shanghai" => GameType.shanghai,
      "Football" => GameType.football,
      _ => GameType.x01,
    };
    maxRounds = switch (type) {
      GameType.countup => 8,
      GameType.shanghai => 7,
      _ => 0,
    };
    final s = (type == GameType.x01) ? (kStartScores[mode] ?? 501) : 0;
    players = names.map((n) => Player(n, s)).toList();
    current = 0;
    round = 1;
    possession = -1;
    turnDarts = [];
    turnStartScore = s;
    active = true;
    winner = null;
    message = _turnMsg();
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
    switch (type) {
      case GameType.x01: _x01Dart(label, value, multiplier);
      case GameType.cricket || GameType.cutthroat: _cricketDart(label, value, multiplier);
      case GameType.clock: _clockDart(label);
      case GameType.countup: _simpleAdd(label, value);
      case GameType.shanghai: _shanghaiDart(label, value, multiplier);
      case GameType.football: _footballDart(label, multiplier);
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
      if (doubleOut && !isDouble) { bust = true; }
      else { p.score = 0; turnDarts.add(TurnDart(label, value)); _win(p); return; }
    } else if (remaining == 1 && doubleOut) { bust = true; }
    if (bust) {
      turnDarts.add(TurnDart(label, value, bust: true));
      p.score = turnStartScore;
      message = "💥 BUST ! ${p.name}";
      notifyListeners(); return;
    }
    p.score = remaining;
    turnDarts.add(TurnDart(label, value));
    message = turnDarts.length >= 3 ? "${p.name} : retirez les fléchettes"
                                    : "${p.name} — ${p.score} restants";
    notifyListeners();
  }

  // ---------------- Cricket / Cut Throat ----------------
  void _cricketDart(String label, int value, int multiplier) {
    final p = players[current];
    p.dartsThrown++;
    final base = baseFromLabel(label);
    if (!cricketTargets.contains(base)) {
      turnDarts.add(TurnDart(label, value)); message = p.name; notifyListeners(); return;
    }
    final prev = p.marks[base] ?? 0;
    final closing = (3 - prev).clamp(0, multiplier);
    final scoring = multiplier - closing;
    p.marks[base] = prev + closing;
    if (scoring > 0) {
      final closedByAll = players.where((o) => o != p).every((o) => (o.marks[base] ?? 0) >= 3);
      if (!closedByAll) {
        final pts = base * scoring;
        if (type == GameType.cutthroat) {
          for (final o in players) { if (o != p && (o.marks[base] ?? 0) < 3) o.score += pts; }
        } else { p.score += pts; }
      }
    }
    turnDarts.add(TurnDart(label, value));
    message = p.name; notifyListeners();
    _checkCricketWin(p);
  }

  void _checkCricketWin(Player p) {
    if (!p.hasClosedAll()) return;
    final others = players.where((o) => o != p).map((o) => o.score);
    final ok = type == GameType.cutthroat
        ? others.every((s) => p.score <= s) : others.every((s) => p.score >= s);
    if (ok) _win(p);
  }

  // ---------------- Around the Clock ----------------
  void _clockDart(String label) {
    final p = players[current];
    p.dartsThrown++;
    final base = baseFromLabel(label);
    if (base == p.target) {
      p.target++;
      p.score = p.target - 1;      // nombres validés
      if (p.target > 20) { turnDarts.add(TurnDart(label, base)); _win(p); return; }
      message = "${p.name} → vise le ${p.target}";
    } else {
      message = "${p.name} → vise le ${p.target}";
    }
    turnDarts.add(TurnDart(label, base));
    notifyListeners();
  }

  // ---------------- Count Up (somme sur N manches) ----------------
  void _simpleAdd(String label, int value) {
    final p = players[current];
    p.dartsThrown++;
    p.score += value;
    turnDarts.add(TurnDart(label, value));
    message = "${p.name} — ${p.score} pts";
    notifyListeners();
  }

  // ---------------- Shanghai (manches 1..7) ----------------
  void _shanghaiDart(String label, int value, int multiplier) {
    final p = players[current];
    p.dartsThrown++;
    final base = baseFromLabel(label);
    if (base == round) {
      p.score += value;
      // Shanghai = simple + double + triple de la cible dans le même tour → victoire
      final mults = turnDarts.where((d) => baseFromLabel(d.label) == round)
          .map((d) => multFromLabel(d.label)).toSet()..add(multiplier);
      if (mults.containsAll({1, 2, 3})) {
        turnDarts.add(TurnDart(label, value));
        message = "🎯 SHANGHAI ! ${p.name} gagne !"; _win(p); return;
      }
    }
    turnDarts.add(TurnDart(label, value));
    message = "${p.name} — manche $round (vise $round)";
    notifyListeners();
  }

  // ---------------- Football (doubles = possession + buts) ----------------
  void _footballDart(String label, int multiplier) {
    final p = players[current];
    p.dartsThrown++;
    const goalsToWin = 10;
    if (multiplier == 2) {           // un double
      if (possession == current) {
        p.score++;                   // but !
        message = "⚽ BUT ! ${p.name} : ${p.score}";
        if (p.score >= goalsToWin) { turnDarts.add(TurnDart(label, 0)); _win(p); return; }
      } else {
        possession = current;        // prend / vole la possession
        message = "${p.name} a la possession";
      }
    } else {
      message = "${p.name} — possession : "
          "${possession >= 0 ? players[possession].name : 'aucune'}";
    }
    turnDarts.add(TurnDart(label, 0));
    notifyListeners();
  }

  // ---------------- Commun ----------------
  void _win(Player p) {
    winner = p.name; active = false;
    message = "🏆 ${p.name} a gagné !"; notifyListeners();
  }

  void nextPlayer() {
    if (!active || winner != null) return;
    current = (current + 1) % players.length;
    if (current == 0) {
      round++;
      // Fin des jeux à nombre de manches fixe
      if (maxRounds > 0 && round > maxRounds) { _endByScore(); return; }
    }
    turnDarts = [];
    turnStartScore = players[current].score;
    message = _turnMsg();
    notifyListeners();
  }

  void _endByScore() {
    // Count Up : plus haut score gagne. (Shanghai aussi si pas de shanghai.)
    final best = players.reduce((a, b) => a.score >= b.score ? a : b);
    _win(best);
  }

  String _turnMsg() {
    final n = players[current].name;
    return switch (type) {
      GameType.clock => "$n → vise le ${players[current].target}",
      GameType.shanghai => "$n — manche $round/7 (vise $round)",
      GameType.countup => "$n — manche $round/8",
      GameType.football => "$n — possession : ${possession >= 0 ? players[possession].name : 'aucune'}",
      _ => "Au tour de $n",
    };
  }

  void onTakeout() => nextPlayer();

  void correctDart(int index, String label, int value, int multiplier) {
    if (index >= turnDarts.length || type != GameType.x01) return;
    final darts = List<TurnDart>.from(turnDarts);
    darts[index] = TurnDart(label, value);
    final p = players[current];
    p.score = turnStartScore;
    turnDarts = [];
    final saved = winner; winner = null; active = true;
    for (final d in darts) { _x01Dart(d.label, d.value, multFromLabel(d.label)); }
    if (winner == null) winner = saved;
    notifyListeners();
  }

  int get turnTotal => turnDarts.where((d) => !d.bust).fold(0, (s, d) => s + d.value);

  /// Ligne de contexte pour l'UI (manche, cible, possession…)
  String get contextLine => switch (type) {
    GameType.shanghai => "Manche $round / 7 — Cible : $round",
    GameType.countup => "Manche $round / 8",
    GameType.clock => "Chacun vise sa propre cible",
    GameType.football => "Premier à 10 buts",
    _ => "",
  };
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
