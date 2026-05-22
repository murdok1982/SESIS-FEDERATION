import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:nearby_connections/nearby_connections.dart';
import '../storage/local_db.dart';
import '../storage/offline_queue.dart';
import 'mesh_protocol.dart';

enum MeshConnectionState { disconnected, discovering, advertising, connected }

class MeshService {
  static final MeshService _instance = MeshService._();
  factory MeshService() => _instance;
  MeshService._();

  final Nearby _nearby = Nearby();
  final OfflineQueue _offlineQueue = OfflineQueue();

  final StreamController<MeshMessage> _messageController = StreamController<MeshMessage>.broadcast();
  final ValueNotifier<MeshConnectionState> connectionState = ValueNotifier(MeshConnectionState.disconnected);
  final ValueNotifier<int> peerCount = ValueNotifier(0);

  final Map<String, String> _connectedPeers = {};

  Stream<MeshMessage> get messages => _messageController.stream;
  String get endpointId => _nearby.getLocalEndpointId() ?? '';

  Future<bool> initialize() async {
    try {
      await _nearby.init(
        onEndpointDiscovered: _onEndpointDiscovered,
        onEndpointLost: _onEndpointLost,
        onConnectionInitiated: _onConnectionInitiated,
        onConnectionResult: _onConnectionResult,
        onDisconnected: _onDisconnected,
        onPayload: _onPayload,
        serviceId: 'sesis-mesh',
      );
      return true;
    } catch (e) {
      debugPrint('Mesh init failed: $e');
      return false;
    }
  }

  Future<void> startAdvertising() async {
    try {
      await _nearby.startAdvertising(
        'SESIS-COP-${DateTime.now().millisecondsSinceEpoch}',
        Strategy.P2P_CLUSTER,
        onConnectionInitiated: _onConnectionInitiated,
        onConnectionResult: _onConnectionResult,
        onDisconnected: _onDisconnected,
      );
      connectionState.value = MeshConnectionState.advertising;
    } catch (e) {
      debugPrint('Advertising failed: $e');
    }
  }

  Future<void> startDiscovery() async {
    try {
      await _nearby.startDiscovery(
        'SESIS-COP-${DateTime.now().millisecondsSinceEpoch}',
        Strategy.P2P_CLUSTER,
        onEndpointDiscovered: _onEndpointDiscovered,
        onEndpointLost: _onEndpointLost,
        onConnectionInitiated: _onConnectionInitiated,
        onConnectionResult: _onConnectionResult,
        onDisconnected: _onDisconnected,
      );
      connectionState.value = MeshConnectionState.discovering;
    } catch (e) {
      debugPrint('Discovery failed: $e');
    }
  }

  Future<void> sendMessage(MeshMessage message) async {
    if (_connectedPeers.isEmpty) {
      await _offlineQueue.enqueue(message);
      return;
    }
    final payload = Payload(bytes: utf8.encode(jsonEncode(message.toJson())));
    for (final endpoint in _connectedPeers.keys) {
      try {
        await _nearby.sendPayload(endpoint, payload);
      } catch (e) {
        debugPrint('Send failed to $endpoint: $e');
        await _offlineQueue.enqueue(message);
      }
    }
  }

  Future<void> disconnect() async {
    try {
      await _nearby.stopAdvertising();
      await _nearby.stopDiscovery();
      for (final endpoint in _connectedPeers.keys) {
        await _nearby.disconnectFromEndpoint(endpoint);
      }
      _connectedPeers.clear();
      peerCount.value = 0;
      connectionState.value = MeshConnectionState.disconnected;
    } catch (e) {
      debugPrint('Disconnect error: $e');
    }
  }

  void _onEndpointDiscovered(String endpointId, String info, String name) {
    _nearby.requestConnection('SESIS-COP', endpointId).catchError((e) {
      debugPrint('Connection request failed: $e');
    });
  }

  void _onEndpointLost(String endpointId) {
    _connectedPeers.remove(endpointId);
    peerCount.value = _connectedPeers.length;
  }

  void _onConnectionInitiated(String endpointId, ConnectionInfo info) {
    _nearby.acceptConnection(endpointId).catchError((e) {
      debugPrint('Accept failed: $e');
    });
  }

  void _onConnectionResult(String endpointId, Status status) {
    if (status == Status.CONNECTED) {
      _connectedPeers[endpointId] = endpointId;
      peerCount.value = _connectedPeers.length;
      connectionState.value = MeshConnectionState.connected;
    }
  }

  void _onDisconnected(String endpointId) {
    _connectedPeers.remove(endpointId);
    peerCount.value = _connectedPeers.length;
    if (_connectedPeers.isEmpty) {
      connectionState.value = MeshConnectionState.disconnected;
    }
  }

  void _onPayload(String endpointId, Payload payload) {
    if (payload.bytes != null) {
      try {
        final json = jsonDecode(utf8.decode(payload.bytes!)) as Map<String, dynamic>;
        final message = MeshMessage.fromJson(json);
        _messageController.add(message);
        _forwardMessage(message);
      } catch (e) {
        debugPrint('Payload decode error: $e');
      }
    }
  }

  void _forwardMessage(MeshMessage message) {
    if (message.ttl > 0 && _connectedPeers.length > 1) {
      final forwarded = MeshMessage(
        type: message.type,
        payload: message.payload,
        senderId: message.senderId,
        timestamp: message.timestamp,
        ttl: message.ttl - 1,
        signature: message.signature,
      );
      sendMessage(forwarded);
    }
  }

  void dispose() {
    disconnect();
    _messageController.close();
  }
}
