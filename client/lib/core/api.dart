import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'data.dart';

class ApiException implements Exception {
  final String message;
  final String code;
  final int status;
  final Object? cause;
  ApiException(this.message, {this.code = '', this.status = 0, this.cause});
  @override
  String toString() => message;
}

class ApiClient {
  String baseUrl;
  String token;
  final HttpClient _http;
  ApiClient({
    this.baseUrl = 'http://10.0.2.2:8787',
    this.token = '',
    HttpClient? http,
  }) : _http = http ?? HttpClient() {
    _http.connectionTimeout = const Duration(seconds: 5);
  }
  Future<Json> get(String path) => request('GET', path);
  Future<Json> post(String path, [Json? data, String? key]) =>
      request('POST', path, data: data ?? {}, key: key);
  Future<Json> put(String path, Json data) => request('PUT', path, data: data);
  Future<Json> patch(String path, Json data) =>
      request('PATCH', path, data: data);
  Future<Json> delete(String path) => request('DELETE', path);

  Future<Json> request(
    String method,
    String path, {
    Json? data,
    String? key,
  }) async {
    final bytes = await _send(method, path, data, key, 'application/json');
    final envelope = object(jsonDecode(utf8.decode(bytes)));
    if (!envelope.containsKey('data')) {
      throw ApiException('电脑服务返回的数据格式不正确', code: 'INVALID_RESPONSE');
    }
    final result = envelope['data'];
    return result is List ? {'items': result} : object(result);
  }

  Future<Uint8List> report(String period, String end) async {
    final bytes = await _send(
      'POST',
      '/reports',
      {'period': period, 'end': end},
      null,
      'application/pdf',
    );
    if (bytes.length < 5 ||
        ascii.decode(bytes.sublist(0, 5), allowInvalid: true) != '%PDF-') {
      throw ApiException('电脑服务未返回有效 PDF');
    }
    return bytes;
  }

  Future<Uint8List> _send(
    String method,
    String path,
    Json? data,
    String? key,
    String accept,
  ) async {
    try {
      final request = await _http.openUrl(
        method,
        Uri.parse('$baseUrl/api/v1$path'),
      );
      request.followRedirects = false;
      request.headers.set(HttpHeaders.acceptHeader, accept);
      if (token.isNotEmpty) {
        request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      }
      if (data != null) {
        request.headers.contentType = ContentType.json;
        if (key != null) request.headers.set('Idempotency-Key', key);
        final payload = utf8.encode(jsonEncode(data));
        request.contentLength = payload.length;
        request.add(payload);
      }
      final response = await request.close().timeout(
        const Duration(seconds: 70),
      );
      final bytes = BytesBuilder();
      await for (final chunk in response.timeout(const Duration(seconds: 70))) {
        bytes.add(chunk);
        if (bytes.length > 10 * 1024 * 1024) {
          throw ApiException('响应超过 10 MB，已停止读取');
        }
      }
      final result = bytes.takeBytes();
      if (response.statusCode >= 300) {
        final body = object(jsonDecode(utf8.decode(result)));
        throw ApiException(
          body.s('message'),
          code: body.s('code'),
          status: response.statusCode,
        );
      }
      return result;
    } on SocketException catch (e) {
      throw ApiException('无法连接电脑服务，请检查地址、端口和电脑上的服务窗口', cause: e);
    } on TimeoutException catch (e) {
      throw ApiException('电脑服务响应超时；保存请求可使用原内容重试', cause: e);
    } on HttpException catch (e) {
      throw ApiException('与电脑服务的连接中断', cause: e);
    }
  }

  void close() => _http.close();
}

/// A write is frozen after the first attempt. Retrying keeps both content and key.
class PendingWrite {
  final String key;
  final String path;
  final String encoded;
  String? serverUrl;
  PendingWrite(this.path, Json payload, {String? key, this.serverUrl})
    : key = key ?? operationKey(),
      encoded = jsonEncode(payload);
  Json get payload => object(jsonDecode(encoded));
  Json toJson() => {
    'key': key,
    'path': path,
    'payload': payload,
    'server_url': serverUrl,
  };
  factory PendingWrite.fromJson(Json json) => PendingWrite(
    json.s('path'),
    json.obj('payload'),
    key: json.s('key'),
    serverUrl: json['server_url'] as String?,
  );
  Future<Json> send(ApiClient api) {
    if (serverUrl != null && api.baseUrl != serverUrl) {
      throw ApiException('此待处理请求属于 $serverUrl，请切回该电脑服务后重试');
    }
    return api.post(path, payload, key);
  }
}
