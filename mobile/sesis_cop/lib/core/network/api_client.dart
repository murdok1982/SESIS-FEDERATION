import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../../core/constants.dart';

class ApiClient {
  ApiClient._();
  static final ApiClient _instance = ApiClient._();
  factory ApiClient() => _instance;

  final http.Client _client = http.Client();
  String? _authToken;

  static const String _certFingerprint = 'SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=';

  void setToken(String token) {
    _authToken = token;
  }

  void clearToken() {
    _authToken = null;
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (_authToken != null) 'Authorization': 'Bearer $_authToken',
        'X-Client-Version': AppConstants.version,
      };

  Future<Map<String, dynamic>> get(String path, {Map<String, String>? queryParams}) async {
    try {
      final uri = Uri.parse('${AppConstants.apiBaseUrl}$path').replace(queryParameters: queryParams);
      final response = await _client.get(uri, headers: _headers).timeout(
        Duration(seconds: AppConstants.connectionTimeout),
      );
      return _handleResponse(response);
    } on SocketException {
      throw ApiException('No internet connection', 0);
    } on http.ClientException catch (e) {
      throw ApiException(e.message, 0);
    }
  }

  Future<Map<String, dynamic>> post(String path, {Map<String, dynamic>? body}) async {
    try {
      final uri = Uri.parse('${AppConstants.apiBaseUrl}$path');
      final response = await _client.post(uri, headers: _headers, body: body != null ? jsonEncode(body) : null).timeout(
        Duration(seconds: AppConstants.connectionTimeout),
      );
      return _handleResponse(response);
    } on SocketException {
      throw ApiException('No internet connection', 0);
    } on http.ClientException catch (e) {
      throw ApiException(e.message, 0);
    }
  }

  Future<Map<String, dynamic>> put(String path, {Map<String, dynamic>? body}) async {
    try {
      final uri = Uri.parse('${AppConstants.apiBaseUrl}$path');
      final response = await _client.put(uri, headers: _headers, body: body != null ? jsonEncode(body) : null).timeout(
        Duration(seconds: AppConstants.connectionTimeout),
      );
      return _handleResponse(response);
    } on SocketException {
      throw ApiException('No internet connection', 0);
    } on http.ClientException catch (e) {
      throw ApiException(e.message, 0);
    }
  }

  Future<Map<String, dynamic>> delete(String path) async {
    try {
      final uri = Uri.parse('${AppConstants.apiBaseUrl}$path');
      final response = await _client.delete(uri, headers: _headers).timeout(
        Duration(seconds: AppConstants.connectionTimeout),
      );
      return _handleResponse(response);
    } on SocketException {
      throw ApiException('No internet connection', 0);
    } on http.ClientException catch (e) {
      throw ApiException(e.message, 0);
    }
  }

  Map<String, dynamic> _handleResponse(http.Response response) {
    final body = response.body.isNotEmpty ? jsonDecode(response.body) as Map<String, dynamic> : <String, dynamic>{};
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return body;
    }
    throw ApiException(body['message'] as String? ?? 'Request failed', response.statusCode);
  }

  void dispose() {
    _client.close();
  }
}

class ApiException implements Exception {
  final String message;
  final int statusCode;
  ApiException(this.message, this.statusCode);

  @override
  String toString() => 'ApiException($statusCode): $message';
}
