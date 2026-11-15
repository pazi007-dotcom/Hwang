import 'package:material_ui/material_ui.dart';

import 'row_db.dart';
import 'sqlite_db.dart';
import 'stations.dart';
import 'store.dart';
import 'sync.dart';
import 'tokens.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final db = await SqfliteDb.open();
  var device = await db.setting('device');
  if (device == null) {
    device = 'phone-${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}';
    await db.setSetting('device', device);
  }
  runApp(JinsungApp(store: Store(db, device: device)));
}

class JinsungApp extends StatefulWidget {
  const JinsungApp({super.key, required this.store});
  final Store store;
  @override
  State<JinsungApp> createState() => _JinsungAppState();
}

class _JinsungAppState extends State<JinsungApp> {
  bool outdoor = false;
  @override
  Widget build(BuildContext context) {
    final t = outdoor ? Tokens.outdoor : Tokens.navy;
    return MaterialApp(
      title: '진성현장',
      debugShowCheckedModeBanner: false,
      theme: t.theme(),
      home: Shell(store: widget.store, tokens: t, onToggleOutdoor: () => setState(() => outdoor = !outdoor)),
    );
  }
}

class Shell extends StatefulWidget {
  const Shell({super.key, required this.store, required this.tokens, required this.onToggleOutdoor});
  final Store store;
  final Tokens tokens;
  final VoidCallback onToggleOutdoor;
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int tab = 0;
  String? siteId;
  List<Rec> sites = [];
  int version = 0; // 자료가 바뀌면 올려서 화면을 다시 그린다

  static const titles = ['오늘 현장 보기', '오늘 일지 쓰기', '집 PC와 맞추기'];

  @override
  void initState() {
    super.initState();
    reload();
  }

  Future<void> reload() async {
    final list = await widget.store.db.all('site');
    list.sort((a, b) => (a['created_at'] as String).compareTo(b['created_at'] as String));
    if (!mounted) return;
    setState(() {
      sites = list;
      if (siteId == null || !list.any((s) => s['id'] == siteId)) {
        siteId = list.isEmpty ? null : list.first['id'] as String;
      }
      version++;
    });
  }

  Future<void> addEmergencySite() async {
    final name = await askText(context, '긴급 현장 만들기', '현장 이름');
    if (name == null || name.trim().isEmpty) return;
    try {
      final id = await widget.store.quickEmergencySite(name);
      siteId = id;
      await reload();
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    final pages = [
      HomePage(key: ValueKey('h$version$siteId'), store: widget.store, siteId: siteId, tokens: t),
      LogPage(key: ValueKey('l$version$siteId'), store: widget.store, siteId: siteId, tokens: t,
          onChanged: reload),
      SyncPage(key: ValueKey('s$version'), store: widget.store, tokens: t, onChanged: reload),
    ];
    return Scaffold(
      appBar: AppBar(title: Text(titles[tab]), actions: [
        TextButton(
            onPressed: widget.onToggleOutdoor,
            child: Text('야외 모드', style: TextStyle(color: t.text, fontSize: Tokens.fNote))),
      ]),
      body: SafeArea(
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Tokens.pad, 0, Tokens.pad, Tokens.gap),
            child: Row2(children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  key: ValueKey('site$siteId${sites.length}'),
                  initialValue: siteId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: '현장'),
                  items: [
                    for (final s in sites)
                      DropdownMenuItem(value: s['id'] as String, child: Text(s['name'] as String)),
                  ],
                  onChanged: (v) => setState(() {
                    siteId = v;
                    version++;
                  }),
                ),
              ),
              SizedBox(
                width: 120,
                child: OutlinedButton(onPressed: addEmergencySite, child: const Text('+ 긴급 현장')),
              ),
            ]),
          ),
          Expanded(child: pages[tab]),
        ]),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: '홈'),
          NavigationDestination(icon: Icon(Icons.edit_note_outlined), label: '일지'),
          NavigationDestination(icon: Icon(Icons.sync_outlined), label: '동기화'),
        ],
      ),
    );
  }
}

class Row2 extends StatelessWidget {
  const Row2({super.key, required this.children});
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => Row(children: [
        for (var i = 0; i < children.length; i++) ...[
          if (i > 0) const SizedBox(width: Tokens.gap),
          children[i],
        ],
      ]);
}

class Section extends StatelessWidget {
  const Section({super.key, required this.title, required this.children});
  final String title;
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(Tokens.pad),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            ...children,
          ]),
        ),
      );
}

class Badge2 extends StatelessWidget {
  const Badge2(this.text, this.color, {super.key});
  final String text;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
        decoration: BoxDecoration(
            border: Border.all(color: color), borderRadius: BorderRadius.circular(999)),
        child: Text(text,
            style: TextStyle(color: color, fontSize: Tokens.fNote, fontWeight: FontWeight.w700)),
      );
}

Widget bigNumber(BuildContext context, String label, String value, String unit, Tokens t) => Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.bodySmall),
        Text.rich(TextSpan(children: [
          TextSpan(
              text: value,
              style: TextStyle(
                  fontSize: 28, fontWeight: FontWeight.w700, color: t.text,
                  fontFeatures: const [FontFeature.tabularFigures()])),
          TextSpan(text: ' $unit', style: TextStyle(fontSize: Tokens.fNote, color: t.sub)),
        ])),
      ],
    );

void showMessage(BuildContext context, String text) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

Future<String?> askText(BuildContext context, String title, String label, {String initial = ''}) {
  final c = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(controller: c, autofocus: true, decoration: InputDecoration(labelText: label)),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('취소')),
        FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('확인')),
      ],
    ),
  );
}

// ───────────────────────── 홈 ─────────────────────────
class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.store, required this.siteId, required this.tokens});
  final Store store;
  final String? siteId;
  final Tokens tokens;

  Future<Map<String, dynamic>> _load() async {
    final today = workDateOf(DateTime.now());
    final id = siteId!;
    final logs = (await store.db.all('work_log')).where((l) => l['site_id'] == id).toList()
      ..sort((a, b) => (b['work_date'] as String).compareTo(a['work_date'] as String));
    final lines = await store.db.all('input_line');
    final recent = [
      for (final l in logs.take(7))
        {
          'work_date': l['work_date'],
          'no_work': l['no_work'] == 1,
          'count': lines.where((x) => x['log_id'] == l['id']).length,
          'amount': lines.where((x) => x['log_id'] == l['id']).fold<int>(0, (s, x) => s + (x['amount'] as int)),
        },
    ];
    return {
      'today': today,
      'hasToday': logs.any((l) => l['work_date'] == today),
      'cost': await store.monthCost(id, today.substring(0, 7)),
      'locked': await store.isLocked(today.substring(0, 7)),
      'conflicts': (await store.db.openConflicts()).length,
      'pending': (await store.db.changesSince(await store.db.cursor('집PC', 'out'), onlyDevice: store.device)).length,
      'recent': recent,
    };
  }

  @override
  Widget build(BuildContext context) {
    final t = tokens;
    if (siteId == null) {
      return const Center(
          child: Padding(
              padding: EdgeInsets.all(Tokens.group),
              child: Text('현장이 없습니다. 동기화로 현장을 받아 오거나 + 긴급 현장으로 만드세요.')));
    }
    return FutureBuilder<Map<String, dynamic>>(
      future: _load(),
      builder: (context, snap) {
        if (!snap.hasData) return const Center(child: CircularProgressIndicator());
        final d = snap.data!;
        final todo = <String>[
          if (!(d['hasToday'] as bool)) '오늘 일지 미작성',
          if ((d['conflicts'] as int) > 0) '충돌 검토 ${d['conflicts']}건',
          if ((d['pending'] as int) > 0) '집 PC로 보낼 기록 ${d['pending']}건',
        ];
        return ListView(padding: const EdgeInsets.all(Tokens.pad), children: [
          Section(title: '이달', children: [
            Row(children: [
              Expanded(child: bigNumber(context, '투입 원가', wonText(d['cost'] as int), '원', t)),
              Expanded(child: bigNumber(context, '월 마감', (d['locked'] as bool) ? '마감' : '진행 중', '', t)),
            ]),
          ]),
          const SizedBox(height: Tokens.gap),
          Section(title: '오늘 할 일', children: [
            if (todo.isEmpty) Text('오늘 할 일이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
            for (final x in todo.take(3))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(children: [Badge2('할 일', t.warn), const SizedBox(width: 8), Expanded(child: Text(x))]),
              ),
          ]),
          const SizedBox(height: Tokens.gap),
          Section(title: '최근 일지', children: [
            if ((d['recent'] as List).isEmpty) Text('일지가 없습니다.', style: Theme.of(context).textTheme.bodySmall),
            for (final r in d['recent'] as List)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(children: [
                  Expanded(child: Text(r['work_date'] as String)),
                  Text((r['no_work'] as bool) ? '작업 없음' : '${r['count']}줄',
                      style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(width: Tokens.gap),
                  Text('${wonText(r['amount'] as int)}원',
                      style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()])),
                ]),
              ),
          ]),
        ]);
      },
    );
  }
}

// ───────────────────────── 일지 ─────────────────────────
class LogPage extends StatefulWidget {
  const LogPage({super.key, required this.store, required this.siteId, required this.tokens,
      required this.onChanged});
  final Store store;
  final String? siteId;
  final Tokens tokens;
  final Future<void> Function() onChanged;
  @override
  State<LogPage> createState() => _LogPageState();
}

class _LogPageState extends State<LogPage> {
  DateTime date = DateTime.now();
  String kind = '인력';
  String? rateId;
  String? payeeId;
  String? workTypeId;
  final qty = TextEditingController(text: '1');
  final staFrom = TextEditingController();
  final staTo = TextEditingController();

  String get workDate => workDateOf(date);

  Future<Map<String, dynamic>> _load() async {
    final s = widget.store;
    final rates = (await s.db.all('rate')).where((r) => r['kind'] == kind).toList()
      ..sort((a, b) => ('${a['item']}${a['spec']}').compareTo('${b['item']}${b['spec']}'));
    final payees = await s.db.all('payee')
      ..sort((a, b) => (a['name'] as String).compareTo(b['name'] as String));
    final wts = (await s.db.all('work_type')).where((w) => w['site_id'] == widget.siteId).toList();
    final lines = widget.siteId == null ? <Rec>[] : await s.linesOf(widget.siteId!, workDate);
    return {
      'rates': rates, 'payees': payees, 'wts': wts, 'lines': lines,
      'names': {for (final p in payees) p['id']: p['name']},
    };
  }

  Future<void> _pickDate() async {
    final d = await showDatePicker(
        context: context, initialDate: date, firstDate: DateTime(2020), lastDate: DateTime(2100),
        helpText: '작업일 (밀린 일지는 날짜를 바꿔서 입력)');
    if (d != null) setState(() => date = d);
  }

  Future<void> _save(List<Rec> rates) async {
    final s = widget.store;
    try {
      final rate = rates.firstWhere((r) => r['id'] == rateId, orElse: () => throw StoreError('항목을 골라 주세요.'));
      if (payeeId == null) throw StoreError('받는 곳을 골라 주세요.');
      String? a, b;
      if (staFrom.text.trim().isNotEmpty && staTo.text.trim().isNotEmpty) {
        var x = parseSta(staFrom.text), y = parseSta(staTo.text);
        if (y < x) (x, y) = (y, x);
        a = staText(x);
        b = staText(y);
      }
      String? reason;
      if (await s.isLocked(workDate.substring(0, 7))) {
        if (!mounted) return;
        reason = await askText(context, '마감된 달입니다', '추가하는 사유 (정정 보고서에 남습니다)');
        if (reason == null || reason.trim().isEmpty) return;
      }
      await s.addInput(widget.siteId, workDate, kind, rate['item'] as String, qty.text, payeeId!,
          spec: (rate['spec'] ?? '') as String, workTypeId: workTypeId, staFrom: a, staTo: b, reason: reason);
      if (workTypeId != null && a != null && b != null) {
        await s.addProgress(widget.siteId!, workDate, workTypeId!, staText(num.parse(b) - num.parse(a)), 'm',
            staFrom: a, staTo: b);
      }
      await widget.onChanged();
      if (mounted) showMessage(context, '$workDate 일지에 저장했습니다.');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  Future<void> _noWork() async {
    try {
      await widget.store.markNoWork(widget.siteId!, workDate);
      await widget.onChanged();
      if (mounted) showMessage(context, "$workDate '작업 없음'으로 남겼습니다.");
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    if (widget.siteId == null) return const Center(child: Text('현장을 먼저 고르세요.'));
    return FutureBuilder<Map<String, dynamic>>(
      future: _load(),
      builder: (context, snap) {
        if (!snap.hasData) return const Center(child: CircularProgressIndicator());
        final d = snap.data!;
        final rates = d['rates'] as List<Rec>;
        final payees = d['payees'] as List<Rec>;
        final wts = d['wts'] as List<Rec>;
        final lines = d['lines'] as List<Rec>;
        final names = d['names'] as Map;
        final total = lines.fold<int>(0, (s, l) => s + (l['amount'] as int));
        if (!rates.any((r) => r['id'] == rateId)) rateId = null;
        return ListView(padding: const EdgeInsets.all(Tokens.pad), children: [
          Section(title: '1. 작업일', children: [
            OutlinedButton(onPressed: _pickDate, child: Text(workDate)),
          ]),
          const SizedBox(height: Tokens.gap),
          Section(title: '2. 투입 한 줄', children: [
            SegmentedButton<String>(
              segments: [for (final k in kinds) ButtonSegment(value: k, label: Text(k))],
              selected: {kind},
              onSelectionChanged: (v) => setState(() {
                kind = v.first;
                rateId = null;
              }),
            ),
            const SizedBox(height: Tokens.gap),
            DropdownButtonFormField<String>(
              key: ValueKey('rate$kind$rateId'),
              initialValue: rateId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: '항목 (기준 정보 단가)'),
              items: [
                for (final r in rates)
                  DropdownMenuItem(
                      value: r['id'] as String,
                      child: Text('${r['item']} ${r['spec'] ?? ''} · ${wonText(r['unit_price'] as int)}원/${r['unit']}'
                          '${r['is_draft'] == 1 ? ' (초안)' : ''}')),
              ],
              onChanged: (v) => setState(() => rateId = v),
            ),
            const SizedBox(height: Tokens.gap),
            Row2(children: [
              Expanded(
                child: TextField(
                    controller: qty,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: '수량 (반일 = 0.5)')),
              ),
              Expanded(
                child: DropdownButtonFormField<String>(
                  key: ValueKey('payee$payeeId${payees.length}'),
                  initialValue: payeeId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: '받는 곳'),
                  items: [
                    for (final p in payees)
                      DropdownMenuItem(value: p['id'] as String, child: Text(p['name'] as String)),
                  ],
                  onChanged: (v) => setState(() => payeeId = v),
                ),
              ),
            ]),
            const SizedBox(height: Tokens.gap),
            DropdownButtonFormField<String?>(
              key: ValueKey('wt$workTypeId${wts.length}'),
              initialValue: workTypeId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: '공종 (선택)'),
              items: [
                const DropdownMenuItem(value: null, child: Text('공종 없음')),
                for (final w in wts)
                  DropdownMenuItem(value: w['id'] as String, child: Text(w['name'] as String)),
              ],
              onChanged: (v) => setState(() => workTypeId = v),
            ),
            const SizedBox(height: Tokens.gap),
            Row2(children: [
              Expanded(
                  child: TextField(
                      controller: staFrom, decoration: const InputDecoration(labelText: '측점 시작 (No.2+10)'))),
              Expanded(
                  child: TextField(controller: staTo, decoration: const InputDecoration(labelText: '측점 끝 (No.4)'))),
            ]),
            const SizedBox(height: Tokens.gap),
            FilledButton(onPressed: () => _save(rates), child: const Text('저장')),
            const SizedBox(height: 8),
            OutlinedButton(onPressed: _noWork, child: const Text('오늘은 작업 없음 (비 등)')),
          ]),
          const SizedBox(height: Tokens.gap),
          Section(title: '3. $workDate 투입 · 합계 ${wonText(total)}원', children: [
            if (lines.isEmpty) Text('아직 입력한 줄이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
            for (final l in lines)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(children: [
                  Badge2(l['kind'] as String, t.blue),
                  const SizedBox(width: 8),
                  Expanded(
                      child: Text('${l['item']} ${l['spec'] ?? ''} ${l['qty']}${l['unit']} · ${names[l['payee_id']] ?? ''}'
                          '${l['sta_from'] != null ? '\n${formatSta(num.parse(l['sta_from'] as String))} ~ ${formatSta(num.parse(l['sta_to'] as String))}' : ''}')),
                  Text('${wonText(l['amount'] as int)}원',
                      style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()])),
                ]),
              ),
          ]),
        ]);
      },
    );
  }
}

// ───────────────────────── 동기화 ─────────────────────────
class SyncPage extends StatefulWidget {
  const SyncPage({super.key, required this.store, required this.tokens, required this.onChanged});
  final Store store;
  final Tokens tokens;
  final Future<void> Function() onChanged;
  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> {
  final url = TextEditingController();
  final token = TextEditingController();
  String status = '';
  bool busy = false;

  @override
  void initState() {
    super.initState();
    () async {
      url.text = await widget.store.db.setting('server_url') ?? '';
      token.text = await widget.store.db.setting('server_token') ?? '';
      final last = await widget.store.db.setting('last_sync') ?? '';
      if (mounted) setState(() => status = last);
    }();
  }

  Future<void> _sync() async {
    final s = widget.store;
    final base = url.text.trim().replaceAll(RegExp(r'/+$'), '');
    if (base.isEmpty) return showMessage(context, '집 PC 주소를 넣어 주세요. (예: http://100.x.x.x:8765)');
    setState(() => busy = true);
    try {
      await s.db.setSetting('server_url', base);
      await s.db.setSetting('server_token', token.text);
      final r = await ServerLink(base, token: token.text).sync(s);
      final text = '${s.now().substring(0, 16).replaceFirst('T', ' ')} · $r';
      await s.db.setSetting('last_sync', text);
      await widget.onChanged();
      if (mounted) setState(() => status = text);
    } on StoreError catch (e) {
      if (mounted) setState(() => status = '실패: ${e.message}');
    } catch (e) {
      if (mounted) setState(() => status = '집 PC에 연결되지 않았습니다. 입력은 폰에 그대로 남아 있습니다.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    return FutureBuilder<List<Rec>>(
      future: widget.store.db.openConflicts(),
      builder: (context, snap) {
        final conflicts = snap.data ?? const <Rec>[];
        return ListView(padding: const EdgeInsets.all(Tokens.pad), children: [
          Section(title: '집 PC 서버', children: [
            TextField(controller: url, decoration: const InputDecoration(labelText: '주소 (Tailscale)')),
            const SizedBox(height: Tokens.gap),
            TextField(controller: token, obscureText: true, decoration: const InputDecoration(labelText: '토큰')),
            const SizedBox(height: Tokens.gap),
            FilledButton(onPressed: busy ? null : _sync, child: Text(busy ? '맞추는 중…' : '지금 맞추기')),
            if (status.isNotEmpty)
              Padding(padding: const EdgeInsets.only(top: 8), child: Text(status, style: Theme.of(context).textTheme.bodySmall)),
          ]),
          const SizedBox(height: Tokens.gap),
          Section(title: '충돌 검토 ${conflicts.length}건', children: [
            if (conflicts.isEmpty) Text('충돌이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
            for (final c in conflicts) ...[
              Text('${c['table_name']} · 두 기기가 같은 기록을 고쳤습니다.', style: Theme.of(context).textTheme.bodySmall),
              Text('먼저 저장된 값: ${_show(c['current'] as Map, c['incoming'] as Map)}'),
              Text('이 폰의 값: ${_show(c['incoming'] as Map, c['incoming'] as Map)}', style: TextStyle(color: t.warn)),
              const SizedBox(height: 8),
              Row2(children: [
                Expanded(child: OutlinedButton(onPressed: () => _resolve(c, 'current'), child: const Text('먼저 값 유지'))),
                Expanded(child: FilledButton(onPressed: () => _resolve(c, 'incoming'), child: const Text('이 폰 값'))),
              ]),
              const Divider(height: Tokens.group),
            ],
          ]),
        ]);
      },
    );
  }

  String _show(Map values, Map keys) =>
      keys.keys.where((k) => k != 'amount').map((k) => '$k=${values[k] ?? '삭제'}').join(', ');

  Future<void> _resolve(Rec c, String keep) async {
    try {
      await widget.store.resolveConflict(c, keep);
      await widget.onChanged();
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }
}
