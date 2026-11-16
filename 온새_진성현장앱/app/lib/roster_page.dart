// 명부 탭: 작업자·장비 미리 등록 → 사람·장비별 출역표(달력), 월·연간 집계.
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import 'ledger.dart';
import 'main.dart';
import 'roster.dart';
import 'store.dart';
import 'tokens.dart';

class RosterPage extends StatefulWidget {
  const RosterPage({super.key, required this.store, required this.tokens, required this.onChanged});
  final Store store;
  final Tokens tokens;
  final Future<void> Function() onChanged;
  @override
  State<RosterPage> createState() => _RosterPageState();
}

class _RosterPageState extends State<RosterPage> {
  int refresh = 0;
  Store get s => widget.store;

  Future<void> _edit([RosterEntry? r]) async {
    final ok = await showModalBottomSheet<bool>(
        context: context, isScrollControlled: true, builder: (_) => RosterEditor(entry: r));
    if (ok != true) return;
    final v = RosterEditor.result!;
    try {
      await s.saveRoster(kind: v['kind']!, payee: v['payee']!, item: v['item']!, unit: v['unit']!,
          unitPrice: v['price']!, spec: v['spec']!, phone: v['phone'], memo: v['memo']);
      setState(() => refresh++);
      await widget.onChanged();
      if (mounted) showMessage(context, '명부에 저장했습니다: ${v['payee']} · ${v['item']}');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    return FutureBuilder<List<RosterEntry>>(
      key: ValueKey('roster$refresh'),
      future: s.roster(),
      builder: (context, snap) {
        if (!snap.hasData) return const Center(child: CircularProgressIndicator());
        final list = snap.data!;
        return ListView(padding: const EdgeInsets.all(Tokens.pad), children: [
          FilledButton(key: const ValueKey('r_add'), onPressed: () => _edit(), child: const Text('+ 작업자·장비 등록')),
          const SizedBox(height: 8),
          Text('일지에 처음 적은 사람·장비도 저장할 때 여기에 자동으로 들어옵니다. 누르면 출역표(날짜별 공수)와 월·연간 합계가 나옵니다.',
              style: Theme.of(context).textTheme.bodySmall),
          for (final k in kinds)
            if (list.any((r) => r.kind == k)) ...[
              const SizedBox(height: Tokens.gap),
              Section(title: '$k ${list.where((r) => r.kind == k).length}', children: [
                for (final r in list.where((r) => r.kind == k))
                  InkWell(
                    onTap: () async {
                      await Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => AttendancePage(store: s, entry: r, tokens: t, onEdit: () => _edit(r))));
                      setState(() => refresh++);
                    },
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      child: Row(children: [
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(r.payeeName, style: const TextStyle(fontWeight: FontWeight.w700)),
                            Text('${r.item}${r.spec.isEmpty ? '' : ' ${r.spec}'} · ${wonText(r.price)}원/${r.unit}'
                                '${r.row['phone'] != null ? ' · ${r.row['phone']}' : ''}',
                                style: Theme.of(context).textTheme.bodySmall),
                          ]),
                        ),
                        Icon(Icons.chevron_right, color: t.sub),
                      ]),
                    ),
                  ),
              ]),
            ],
          if (list.isEmpty) ...[
            const SizedBox(height: Tokens.group),
            Text('등록된 작업자·장비가 없습니다.', style: Theme.of(context).textTheme.bodySmall),
          ],
        ]);
      },
    );
  }
}

class RosterEditor extends StatefulWidget {
  const RosterEditor({super.key, this.entry});
  final RosterEntry? entry;
  static Map<String, String>? result;
  @override
  State<RosterEditor> createState() => _RosterEditorState();
}

class _RosterEditorState extends State<RosterEditor> {
  late String kind = widget.entry?.kind ?? '인력';
  late final c = {
    'payee': TextEditingController(text: widget.entry?.payeeName ?? ''),
    'item': TextEditingController(text: widget.entry?.item ?? ''),
    'spec': TextEditingController(text: widget.entry?.spec ?? ''),
    'unit': TextEditingController(text: widget.entry?.unit ?? defaultUnit['인력']),
    'price': TextEditingController(text: widget.entry == null ? '' : '${widget.entry!.price}'),
    'phone': TextEditingController(text: (widget.entry?.row['phone'] ?? '') as String),
    'memo': TextEditingController(text: (widget.entry?.row['memo'] ?? '') as String),
  };

  @override
  Widget build(BuildContext context) {
    final labels = {
      'payee': kind == '인력' ? '이름 (또는 팀)' : '업체',
      'item': kind == '인력' ? '직종 (보통인부, 형틀목공 …)' : kind == '장비' ? '기종 (6W, 덤프 25톤 …)' : '항목',
      'spec': '규격 (선택)', 'unit': '단위', 'price': '단가 (원)', 'phone': '연락처 (선택)', 'memo': '메모 (계좌·차량번호 등)',
    };
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(Tokens.pad),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(widget.entry == null ? '작업자·장비 등록' : '명부 고치기', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: Tokens.gap),
          SegmentedButton<String>(
            showSelectedIcon: false,
            segments: [for (final k in kinds) ButtonSegment(value: k, label: Text(k))],
            selected: {kind},
            onSelectionChanged: widget.entry != null
                ? null
                : (v) => setState(() {
                      kind = v.first;
                      c['unit']!.text = defaultUnit[kind]!;
                    }),
          ),
          for (final k in labels.keys) ...[
            const SizedBox(height: Tokens.gap),
            TextField(
              key: ValueKey('re_$k'),
              controller: c[k],
              keyboardType: k == 'price' ? TextInputType.number : k == 'phone' ? TextInputType.phone : null,
              decoration: InputDecoration(labelText: labels[k]),
            ),
          ],
          const SizedBox(height: Tokens.gap),
          FilledButton(
            key: const ValueKey('re_save'),
            onPressed: () {
              RosterEditor.result = {'kind': kind, for (final e in c.entries) e.key: e.value.text};
              Navigator.pop(context, true);
            },
            child: const Text('저장'),
          ),
        ]),
      ),
    );
  }
}

/// 출역표: 한 사람(장비)의 한 달 달력 + 날짜별 현장·공수 + 월 합계 + 연간(1~12월).
class AttendancePage extends StatefulWidget {
  const AttendancePage({super.key, required this.store, required this.entry, required this.tokens, required this.onEdit});
  final Store store;
  final RosterEntry entry;
  final Tokens tokens;
  final Future<void> Function() onEdit;
  @override
  State<AttendancePage> createState() => _AttendancePageState();
}

class _AttendancePageState extends State<AttendancePage> {
  String month = workDateOf(DateTime.now()).substring(0, 7);
  Store get s => widget.store;
  RosterEntry get r => widget.entry;

  Future<Map<String, dynamic>> _load() async {
    final payeeId = r.row['payee_id'] as String;
    final days = await s.personMonth(payeeId, month, item: r.item);
    final year = (await s.yearByPayee(month.substring(0, 4)))
        .where((y) => y.key.startsWith('$payeeId|${r.kind}|${r.item}|'))
        .toList();
    return {'days': days, 'year': year};
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    return Scaffold(
      appBar: AppBar(title: Text('${r.payeeName} 출역표'), actions: [
        TextButton(onPressed: widget.onEdit, child: Text('고치기', style: TextStyle(color: t.text))),
      ]),
      body: FutureBuilder<Map<String, dynamic>>(
        key: ValueKey(month),
        future: _load(),
        builder: (context, snap) {
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final days = snap.data!['days'] as Map<String, DayWork>;
          final year = snap.data!['year'] as List<YearRow>;
          final y = int.parse(month.substring(0, 4)), m = int.parse(month.substring(5));
          final first = DateTime(y, m, 1);
          final last = DateTime(y, m + 1, 0).day;
          final lead = first.weekday % 7; // 일요일 시작
          final qty = days.values.fold<num>(0, (a, d) => a + d.qty);
          final amount = days.values.fold<int>(0, (a, d) => a + d.amount);
          final sorted = days.values.toList()..sort((a, b) => a.date.compareTo(b.date));
          return ListView(padding: const EdgeInsets.all(Tokens.pad), children: [
            Text('${r.kind} · ${r.item}${r.spec.isEmpty ? '' : ' ${r.spec}'} · ${wonText(r.price)}원/${r.unit}',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: Tokens.gap),
            Row2(children: [
              SizedBox(width: 56, child: OutlinedButton(onPressed: () => setState(() => month = monthShift(month, -1)), child: const Text('◀'))),
              Expanded(child: Center(child: Text(month, style: Theme.of(context).textTheme.titleMedium))),
              SizedBox(width: 56, child: OutlinedButton(onPressed: () => setState(() => month = monthShift(month, 1)), child: const Text('▶'))),
            ]),
            const SizedBox(height: Tokens.gap),
            Section(title: '이달 ${days.length}일 · ${fmtQty(qty)}${r.unit == '인' ? '공수' : r.unit} · ${wonText(amount)}원', children: [
              // 달력
              Row(children: [
                for (final w in const ['일', '월', '화', '수', '목', '금', '토'])
                  Expanded(child: Center(child: Text(w, style: Theme.of(context).textTheme.bodySmall))),
              ]),
              const SizedBox(height: 4),
              for (var row = 0; row * 7 < lead + last; row++)
                Row(children: [
                  for (var col = 0; col < 7; col++)
                    Expanded(
                      child: Builder(builder: (context) {
                        final d = row * 7 + col - lead + 1;
                        if (d < 1 || d > last) return const SizedBox(height: 52);
                        final key = '$month-${d.toString().padLeft(2, '0')}';
                        final w = days[key];
                        final multi = (w?.parts.map((p) => p.site).toSet().length ?? 0) > 1;
                        return Container(
                          height: 52,
                          margin: const EdgeInsets.all(2),
                          decoration: BoxDecoration(
                            color: w == null ? null : t.blue.withValues(alpha: 0.22),
                            border: Border.all(color: w == null ? t.line : t.blue),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                            Text('$d', style: TextStyle(fontSize: 12, color: t.sub)),
                            if (w != null)
                              FittedBox(
                                child: Text('${fmtQty(w.qty)}${multi ? '*' : ''}',
                                    style: TextStyle(fontWeight: FontWeight.w700, color: t.text)),
                              ),
                          ]),
                        );
                      }),
                    ),
                ]),
              const SizedBox(height: 4),
              Text('숫자 = 그날 ${r.unit == '인' ? '공수' : r.unit}, * = 두 현장 이상', style: Theme.of(context).textTheme.bodySmall),
            ]),
            const SizedBox(height: Tokens.gap),
            Section(title: '날짜별', children: [
              if (sorted.isEmpty) Text('이 달에는 출역이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
              for (final d in sorted)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    SizedBox(width: 48, child: Text(d.date.substring(5))),
                    Expanded(child: Text(d.parts.map((p) => '${p.site} ${fmtQty(p.qty)}${p.unit}').join('\n'))),
                    Text(wonText(d.amount)),
                  ]),
                ),
              if (sorted.isNotEmpty) ...[
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () async {
                    final text = await s.personText(r.row['payee_id'] as String, r.payeeName, month);
                    await Clipboard.setData(ClipboardData(text: text));
                    if (context.mounted) showMessage(context, '출역 확인서를 복사했습니다. 카톡·문자에 붙여 넣으세요.');
                  },
                  child: const Text('출역 확인서 복사 (본인 확인용)'),
                ),
              ],
            ]),
            const SizedBox(height: Tokens.gap),
            Section(title: '${month.substring(0, 4)}년 월별', children: [
              if (year.isEmpty) Text('올해 출역이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
              for (final yr in year) ...[
                for (var mm = 1; mm <= 12; mm++)
                  if (yr.qty[mm] != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(children: [
                        SizedBox(width: 48, child: Text('$mm월')),
                        Expanded(child: Text('${fmtQty(yr.qty[mm]!)}${yr.unit == '인' ? '공수' : yr.unit}')),
                        Text(wonText(yr.amount[mm]!)),
                      ]),
                    ),
                const Divider(),
                Row(children: [
                  const SizedBox(width: 48, child: Text('합계', style: TextStyle(fontWeight: FontWeight.w700))),
                  Expanded(child: Text('${fmtQty(yr.qtyTotal)}${yr.unit == '인' ? '공수' : yr.unit}', style: const TextStyle(fontWeight: FontWeight.w700))),
                  Text(wonText(yr.amountTotal), style: const TextStyle(fontWeight: FontWeight.w700)),
                ]),
              ],
            ]),
            const SizedBox(height: Tokens.gap),
            OutlinedButton(
              onPressed: () async {
                await s.retireRoster(r.id);
                if (context.mounted) Navigator.pop(context);
              },
              child: const Text('명부에서 빼기 (지난 기록은 그대로)'),
            ),
          ]);
        },
      ),
    );
  }
}
