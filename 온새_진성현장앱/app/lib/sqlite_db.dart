import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import 'row_db.dart';

/// 폰 안의 SQLite. 인터넷이 없어도 모든 입력이 여기에 저장된다.
class SqfliteDb implements RowDb {
  SqfliteDb._(this._db);
  final Database _db;

  static Future<SqfliteDb> open([String name = 'jinsung.db']) async {
    final path = p.join(await getDatabasesPath(), name);
    final db = await openDatabase(path, version: 1, onCreate: (db, _) async {
      await db.execute('CREATE TABLE row (table_name TEXT NOT NULL, id TEXT NOT NULL,'
          ' data TEXT NOT NULL, PRIMARY KEY (table_name, id))');
      await db.execute('CREATE TABLE change_log (seq INTEGER PRIMARY KEY AUTOINCREMENT,'
          ' table_name TEXT NOT NULL, row_id TEXT NOT NULL, op TEXT NOT NULL, base_version INTEGER,'
          ' data_json TEXT, reason TEXT, device TEXT NOT NULL, at TEXT NOT NULL)');
      await db.execute('CREATE TABLE sync_cursor (peer TEXT NOT NULL, dir TEXT NOT NULL,'
          ' seq INTEGER NOT NULL, PRIMARY KEY (peer, dir))');
      await db.execute('CREATE TABLE id_alias (alias_id TEXT PRIMARY KEY, real_id TEXT NOT NULL)');
      await db.execute('CREATE TABLE conflict (id TEXT PRIMARY KEY, data TEXT NOT NULL,'
          ' resolved INTEGER NOT NULL DEFAULT 0)');
      await db.execute('CREATE TABLE setting (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
    });
    return SqfliteDb._(db);
  }

  @override
  Future<Rec?> get(String table, String id) async {
    final r = await _db.query('row', where: 'table_name=? AND id=?', whereArgs: [table, id]);
    return r.isEmpty ? null : jsonDecode(r.first['data'] as String) as Rec;
  }

  @override
  Future<List<Rec>> all(String table) async {
    final r = await _db.query('row', where: 'table_name=?', whereArgs: [table]);
    return r.map((e) => jsonDecode(e['data'] as String) as Rec).toList();
  }

  @override
  Future<void> put(String table, Rec row) => _db.insert(
      'row', {'table_name': table, 'id': row['id'], 'data': jsonEncode(row)},
      conflictAlgorithm: ConflictAlgorithm.replace);

  @override
  Future<void> remove(String table, String id) =>
      _db.delete('row', where: 'table_name=? AND id=?', whereArgs: [table, id]);

  @override
  Future<int> appendChange(Rec change) {
    final c = Map<String, dynamic>.from(change)..remove('seq');
    return _db.insert('change_log', c);
  }

  @override
  Future<List<Rec>> changesSince(int seq, {String? onlyDevice}) async {
    final r = await _db.query('change_log',
        where: onlyDevice == null ? 'seq > ?' : 'seq > ? AND device = ?',
        whereArgs: onlyDevice == null ? [seq] : [seq, onlyDevice],
        orderBy: 'seq');
    return r.map((e) => Map<String, dynamic>.from(e)).toList();
  }

  @override
  Future<int> cursor(String peer, String dir) async {
    final r = await _db.query('sync_cursor', where: 'peer=? AND dir=?', whereArgs: [peer, dir]);
    return r.isEmpty ? 0 : r.first['seq'] as int;
  }

  @override
  Future<void> setCursor(String peer, String dir, int seq) => _db.insert(
      'sync_cursor', {'peer': peer, 'dir': dir, 'seq': seq},
      conflictAlgorithm: ConflictAlgorithm.replace);

  @override
  Future<String?> alias(String id) async {
    final r = await _db.query('id_alias', where: 'alias_id=?', whereArgs: [id]);
    return r.isEmpty ? null : r.first['real_id'] as String;
  }

  @override
  Future<void> setAlias(String aliasId, String realId) => _db.insert(
      'id_alias', {'alias_id': aliasId, 'real_id': realId},
      conflictAlgorithm: ConflictAlgorithm.replace);

  @override
  Future<void> addConflict(Rec conflict) =>
      _db.insert('conflict', {'id': conflict['id'], 'data': jsonEncode(conflict), 'resolved': 0});

  @override
  Future<List<Rec>> openConflicts() async {
    final r = await _db.query('conflict', where: 'resolved=0');
    return r.map((e) => jsonDecode(e['data'] as String) as Rec).toList();
  }

  @override
  Future<void> closeConflict(String id) =>
      _db.update('conflict', {'resolved': 1}, where: 'id=?', whereArgs: [id]);

  @override
  Future<String?> setting(String key) async {
    final r = await _db.query('setting', where: 'key=?', whereArgs: [key]);
    return r.isEmpty ? null : r.first['value'] as String;
  }

  @override
  Future<void> setSetting(String key, String value) => _db.insert(
      'setting', {'key': key, 'value': value},
      conflictAlgorithm: ConflictAlgorithm.replace);
}
