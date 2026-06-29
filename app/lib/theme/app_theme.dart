import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

/// Configuration graphique d'un client.
/// Chargée depuis assets/clients/<nom>.json
class ClientTheme {
  final String name;
  final Color primaryColor;
  final Color secondaryColor;
  final Color backgroundColor;
  final Color surfaceColor;
  final Color accentColor;
  final Color textColor;
  final String fontFamily;
  final String? logo;
  final String? backgroundImage;
  final Map<String, bool> modules;
  final Map<String, dynamic>? payment;

  const ClientTheme({
    required this.name,
    required this.primaryColor,
    required this.secondaryColor,
    required this.backgroundColor,
    required this.surfaceColor,
    required this.accentColor,
    required this.textColor,
    required this.fontFamily,
    this.logo,
    this.backgroundImage,
    required this.modules,
    this.payment,
  });

  factory ClientTheme.fromJson(Map<String, dynamic> j) => ClientTheme(
        name: j['name'],
        primaryColor: _hex(j['primaryColor']),
        secondaryColor: _hex(j['secondaryColor']),
        backgroundColor: _hex(j['backgroundColor']),
        surfaceColor: _hex(j['surfaceColor']),
        accentColor: _hex(j['accentColor']),
        textColor: _hex(j['textColor']),
        fontFamily: j['fontFamily'] ?? 'Roboto',
        logo: j['logo'],
        backgroundImage: j['backgroundImage'],
        modules: Map<String, bool>.from(j['modules'] ?? {}),
        payment: j['payment'],
      );

  bool get hasPayment => modules['payment'] == true;
  bool get hasStats => modules['stats'] == true;

  static Color _hex(String hex) {
    final h = hex.replaceFirst('#', '');
    return Color(int.parse('FF$h', radix: 16));
  }
}

/// Charge un ClientTheme depuis un fichier JSON dans les assets.
Future<ClientTheme> loadClientTheme(String clientName) async {
  final raw = await rootBundle.loadString('clients/$clientName.json');
  return ClientTheme.fromJson(jsonDecode(raw));
}

/// Convertit un ClientTheme en ThemeData Flutter.
ThemeData buildTheme(ClientTheme ct) {
  final textTheme = GoogleFonts.getTextTheme(
    ct.fontFamily,
    ThemeData.dark().textTheme,
  ).apply(bodyColor: ct.textColor, displayColor: ct.textColor);

  return ThemeData(
    brightness: Brightness.dark,
    primaryColor: ct.primaryColor,
    scaffoldBackgroundColor: ct.backgroundColor,
    colorScheme: ColorScheme.dark(
      primary: ct.primaryColor,
      secondary: ct.accentColor,
      surface: ct.surfaceColor,
      onPrimary: ct.textColor,
      onSecondary: ct.backgroundColor,
      onSurface: ct.textColor,
    ),
    textTheme: textTheme,
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: ct.primaryColor,
        foregroundColor: ct.textColor,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      ),
    ),
    cardTheme: CardTheme(
      color: ct.surfaceColor,
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: ct.surfaceColor,
      foregroundColor: ct.textColor,
      elevation: 0,
    ),
  );
}
