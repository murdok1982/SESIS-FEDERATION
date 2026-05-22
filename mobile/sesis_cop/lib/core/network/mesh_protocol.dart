import 'dart:convert';
import 'package:flutter/foundation.dart';

enum MeshMessageType {
  intelUpdate,
  fieldReport,
  alert,
  locationBeacon,
  opord,
  duressSignal,
}

extension MeshMessageTypeExtension on MeshMessageType {
  String get value {
    return name[0].toLowerCase() + name.substring(1);
  }

  static MeshMessageType fromString(String s) {
    return MeshMessageType.values.firstWhere(
      (e) => e.name.toLowerCase() == s.toLowerCase(),
      orElse: () => MeshMessageType.intelUpdate,
    );
  }
}

class MeshMessage {
  final MeshMessageType type;
  final Map<String, dynamic> payload;
  final String senderId;
  final int timestamp;
  final int ttl;
  final String signature;
  final String? relayPath;

  const MeshMessage({
    required this.type,
    required this.payload,
    required this.senderId,
    required this.timestamp,
    this.ttl = 3,
    this.signature = '',
    this.relayPath,
  });

  Map<String, dynamic> toJson() => {
        'type': type.value,
        'payload': payload,
        'senderId': senderId,
        'timestamp': timestamp,
        'ttl': ttl,
        'signature': signature,
        if (relayPath != null) 'relayPath': relayPath,
      };

  factory MeshMessage.fromJson(Map<String, dynamic> json) => MeshMessage(
        type: MeshMessageTypeExtension.fromString(json['type'] as String),
        payload: Map<String, dynamic>.from(json['payload'] as Map),
        senderId: json['senderId'] as String,
        timestamp: json['timestamp'] as int,
        ttl: json['ttl'] as int? ?? 3,
        signature: json['signature'] as String? ?? '',
        relayPath: json['relayPath'] as String?,
      );

  MeshMessage copyWith({
    MeshMessageType? type,
    Map<String, dynamic>? payload,
    String? senderId,
    int? timestamp,
    int? ttl,
    String? signature,
    String? relayPath,
  }) {
    return MeshMessage(
      type: type ?? this.type,
      payload: payload ?? this.payload,
      senderId: senderId ?? this.senderId,
      timestamp: timestamp ?? this.timestamp,
      ttl: ttl ?? this.ttl,
      signature: signature ?? this.signature,
      relayPath: relayPath ?? this.relayPath,
    );
  }
}

class MeshRouter {
  final Map<String, List<MeshMessage>> _messageStore = {};
  final Set<String> _seenMessages = {};

  void store(String nodeId, MeshMessage message) {
    final msgId = '${message.senderId}_${message.timestamp}_${message.type.value}';
    if (_seenMessages.contains(msgId)) return;
    _seenMessages.add(msgId);
    _messageStore.putIfAbsent(nodeId, () => []).add(message);

    if (_messageStore.length > 1000) {
      final oldest = _messageStore.keys.first;
      _messageStore[oldest]?.removeAt(0);
      if (_messageStore[oldest]?.isEmpty ?? true) {
        _messageStore.remove(oldest);
      }
    }
  }

  List<MeshMessage> getMessagesForRelay(String nodeId) {
    final messages = _messageStore[nodeId];
    if (messages == null) return [];
    return messages.where((m) => m.ttl > 0).toList();
  }

  void clear() {
    _messageStore.clear();
    _seenMessages.clear();
  }
}
