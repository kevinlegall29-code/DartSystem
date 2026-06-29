"""
Moteur de jeu : 501 / 301 (double-out optionnel).
Conçu pour s'étendre à d'autres modes (Cricket, Around the Clock...).
"""

import logging

logger = logging.getLogger(__name__)

START_SCORES = {"501": 501, "301": 301, "701": 701}


class GameEngine:
    def __init__(self):
        self.engine_hook = None   # callback pour réinitialiser le compteur du moteur
        self.reset()

    def _reset_engine_turn(self):
        if self.engine_hook:
            try:
                self.engine_hook()
            except Exception:
                pass

    def reset(self):
        self.active = False
        self.mode = None
        self.players = []          # [{name, score, start, darts_thrown, history}]
        self.current = 0
        self.turn_darts = []       # [{label, value, bust?}]
        self.turn_start_score = 0
        self.double_out = True
        self.winner = None
        self.message = "Aucune partie en cours"

    # ------------------------------------------------------------------

    def start(self, mode: str, players: list[str], double_out: bool = True) -> dict:
        start = START_SCORES.get(mode, 501)
        self.mode = mode
        self.double_out = double_out
        self.players = [
            {"name": p, "score": start, "start": start, "darts": 0, "avg": 0.0}
            for p in players
        ]
        self.current = 0
        self.turn_darts = []
        self.turn_start_score = start
        self.active = True
        self.winner = None
        self.message = f"Au tour de {players[0]}"
        self._reset_engine_turn()
        logger.info(f"Partie {mode} démarrée : {players} (double-out={double_out})")
        return self.state()

    def register_dart(self, label: str, value: int, multiplier: int) -> dict:
        """Enregistre une fléchette détectée. Gère bust et victoire."""
        if not self.active or self.winner:
            return self.state()
        if len(self.turn_darts) >= 3:
            return self.state()   # tour déjà plein, attend le retrait

        p = self.players[self.current]
        if not self.turn_darts:
            self.turn_start_score = p["score"]

        remaining = p["score"] - value
        is_double = (multiplier == 2)   # inclut DBULL (25×2)
        p["darts"] += 1

        # --- Vérification bust / victoire ---
        bust = False
        if remaining < 0:
            bust = True
        elif remaining == 0:
            if self.double_out and not is_double:
                bust = True       # doit finir sur un double
            else:
                p["score"] = 0
                self.turn_darts.append({"label": label, "value": value})
                self.winner = p["name"]
                self.active = False
                self.message = f"🏆 {p['name']} a gagné !"
                logger.info(f"Victoire : {p['name']}")
                return self.state()
        elif remaining == 1 and self.double_out:
            bust = True           # impossible de finir depuis 1 en double-out

        if bust:
            self.turn_darts.append({"label": label, "value": value, "bust": True})
            p["score"] = self.turn_start_score   # annule le tour
            self.message = f"💥 BUST ! {p['name']} reste à {p['score']}"
            logger.info(f"Bust : {p['name']}")
            return self.state()

        # --- Fléchette valide ---
        p["score"] = remaining
        self.turn_darts.append({"label": label, "value": value})
        if len(self.turn_darts) >= 3:
            self.message = f"{p['name']} : retirez les fléchettes"
        else:
            self.message = f"{p['name']} — {p['score']} restants"
        return self.state()

    def correct_dart(self, index: int, label: str, value: int, multiplier: int) -> dict:
        """Corrige manuellement une fléchette du tour en cours, recalcule le score."""
        if not self.turn_darts or index >= len(self.turn_darts):
            return self.state()
        p = self.players[self.current]
        # Recalcule depuis le début du tour
        p["score"] = self.turn_start_score
        self.turn_darts[index] = {"label": label, "value": value}
        # Rejoue les fléchettes du tour
        darts = self.turn_darts
        self.turn_darts = []
        saved_score = self.turn_start_score
        p["score"] = saved_score
        for d in darts:
            self.register_dart(d["label"], d["value"], _mult_from_label(d["label"]))
        return self.state()

    def end_turn(self) -> dict:
        """Fin de tour (retrait des fléchettes) → joueur suivant."""
        if not self.active or self.winner:
            return self.state()
        self._next_player()
        return self.state()

    def _next_player(self):
        self.current = (self.current + 1) % len(self.players)
        self.turn_darts = []
        self.turn_start_score = self.players[self.current]["score"]
        self.message = f"Au tour de {self.players[self.current]['name']}"
        self._reset_engine_turn()

    # ------------------------------------------------------------------

    def state(self) -> dict:
        return {
            "active": self.active,
            "mode": self.mode,
            "double_out": self.double_out,
            "players": self.players,
            "current": self.current,
            "turn_darts": self.turn_darts,
            "turn_total": sum(d["value"] for d in self.turn_darts if not d.get("bust")),
            "winner": self.winner,
            "message": self.message,
        }


def _mult_from_label(label: str) -> int:
    label = label.upper()
    if label == "DBULL":
        return 2
    if label.startswith("T"):
        return 3
    if label.startswith("D"):
        return 2
    return 1


# Singleton partagé
game = GameEngine()
