import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Un impact à dessiner sur la cible (position normalisée 0–800, centre 400).
class Impact {
  final double x;
  final double y;
  final String label;
  final bool latest;   // dernière fléchette → mise en évidence
  const Impact(this.x, this.y, this.label, {this.latest = false});
}

/// Vue d'une cible de fléchettes avec les croix aux impacts calculés.
///
/// Espace normalisé : centre (400,400), rayon extérieur du double = 340.
/// Convention identique à la détection : 20 en haut, sens horaire.
class DartboardView extends StatelessWidget {
  final List<Impact> impacts;
  final Color glow;
  const DartboardView({super.key, this.impacts = const [], required this.glow});

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1,
      child: CustomPaint(painter: _DartboardPainter(impacts, glow)),
    );
  }
}

class _DartboardPainter extends CustomPainter {
  final List<Impact> impacts;
  final Color glow;
  _DartboardPainter(this.impacts, this.glow);

  // Ordre des secteurs dans le sens horaire en partant du haut (20).
  static const sectors = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17,
                          3, 19, 7, 16, 8, 11, 14, 9, 12, 5];

  // Rayons normalisés : bullInner, bullOuter, tripleIn, tripleOut, doubleIn, doubleOut
  static const rBullIn = 14.0, rBullOut = 32.0;
  static const rTripIn = 194.0, rTripOut = 214.0;
  static const rDblIn = 320.0, rDblOut = 340.0;

  static const cBlack = Color(0xFF15171C);
  static const cCream = Color(0xFFE7D7A8);
  static const cRed = Color(0xFFD23B3B);
  static const cGreen = Color(0xFF2FA85C);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final R = size.width / 2 * 0.86;          // marge pour les numéros
    final s = R / rDblOut;                     // échelle normalisé → pixels

    double px(double r) => r * s;
    // Angle "horaire depuis le haut" (deg) → angle canvas (rad).
    double ca(double deg) => (deg - 90) * math.pi / 180;

    // --- Halo extérieur néon ---
    canvas.drawCircle(center, R + px(10),
        Paint()
          ..color = glow.withValues(alpha: .25)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 14));
    // Anneau de bordure
    canvas.drawCircle(center, R + px(8),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3
          ..color = glow.withValues(alpha: .9));

    // Disque noir de fond (zone hors-score)
    canvas.drawCircle(center, R + px(7), Paint()..color = const Color(0xFF0A0B0F));

    // --- Secteurs ---
    for (int k = 0; k < 20; k++) {
      final a0 = ca(k * 18 - 9);
      final a1 = ca(k * 18 + 9);
      final isDark = k % 2 == 0;             // 20 (k=0) = noir
      final single = isDark ? cBlack : cCream;
      final ring = isDark ? cRed : cGreen;

      // Single intérieur (entre bull et triple) + extérieur (entre triple et double)
      _annulus(canvas, center, px(rBullOut), px(rTripIn), a0, a1, single);
      _annulus(canvas, center, px(rTripOut), px(rDblIn), a0, a1, single);
      // Triple et double
      _annulus(canvas, center, px(rTripIn), px(rTripOut), a0, a1, ring);
      _annulus(canvas, center, px(rDblIn), px(rDblOut), a0, a1, ring);
    }

    // --- Bull ---
    canvas.drawCircle(center, px(rBullOut), Paint()..color = cGreen);
    canvas.drawCircle(center, px(rBullIn), Paint()..color = cRed);

    // --- Lignes radiales fines (séparation des secteurs) ---
    final wire = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.6
      ..color = Colors.black.withValues(alpha: .35);
    for (int k = 0; k < 20; k++) {
      final a = ca(k * 18 - 9);
      canvas.drawLine(
        center + Offset(math.cos(a), math.sin(a)) * px(rBullOut),
        center + Offset(math.cos(a), math.sin(a)) * px(rDblOut),
        wire,
      );
    }

    // --- Numéros ---
    for (int k = 0; k < 20; k++) {
      final a = ca(k * 18.0);
      final pos = center + Offset(math.cos(a), math.sin(a)) * (R + px(2));
      final tp = TextPainter(
        text: TextSpan(
          text: "${sectors[k]}",
          style: TextStyle(
            color: Colors.white.withValues(alpha: .85),
            fontSize: R * 0.085,
            fontWeight: FontWeight.w700,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, pos - Offset(tp.width / 2, tp.height / 2));
    }

    // --- Impacts (croix) ---
    // Le scoring place la frontière 20/1 en haut (le 20 occupe 342–360°).
    // Notre cible dessine le 20 CENTRÉ en haut → on tourne les impacts d'un
    // demi-secteur (+9°) pour les aligner sur les secteurs visuels.
    const half = 9 * math.pi / 180;
    for (final imp in impacts) {
      final dx = imp.x - 400, dy = imp.y - 400;
      final mag = math.sqrt(dx * dx + dy * dy);
      final theta = math.atan2(dx, -dy) + half;   // horaire depuis le haut + offset visuel
      final p = center + Offset(math.sin(theta), -math.cos(theta)) * (mag * s);
      _cross(canvas, p, imp.latest, px(15));
    }
  }

  void _annulus(Canvas c, Offset ctr, double rIn, double rOut,
      double a0, double a1, Color color) {
    final outer = Rect.fromCircle(center: ctr, radius: rOut);
    final inner = Rect.fromCircle(center: ctr, radius: rIn);
    final path = Path()
      ..moveTo(ctr.dx + rIn * math.cos(a0), ctr.dy + rIn * math.sin(a0))
      ..lineTo(ctr.dx + rOut * math.cos(a0), ctr.dy + rOut * math.sin(a0))
      ..arcTo(outer, a0, a1 - a0, false)
      ..lineTo(ctr.dx + rIn * math.cos(a1), ctr.dy + rIn * math.sin(a1))
      ..arcTo(inner, a1, a0 - a1, false)
      ..close();
    c.drawPath(path, Paint()..color = color..isAntiAlias = true);
  }

  void _cross(Canvas c, Offset p, bool latest, double r) {
    final col = latest ? Colors.cyanAccent : Colors.white;
    // Halo
    c.drawCircle(p, r * 0.9,
        Paint()
          ..color = col.withValues(alpha: latest ? .5 : .25)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6));
    final pen = Paint()
      ..color = col
      ..strokeWidth = latest ? 3.5 : 2.5
      ..strokeCap = StrokeCap.round;
    c.drawLine(p + Offset(-r, -r), p + Offset(r, r), pen);
    c.drawLine(p + Offset(r, -r), p + Offset(-r, r), pen);
  }

  @override
  bool shouldRepaint(covariant _DartboardPainter old) =>
      old.impacts != impacts || old.glow != glow;
}
