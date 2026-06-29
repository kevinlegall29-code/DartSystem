import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'theme/app_theme.dart';
import 'screens/connect_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final clientName = prefs.getString('client_name') ?? 'default';

  ClientTheme clientTheme;
  try {
    clientTheme = await loadClientTheme(clientName);
  } catch (_) {
    clientTheme = await loadClientTheme('default');
  }

  runApp(DartSystemApp(clientTheme: clientTheme));
}

class DartSystemApp extends StatelessWidget {
  final ClientTheme clientTheme;
  const DartSystemApp({super.key, required this.clientTheme});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: clientTheme.name,
      theme: buildTheme(clientTheme),
      debugShowCheckedModeBanner: false,
      home: const ConnectScreen(),
    );
  }
}
