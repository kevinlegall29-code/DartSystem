import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/board_service.dart';
import 'game_screen.dart';
import 'calibration_screen.dart';

/// Écran de connexion au RPi.
/// L'utilisateur entre l'IP (ou on utilise la dernière connue).
class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key});

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  final _ipController = TextEditingController(text: '192.168.50.1');
  bool _connecting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSavedIp();
  }

  Future<void> _loadSavedIp() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString('board_ip');
    if (saved != null) _ipController.text = saved;
  }

  Future<void> _connect() async {
    setState(() { _connecting = true; _error = null; });

    final service = BoardService(host: _ipController.text.trim());
    final ok = await service.isReachable();

    if (!mounted) return;

    if (!ok) {
      setState(() {
        _connecting = false;
        _error = 'Impossible de joindre le RPi — vérifiez le Wi-Fi et l\'IP';
      });
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('board_ip', _ipController.text.trim());

    // Vérifie si les caméras sont calibrées
    final calStatus = await service.calibrationStatus();
    final allCalibrated = calStatus.values.every((v) => v['ready'] == true);

    if (!mounted) return;
    setState(() => _connecting = false);

    if (!allCalibrated) {
      Navigator.push(context, MaterialPageRoute(
        builder: (_) => CalibrationScreen(service: service),
      ));
    } else {
      service.connectWebSocket();
      Navigator.pushReplacement(context, MaterialPageRoute(
        builder: (_) => GameScreen(service: service),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.sports, size: 72, color: theme.colorScheme.primary),
                const SizedBox(height: 16),
                Text('DartSystem',
                    style: theme.textTheme.headlineLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.primary,
                    )),
                const SizedBox(height: 48),
                TextField(
                  controller: _ipController,
                  decoration: const InputDecoration(
                    labelText: 'Adresse IP du Raspberry Pi',
                    hintText: '192.168.50.1',
                    prefixIcon: Icon(Icons.router),
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: 24),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(_error!,
                        style: TextStyle(color: theme.colorScheme.error),
                        textAlign: TextAlign.center),
                  ),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _connecting ? null : _connect,
                    icon: _connecting
                        ? const SizedBox(
                            width: 18, height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.wifi),
                    label: Text(_connecting ? 'Connexion...' : 'Se connecter'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
