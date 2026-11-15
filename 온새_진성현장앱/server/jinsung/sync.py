"""변경 기록 기반 동기화 (설계안 12장, 0단계 통과 기준).

원칙
- 모든 추가·수정·삭제는 change_log 에 순서대로 쌓인다. 기기는 '보낸 곳까지'와
  '받은 곳까지'만 기억한다. 인터넷이 끊겨도 입력은 계속되고, 연결되면 밀린 만큼 오간다.
- 같은 기록을 두 기기가 따로 고쳤으면 어느 쪽도 자동으로 덮어쓰지 않는다. 늦게 온 쪽 기기에
  '충돌 검토'가 생기고, 그 기기의 기록은 먼저 저장된 값으로 맞춰진다(내 값은 충돌 기록에 보관).
- 두 기기가 같은 현장·같은 날 일지를 따로 만들었으면 하나로 잇는다(id_alias).
- 순서: 항상 보내기(push) → 받기(pull).
"""
from __future__ import annotations

import json
import sqlite3

from .store import SYNCED, Store, new_id

# 다른 기록의 번호를 가리키는 칸 (별칭을 풀어 줄 대상)
_REFS = ("log_id", "site_id", "payee_id", "work_type_id", "run_id")


def _real(store: Store, row_id):
    if row_id is None:
        return None
    r = store.db.execute("SELECT real_id FROM id_alias WHERE alias_id=?", (row_id,)).fetchone()
    return r["real_id"] if r else row_id


def changes_since(store: Store, seq: int, exclude_device: str | None = None,
                  only_device: str | None = None) -> list[dict]:
    sql = "SELECT * FROM change_log WHERE seq > ?"
    args: list = [seq]
    if exclude_device:
        sql += " AND device != ?"
        args.append(exclude_device)
    if only_device:
        sql += " AND device = ?"
        args.append(only_device)
    return [dict(r) for r in store.db.execute(sql + " ORDER BY seq", args)]


def _find_twin(store: Store, table: str, data: dict):
    """고유 조건이 같은 '쌍둥이' 기록 (두 기기가 같은 것을 따로 만든 경우)."""
    if table == "work_log":
        return store.db.execute("SELECT id FROM work_log WHERE site_id=? AND work_date=?",
                                (data["site_id"], data["work_date"])).fetchone()
    if table == "station":
        return store.db.execute("SELECT id FROM station WHERE site_id=? AND sta_m=?",
                                (data["site_id"], data["sta_m"])).fetchone()
    if table == "allocation":
        return store.db.execute(
            "SELECT id FROM allocation WHERE site_id=? AND item=? AND spec=?",
            (data["site_id"], data["item"], data["spec"])).fetchone()
    if table == "site" and data.get("site_type") == "본사공통":
        return store.db.execute("SELECT id FROM site WHERE site_type='본사공통'").fetchone()
    return None


def apply_change(store: Store, ch: dict) -> dict:
    """상대 기기의 변경 한 건을 적용한다. 결과: 적용 / 건너뜀 / 충돌(+ 지금 값)."""
    table, op = ch["table_name"], ch["op"]
    data = json.loads(ch["data_json"]) if ch["data_json"] else None
    if op == "마감":
        with store.db:
            store.db.execute("INSERT OR IGNORE INTO month_lock (month, locked_at) VALUES (?,?)",
                             (data["month"], ch["at"]))
            store._log_change("month_lock", data["month"], "마감", None, data, device=ch["device"])
        return {"seq": ch["seq"], "status": "적용"}
    if table not in SYNCED:
        return {"seq": ch["seq"], "status": "건너뜀"}
    row_id = _real(store, ch["row_id"])
    cur = store.db.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()

    if op == "추가":
        if cur is not None:
            return {"seq": ch["seq"], "status": "건너뜀"}
        data = {k: (_real(store, v) if k in _REFS else v) for k, v in data.items()}
        twin = _find_twin(store, table, data)
        if twin is not None:
            with store.db:
                store.db.execute("INSERT OR REPLACE INTO id_alias (alias_id, real_id) VALUES (?,?)",
                                 (ch["row_id"], twin["id"]))
            return {"seq": ch["seq"], "status": "이어 붙임", "real_id": twin["id"]}
        cols = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        with store.db:
            store.db.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(data.values()))
            store._log_change(table, data["id"], "추가", None, data, device=ch["device"])
        return {"seq": ch["seq"], "status": "적용"}

    if cur is None:
        return {"seq": ch["seq"], "status": "건너뜀"}       # 이미 지워진 기록
    cur = dict(cur)
    base = ch["base_version"]

    if op == "수정":
        data = {k: (_real(store, v) if k in _REFS else v) for k, v in data.items()}
        if cur["version"] == base + 1 and all(cur.get(k) == v for k, v in data.items()):
            return {"seq": ch["seq"], "status": "건너뜀"}   # 같은 변경이 이미 들어와 있음
        if cur["version"] != base:
            return {"seq": ch["seq"], "status": "충돌", "current": cur, "incoming": data,
                    "table": table, "row_id": row_id, "base_version": base}
        sets = ", ".join(f"{k}=?" for k in data)
        with store.db:
            store.db.execute(
                f"UPDATE {table} SET {sets}{', ' if sets else ''}version=?, updated_at=? WHERE id=?",
                [*data.values(), base + 1, ch["at"], row_id])
            store._log_change(table, row_id, "수정", base, data, ch["reason"], device=ch["device"])
            if ch["reason"]:
                store._history(table, row_id, "수정", cur, data, ch["reason"])
        return {"seq": ch["seq"], "status": "적용"}

    if op == "삭제":
        if cur["version"] != base:
            return {"seq": ch["seq"], "status": "충돌", "current": cur, "incoming": {"삭제": True},
                    "table": table, "row_id": row_id, "base_version": base}
        with store.db:
            store.db.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
            store._log_change(table, row_id, "삭제", base, None, ch["reason"], device=ch["device"])
            store._history(table, row_id, "삭제", cur, None, ch["reason"])
        return {"seq": ch["seq"], "status": "적용"}
    return {"seq": ch["seq"], "status": "건너뜀"}


def _cursor(store: Store, peer: str, direction: str) -> int:
    r = store.db.execute("SELECT seq FROM sync_cursor WHERE peer=? AND dir=?",
                         (peer, direction)).fetchone()
    return r["seq"] if r else 0


def _set_cursor(store: Store, peer: str, direction: str, seq: int) -> None:
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO sync_cursor (peer, dir, seq) VALUES (?,?,?)",
                         (peer, direction, seq))


def _adopt(store: Store, res: dict) -> None:
    """내 변경이 늦었다 → 먼저 저장된 값으로 맞추고, 내 값은 '충돌 검토'에 남긴다."""
    table, cur = res["table"], res["current"]
    mine = store.db.execute(f"SELECT * FROM {table} WHERE id=?", (res["row_id"],)).fetchone()
    with store.db:
        if mine is None:                       # 나는 지웠는데 상대는 고침 → 상대 값으로 되살림
            cols = ", ".join(cur)
            marks = ", ".join("?" for _ in cur)
            try:
                store.db.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(cur.values()))
            except sqlite3.IntegrityError:
                pass
        else:
            sets = ", ".join(f"{k}=?" for k in cur if k != "id")
            store.db.execute(f"UPDATE {table} SET {sets} WHERE id=?",
                             [v for k, v in cur.items() if k != "id"] + [res["row_id"]])
        store.db.execute(
            "INSERT INTO conflict (id, table_name, row_id, base_version, current_json,"
            " incoming_json, device, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_id(), table, res["row_id"], res["base_version"],
             json.dumps(cur, ensure_ascii=False),
             json.dumps(res["incoming"], ensure_ascii=False), store.device, store._now()))


def sync(client: Store, server: Store, peer: str = "집PC") -> dict:
    """폰(client) ↔ 집 PC(server). 같은 함수를 HTTP 너머로도 쓴다(api.py)."""
    pushed = push(client, lambda chs: [apply_change(server, c) for c in chs], peer)
    pulled = pull(client, lambda seq: changes_since(server, seq, exclude_device=client.device), peer)
    return {"보냄": pushed["보냄"], "받음": pulled["받음"], "충돌": pushed["충돌"] + pulled["충돌"]}


def push(client: Store, send, peer: str = "집PC") -> dict:
    out = changes_since(client, _cursor(client, peer, "out"), only_device=client.device)
    conflicts = 0
    if out:
        for res in send(out):
            if res["status"] == "충돌":
                _adopt(client, res)
                conflicts += 1
            elif res["status"] == "이어 붙임":
                # 내 번호(seq의 row_id)는 그대로 두고, 상대 번호를 내 번호에 잇는다
                mine = next(c for c in out if c["seq"] == res["seq"])
                with client.db:
                    client.db.execute(
                        "INSERT OR REPLACE INTO id_alias (alias_id, real_id) VALUES (?,?)",
                        (res["real_id"], mine["row_id"]))
        _set_cursor(client, peer, "out", out[-1]["seq"])
    return {"보냄": len(out), "충돌": conflicts}


def pull(client: Store, fetch, peer: str = "집PC") -> dict:
    incoming = fetch(_cursor(client, peer, "in"))
    conflicts = 0
    for ch in incoming:
        res = apply_change(client, ch)
        if res["status"] == "충돌":
            # 내 쪽에 아직 안 보낸 변경이 있었다는 뜻 → 다음 push 에서 정리된다
            conflicts += 1
    if incoming:
        _set_cursor(client, peer, "in", incoming[-1]["seq"])
        # 받은 변경이 내 change_log 에 다시 쌓였으므로, 그만큼은 보낼 필요가 없다
    return {"받음": len(incoming), "충돌": conflicts}
