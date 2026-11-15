"""매일 자동 백업 3곳 (설계안 12장): 집 PC + 외장 디스크 + 회사 전용 클라우드 폴더.

한 곳이 실패해도 나머지는 계속한다. 백업 파일은 열어서 무결성을 확인한 뒤에만 '성공'으로 적는다.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .store import Store

PREFIX = "진성현장_"


def backup(store: Store, destinations: list[str | Path], today: str, keep: int = 30) -> list[dict]:
    results = []
    for dest in destinations:
        dest = Path(dest)
        target = dest / f"{PREFIX}{today}.db"
        try:
            if not dest.is_dir():
                raise FileNotFoundError(f"폴더가 없습니다(외장 디스크 연결 확인): {dest}")
            tmp = target.with_suffix(".tmp")
            out = sqlite3.connect(str(tmp))
            with out:
                store.db.backup(out)
            ok = out.execute("PRAGMA integrity_check").fetchone()[0]
            n = out.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
            out.close()
            if ok != "ok":
                raise RuntimeError(f"무결성 검사 실패: {ok}")
            tmp.replace(target)
            old = sorted(dest.glob(f"{PREFIX}*.db"))[:-keep]
            for f in old:
                f.unlink()
            results.append({"dest": str(dest), "ok": True, "file": target.name, "logs": n})
        except Exception as exc:  # noqa: BLE001 — 한 곳 실패가 다른 곳을 막지 않게
            results.append({"dest": str(dest), "ok": False, "error": str(exc)})
    return results


def restore_check(path: str | Path) -> dict:
    """백업 파일을 실제로 열어 본다 (복구 연습)."""
    db = sqlite3.connect(str(path))
    try:
        return {"integrity": db.execute("PRAGMA integrity_check").fetchone()[0],
                "sites": db.execute("SELECT COUNT(*) FROM site").fetchone()[0],
                "logs": db.execute("SELECT COUNT(*) FROM work_log").fetchone()[0],
                "lines": db.execute("SELECT COUNT(*) FROM input_line").fetchone()[0]}
    finally:
        db.close()
