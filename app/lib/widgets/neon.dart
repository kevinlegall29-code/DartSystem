import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Titre façon enseigne néon (police Orbitron, halo lumineux).
class NeonTitle extends StatelessWidget {
  final String text;
  final double size;
  final Color color;
  const NeonTitle(this.text, {super.key, this.size = 30, required this.color});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      textAlign: TextAlign.center,
      style: GoogleFonts.orbitron(
        fontSize: size,
        fontWeight: FontWeight.w800,
        letterSpacing: size * 0.12,
        color: color,
        shadows: [
          Shadow(color: color.withValues(alpha: .9), blurRadius: 12),
          Shadow(color: color.withValues(alpha: .5), blurRadius: 28),
        ],
      ),
    );
  }
}

/// Bouton rectangulaire à contour néon (sélectionnable).
class NeonButton extends StatelessWidget {
  final Widget child;
  final VoidCallback? onTap;
  final Color color;
  final bool selected;
  final EdgeInsets padding;
  const NeonButton({
    super.key,
    required this.child,
    required this.onTap,
    required this.color,
    this.selected = false,
    this.padding = const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: padding,
        decoration: BoxDecoration(
          color: selected ? color.withValues(alpha: .18) : Colors.white.withValues(alpha: .015),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: selected ? 1 : .55), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: selected ? .55 : .22),
              blurRadius: selected ? 16 : 8,
              spreadRadius: selected ? 1 : 0,
            ),
          ],
        ),
        child: child,
      ),
    );
  }
}

/// Grand bouton circulaire lumineux (Start).
class NeonCircleButton extends StatelessWidget {
  final VoidCallback? onTap;
  final Color color;
  final IconData icon;
  final String label;
  final double size;
  const NeonCircleButton({
    super.key,
    required this.onTap,
    required this.color,
    required this.icon,
    required this.label,
    this.size = 150,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    final c = enabled ? color : color.withValues(alpha: .35);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(colors: [
            c.withValues(alpha: .25),
            Colors.transparent,
          ]),
          border: Border.all(color: c, width: 3),
          boxShadow: enabled
              ? [
                  BoxShadow(color: c.withValues(alpha: .7), blurRadius: 26, spreadRadius: 2),
                  BoxShadow(color: c.withValues(alpha: .35), blurRadius: 50, spreadRadius: 6),
                ]
              : null,
        ),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, color: Colors.white, size: size * 0.26),
          const SizedBox(height: 4),
          Text(label,
              style: TextStyle(
                color: Colors.white,
                fontSize: size * 0.13,
                fontWeight: FontWeight.w700,
                letterSpacing: 1,
              )),
        ]),
      ),
    );
  }
}

/// Panneau sombre à liseré néon discret.
class NeonPanel extends StatelessWidget {
  final Widget child;
  final Color color;
  final EdgeInsets padding;
  final bool highlight;
  const NeonPanel({
    super.key,
    required this.child,
    required this.color,
    this.padding = const EdgeInsets.all(14),
    this.highlight = false,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      padding: padding,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: .03),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
            color: color.withValues(alpha: highlight ? .9 : .25),
            width: highlight ? 2 : 1),
        boxShadow: highlight
            ? [BoxShadow(color: color.withValues(alpha: .35), blurRadius: 12)]
            : null,
      ),
      child: child,
    );
  }
}
