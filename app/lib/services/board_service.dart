import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

/// Événements reçus via WebSocket depuis le RPi.
enum DartEvent { dartDetected, gameState, takeout, cameraStatus }

class DartDetectedData {
  final String label;
  final int score;
  final Map<String, dynamic> cameras;
  DartDetectedData({required this.label, required this.score, required this.cameras});
  factory DartDetectedData.fromJson(Map<String, dynamic> j) =>
      DartDetectedData(label: j['label'], score: j['score'], cameras: j['cameras'] ?? {});
}

/// Service unique de communication avec le RPi (REST + WebSocket).
class BoardService {
  final String host;
  final int port;

  BoardService({required this.host, this.port = 8080});

  String get baseUrl => 'http://$host:$port';
  String get wsUrl   => 'ws://$host:$port';

  WebSocketChannel? _channel;
  final _dartController   = StreamController<DartDetectedData>.broadcast();
  final _stateController  = StreamController<Map<String, dynamic>>.broadcast();
  final _takeoutController = StreamController<void>.broadcast();

  Stream<DartDetectedData>       get dartStream   => _dartController.stream;
  Stream<Map<String, dynamic>>   get stateStream  => _stateController.stream;
  Stream<void>                   get takeoutStream => _takeoutController.stream;

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------

  void connectWebSocket() {
    _channel = WebSocketChannel.connect(Uri.parse('$wsUrl/game/ws'));
    _channel!.stream.listen(
      (raw) {
        final msg = jsonDecode(raw as String) as Map<String, dynamic>;
        final type = msg['type'] as String;
        final data = msg['data'];
        switch (type) {
          case 'dart_detected':
            _dartController.add(DartDetectedData.fromJson(data));
          case 'game_state':
            _stateController.add(Map<String, dynamic>.from(data));
          case 'takeout':
            _takeoutController.add(null);
        }
      },
      onError: (_) => Future.delayed(const Duration(seconds: 2), connectWebSocket),
      onDone:  ()  => Future.delayed(const Duration(seconds: 2), connectWebSocket),
    );
  }

  void dispose() {
    _channel?.sink.close();
    _dartController.close();
    _stateController.close();
    _takeoutController.close();
  }

  // ------------------------------------------------------------------
  // REST — Santé
  // ------------------------------------------------------------------

  Future<bool> isReachable() async {
    try {
      final r = await http.get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 3));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ------------------------------------------------------------------
  // REST — Jeu
  // ------------------------------------------------------------------

  Future<Map<String, dynamic>> startGame(String mode, List<String> players) async {
    final r = await http.post(
      Uri.parse('$baseUrl/game/start'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'mode': mode, 'players': players}),
    );
    return jsonDecode(r.body);
  }

  Future<void> stopGame() =>
      http.post(Uri.parse('$baseUrl/game/stop'));

  Future<void> nextPlayer() =>
      http.post(Uri.parse('$baseUrl/game/takeout'));

  Future<void> manualScore(String label) async {
    await http.post(
      Uri.parse('$baseUrl/game/score/manual'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'label': label}),
    );
  }

  // ------------------------------------------------------------------
  // REST — Calibration
  // ------------------------------------------------------------------

  Future<Map<String, dynamic>> calibrationStatus() async {
    final r = await http.get(Uri.parse('$baseUrl/calibration/status'));
    return jsonDecode(r.body);
  }

  Future<Map<String, dynamic>> sendCalibrationPoints(
      int cameraIndex, Map<String, Map<String, double>> points) async {
    final r = await http.post(
      Uri.parse('$baseUrl/calibration/board'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'camera_index': cameraIndex, 'points': points}),
    );
    return jsonDecode(r.body);
  }

  Future<void> reloadCalibrations() =>
      http.post(Uri.parse('$baseUrl/calibration/reload'));

  // ------------------------------------------------------------------
  // Caméras
  // ------------------------------------------------------------------

  String snapshotUrl(int cameraIndex) => '$baseUrl/cameras/snapshot/$cameraIndex';
  String streamUrl(int cameraIndex)   => '$baseUrl/cameras/stream/$cameraIndex';
}
