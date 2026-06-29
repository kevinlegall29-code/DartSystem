import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/board_service.dart';
import 'game_screen.dart';

const _calibPoints = [
  {'key': '20_1',  'label': 'Fil 20 / 1',   'hint': '12h — haut de la cible'},
  {'key': '6_10',  'label': 'Fil 6 / 10',   'hint': '3h — droite'},
  {'key': '3_19',  'label': 'Fil 3 / 19',   'hint': '6h — bas'},
  {'key': '11_14', 'label': 'Fil 11 / 14',  'hint': '9h — gauche'},
];

class CalibrationScreen extends StatefulWidget {
  final BoardService service;
  const CalibrationScreen({super.key, required this.service});

  @override
  State<CalibrationScreen> createState() => _CalibrationScreenState();
}

class _CalibrationScreenState extends State<CalibrationScreen> {
  int _currentCamera = 0;
  int _currentPointIndex = 0;
  final Map<int, Map<String, Map<String, double>>> _allPoints = {};
  String? _normalizedImageB64;
  Map<String, dynamic>? _validation;
  bool _sending = false;

  // Loupe
  Offset? _magnifierPos;
  bool _magnifierActive = false;

  Map<String, Map<String, double>> get _currentPoints =>
      _allPoints[_currentCamera] ?? {};

  String get _streamUrl => widget.service.streamUrl(_currentCamera);

  bool get _cameraComplete => _currentPoints.length == 4;
  bool get _allComplete => [0, 1, 2].every(
      (i) => (_allPoints[i]?.length ?? 0) == 4);

  // ------------------------------------------------------------------

  void _onTapDown(TapDownDetails d, Size size) {
    final px = d.localPosition.dx / size.width * 1280;
    final py = d.localPosition.dy / size.height * 720;
    setState(() {
      _magnifierPos = d.localPosition;
      _magnifierActive = true;
    });
  }

  void _onTapUp(TapUpDetails d, Size size) {
    if (!_magnifierActive) return;
    final px = d.localPosition.dx / size.width * 1280;
    final py = d.localPosition.dy / size.height * 720;

    final key = _calibPoints[_currentPointIndex]['key']!;
    setState(() {
      _allPoints[_currentCamera] ??= {};
      _allPoints[_currentCamera]![key] = {'x': px, 'y': py};
      _magnifierActive = false;
      if (_currentPointIndex < 3) _currentPointIndex++;
    });
  }

  Future<void> _sendCalibration() async {
    if (!_cameraComplete) return;
    setState(() => _sending = true);

    final result = await widget.service.sendCalibrationPoints(
        _currentCamera, _currentPoints);

    setState(() {
      _sending = false;
      _normalizedImageB64 = result['normalized_image_b64'];
      _validation = result['validation'];
    });
  }

  Future<void> _nextCamera() async {
    if (_currentCamera < 2) {
      setState(() {
        _currentCamera++;
        _currentPointIndex = 0;
        _normalizedImageB64 = null;
        _validation = null;
      });
    }
  }

  Future<void> _finish() async {
    await widget.service.reloadCalibrations();
    widget.service.connectWebSocket();
    if (!mounted) return;
    Navigator.pushReplacement(context,
        MaterialPageRoute(builder: (_) => GameScreen(service: widget.service)));
  }

  // ------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Calibration — Caméra ${_currentCamera + 1}/3'),
        actions: [
          if (_allComplete)
            TextButton.icon(
              onPressed: _finish,
              icon: const Icon(Icons.check_circle, color: Colors.green),
              label: const Text('Terminer', style: TextStyle(color: Colors.green)),
            ),
        ],
      ),
      body: Column(
        children: [
          _ProgressBar(camera: _currentCamera, pointIndex: _currentPointIndex,
              points: _currentPoints),
          Expanded(
            child: Row(
              children: [
                // Panneau gauche : vue caméra + placement des points
                Expanded(flex: 3, child: _CameraPanel(
                  streamUrl: _streamUrl,
                  placedPoints: _currentPoints,
                  currentPoint: _calibPoints[min(_currentPointIndex, 3)],
                  magnifierPos: _magnifierPos,
                  magnifierActive: _magnifierActive,
                  onTapDown: _onTapDown,
                  onTapUp: _onTapUp,
                )),
                // Panneau droit : résultat normalisé + validation
                Expanded(flex: 2, child: _ResultPanel(
                  imageB64: _normalizedImageB64,
                  validation: _validation,
                  cameraComplete: _cameraComplete,
                  sending: _sending,
                  currentCamera: _currentCamera,
                  onSend: _sendCalibration,
                  onNext: _currentCamera < 2 ? _nextCamera : null,
                )),
              ],
            ),
          ),
          // Guide des points à placer
          _PointGuide(points: _calibPoints, currentIndex: _currentPointIndex,
              placed: _currentPoints),
        ],
      ),
    );
  }
}

// ------------------------------------------------------------------
// Sous-widgets
// ------------------------------------------------------------------

class _ProgressBar extends StatelessWidget {
  final int camera, pointIndex;
  final Map placed;
  const _ProgressBar({required this.camera, required this.pointIndex, required this.placed});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: theme.colorScheme.surface,
      child: Row(
        children: List.generate(3, (i) => Expanded(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 4),
            height: 6,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(3),
              color: i < camera
                  ? Colors.green
                  : i == camera
                      ? theme.colorScheme.primary
                      : theme.colorScheme.surface.withOpacity(0.3),
            ),
          ),
        )),
      ),
    );
  }
}

class _CameraPanel extends StatelessWidget {
  final String streamUrl;
  final Map<String, Map<String, double>> placedPoints;
  final Map<String, String> currentPoint;
  final Offset? magnifierPos;
  final bool magnifierActive;
  final void Function(TapDownDetails, Size) onTapDown;
  final void Function(TapUpDetails, Size) onTapUp;

  const _CameraPanel({
    required this.streamUrl,
    required this.placedPoints,
    required this.currentPoint,
    required this.magnifierPos,
    required this.magnifierActive,
    required this.onTapDown,
    required this.onTapUp,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (ctx, constraints) {
      final size = Size(constraints.maxWidth, constraints.maxHeight);
      return GestureDetector(
        onTapDown: (d) => onTapDown(d, size),
        onTapUp:   (d) => onTapUp(d, size),
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Stream MJPEG de la caméra
            Image.network(streamUrl, fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => const Center(
                    child: Icon(Icons.videocam_off, size: 64, color: Colors.red))),

            // Points déjà placés
            ...placedPoints.entries.map((e) {
              final ptKey = e.key;
              final px = e.value['x']! / 1280 * size.width;
              final py = e.value['y']! / 720 * size.height;
              return Positioned(
                left: px - 10,
                top:  py - 10,
                child: Container(
                  width: 20, height: 20,
                  decoration: const BoxDecoration(
                    color: Colors.yellow, shape: BoxShape.circle),
                  child: Center(child: Text(
                    _pointIndex(ptKey).toString(),
                    style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold),
                  )),
                ),
              );
            }),

            // Loupe
            if (magnifierActive && magnifierPos != null)
              Positioned(
                left: magnifierPos!.dx - 60,
                top:  magnifierPos!.dy - 120,
                child: _Magnifier(center: magnifierPos!, size: size, streamUrl: streamUrl),
              ),

            // Label point actuel
            Positioned(
              bottom: 12, left: 12,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.black54, borderRadius: BorderRadius.circular(8)),
                child: Text(
                  '→ Touche : ${currentPoint['label']} (${currentPoint['hint']})',
                  style: const TextStyle(color: Colors.yellow, fontWeight: FontWeight.bold),
                ),
              ),
            ),
          ],
        ),
      );
    });
  }

  int _pointIndex(String key) {
    const keys = ['20_1', '6_10', '3_19', '11_14'];
    return keys.indexOf(key) + 1;
  }
}

class _Magnifier extends StatelessWidget {
  final Offset center;
  final Size size;
  final String streamUrl;
  const _Magnifier({required this.center, required this.size, required this.streamUrl});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 120, height: 120,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: Colors.yellow, width: 2),
        boxShadow: [BoxShadow(color: Colors.black54, blurRadius: 8)],
      ),
      child: ClipOval(
        child: Transform.scale(
          scale: 3.0,
          child: Image.network(streamUrl, fit: BoxFit.cover),
        ),
      ),
    );
  }
}

class _ResultPanel extends StatelessWidget {
  final String? imageB64;
  final Map<String, dynamic>? validation;
  final bool cameraComplete, sending;
  final int currentCamera;
  final VoidCallback onSend;
  final VoidCallback? onNext;

  const _ResultPanel({
    required this.imageB64, required this.validation,
    required this.cameraComplete, required this.sending,
    required this.currentCamera, required this.onSend, required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(16),
      color: theme.colorScheme.surface,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (imageB64 == null) ...[
            const Icon(Icons.grid_view, size: 64, color: Colors.white24),
            const SizedBox(height: 12),
            const Text('Vue normalisée\napparaîtra ici',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white38)),
          ] else ...[
            // Image normalisée reçue du RPi
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.memory(
                Uri.parse('data:image/jpeg;base64,$imageB64').data!.contentAsBytes(),
                fit: BoxFit.contain,
              ),
            ),
            const SizedBox(height: 12),
            if (validation != null) _ValidationChip(validation: validation!),
          ],
          const SizedBox(height: 24),
          if (cameraComplete && imageB64 == null)
            ElevatedButton.icon(
              onPressed: sending ? null : onSend,
              icon: sending
                  ? const SizedBox(width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.calculate),
              label: Text(sending ? 'Calcul...' : 'Calculer homographie'),
            ),
          if (imageB64 != null && onNext != null) ...[
            const SizedBox(height: 8),
            ElevatedButton.icon(
              onPressed: onNext,
              icon: const Icon(Icons.arrow_forward),
              label: Text('Caméra ${currentCamera + 2}'),
            ),
          ],
        ],
      ),
    );
  }
}

class _ValidationChip extends StatelessWidget {
  final Map<String, dynamic> validation;
  const _ValidationChip({required this.validation});

  @override
  Widget build(BuildContext context) {
    final score = (validation['quality_score'] as num).toDouble();
    final ok = score >= 80;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(ok ? Icons.check_circle : Icons.warning,
            color: ok ? Colors.green : Colors.orange),
        const SizedBox(width: 8),
        Text('Score qualité : ${score.toStringAsFixed(1)}%',
            style: TextStyle(color: ok ? Colors.green : Colors.orange,
                fontWeight: FontWeight.bold)),
      ],
    );
  }
}

class _PointGuide extends StatelessWidget {
  final List<Map<String, String>> points;
  final int currentIndex;
  final Map placed;
  const _PointGuide({required this.points, required this.currentIndex, required this.placed});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 70,
      color: Theme.of(context).colorScheme.surface,
      child: Row(
        children: List.generate(points.length, (i) {
          final key = points[i]['key']!;
          final done = placed.containsKey(key);
          final active = i == currentIndex && !done;
          return Expanded(
            child: Container(
              margin: const EdgeInsets.all(6),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: done ? Colors.green : active ? Colors.yellow : Colors.white24,
                  width: active ? 2 : 1,
                ),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(done ? Icons.check_circle : Icons.radio_button_unchecked,
                      size: 16,
                      color: done ? Colors.green : active ? Colors.yellow : Colors.white38),
                  Text(points[i]['label']!,
                      style: TextStyle(
                          fontSize: 10,
                          color: done ? Colors.green : active ? Colors.yellow : Colors.white38)),
                ],
              ),
            ),
          );
        }),
      ),
    );
  }
}
