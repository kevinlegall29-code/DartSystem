import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'ble/dart_ble.dart';
import 'game/game_engine.dart';
import 'theme/client_theme.dart';
import 'screens/home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final theme = await loadClientTheme('default');
  runApp(DartSystemApp(theme: theme));
}

class DartSystemApp extends StatefulWidget {
  final ClientTheme theme;
  const DartSystemApp({super.key, required this.theme});

  @override
  State<DartSystemApp> createState() => _DartSystemAppState();
}

class _DartSystemAppState extends State<DartSystemApp> {
  final ble = DartBle();
  final game = GameEngine();

  @override
  void initState() {
    super.initState();
    _initBle();
  }

  Future<void> _initBle() async {
    // Permissions BLE Android 12+
    await [
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
      Permission.locationWhenInUse,
    ].request();

    // Relie les events BLE au moteur de jeu
    ble.events.listen((e) {
      if (e.type == 'dart') {
        game.registerDart(e.label, e.value, e.multiplier, x: e.x, y: e.y);
      } else if (e.type == 'takeout') {
        game.onTakeout();
      }
    });
  }

  @override
  void dispose() {
    ble.dispose();
    game.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: ble),
        ChangeNotifierProvider.value(value: game),
      ],
      child: MaterialApp(
        title: widget.theme.name,
        debugShowCheckedModeBanner: false,
        theme: widget.theme.toThemeData(),
        home: HomeScreen(clientName: widget.theme.name, clientLogo: widget.theme.logo),
      ),
    );
  }
}
