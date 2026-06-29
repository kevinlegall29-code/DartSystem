import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

/// UUID du service/caractéristique exposés par le Raspberry Pi (api/ble_server.py)
const String kServiceUuid = "a1b2c3d4-0001-4a5b-8c6d-1234567890ab";
const String kCharUuid    = "a1b2c3d4-0002-4a5b-8c6d-1234567890ab";
const String kDeviceName  = "DartSystem";

enum BleStatus { idle, scanning, connecting, connected, disconnected }

/// Événement reçu du Pi.
class DartEvent {
  final String type;            // "dart" | "takeout" | "ping" | "hello"
  final String label;           // ex: "T20"
  final int value;              // points
  final int multiplier;         // 1/2/3
  DartEvent({required this.type, this.label = "", this.value = 0, this.multiplier = 1});

  factory DartEvent.fromJson(Map<String, dynamic> j) => DartEvent(
        type: j['t'] ?? '',
        label: j['label'] ?? '',
        value: (j['value'] ?? 0) as int,
        multiplier: (j['mult'] ?? 1) as int,
      );
}

/// Gère la connexion BLE au DartSystem et expose un flux d'événements.
class DartBle extends ChangeNotifier {
  BleStatus status = BleStatus.idle;
  String? deviceName;

  BluetoothDevice? _device;
  StreamSubscription? _scanSub;
  StreamSubscription? _connSub;
  StreamSubscription? _charSub;

  final _eventController = StreamController<DartEvent>.broadcast();
  Stream<DartEvent> get events => _eventController.stream;

  int eventCount = 0;          // debug : nb d'events BLE reçus
  String lastRaw = "";         // debug : dernier message brut

  void _setStatus(BleStatus s) { status = s; notifyListeners(); }

  /// Scanne et se connecte au premier DartSystem trouvé.
  Future<void> connect() async {
    _setStatus(BleStatus.scanning);
    try {
      await FlutterBluePlus.adapterState
          .where((s) => s == BluetoothAdapterState.on)
          .first
          .timeout(const Duration(seconds: 5));
    } catch (_) {
      _setStatus(BleStatus.disconnected);
      return;
    }

    await _scanSub?.cancel();
    _scanSub = FlutterBluePlus.scanResults.listen((results) async {
      for (final r in results) {
        if (r.device.platformName == kDeviceName ||
            r.advertisementData.serviceUuids
                .any((u) => u.toString().toLowerCase() == kServiceUuid)) {
          await FlutterBluePlus.stopScan();
          await _connectTo(r.device);
          break;
        }
      }
    });

    await FlutterBluePlus.startScan(
      withServices: [Guid(kServiceUuid)],
      timeout: const Duration(seconds: 15),
    );
  }

  Future<void> _connectTo(BluetoothDevice device) async {
    _device = device;
    _setStatus(BleStatus.connecting);
    try {
      await device.connect(timeout: const Duration(seconds: 10), autoConnect: false);
      deviceName = device.platformName;

      _connSub?.cancel();
      _connSub = device.connectionState.listen((s) {
        if (s == BluetoothConnectionState.disconnected) {
          _setStatus(BleStatus.disconnected);
          // Reconnexion automatique
          Future.delayed(const Duration(seconds: 2), connect);
        }
      });

      final services = await device.discoverServices();
      for (final svc in services) {
        if (svc.uuid.toString().toLowerCase() != kServiceUuid) continue;
        for (final c in svc.characteristics) {
          if (c.uuid.toString().toLowerCase() != kCharUuid) continue;
          _charSub?.cancel();
          _charSub = c.onValueReceived.listen(_onData);
          await c.setNotifyValue(true);
        }
      }
      _setStatus(BleStatus.connected);
    } catch (e) {
      debugPrint("BLE connect error: $e");
      _setStatus(BleStatus.disconnected);
      Future.delayed(const Duration(seconds: 2), connect);
    }
  }

  void _onData(List<int> data) {
    if (data.isEmpty) return;
    eventCount++;
    try {
      lastRaw = utf8.decode(data);
      debugPrint("BLE reçu: $lastRaw");
      final msg = jsonDecode(lastRaw) as Map<String, dynamic>;
      _eventController.add(DartEvent.fromJson(msg));
    } catch (e) {
      debugPrint("BLE parse error: $e ($lastRaw)");
    }
    notifyListeners();
  }

  Future<void> disconnect() async {
    await _scanSub?.cancel();
    await _charSub?.cancel();
    await _connSub?.cancel();
    await _device?.disconnect();
    _setStatus(BleStatus.idle);
  }

  @override
  void dispose() {
    disconnect();
    _eventController.close();
    super.dispose();
  }
}
