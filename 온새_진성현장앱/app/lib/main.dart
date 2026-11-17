import 'dart:async';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import 'device.dart';
import 'ledger.dart';
import 'payout.dart';
import 'roster.dart';
import 'roster_page.dart';
import 'row_db.dart';
import 'sqlite_db.dart';
import 'stations.dart';
import 'store.dart';
import 'sync.dart';
import 'tokens.dart';
import 'works.dart';

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
      // 날짜 고르기·확인 단추까지 한국어로
      locale: const Locale('ko', 'KR'),
      supportedLocales: const [Locale('ko', 'KR')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
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

class _ShellState extends State<Shell> with WidgetsBindingObserver {
  int tab = 0;
  String today = workDateOf(DateTime.now()); // 앱을 켜 둔 채 날이 바뀌면 일지 날짜도 오늘로
  String? siteId;
  List<Rec> sites = [];
  int version = 0; // 자료가 바뀌면 올려서 화면을 다시 그린다
  String? logDate; // 「진행 중」에서 고른 일지 날짜
  Map<String, List<String>> missing = {}; // 진행 중 현장 → 밀린 일지 날짜

  static const titles = ['오늘 현장 보기', '오늘 일지 쓰기', '결제 요청·한 달 집계', '작업자·장비 명부', '집 PC와 맞추기'];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    reload();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// 다음 날 아침 앱을 다시 열면(백그라운드에서 돌아오면) 일지·결제 화면이 오늘 기준으로 바뀐다.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && workDateOf(DateTime.now()) != today) {
      today = workDateOf(DateTime.now());
      logDate = null;
      reload();
    }
  }

  Future<void> reload() async {
    final list = await widget.store.db.all('site');
    list.sort((a, b) => (a['created_at'] as String).compareTo(b['created_at'] as String));
    final miss = <String, List<String>>{
      for (final x in list)
        if (x['status'] == '진행')
          x['id'] as String: await widget.store.missingLogDays(x['id'] as String, workDateOf(DateTime.now())),
    };
    if (!mounted) return;
    setState(() {
      sites = list;
      missing = miss;
      if (siteId == null || !list.any((s) => s['id'] == siteId)) {
        siteId = list.isEmpty ? null : list.first['id'] as String;
      }
      version++;
    });
  }

  /// 「진행 중」 공사 누르기 → 날짜 고르기(오늘 / 밀린 날) → 그 현장·그 날짜 일지로 바로.
  Future<void> _continueLog(Rec site) async {
    final today = workDateOf(DateTime.now());
    final miss = missing[site['id']] ?? const <String>[];
    const yo = ['월', '화', '수', '목', '금', '토', '일'];
    String label(String d) =>
        '${int.parse(d.substring(5, 7))}/${int.parse(d.substring(8))} (${yo[DateTime.parse(d).weekday - 1]})';
    final picked = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(Tokens.pad),
          children: [
            Text('${site['name']}', style: Theme.of(ctx).textTheme.titleMedium),
            const SizedBox(height: 8),
            ListTile(
              key: const ValueKey('cl_view'),
              leading: const Icon(Icons.home_outlined),
              title: const Text('현장 보기 (공사 건·공정·발주 체크)'),
              onTap: () => Navigator.pop(ctx, 'view'),
            ),
            ListTile(
              key: const ValueKey('cl_today'),
              leading: const Icon(Icons.today),
              title: Text('오늘 ${label(today)}'),
              onTap: () => Navigator.pop(ctx, today),
            ),
            for (final d in miss.reversed)
              ListTile(
                key: ValueKey('cl_$d'),
                leading: Icon(Icons.history, color: widget.tokens.warn),
                title: Text('밀린 날 ${label(d)}'),
                subtitle: const Text('일지 없음'),
                onTap: () => Navigator.pop(ctx, d),
              ),
            ListTile(
              leading: const Icon(Icons.calendar_month),
              title: const Text('다른 날 고르기'),
              onTap: () async {
                final d = await showDatePicker(
                  context: ctx,
                  initialDate: DateTime.now(),
                  firstDate: DateTime(2020),
                  lastDate: DateTime(2100),
                  helpText: '${site['name']} 일지 날짜',
                );
                if (ctx.mounted) Navigator.pop(ctx, d == null ? null : workDateOf(d));
              },
            ),
          ],
        ),
      ),
    );
    if (picked == null) return;
    openSite(site['id'] as String, picked == 'view' ? null : picked);
  }

  /// 현장 고르기 + 화면 이동: date 가 없으면 홈(현장 보기), 있으면 그 날짜 일지.
  void openSite(String id, String? date) => setState(() {
    siteId = id;
    logDate = date;
    tab = date == null ? 0 : 1;
    version++;
  });

  /// 완공·취소된 지난 공사 고르기 (기록 보기).
  Future<void> _pastSites() async {
    final past = sites.where((x) => const ['완공', '취소'].contains(x['status'])).toList().reversed.toList();
    final id = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(Tokens.pad),
          children: [
            Text('지난 공사', style: Theme.of(ctx).textTheme.titleMedium),
            for (final x in past)
              ListTile(
                title: Text(x['name'] as String),
                subtitle: Text('${x['status']}${x['end_date'] != null ? ' · ${x['end_date']}' : ''}'),
                onTap: () => Navigator.pop(ctx, x['id'] as String),
              ),
          ],
        ),
      ),
    );
    if (id != null) openSite(id, null);
  }

  /// 접수: 구분 → 이름 → 위치 → 연락처(폰에서 고르기) → 지시사항 → 구분별 체크리스트. 그날 일지에 [접수] 줄이 남는다.
  Future<void> receiveJob() async {
    final name = TextEditingController();
    final inst = TextEditingController();
    final cname = TextEditingController();
    final cphone = TextEditingController();
    final addr = TextEditingController();
    var type = jobTypes.first;
    Here? here;
    var hereMsg = '';
    final checked = <String>{};
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) {
          final sub = Theme.of(ctx).textTheme.bodySmall;
          return Padding(
            padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(Tokens.pad),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('공사 건 접수', style: Theme.of(ctx).textTheme.titleMedium),
                  const SizedBox(height: Tokens.gap),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final j in jobTypes)
                        ChoiceChip(
                          key: ValueKey('jt_$j'),
                          label: Text(j),
                          selected: type == j,
                          onSelected: (_) => setD(() {
                            type = j;
                            checked.clear();
                          }),
                        ),
                    ],
                  ),
                  const SizedBox(height: Tokens.gap),
                  TextField(
                    key: const ValueKey('rc_name'),
                    controller: name,
                    decoration: const InputDecoration(labelText: '공사 이름'),
                  ),
                  const SizedBox(height: Tokens.gap),
                  TextField(
                    key: const ValueKey('rc_addr'),
                    controller: addr,
                    decoration: const InputDecoration(labelText: '공사 위치 (주소·마을·도로명 등)'),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Expanded(child: Text(hereMsg.isEmpty ? '현장에 있으면 「지금 위치」로 좌표를 남깁니다.' : hereMsg, style: sub)),
                      TextButton.icon(
                        key: const ValueKey('rc_here'),
                        icon: const Icon(Icons.my_location, size: 18),
                        label: const Text('지금 위치'),
                        onPressed: () async {
                          setD(() => hereMsg = '위치 찾는 중…');
                          try {
                            here = await DeviceKit.here();
                            setD(
                              () => hereMsg = '좌표 저장: ${here!.lat.toStringAsFixed(5)}, ${here!.lon.toStringAsFixed(5)}',
                            );
                          } on StoreError catch (e) {
                            setD(() => hereMsg = e.message);
                          } catch (_) {
                            setD(() => hereMsg = '위치를 못 잡았습니다. 주소만 적어 주세요.');
                          }
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: Tokens.gap),
                  OutlinedButton.icon(
                    key: const ValueKey('rc_contact'),
                    icon: const Icon(Icons.contacts_outlined, size: 18),
                    label: const Text('폰 연락처에서 고르기'),
                    onPressed: () async {
                      try {
                        final c = await DeviceKit.pickContact();
                        if (c != null) {
                          setD(() {
                            cname.text = c.name;
                            cphone.text = c.phone;
                          });
                        }
                      } catch (_) {
                        if (ctx.mounted) showMessage(ctx, '연락처를 열지 못했습니다. 직접 적어 주세요.');
                      }
                    },
                  ),
                  const SizedBox(height: 8),
                  Row2(
                    children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('rc_cname'),
                          controller: cname,
                          decoration: const InputDecoration(labelText: '연락처 이름'),
                        ),
                      ),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('rc_cphone'),
                          controller: cphone,
                          keyboardType: TextInputType.phone,
                          decoration: const InputDecoration(labelText: '전화번호'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: Tokens.gap),
                  TextField(
                    key: const ValueKey('rc_inst'),
                    controller: inst,
                    maxLines: 3,
                    decoration: const InputDecoration(labelText: '지시사항'),
                  ),
                  const SizedBox(height: Tokens.gap),
                  Text('$type 체크리스트', style: const TextStyle(fontWeight: FontWeight.w700)),
                  Text('이미 한 것은 체크. 안 한 것은 할 일로 남아 홈에서 알려 줍니다.', style: sub),
                  for (final c in firstChecks[type]!)
                    CheckboxListTile(
                      key: ValueKey('ck_$c'),
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      value: checked.contains(c),
                      title: Text(c),
                      onChanged: (v) => setD(() => v == true ? checked.add(c) : checked.remove(c)),
                    ),
                  const SizedBox(height: Tokens.gap),
                  FilledButton(
                    key: const ValueKey('rc_ok'),
                    onPressed: () => Navigator.pop(ctx, true),
                    child: const Text('접수'),
                  ),
                  TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
                ],
              ),
            ),
          );
        },
      ),
    );
    if (ok != true) return;
    try {
      final id = await widget.store.receive(
        name.text,
        type,
        workDateOf(DateTime.now()),
        instructions: inst.text,
        contactName: cname.text,
        contactPhone: cphone.text,
        address: addr.text,
        lat: here?.lat,
        lon: here?.lon,
        checked: checked,
      );
      siteId = id;
      await reload();
      if (mounted) {
        final left = firstChecks[type]!.length - checked.length;
        showMessage(context, '접수했습니다. 오늘 일지에 남겼습니다.${left > 0 ? ' 확인할 것 $left개는 할 일로.' : ''}');
      }
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    final pages = [
      HomePage(
        key: ValueKey('h$version$siteId'),
        store: widget.store,
        siteId: siteId,
        tokens: t,
        onChanged: reload,
        onOpenLog: (d) => openSite(siteId!, d),
        onOpenSync: () => setState(() => tab = 4),
      ),
      LogPage(
        key: ValueKey('l$siteId$today$logDate'),
        store: widget.store,
        siteId: siteId,
        tokens: t,
        onChanged: reload,
        initialDate: logDate,
      ),
      PayPage(key: ValueKey('p$version$today'), store: widget.store, tokens: t, onChanged: reload),
      RosterPage(
        key: ValueKey('r$version$siteId'),
        store: widget.store,
        tokens: t,
        onChanged: reload,
        siteId: siteId,
        siteName: sites.where((x) => x['id'] == siteId).map((x) => x['name'] as String).firstOrNull,
      ),
      SyncPage(key: ValueKey('s$version'), store: widget.store, tokens: t, onChanged: reload),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(titles[tab]),
        actions: [
          TextButton(
            onPressed: widget.onToggleOutdoor,
            child: Text(
              '야외 모드',
              style: TextStyle(color: t.text, fontSize: Tokens.fNote),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // 현장 줄 하나: 진행·접수·보류 공사 버튼 + 접수 + 지난 공사. 누르면 현장 보기 / 오늘·밀린 날 일지.
            // 결제 요청·동기화는 모든 현장을 함께 보므로 현장 줄을 숨긴다
            if (tab != 2 && tab != 4)
              Container(
                key: const ValueKey('sitebar'),
                width: double.infinity,
                padding: const EdgeInsets.fromLTRB(Tokens.pad, 8, Tokens.pad, Tokens.gap),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    for (final x in sites.where((x) => const ['진행', '접수', '보류'].contains(x['status'] ?? '진행')))
                      ActionChip(
                        key: ValueKey('og_${x['name']}'),
                        visualDensity: VisualDensity.compact,
                        side: BorderSide(color: x['id'] == siteId ? t.blue : t.line, width: x['id'] == siteId ? 2 : 1),
                        backgroundColor: x['id'] == siteId ? t.blue.withValues(alpha: 0.18) : null,
                        avatar: (missing[x['id']] ?? const []).isNotEmpty
                            ? Icon(Icons.edit_note, size: 18, color: t.warn)
                            : null,
                        label: Text(
                          '${x['name']}'
                          '${(x['status'] ?? '진행') == '진행' ? '' : ' (${x['status']})'}'
                          '${(missing[x['id']] ?? const []).isEmpty ? '' : ' · 밀린 ${missing[x['id']]!.length}일'}',
                        ),
                        onPressed: () => _continueLog(x),
                      ),
                    ActionChip(
                      key: const ValueKey('og_new'),
                      visualDensity: VisualDensity.compact,
                      avatar: const Icon(Icons.add, size: 18),
                      label: const Text('접수'),
                      onPressed: receiveJob,
                    ),
                    if (sites.any((x) => const ['완공', '취소'].contains(x['status'])))
                      ActionChip(
                        key: const ValueKey('og_past'),
                        visualDensity: VisualDensity.compact,
                        label: Text('지난 공사 ${sites.where((x) => const ['완공', '취소'].contains(x['status'])).length}'),
                        onPressed: _pastSites,
                      ),
                  ],
                ),
              ),
            Expanded(child: pages[tab]),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: '홈'),
          NavigationDestination(icon: Icon(Icons.edit_note_outlined), label: '일지'),
          NavigationDestination(icon: Icon(Icons.payments_outlined), label: '결제 요청'),
          NavigationDestination(icon: Icon(Icons.badge_outlined), label: '명부'),
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
  Widget build(BuildContext context) => Row(
    children: [
      for (var i = 0; i < children.length; i++) ...[if (i > 0) const SizedBox(width: Tokens.gap), children[i]],
    ],
  );
}

/// 숫자 칸을 누르면 안의 값이 통째로 선택된다 → 바로 치면 바뀐다 (1 뒤에 0.5가 붙어 10.5가 되는 일 방지).
void selectAll(TextEditingController c) => c.selection = TextSelection(baseOffset: 0, extentOffset: c.text.length);

class Section extends StatelessWidget {
  const Section({super.key, required this.title, required this.children});
  final String title;
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(Tokens.pad),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          ...children,
        ],
      ),
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
      border: Border.all(color: color),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      text,
      style: TextStyle(color: color, fontSize: Tokens.fNote, fontWeight: FontWeight.w700),
    ),
  );
}

Widget bigNumber(BuildContext context, String label, String value, String unit, Tokens t) => Column(
  crossAxisAlignment: CrossAxisAlignment.start,
  children: [
    Text(label, style: Theme.of(context).textTheme.bodySmall),
    // 금액이 길어도 줄바꿈되지 않고 칸 안에서 작아진다(숫자가 쪼개지면 잘못 읽힘)
    FittedBox(
      fit: BoxFit.scaleDown,
      alignment: Alignment.centerLeft,
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: value,
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w700,
                color: t.text,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
            TextSpan(
              text: ' $unit',
              style: TextStyle(fontSize: Tokens.fNote, color: t.sub),
            ),
          ],
        ),
        maxLines: 1,
        softWrap: false,
      ),
    ),
  ],
);

/// 알림은 2.5초만, 이전 알림은 바로 치운다 (저장 단추를 오래 가리지 않게).
void showMessage(BuildContext context, String text) {
  final m = ScaffoldMessenger.of(context);
  m.hideCurrentSnackBar();
  m.showSnackBar(SnackBar(content: Text(text), duration: const Duration(milliseconds: 2500)));
}

Future<String?> askText(BuildContext context, String title, String label, {String initial = ''}) {
  final c = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: c,
        autofocus: true,
        decoration: InputDecoration(labelText: label),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('취소')),
        FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('확인')),
      ],
    ),
  );
}

// ───────────────────────── 홈 ─────────────────────────
class HomePage extends StatelessWidget {
  const HomePage({
    super.key,
    required this.store,
    required this.siteId,
    required this.tokens,
    required this.onChanged,
    required this.onOpenLog,
    required this.onOpenSync,
  });
  final Store store;
  final void Function(String date) onOpenLog; // 그 날짜 일지로
  final VoidCallback onOpenSync;
  final String? siteId;
  final Tokens tokens;
  final Future<void> Function() onChanged;

  /// 공사 건 상태 바꾸기: 진행 / 보류 / 취소 / 완공.
  Future<void> _act(BuildContext context, String action) async {
    final today = workDateOf(DateTime.now());
    try {
      if (action == '진행') {
        final d = await askText(context, '진행', '시작 예정일 (비우면 일정 없이 진행)', initial: today);
        if (d == null) return;
        await store.proceed(siteId!, plannedStart: d.trim());
        if (context.mounted) showMessage(context, '진행으로 바꿨습니다. 집 PC와 맞추면 발주·체크 일정이 만들어집니다.');
      } else if (action == '완공') {
        final d = await askText(context, '완공', '완공일', initial: today);
        if (d == null) return;
        await store.complete(siteId!, d.trim());
      } else {
        final r = await askText(context, action, '$action 사유');
        if (r == null) return;
        if (action == '보류') {
          await store.hold(siteId!, r);
        } else {
          final result = await store.cancel(siteId!, r);
          if (context.mounted) {
            showMessage(context, result == '파기' ? '투입이 없어 파기했습니다.' : "투입 기록이 있어 '취소'로 보관했습니다.");
          }
        }
      }
      await onChanged();
    } on StoreError catch (e) {
      if (context.mounted) showMessage(context, e.message);
    }
  }

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
      'site': await store.mustGet('site', id),
      'tasks': await store.dueTasks(today, siteId: id),
      'today': today,
      'hasToday': logs.any((l) => l['work_date'] == today),
      'cost': await store.monthCost(id, today.substring(0, 7)),
      'locked': await store.isLocked(today.substring(0, 7)),
      'conflicts': (await store.db.openConflicts()).length,
      'pending': (await store.db.changesSince(await store.db.cursor('집PC', 'out'), onlyDevice: store.device)).length,
      'recent': recent,
      'works': await store.workProgress(id),
    };
  }

  /// 공종 추가: 이름·연장. U형 개거면 내폭·높이 → 집 PC가 물량·발주 일정을 계산.
  Future<void> _addWork(BuildContext context) async {
    final name = TextEditingController(text: 'U형 개거');
    final len = TextEditingController();
    final w = TextEditingController(text: '1.0');
    final h = TextEditingController(text: '1.0');
    var channel = true;
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => Padding(
          padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Tokens.pad),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('공종 추가', style: Theme.of(ctx).textTheme.titleMedium),
                const SizedBox(height: Tokens.gap),
                Wrap(
                  spacing: 8,
                  children: [
                    ChoiceChip(
                      label: const Text('U형 개거 (물량·발주 자동)'),
                      selected: channel,
                      onSelected: (_) => setD(() {
                        channel = true;
                        if (name.text.isEmpty) name.text = 'U형 개거';
                      }),
                    ),
                    ChoiceChip(
                      label: const Text('기타'),
                      selected: !channel,
                      onSelected: (_) => setD(() {
                        channel = false;
                        if (name.text == 'U형 개거') name.text = '';
                      }),
                    ),
                  ],
                ),
                const SizedBox(height: Tokens.gap),
                TextField(
                  key: const ValueKey('wt_name'),
                  controller: name,
                  decoration: const InputDecoration(labelText: '공종 이름'),
                ),
                const SizedBox(height: Tokens.gap),
                TextField(
                  key: const ValueKey('wt_len'),
                  controller: len,
                  onTap: () => selectAll(len),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: '설계 연장 (m)'),
                ),
                if (channel) ...[
                  const SizedBox(height: Tokens.gap),
                  Row2(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: w,
                          onTap: () => selectAll(w),
                          decoration: const InputDecoration(labelText: '내폭 (m)'),
                        ),
                      ),
                      Expanded(
                        child: TextField(
                          controller: h,
                          onTap: () => selectAll(h),
                          decoration: const InputDecoration(labelText: '높이 (m)'),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: Tokens.gap),
                FilledButton(
                  key: const ValueKey('wt_save'),
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('추가'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    if (ok != true) return;
    try {
      await store.addWorkType(
        siteId!,
        name.text,
        len.text,
        channel: channel,
        innerW: w.text.trim(),
        wallH: h.text.trim(),
      );
      await onChanged();
      if (context.mounted) {
        showMessage(context, channel ? '공종을 추가했습니다. 집 PC와 맞추면 물량·발주 일정이 내려옵니다.' : '공종을 추가했습니다.');
      }
    } on StoreError catch (e) {
      if (context.mounted) showMessage(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = tokens;
    if (siteId == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(Tokens.group),
          child: Text('현장이 없습니다. 위쪽 「+ 접수」로 공사 건을 만들거나, 동기화 탭에서 집 PC의 현장을 받아 오세요.'),
        ),
      );
    }
    return FutureBuilder<Map<String, dynamic>>(
      future: _load(),
      builder: (context, snap) {
        if (!snap.hasData) return const Center(child: CircularProgressIndicator());
        final d = snap.data!;
        final site = d['site'] as Rec;
        final status = (site['status'] ?? '진행') as String;
        final tasks = d['tasks'] as List<Rec>;
        final actions = switch (status) {
          '접수' => ['진행', '보류', '취소'],
          '보류' => ['진행', '취소'],
          '진행' => ['완공', '보류', '취소'],
          _ => <String>[],
        };
        final todayRow = (d['recent'] as List).cast<Map>().where((r) => r['work_date'] == d['today']).firstOrNull;
        return ListView(
          padding: const EdgeInsets.all(Tokens.pad),
          children: [
            Section(
              title: '공사 건',
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Badge2(status, status == '진행' ? t.ok : t.warn),
                    if (site['job_type'] != null) Badge2(site['job_type'] as String, t.blue),
                    if (site['planned_start'] != null) Text('시작 예정 ${site['planned_start']}'),
                  ],
                ),
                if ((site['address'] ?? '') != '' || site['gps_lat'] != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      '위치: ${site['address'] ?? ''}'
                      '${site['gps_lat'] != null ? ' (${(site['gps_lat'] as num).toStringAsFixed(5)}, ${(site['gps_lon'] as num).toStringAsFixed(5)})' : ''}',
                    ),
                  ),
                if ((site['instructions'] ?? '') != '')
                  Padding(padding: const EdgeInsets.only(top: 8), child: Text(site['instructions'] as String)),
                if ((site['status_reason'] ?? '') != '')
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text('사유: ${site['status_reason']}', style: Theme.of(context).textTheme.bodySmall),
                  ),
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    '이달 투입 ${wonText(d['cost'] as int)}원 · ${(d['locked'] as bool) ? '마감된 달' : '마감 전'}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
                if (actions.isNotEmpty) ...[
                  const SizedBox(height: Tokens.gap),
                  Row2(
                    children: [
                      for (final a in actions)
                        Expanded(
                          child: OutlinedButton(onPressed: () => _act(context, a), child: Text(a)),
                        ),
                    ],
                  ),
                ],
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '공종·공정률',
              children: [
                for (final w in d['works'] as List<WorkProgress>) ...[
                  Row(
                    children: [
                      Expanded(
                        child: Text(w.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                      ),
                      Text(
                        '${(w.rate * 100).toStringAsFixed(0)}%',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  LinearProgressIndicator(value: w.rate, minHeight: 8, borderRadius: BorderRadius.circular(4)),
                  Text('${fmtQty(w.done)} / ${fmtQty(w.design)}m', style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 8),
                ],
                if ((d['works'] as List).isEmpty)
                  Text('공종을 넣으면 일지에서 측점으로 시공 연장을 남기고 공정률이 나옵니다.', style: Theme.of(context).textTheme.bodySmall),
                if (status != '완공' && status != '취소')
                  OutlinedButton(
                    key: const ValueKey('wt_add'),
                    onPressed: () => _addWork(context),
                    child: const Text('+ 공종 추가'),
                  ),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '발주·체크 (기한순)',
              children: [
                if (tasks.isEmpty) Text('이틀 안에 챙길 일이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
                for (final k in tasks.take(8))
                  InkWell(
                    onTap: () async {
                      try {
                        await store.checkTask(k['id'] as String, d['today'] as String);
                        await onChanged();
                      } catch (e) {
                        if (context.mounted) showMessage(context, '체크하지 못했습니다: $e');
                      }
                    },
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(Icons.check_box_outline_blank, color: t.sub),
                          const SizedBox(width: 8),
                          Badge2(k['when'] as String, (k['late'] as bool) ? t.bad : t.warn),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text('${k['title']}${k['qty'] != null ? ' ${k['qty']}${k['unit'] ?? ''}' : ''}'),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '날짜별 일지 (누르면 그날로)',
              children: [
                InkWell(
                  key: const ValueKey('home_today'),
                  onTap: () => onOpenLog(d['today'] as String),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                      children: [
                        Badge2('오늘', todayRow == null ? t.warn : t.ok),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            todayRow == null
                                ? (status == '진행' ? '아직 안 씀 — 눌러서 쓰기' : '일지 없음')
                                : (todayRow['no_work'] as bool)
                                ? '작업 없음'
                                : '${todayRow['count']}줄 · ${wonText(todayRow['amount'] as int)}원',
                          ),
                        ),
                        Icon(Icons.chevron_right, color: t.sub),
                      ],
                    ),
                  ),
                ),
                for (final r in (d['recent'] as List).cast<Map>().where((r) => r['work_date'] != d['today']))
                  InkWell(
                    onTap: () => onOpenLog(r['work_date'] as String),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Row(
                        children: [
                          Expanded(child: Text(r['work_date'] as String)),
                          Text(
                            (r['no_work'] as bool) ? '작업 없음' : '${r['count']}줄',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(width: Tokens.gap),
                          Text(
                            '${wonText(r['amount'] as int)}원',
                            style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()]),
                          ),
                        ],
                      ),
                    ),
                  ),
                if ((d['pending'] as int) > 0 || (d['conflicts'] as int) > 0)
                  TextButton(
                    onPressed: onOpenSync,
                    child: Text(
                      [
                        if ((d['pending'] as int) > 0) '집 PC로 보낼 기록 ${d['pending']}건',
                        if ((d['conflicts'] as int) > 0) '충돌 검토 ${d['conflicts']}건',
                      ].join(' · '),
                    ),
                  ),
              ],
            ),
          ],
        );
      },
    );
  }
}

// ───────────────────────── 일지 ─────────────────────────
/// 업무일지: 모든 공사의 시작. 기준 정보 없이도 바로 입력되고, 처음 쓴 업체·항목은 저장할 때 등록된다.
class LogPage extends StatefulWidget {
  const LogPage({
    super.key,
    required this.store,
    required this.siteId,
    required this.tokens,
    required this.onChanged,
    this.initialDate,
  });
  final Store store;
  final String? initialDate; // 「진행 중」에서 고른 날 (밀린 일지)
  final String? siteId;
  final Tokens tokens;
  final Future<void> Function() onChanged;
  @override
  State<LogPage> createState() => _LogPageState();
}

class _LogPageState extends State<LogPage> {
  late DateTime date = widget.initialDate == null ? DateTime.now() : DateTime.parse(widget.initialDate!);
  String? progWt;
  final progFrom = TextEditingController();
  final progTo = TextEditingController();
  String kind = '인력';
  final item = TextEditingController();
  final spec = TextEditingController();
  final qty = TextEditingController(text: '1');
  final unit = TextEditingController(text: defaultUnit['인력']);
  final price = TextEditingController();
  final payee = TextEditingController();
  final note = TextEditingController();
  final content = TextEditingController();
  final staFrom = TextEditingController();
  final staTo = TextEditingController();
  String? workTypeId;
  bool priceTouched = false;
  int refresh = 0;

  String get workDate => workDateOf(date);
  Store get s => widget.store;

  @override
  void initState() {
    super.initState();
    for (final c in [qty, price]) {
      c.addListener(() => setState(() {}));
    }
  }

  int? get amount {
    final q = num.tryParse(qty.text.trim());
    final p = int.tryParse(price.text.replaceAll(',', '').trim());
    return (q == null || p == null) ? null : (q * p).round();
  }

  Timer? _debounce;
  void _fillSoon() {
    setState(() {});
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), _fill);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  Future<void> _fill() async {
    // 항목·받는 곳이 정해지면 단가·단위를 미리 채운다(직접 고친 단가는 건드리지 않음)
    final sg = await s.suggest(kind, item.text, payee.text, workDate);
    if (!mounted) return;
    setState(() {
      if (!priceTouched) price.text = sg.price?.toString() ?? price.text;
      if (sg.unit != null) unit.text = sg.unit!;
      if (sg.spec != null && spec.text.isEmpty) spec.text = sg.spec!;
    });
  }

  Future<Map<String, dynamic>> _load() async {
    final items = await s.recentItems(kind);
    final payees = await s.recentPayees(kind, item: item.text.trim());
    final wts = (await s.db.all('work_type')).where((w) => w['site_id'] == widget.siteId).toList();
    final works = widget.siteId == null ? <WorkProgress>[] : await s.workProgress(widget.siteId!, workDate: workDate);
    if (progFrom.text.isEmpty && works.isNotEmpty) {
      // 시공 측점 시작 = 지난번 끝 (매일 이어서)
      num end = 0;
      for (final p in await s.db.all('progress')) {
        if (p['work_type_id'] == (progWt ?? works.first.id)) {
          end = [end, num.tryParse((p['sta_to'] ?? '0') as String) ?? 0].reduce((a, b) => a > b ? a : b);
        }
      }
      progFrom.text = formatSta(end);
    }
    final lines = widget.siteId == null ? <Rec>[] : await s.linesOf(widget.siteId!, workDate);
    final names = {for (final p in await s.db.all('payee')) p['id']: p['name']};
    Rec? log;
    for (final l in await s.db.all('work_log')) {
      if (l['site_id'] == widget.siteId && l['work_date'] == workDate) log = l;
    }
    return {'items': items, 'payees': payees, 'wts': wts, 'lines': lines, 'names': names, 'log': log, 'works': works};
  }

  Future<void> _pickDate() async {
    final d = await showDatePicker(
      context: context,
      initialDate: date,
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
      helpText: '작업일 (밀린 일지는 그날로 바꿔서 입력)',
    );
    if (d != null) setState(() => date = d);
  }

  void _setKind(String k) => setState(() {
    kind = k;
    item.clear();
    spec.clear();
    payee.clear();
    price.clear();
    priceTouched = false;
    unit.text = defaultUnit[k]!;
    qty.text = '1';
  });

  Future<String?> _reasonIfLocked() async {
    if (!await s.isLocked(workDate.substring(0, 7))) return '';
    if (!mounted) return null;
    final r = await askText(context, '월말 보고를 보낸 달입니다', '고치는 사유 (정정 보고서에 남습니다)');
    return (r == null || r.trim().isEmpty) ? null : r.trim();
  }

  Future<void> _save() async {
    try {
      final reason = await _reasonIfLocked();
      if (reason == null) return;
      String? a, b;
      if (staFrom.text.trim().isNotEmpty && staTo.text.trim().isNotEmpty) {
        var x = parseSta(staFrom.text), y = parseSta(staTo.text);
        if (y < x) (x, y) = (y, x);
        a = staText(x);
        b = staText(y);
      }
      final warn = await s.overbook(workDate, kind, item.text.trim(), payee.text.trim(), qty.text);
      if (warn != null && !await _confirm('하루 겹침 확인', warn)) return;
      await s.addLine(
        siteId: widget.siteId,
        workDate: workDate,
        kind: kind,
        item: item.text,
        spec: spec.text,
        qty: qty.text,
        unit: unit.text,
        unitPrice: price.text,
        payee: payee.text,
        note: note.text,
        workTypeId: workTypeId,
        staFrom: a,
        staTo: b,
        reason: reason.isEmpty ? null : reason,
      );
      if (workTypeId != null && a != null && b != null) {
        await s.addProgress(
          widget.siteId!,
          workDate,
          workTypeId!,
          staText(num.parse(b) - num.parse(a)),
          'm',
          staFrom: a,
          staTo: b,
        );
      }
      final saved = '${item.text.trim()} ${qty.text.trim()}${unit.text.trim()} · ${payee.text.trim()}';
      setState(() {
        // 같은 항목을 여러 사람에게 이어서 넣는 경우가 많아 항목·단가는 남기고 받는 곳·메모만 비운다
        payee.clear();
        note.clear();
        qty.text = '1';
        priceTouched = false;
        refresh++;
      });
      await widget.onChanged();
      if (mounted) showMessage(context, '저장: $saved');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  Future<bool> _confirm(String title, String text) async =>
      await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: Text(text),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('고치기')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('그대로 저장')),
          ],
        ),
      ) ??
      false;

  /// 명부에서 고르기: 체크한 사람·장비를 한 번에 넣는다(수량 기본 1, 반나절은 0.5로).
  Future<void> _pickRoster() async {
    final list = await s.roster();
    if (!mounted) return;
    if (list.isEmpty) return showMessage(context, '명부가 비어 있습니다. 명부 탭에서 등록하거나 아래에서 직접 한 줄 넣으세요.');
    final picked = <String, TextEditingController>{};
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          title: Text('$workDate 나온 사람·장비'),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView(
              shrinkWrap: true,
              children: [
                for (final k in kinds)
                  if (list.any((r) => r.kind == k)) ...[
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(k, style: Theme.of(ctx).textTheme.bodySmall),
                    ),
                    for (final r in list.where((r) => r.kind == k))
                      Row(
                        children: [
                          Checkbox(
                            key: ValueKey('pick_${r.label}'),
                            value: picked.containsKey(r.id),
                            onChanged: (v) => setD(
                              () => v == true ? picked[r.id] = TextEditingController(text: '1') : picked.remove(r.id),
                            ),
                          ),
                          Expanded(child: Text('${r.label}\n${wonText(r.price)}원/${r.unit}')),
                          if (picked.containsKey(r.id))
                            SizedBox(
                              width: 64,
                              child: TextField(
                                key: ValueKey('pickq_${r.label}'),
                                controller: picked[r.id],
                                onTap: () => selectAll(picked[r.id]!),
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                decoration: InputDecoration(labelText: r.unit),
                              ),
                            ),
                        ],
                      ),
                  ],
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('고른 것 넣기')),
          ],
        ),
      ),
    );
    if (ok != true || picked.isEmpty) return;
    try {
      final byId = {for (final r in list) r.id: r};
      final warns = <String>[];
      for (final e in picked.entries) {
        final r = byId[e.key]!;
        final w = await s.overbook(workDate, r.kind, r.item, r.payeeName, e.value.text);
        if (w != null) warns.add(w);
      }
      if (warns.isNotEmpty && !await _confirm('하루 겹침 확인', warns.join('\n\n'))) return;
      final reason = await _reasonIfLocked();
      if (reason == null) return;
      final n = await s.addFromRoster(widget.siteId!, workDate, [
        for (final e in picked.entries) (e.key, e.value.text),
      ], reason: reason.isEmpty ? null : reason);
      setState(() => refresh++);
      await widget.onChanged();
      if (mounted) showMessage(context, '$n줄을 넣었습니다.');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  /// 어제와 같이: 이전 일지의 줄을 보여 주고 고른 것만 복사한다(자재·외주·가끔 쓴 장비는 기본으로 꺼짐).
  Future<void> _copyLast() async {
    final c = await s.copyCandidates(widget.siteId!, workDate);
    if (!mounted) return;
    if (c.items.isEmpty) return showMessage(context, '복사할 이전 일지가 없습니다.');
    var items = [...c.items];
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          title: Text('${c.from} → $workDate 복사'),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView(
              shrinkWrap: true,
              children: [
                Text('자재·외주·가끔 쓴 장비는 꺼 두었습니다. 오늘 쓴 것만 켜세요.', style: Theme.of(ctx).textTheme.bodySmall),
                for (var i = 0; i < items.length; i++)
                  CheckboxListTile(
                    key: ValueKey('copy_$i'),
                    contentPadding: EdgeInsets.zero,
                    value: items[i].pick,
                    onChanged: (v) =>
                        setD(() => items[i] = (line: items[i].line, payee: items[i].payee, pick: v ?? false)),
                    title: Text(
                      '${items[i].line['item']} ${items[i].line['qty']}${items[i].line['unit']} · ${items[i].payee}',
                    ),
                    subtitle: Text('${items[i].line['kind']} · ${wonText(items[i].line['amount'] as int)}원'),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('고른 줄 복사')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    try {
      final warns = <String>[];
      for (final x in items.where((x) => x.pick)) {
        final w = await s.overbook(
          workDate,
          x.line['kind'] as String,
          x.line['item'] as String,
          x.payee,
          x.line['qty']!,
        );
        if (w != null) warns.add(w);
      }
      if (warns.isNotEmpty && !await _confirm('하루 겹침 확인', warns.join('\n\n'))) return;
      final n = await s.copyLines(widget.siteId!, workDate, items);
      setState(() => refresh++);
      await widget.onChanged();
      if (mounted) showMessage(context, '$n줄을 $workDate 로 복사했습니다. 다른 것만 고치세요.');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  Future<void> _noWork() async {
    try {
      await s.markNoWork(widget.siteId!, workDate);
      setState(() => refresh++);
      await widget.onChanged();
      if (mounted) showMessage(context, "$workDate '작업 없음'으로 남겼습니다.");
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  Future<void> _saveContent() async {
    try {
      await s.setLogContent(widget.siteId!, workDate, content.text);
      setState(() => refresh++);
      await widget.onChanged(); // 위쪽 「밀린 n일」·홈 '오늘 일지 미작성'도 바로 바뀌게
      if (mounted) showMessage(context, '작업 내용을 저장했습니다.');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  Future<void> _edit(Rec l, Map names) async {
    final r = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => LineEditor(line: l, payeeName: (names[l['payee_id']] ?? '') as String),
    );
    if (r == null) return;
    try {
      final reason = await _reasonIfLocked();
      if (reason == null) return;
      if (r == 'delete') {
        await s.deleteLine(l['id'] as String, reason: reason.isEmpty ? null : reason);
      } else {
        final v = LineEditor.result!;
        await s.editLine(
          l['id'] as String,
          qty: v['qty'],
          unitPrice: v['price'],
          payee: v['payee'],
          item: v['item'],
          spec: v['spec'],
          unit: v['unit'],
          note: v['note'],
          reason: reason.isEmpty ? null : reason,
        );
      }
      setState(() => refresh++);
      await widget.onChanged();
      if (mounted) showMessage(context, r == 'delete' ? '지웠습니다.' : '고쳤습니다.');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  Widget _chips(List<String> all, TextEditingController c, VoidCallback after) {
    final typed = c.text.trim();
    final list = all.where((x) => typed.isEmpty || (x.contains(typed) && x != typed)).take(8).toList();
    if (list.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final x in list)
            ActionChip(
              label: Text(x, overflow: TextOverflow.ellipsis),
              onPressed: () {
                setState(() => c.text = x);
                after();
              },
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    if (widget.siteId == null) {
      return const Center(
        child: Padding(padding: EdgeInsets.all(Tokens.group), child: Text('위쪽 「+ 접수」로 현장(공사 건)을 먼저 만드세요.')),
      );
    }
    return FutureBuilder<Map<String, dynamic>>(
      key: ValueKey('log$refresh$kind$workDate'),
      future: _load(),
      builder: (context, snap) {
        if (!snap.hasData) return const Center(child: CircularProgressIndicator());
        final d = snap.data!;
        final lines = d['lines'] as List<Rec>;
        final names = d['names'] as Map;
        final wts = d['wts'] as List<Rec>;
        final log = d['log'] as Rec?;
        if (content.text.isEmpty && (log?['content'] ?? '') != '') content.text = log!['content'] as String;
        final total = lines.fold<int>(0, (a, l) => a + (l['amount'] as int));
        final byKind = {
          for (final k in kinds) k: lines.where((l) => l['kind'] == k).fold<int>(0, (a, l) => a + (l['amount'] as int)),
        };
        final amt = amount;
        return ListView(
          padding: const EdgeInsets.all(Tokens.pad),
          children: [
            Section(
              title: '1. 작업일',
              children: [
                Row2(
                  children: [
                    Expanded(
                      child: OutlinedButton(onPressed: _pickDate, child: Text(workDate)),
                    ),
                    Expanded(
                      child: OutlinedButton(onPressed: _copyLast, child: const Text('어제와 같이')),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final w in const ['맑음', '흐림', '비', '눈', '한파', '폭염'])
                      ChoiceChip(
                        label: Text(w),
                        selected: log?['weather'] == w,
                        onSelected: (_) async {
                          try {
                            await s.setWeather(widget.siteId!, workDate, w);
                            setState(() => refresh++);
                          } on StoreError catch (e) {
                            if (context.mounted) showMessage(context, e.message);
                          }
                        },
                      ),
                  ],
                ),
                if (log?['no_work'] == 1)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Badge2('작업 없음 (${log!['weather'] ?? ''})', t.warn),
                  ),
                if ((log?['note'] ?? '') != '')
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(log!['note'] as String, style: Theme.of(context).textTheme.bodySmall),
                  ),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '2. 명부에서 고르기 (체크만)',
              children: [
                OutlinedButton(
                  key: const ValueKey('f_roster'),
                  onPressed: _pickRoster,
                  child: const Text('오늘 나온 사람·장비 고르기'),
                ),
                Text('미리 등록한(또는 전에 적은) 사람·장비를 체크하면 단가·단위까지 한 번에 들어갑니다.', style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '3. 직접 한 줄 넣기',
              children: [
                SegmentedButton<String>(
                  showSelectedIcon: false,
                  segments: [for (final k in kinds) ButtonSegment(value: k, label: Text(k))],
                  selected: {kind},
                  onSelectionChanged: (v) => _setKind(v.first),
                ),
                const SizedBox(height: Tokens.gap),
                TextField(
                  key: const ValueKey('f_item'),
                  controller: item,
                  decoration: InputDecoration(
                    labelText: kind == '인력'
                        ? '직종 (보통인부, 형틀목공 …)'
                        : kind == '장비'
                        ? '장비 (6W, 덤프 25톤 …)'
                        : kind == '자재'
                        ? '자재 (레미콘, 와이어메쉬 …)'
                        : '외주 내용',
                  ),
                  onChanged: (_) => _fillSoon(),
                  onEditingComplete: _fill,
                ),
                _chips(d['items'] as List<String>, item, _fill),
                if (kind == '자재' || kind == '장비') ...[
                  const SizedBox(height: Tokens.gap),
                  TextField(
                    controller: spec,
                    decoration: InputDecoration(labelText: kind == '자재' ? '규격 (25-21-08 등, 선택)' : '규격 (선택)'),
                  ),
                ],
                const SizedBox(height: Tokens.gap),
                TextField(
                  key: const ValueKey('f_payee'),
                  controller: payee,
                  decoration: InputDecoration(labelText: kind == '인력' ? '받는 사람 (이름 또는 팀)' : '받는 업체'),
                  onChanged: (_) => _fillSoon(),
                  onEditingComplete: _fill,
                ),
                _chips(d['payees'] as List<String>, payee, _fill),
                const SizedBox(height: Tokens.gap),
                Row2(
                  children: [
                    Expanded(
                      flex: 3,
                      child: TextField(
                        key: const ValueKey('f_qty'),
                        controller: qty,
                        onTap: () => selectAll(qty),
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: '수량 (반일 0.5)'),
                      ),
                    ),
                    Expanded(
                      flex: 2,
                      child: TextField(
                        controller: unit,
                        decoration: const InputDecoration(labelText: '단위'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: Tokens.gap),
                TextField(
                  key: const ValueKey('f_price'),
                  controller: price,
                  onTap: () => selectAll(price),
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '단가 (원)'),
                  onChanged: (_) => priceTouched = true,
                ),
                const SizedBox(height: Tokens.gap),
                TextField(
                  controller: note,
                  decoration: const InputDecoration(labelText: '메모 (선택: 작업 위치, 차량번호 등)'),
                ),
                ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: Text('공종·측점 (선택)', style: Theme.of(context).textTheme.bodySmall),
                  children: [
                    DropdownButtonFormField<String?>(
                      key: ValueKey('wt$workTypeId${wts.length}'),
                      initialValue: workTypeId,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: '공종'),
                      items: [
                        const DropdownMenuItem(value: null, child: Text('공종 없음')),
                        for (final w in wts)
                          DropdownMenuItem(value: w['id'] as String, child: Text(w['name'] as String)),
                      ],
                      onChanged: (v) => setState(() => workTypeId = v),
                    ),
                    const SizedBox(height: Tokens.gap),
                    Row2(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: staFrom,
                            decoration: const InputDecoration(labelText: '측점 시작 (No.2+10)'),
                          ),
                        ),
                        Expanded(
                          child: TextField(
                            controller: staTo,
                            decoration: const InputDecoration(labelText: '측점 끝 (No.4)'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: Tokens.gap),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  amt == null ? '금액: 수량과 단가를 넣으면 계산됩니다' : '금액 ${wonText(amt)}원',
                  style: TextStyle(fontSize: Tokens.fSub, fontWeight: FontWeight.w700, color: t.text),
                ),
                const SizedBox(height: 8),
                FilledButton(key: const ValueKey('f_save'), onPressed: _save, child: const Text('저장')),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '4. $workDate 투입 ${lines.length}줄 · ${wonText(total)}원',
              children: [
                if (lines.isEmpty) Text('아직 입력한 줄이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
                if (lines.isNotEmpty)
                  Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    children: [
                      for (final k in kinds)
                        if (byKind[k]! > 0)
                          Text('$k ${wonText(byKind[k]!)}', style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                for (final l in lines)
                  InkWell(
                    onTap: () => _edit(l, names),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Badge2(l['kind'] as String, t.blue),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '${l['item']}${(l['spec'] ?? '') == '' ? '' : ' ${l['spec']}'} ${l['qty']}${l['unit']}',
                                ),
                                Text(
                                  '${names[l['payee_id']] ?? ''} · 단가 ${wonText(l['unit_price'] as int)}'
                                  '${l['note'] != null ? ' · ${l['note']}' : ''}'
                                  '${l['sta_from'] != null ? ' · ${formatSta(num.parse(l['sta_from'] as String))}~${formatSta(num.parse(l['sta_to'] as String))}' : ''}',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            wonText(l['amount'] as int),
                            style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()]),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (lines.isNotEmpty) Text('줄을 누르면 고치거나 지울 수 있습니다.', style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '5. 작업 내용 (보고서·사진대지에 쓰임)',
              children: [
                TextField(
                  controller: content,
                  maxLines: 3,
                  decoration: const InputDecoration(labelText: '오늘 한 일'),
                ),
                const SizedBox(height: 8),
                Row2(
                  children: [
                    Expanded(
                      child: OutlinedButton(onPressed: _saveContent, child: const Text('내용 저장')),
                    ),
                    Expanded(
                      child: OutlinedButton(onPressed: _noWork, child: const Text('작업 없음(비 등)')),
                    ),
                  ],
                ),
              ],
            ),
            if ((d['works'] as List<WorkProgress>).isNotEmpty) ...[
              const SizedBox(height: Tokens.gap),
              Section(
                title: '6. 오늘 시공 (공정률)',
                children: [
                  for (final w in d['works'] as List<WorkProgress>) ...[
                    Text(
                      '${w.name}  ${fmtQty(w.done)}/${fmtQty(w.design)}m (${(w.rate * 100).toStringAsFixed(0)}%)',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    for (final p in w.today)
                      Text(
                        '  $workDate  ${formatSta(num.parse(p['sta_from'] as String))} → ${formatSta(num.parse(p['sta_to'] as String))}  ${p['qty']}m',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                  ],
                  const SizedBox(height: 8),
                  if ((d['works'] as List).length > 1)
                    DropdownButtonFormField<String>(
                      initialValue: progWt ?? (d['works'] as List<WorkProgress>).first.id,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: '공종'),
                      items: [
                        for (final w in d['works'] as List<WorkProgress>)
                          DropdownMenuItem(value: w.id, child: Text(w.name)),
                      ],
                      onChanged: (v) => progWt = v,
                    ),
                  Row2(
                    children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('pg_from'),
                          controller: progFrom,
                          decoration: const InputDecoration(labelText: '시공 측점 시작'),
                        ),
                      ),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('pg_to'),
                          controller: progTo,
                          decoration: const InputDecoration(labelText: '시공 측점 끝'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    key: const ValueKey('pg_save'),
                    onPressed: () async {
                      try {
                        await s.addProgressSta(
                          widget.siteId!,
                          workDate,
                          progWt ?? (d['works'] as List<WorkProgress>).first.id,
                          progFrom.text,
                          progTo.text,
                        );
                        progFrom.text = progTo.text; // 내일은 오늘 끝에서 시작
                        progTo.clear();
                        setState(() => refresh++);
                        await widget.onChanged();
                        if (context.mounted) showMessage(context, '시공 연장을 남겼습니다.');
                      } on StoreError catch (e) {
                        if (context.mounted) showMessage(context, e.message);
                      }
                    },
                    child: const Text('시공 연장 저장'),
                  ),
                ],
              ),
            ],
          ],
        );
      },
    );
  }
}

/// 한 줄 고치기·지우기 화면.
class LineEditor extends StatefulWidget {
  const LineEditor({super.key, required this.line, required this.payeeName});
  final Rec line;
  final String payeeName;
  static Map<String, String>? result;
  @override
  State<LineEditor> createState() => _LineEditorState();
}

class _LineEditorState extends State<LineEditor> {
  late final c = {
    'item': TextEditingController(text: widget.line['item'] as String),
    'spec': TextEditingController(text: (widget.line['spec'] ?? '') as String),
    'qty': TextEditingController(text: widget.line['qty'] as String),
    'unit': TextEditingController(text: widget.line['unit'] as String),
    'price': TextEditingController(text: '${widget.line['unit_price']}'),
    'payee': TextEditingController(text: widget.payeeName),
    'note': TextEditingController(text: (widget.line['note'] ?? '') as String),
  };
  bool confirmDelete = false;

  @override
  Widget build(BuildContext context) {
    final labels = {
      'item': '항목',
      'spec': '규격',
      'qty': '수량',
      'unit': '단위',
      'price': '단가 (원)',
      'payee': '받는 곳',
      'note': '메모',
    };
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(Tokens.pad),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${widget.line['kind']} 한 줄 고치기', style: Theme.of(context).textTheme.titleMedium),
            for (final k in labels.keys) ...[
              const SizedBox(height: Tokens.gap),
              TextField(
                key: ValueKey('e_$k'),
                controller: c[k],
                onTap: (k == 'qty' || k == 'price') ? () => selectAll(c[k]!) : null,
                keyboardType: (k == 'qty' || k == 'price')
                    ? const TextInputType.numberWithOptions(decimal: true)
                    : null,
                decoration: InputDecoration(labelText: labels[k]),
              ),
            ],
            const SizedBox(height: Tokens.gap),
            FilledButton(
              key: const ValueKey('e_save'),
              onPressed: () {
                LineEditor.result = {for (final e in c.entries) e.key: e.value.text};
                Navigator.pop(context, 'save');
              },
              child: const Text('고친 내용 저장'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              key: const ValueKey('e_delete'),
              onPressed: () {
                if (!confirmDelete) return setState(() => confirmDelete = true);
                Navigator.pop(context, 'delete');
              },
              child: Text(confirmDelete ? '정말 지웁니다 (한 번 더 누르기)' : '이 줄 지우기'),
            ),
          ],
        ),
      ),
    );
  }
}

// ───────────────────────── 결제·집계 ─────────────────────────
/// 월말에 가장 중요한 것: 누구에게 얼마를 줘야 하나 + 현장별 한 달 집계. 업무일지 줄을 더할 뿐이다.
class PayPage extends StatefulWidget {
  const PayPage({super.key, required this.store, required this.tokens, required this.onChanged});
  final Store store;
  final Tokens tokens;
  final Future<void> Function() onChanged;
  @override
  State<PayPage> createState() => _PayPageState();
}

class _PayPageState extends State<PayPage> {
  // 1~10일은 지난달 보고·결제 요청 시기 → 지난달을 먼저 보여 준다
  String month = DateTime.now().day <= 10
      ? monthShift(workDateOf(DateTime.now()).substring(0, 7), -1)
      : workDateOf(DateTime.now()).substring(0, 7);
  int refresh = 0;
  Store get s => widget.store;

  Future<Map<String, dynamic>> _load() async => {
    'pay': await s.monthPayments(month),
    'payouts': await s.monthPayouts(month),
    'req': await s.lastPayRequest(month),
    'sites': await s.monthSites(month),
    'locked': await s.isLocked(month),
    'yearSites': await s.yearBySite(month.substring(0, 4)),
  };

  Future<void> _detail(PayeeTotal p) async {
    final lines = await s.linesOfPayee(p.payeeId, month);
    final sites = {for (final x in await s.db.all('site')) x['id']: x['name']};
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        builder: (ctx, sc) => ListView(
          controller: sc,
          padding: const EdgeInsets.all(Tokens.pad),
          children: [
            Text('${p.name} · $month', style: Theme.of(ctx).textTheme.titleMedium),
            Text('${lines.length}줄 · ${wonText(p.total)}원', style: Theme.of(ctx).textTheme.bodySmall),
            const Divider(),
            for (final l in lines)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 48, child: Text((l['work_date'] as String).substring(5))),
                    Expanded(
                      child: Text(
                        '${sites[l['site_id']] ?? ''}\n${l['item']} ${l['qty']}${l['unit']} × ${wonText(l['unit_price'] as int)}',
                      ),
                    ),
                    Text(wonText(l['amount'] as int)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _pay(PayeeTotal p) async {
    final a = await askText(context, '${p.name} 일부 지급 (사장님이 보낸 금액)', '보낸 금액 (원)', initial: '${p.balance}');
    if (a == null) return;
    try {
      await s.recordPayment(p.payeeId, month, a, workDateOf(DateTime.now()));
      setState(() => refresh++);
      await widget.onChanged();
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
    }
  }

  String _reqLine(PayRequest r, int sendSum) {
    final d = r.date.substring(5);
    if (sendSum == 0) return '$d 요청 ${wonText(r.amount)}원 → 결제 끝남';
    final head = switch (r.status) {
      '전송됨' => '$d 대표님께 보냄 · ${wonText(r.amount)}원 · 결제 기다림',
      '보낼 요청' => '$d 보낼 준비 · 집 PC와 맞추면 보내집니다',
      '보낼 함 대기' => '$d 집 PC 보낼 함에 있음 (PC 메일 설정 필요)',
      '실패' => '$d 못 보냄: ${r.result}',
      _ => '$d 카톡으로 요청 · ${wonText(r.amount)}원',
    };
    return r.amount == sendSum || r.status == '실패' ? head : '$head\n→ 지금 ${wonText(sendSum)}원 (바뀜, 다시 보내 주세요)';
  }

  Future<void> _allPaid(int sum) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('사장님이 결제를 마치셨나요?'),
        content: Text('남은 ${wonText(sum)}원을 전부 지급된 것으로 기록합니다.\n(뗀 세금·부가세도 함께 기록, 다음 달 이월 0)'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아직')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('결제 끝남')),
        ],
      ),
    );
    if (ok != true) return;
    final n = await s.markAllPaid(month, workDateOf(DateTime.now()));
    setState(() => refresh++);
    await widget.onChanged();
    if (mounted) showMessage(context, '$n건을 지급 완료로 기록했습니다.');
  }

  Future<void> _account(Payout o) async {
    if (await editPayeeInfo(context, s, o.payeeId, o.name) == true) {
      setState(() => refresh++);
      await widget.onChanged();
    }
  }

  /// 대표님께 월말 보고 메일: 확인 창 → 요청 기록 → 집 PC와 맞추기(집 PC가 보고서를 만들어 보냄).
  Future<void> _sendMail(int sendSum, List<Payout> payouts) async {
    final noAcc = [
      for (final o in payouts)
        if (o.transfer > 0 && !o.hasAccount) o.name,
    ];
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('$month 월말 보고를 대표님께 보낼까요?'),
        content: Text(
          [
            '결제 요청 ${wonText(sendSum)}원 · ${payouts.where((o) => o.transfer > 0).length}건',
            '사람·업체별 계좌와 금액, 현장별 집계, 월말보고 Excel이 함께 갑니다.',
            if (noAcc.isNotEmpty) '※ 계좌 없음: ${noAcc.join(', ')} (메일에 「계좌 확인 필요」로 표시)',
            '보낸 달은 마감됩니다. 나중에 고치면 정정본으로 다시 보냅니다.',
          ].join('\n\n'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아니요')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('보내기')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await s.markPayRequested(month, status: '보낼 요청');
    } on StoreError catch (e) {
      if (mounted) showMessage(context, e.message);
      return;
    }
    var msg = '집 PC와 연결되면 바로 보내집니다.';
    final base = (await s.db.setting('server_url') ?? '').trim();
    if (base.isNotEmpty) {
      try {
        await ServerLink(base, token: await s.db.setting('server_token') ?? '').sync(s);
        final r = await s.lastPayRequest(month);
        msg = r?.status == '전송됨' ? '대표님께 보냈습니다.' : '집 PC: ${r?.status ?? ''} ${r?.result ?? ''}';
      } catch (_) {
        msg = '집 PC에 연결되지 않았습니다. 「동기화」에서 맞추면 그때 보내집니다.';
      }
    }
    setState(() => refresh++);
    await widget.onChanged();
    if (mounted) showMessage(context, msg);
  }

  /// 카톡용: 결제 요청(누구에게 얼마) + 현장별 한 달 집계를 한 글로.
  Future<void> _copyRequest() async {
    final pay = await s.paymentText(month);
    final i = pay.indexOf('[현장별]');
    final text = '${await s.payoutText(month)}${i < 0 ? '' : '\n\n${pay.substring(i)}'}';
    await Clipboard.setData(ClipboardData(text: text));
    if (mounted) showMessage(context, '결제 요청과 현장별 집계를 복사했습니다. 카톡에 붙여 넣으세요.');
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.tokens;
    return FutureBuilder<Map<String, dynamic>>(
      key: ValueKey('pay$month$refresh'),
      future: _load(),
      builder: (context, snap) {
        if (snap.hasError) return Center(child: Text('결제 집계를 못 불러왔습니다: ${snap.error}'));
        if (!snap.hasData) return const Center(child: CircularProgressIndicator());
        final pay = snap.data!['pay'] as List<PayeeTotal>;
        final sites = snap.data!['sites'] as List<SiteTotal>;
        final yearSites = snap.data!['yearSites'] as List<YearRow>;
        final yy = month.substring(0, 4);
        final total = pay.fold<int>(0, (a, p) => a + p.total);
        final due = pay.fold<int>(0, (a, p) => a + p.balance);
        final payouts = snap.data!['payouts'] as List<Payout>;
        final groups = <String, List<Payout>>{};
        for (final o in payouts) {
          groups.putIfAbsent(o.group, () => []).add(o);
        }
        final sendSum = payouts.fold<int>(0, (a, o) => a + (o.transfer > 0 ? o.transfer : 0));
        final noAccount = payouts.where((o) => o.transfer > 0 && !o.hasAccount).length;
        final req = snap.data!['req'] as PayRequest?;
        return ListView(
          padding: const EdgeInsets.all(Tokens.pad),
          children: [
            Row2(
              children: [
                SizedBox(
                  width: 56,
                  child: OutlinedButton(
                    onPressed: () => setState(() => month = monthShift(month, -1)),
                    child: const Text('◀'),
                  ),
                ),
                Expanded(
                  child: Center(child: Text(month, style: Theme.of(context).textTheme.titleMedium)),
                ),
                SizedBox(
                  width: 56,
                  child: OutlinedButton(
                    onPressed: () => setState(() => month = monthShift(month, 1)),
                    child: const Text('▶'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '대표님께 월말 보고 · 결제 요청',
              children: [
                bigNumber(context, '결제하실 돈', wonText(sendSum), '원', t),
                Text(
                  [
                    for (final g in groups.keys) '$g ${groups[g]!.length}${g == '작업자' ? '명' : '곳'}',
                    if (noAccount > 0) '계좌 없음 $noAccount',
                    if (snap.data!['locked'] as bool) '마감된 달',
                  ].join(' · '),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                Text(
                  '이달 투입 ${wonText(total)}원 · 일지 기준 남은 돈 ${wonText(due)}원',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                if (req != null)
                  Text(
                    _reqLine(req, sendSum),
                    style: TextStyle(
                      color: req.status == '실패' || (sendSum > 0 && req.amount != sendSum) ? t.warn : t.sub,
                    ),
                  ),
                if (noAccount > 0) Text('계좌 없는 사람은 아래에서 「계좌 넣기」로 먼저 넣어 주세요.', style: TextStyle(color: t.warn)),
                const SizedBox(height: 8),
                FilledButton(
                  key: const ValueKey('send_mail'),
                  // 보낸 뒤 숫자가 그대로면 다시 못 누른다(두 번 보내기 방지). 일지를 고쳐 숫자가 바뀌면 정정 보고.
                  onPressed: sendSum > 0 && !(req?.status == '전송됨' && req!.amount == sendSum)
                      ? () => _sendMail(sendSum, payouts)
                      : null,
                  child: Text(
                    req?.status == '전송됨'
                        ? (req!.amount == sendSum || sendSum == 0 ? '보고 보냄 (${req.date.substring(5)})' : '정정 보고 다시 보내기')
                        : '대표님께 보고 메일 보내기',
                  ),
                ),
                const SizedBox(height: 4),
                Wrap(
                  alignment: WrapAlignment.end,
                  children: [
                    TextButton(onPressed: _copyRequest, child: const Text('카톡용 복사')),
                    TextButton(
                      key: const ValueKey('all_paid'),
                      onPressed: req != null && sendSum > 0 ? () => _allPaid(sendSum) : null,
                      child: const Text('결제 끝남'),
                    ),
                  ],
                ),
              ],
            ),
            if (payouts.isEmpty) ...[
              const SizedBox(height: Tokens.gap),
              Text('이 달에는 투입이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
            ],
            for (final g in groups.keys) ...[
              const SizedBox(height: Tokens.gap),
              Section(
                title:
                    '$g ${groups[g]!.length}${g == '작업자' ? '명' : '곳'} · ${wonText(groups[g]!.fold<int>(0, (a, o) => a + (o.transfer > 0 ? o.transfer : 0)))}원',
                children: [
                  for (final o in groups[g]!) ...[
                    InkWell(
                      key: ValueKey('po_${o.name}'),
                      onTap: () => _detail(o.p),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(o.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                                ),
                                Text(
                                  '${wonText(o.transfer)}원',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w700,
                                    color: o.transfer > 0 ? t.text : t.sub,
                                    fontFeatures: const [FontFeature.tabularFigures()],
                                  ),
                                ),
                              ],
                            ),
                            Text(o.accountText, style: TextStyle(color: o.hasAccount ? t.text : t.warn)),
                            Text(o.breakdown, style: Theme.of(context).textTheme.bodySmall),
                            if (o.p.bySite.length > 1)
                              for (final e in o.p.bySite.entries)
                                Text('  ${e.key}  ${wonText(e.value)}', style: Theme.of(context).textTheme.bodySmall),
                          ],
                        ),
                      ),
                    ),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        TextButton(onPressed: () => _account(o), child: Text(o.hasAccount ? '계좌·방식' : '계좌 넣기')),
                        if (o.transfer > 0) TextButton(onPressed: () => _pay(o.p), child: const Text('일부만 지급됨')),
                      ],
                    ),
                    const Divider(height: 1),
                  ],
                ],
              ),
            ],
            const SizedBox(height: Tokens.gap),
            Section(
              title: '현장별 한 달 집계',
              children: [
                if (sites.isEmpty) Text('이 달에는 일지가 없습니다.', style: Theme.of(context).textTheme.bodySmall),
                for (final x in sites) ...[
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(x.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                            ),
                            Text('${wonText(x.total)}원', style: const TextStyle(fontWeight: FontWeight.w700)),
                          ],
                        ),
                        Text(
                          '작업 ${x.workDays}일${x.restDays.isEmpty ? '' : ' · 쉼 ${x.restDays.length}일'} · 인력 ${fmtQty(x.manDays)}공수',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        for (final e in x.equipment.entries)
                          Text(
                            '  ${e.key.split('|')[0]}  ${fmtQty(e.value)}${e.key.split('|')[1]}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        Wrap(
                          spacing: 12,
                          children: [
                            for (final k in kinds)
                              Text('$k ${wonText(x.byKind[k]!)}', style: Theme.of(context).textTheme.bodySmall),
                          ],
                        ),
                        for (final m in x.materials.entries)
                          Text(
                            '  ${m.key.split('|')[0]}  ${fmtQty(m.value)}${m.key.split('|')[1]}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                      ],
                    ),
                  ),
                  const Divider(height: 1),
                ],
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '$yy년 누계 (현장별)',
              children: [
                Text('사람·장비별 올해 누계는 명부 탭에 있습니다.', style: Theme.of(context).textTheme.bodySmall),
                for (final y in yearSites)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(y.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                            ),
                            Text('${wonText(y.amountTotal)}원', style: const TextStyle(fontWeight: FontWeight.w700)),
                          ],
                        ),
                        Text(
                          [
                            for (var m = 1; m <= 12; m++)
                              if (y.amount[m] != null) '$m월 ${wonText(y.amount[m]!)}',
                          ].join(' / '),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ],
        );
      },
    );
  }
}

/// 앱 버전 (pubspec.yaml 의 version 과 같게 올린다). 동기화 탭 맨 아래에 보인다.
const appVersion = '0.4.3';

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
        return ListView(
          padding: const EdgeInsets.all(Tokens.pad),
          children: [
            Section(
              title: '집 PC 서버',
              children: [
                TextField(
                  controller: url,
                  decoration: const InputDecoration(labelText: '주소 (Tailscale)'),
                ),
                const SizedBox(height: Tokens.gap),
                TextField(
                  controller: token,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: '토큰'),
                ),
                const SizedBox(height: Tokens.gap),
                FilledButton(onPressed: busy ? null : _sync, child: Text(busy ? '맞추는 중…' : '지금 맞추기')),
                if (status.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(status, style: Theme.of(context).textTheme.bodySmall),
                  ),
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Section(
              title: '충돌 검토 ${conflicts.length}건',
              children: [
                if (conflicts.isEmpty) Text('충돌이 없습니다.', style: Theme.of(context).textTheme.bodySmall),
                for (final c in conflicts) ...[
                  Text('${c['table_name']} · 두 기기가 같은 기록을 고쳤습니다.', style: Theme.of(context).textTheme.bodySmall),
                  Text('먼저 저장된 값: ${_show(c['current'] as Map, c['incoming'] as Map)}'),
                  Text('이 폰의 값: ${_show(c['incoming'] as Map, c['incoming'] as Map)}', style: TextStyle(color: t.warn)),
                  const SizedBox(height: 8),
                  Row2(
                    children: [
                      Expanded(
                        child: OutlinedButton(onPressed: () => _resolve(c, 'current'), child: const Text('먼저 값 유지')),
                      ),
                      Expanded(
                        child: FilledButton(onPressed: () => _resolve(c, 'incoming'), child: const Text('이 폰 값')),
                      ),
                    ],
                  ),
                  const Divider(height: Tokens.group),
                ],
              ],
            ),
            const SizedBox(height: Tokens.gap),
            Center(
              child: Text(
                '진성현장 앱 $appVersion',
                key: const ValueKey('app_version'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ],
        );
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

/// 받는 곳 계좌·지급 방식 고치기 (결제 탭·명부에서 같이 씀).
Future<bool?> editPayeeInfo(BuildContext context, Store s, String payeeId, String name) async {
  final p = await s.mustGet('payee', payeeId);
  if (!context.mounted) return null;
  final bank = TextEditingController(text: (p['bank'] ?? '') as String);
  final acc = TextEditingController(text: (p['account_no'] ?? '') as String);
  final holder = TextEditingController(text: (p['holder'] ?? name) as String);
  var rule = (p['pay_rule'] as String?) ?? (p['payee_type'] == '개인' ? '일용' : '그대로');
  final ok = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, set) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(Tokens.pad),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('$name 계좌·지급 방식', style: Theme.of(ctx).textTheme.titleMedium),
              const SizedBox(height: Tokens.gap),
              TextField(
                key: const ValueKey('pi_bank'),
                controller: bank,
                decoration: const InputDecoration(labelText: '은행'),
              ),
              const SizedBox(height: Tokens.gap),
              TextField(
                key: const ValueKey('pi_acc'),
                controller: acc,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: '계좌번호'),
              ),
              const SizedBox(height: Tokens.gap),
              TextField(
                key: const ValueKey('pi_holder'),
                controller: holder,
                decoration: const InputDecoration(labelText: '예금주'),
              ),
              const SizedBox(height: Tokens.gap),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final r in payRules)
                    ChoiceChip(
                      label: Text(payRuleLabel[r]!),
                      selected: rule == r,
                      onSelected: (_) => set(() => rule = r),
                    ),
                ],
              ),
              const SizedBox(height: 4),
              Text('일용: 하루 일당 15만원 넘는 부분의 2.7%를 소득세로, 그 10%를 지방소득세로 뗍니다.', style: Theme.of(ctx).textTheme.bodySmall),
              const SizedBox(height: Tokens.gap),
              FilledButton(
                key: const ValueKey('pi_save'),
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('저장'),
              ),
            ],
          ),
        ),
      ),
    ),
  );
  if (ok != true) return ok;
  await s.setPayeeInfo(payeeId, bank: bank.text, account: acc.text, holder: holder.text, rule: rule);
  return true;
}
