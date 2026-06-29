import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

/// Personnalisation par client (bar) : nom, logo, couleurs, police.
class ClientTheme {
  final String name;
  final Color primary;
  final Color accent;
  final Color background;
  final Color surface;
  final Color text;
  final String fontFamily;
  final String? logo;

  const ClientTheme({
    required this.name,
    required this.primary,
    required this.accent,
    required this.background,
    required this.surface,
    required this.text,
    required this.fontFamily,
    this.logo,
  });

  static const fallback = ClientTheme(
    name: "DartSystem",
    primary: Color(0xFF1565C0),
    accent: Color(0xFFFFD700),
    background: Color(0xFF0A0A0A),
    surface: Color(0xFF1A1A2E),
    text: Color(0xFFFFFFFF),
    fontFamily: "Roboto",
  );

  factory ClientTheme.fromJson(Map<String, dynamic> j) => ClientTheme(
        name: j['name'] ?? "DartSystem",
        primary: _hex(j['primaryColor'] ?? "#1565C0"),
        accent: _hex(j['accentColor'] ?? "#FFD700"),
        background: _hex(j['backgroundColor'] ?? "#0A0A0A"),
        surface: _hex(j['surfaceColor'] ?? "#1A1A2E"),
        text: _hex(j['textColor'] ?? "#FFFFFF"),
        fontFamily: j['fontFamily'] ?? "Roboto",
        logo: j['logo'],
      );

  static Color _hex(String h) =>
      Color(int.parse("FF${h.replaceFirst('#', '')}", radix: 16));

  ThemeData toThemeData() {
    final tt = GoogleFonts.getTextTheme(fontFamily, ThemeData.dark().textTheme)
        .apply(bodyColor: text, displayColor: text);
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      primaryColor: primary,
      colorScheme: ColorScheme.dark(
        primary: primary, secondary: accent, surface: surface,
        onPrimary: text, onSecondary: background, onSurface: text,
      ),
      textTheme: tt,
      cardTheme: CardThemeData(color: surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
    );
  }
}

Future<ClientTheme> loadClientTheme(String client) async {
  try {
    final raw = await rootBundle.loadString('assets/clients/$client.json');
    return ClientTheme.fromJson(jsonDecode(raw));
  } catch (_) {
    return ClientTheme.fallback;
  }
}
