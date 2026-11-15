/// 동기화: 항상 보내기(push) → 받기(pull). 인터넷이 끊겨도 입력은 계속되고, 연결되면 밀린 만큼 오간다.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'row_db.dart';
import 'store.dart';

typedef Sender = Future<List<Rec>> Function(List<Rec> changes);
typedef Fetcher = Future<List<Rec>> Function(int since);

class SyncResult {
  SyncResult(this.sent, this.received, this.conflicts);
  final int sent;
  final int received;
  final int conflicts;
  @override
  String toString() => '보냄 $sent · 받음 $received · 충돌 $conflicts';
}

Future<SyncResult> syncWith(Store store, Sender send, Fetcher fetch, {String peer = '집PC'}) async {
  var conflicts = 0;
  final out = await store.db
      .changesSince(await store.db.cursor(peer, 'out'), onlyDevice: store.device);
  if (out.isNotEmpty) {
    for (final res in await send(out)) {
      if (res['status'] == '충돌') {
        await store.adopt(res);
        conflicts++;
      } else if (res['status'] == '이어 붙임') {
        final mine = out.firstWhere((c) => c['seq'] == res['seq']);
        await store.db.setAlias(res['real_id'] as String, mine['row_id'] as String);
      }
    }
    await store.db.setCursor(peer, 'out', out.last['seq'] as int);
  }
  final incoming = await fetch(await store.db.cursor(peer, 'in'));
  for (final ch in incoming) {
    final res = await store.applyChange(ch);
    if (res['status'] == '충돌') conflicts++;
  }
  if (incoming.isNotEmpty) await store.db.setCursor(peer, 'in', incoming.last['seq'] as int);
  return SyncResult(out.length, incoming.length, conflicts);
}

/// 집 PC 서버(HTTP)와 동기화.
class ServerLink {
  ServerLink(this.baseUrl, {this.token, http.Client? client}) : _client = client ?? http.Client();
  final String baseUrl;
  final String? token;
  final http.Client _client;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null && token!.isNotEmpty) 'X-Jinsung-Token': token!,
      };

  List<Rec> _rows(http.Response res) {
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    if (res.statusCode != 200) {
      throw StoreError((body is Map ? body['error'] : null)?.toString() ?? '서버 오류 ${res.statusCode}');
    }
    return (body as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Rec>> send(List<Rec> changes) async => _rows(await _client
      .post(Uri.parse('$baseUrl/api/sync/push'), headers: _headers, body: jsonEncode({'changes': changes}))
      .timeout(const Duration(seconds: 30)));

  Future<List<Rec>> fetch(int since, String device) async => _rows(await _client
      .get(Uri.parse('$baseUrl/api/sync/pull?since=$since&device=${Uri.encodeQueryComponent(device)}'),
          headers: _headers)
      .timeout(const Duration(seconds: 30)));

  Future<SyncResult> sync(Store store) =>
      syncWith(store, send, (since) => fetch(since, store.device));
}
