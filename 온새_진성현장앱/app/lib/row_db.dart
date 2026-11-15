/// 폰 안의 저장소. 서버와 같은 모양의 기록(행)을 표 이름 + 번호로 보관한다.
/// 기록 내용은 서버가 주는 그대로 두기 때문에 서버에 칸이 늘어도 폰 저장 구조는 바뀌지 않는다.
library;

typedef Rec = Map<String, dynamic>;

abstract class RowDb {
  Future<Rec?> get(String table, String id);
  Future<List<Rec>> all(String table);
  Future<void> put(String table, Rec row);
  Future<void> remove(String table, String id);

  /// 변경 기록(동기화 단위)을 쌓고 순번을 돌려준다.
  Future<int> appendChange(Rec change);
  Future<List<Rec>> changesSince(int seq, {String? onlyDevice});

  Future<int> cursor(String peer, String dir);
  Future<void> setCursor(String peer, String dir, int seq);

  Future<String?> alias(String id);
  Future<void> setAlias(String aliasId, String realId);

  Future<void> addConflict(Rec conflict);
  Future<List<Rec>> openConflicts();
  Future<void> closeConflict(String id);

  Future<String?> setting(String key);
  Future<void> setSetting(String key, String value);
}

/// 테스트용(메모리). 실제 폰에서는 SqfliteDb 를 쓴다.
class MemoryDb implements RowDb {
  final Map<String, Map<String, Rec>> _tables = {};
  final List<Rec> _changes = [];
  final Map<String, int> _cursors = {};
  final Map<String, String> _alias = {};
  final List<Rec> _conflicts = [];
  final Map<String, String> _settings = {};

  @override
  Future<Rec?> get(String table, String id) async {
    final r = _tables[table]?[id];
    return r == null ? null : Map<String, dynamic>.from(r);
  }

  @override
  Future<List<Rec>> all(String table) async =>
      (_tables[table]?.values ?? const <Rec>[]).map((r) => Map<String, dynamic>.from(r)).toList();

  @override
  Future<void> put(String table, Rec row) async {
    _tables.putIfAbsent(table, () => {})[row['id'] as String] = Map<String, dynamic>.from(row);
  }

  @override
  Future<void> remove(String table, String id) async {
    _tables[table]?.remove(id);
  }

  @override
  Future<int> appendChange(Rec change) async {
    final seq = _changes.length + 1;
    _changes.add({...change, 'seq': seq});
    return seq;
  }

  @override
  Future<List<Rec>> changesSince(int seq, {String? onlyDevice}) async => _changes
      .where((c) => (c['seq'] as int) > seq && (onlyDevice == null || c['device'] == onlyDevice))
      .map((c) => Map<String, dynamic>.from(c))
      .toList();

  @override
  Future<int> cursor(String peer, String dir) async => _cursors['$peer/$dir'] ?? 0;

  @override
  Future<void> setCursor(String peer, String dir, int seq) async {
    _cursors['$peer/$dir'] = seq;
  }

  @override
  Future<String?> alias(String id) async => _alias[id];

  @override
  Future<void> setAlias(String aliasId, String realId) async {
    _alias[aliasId] = realId;
  }

  @override
  Future<void> addConflict(Rec conflict) async {
    _conflicts.add({...conflict, 'resolved': 0});
  }

  @override
  Future<List<Rec>> openConflicts() async =>
      _conflicts.where((c) => c['resolved'] == 0).map((c) => Map<String, dynamic>.from(c)).toList();

  @override
  Future<void> closeConflict(String id) async {
    for (final c in _conflicts) {
      if (c['id'] == id) c['resolved'] = 1;
    }
  }

  @override
  Future<String?> setting(String key) async => _settings[key];

  @override
  Future<void> setSetting(String key, String value) async {
    _settings[key] = value;
  }
}
