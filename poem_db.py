"""Supabase의 drafts 표에 시를 읽고 쓰는 곳. 주소·키는 .env에서 읽어 온다 (코드에 적지 않음).

app.py는 한글 칸 이름(받은날짜·제목…)으로 시를 다루므로,
표의 영문 칸 이름과 서로 바꾸는 일도 여기서 한다.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TABLE = "drafts"
OBJECT_CHAR = chr(0xFFFC)  # 사진 자리에 찍히는 보이지 않는 글자. 어떤 길로 들어와도 저장 전에 지운다


class SupabaseError(Exception):
    """Supabase와 주고받다 생긴 문제. 메시지는 화면에 그대로 보여 줘도 되는 말."""


class DuplicateError(SupabaseError):
    """받은날짜와 제목이 같은 시가 이미 있을 때."""


def load_env():
    """.env의 KEY=VALUE 줄을 환경변수로 읽어 온다 (이미 있는 값은 덮지 않음)."""
    path = Path(__file__).parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _request(method, query="", body=None, want_rows=False):
    load_env()
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    # 비밀 키가 있으면 그것을 쓴다 (표의 공개 권한을 닫은 뒤에는 이 키만 통한다)
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not base or not key:
        raise SupabaseError(".env에 SUPABASE_URL, SUPABASE_SECRET_KEY 값을 먼저 채워 주세요.")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if want_rows:
        headers["Prefer"] = "return=representation"  # 저장한 줄을 되돌려 받는다
    req = urllib.request.Request(
        f"{base}/rest/v1/{TABLE}{query}",
        method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read() or "null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code == 409:
            raise DuplicateError("받은날짜와 제목이 같은 시가 이미 목록에 있습니다.") from e
        if e.code == 404:
            raise SupabaseError(f"{TABLE} 표를 찾을 수 없습니다. supabase_setup.sql을 먼저 실행해 주세요.") from e
        raise SupabaseError(f"Supabase 오류 {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise SupabaseError(f"Supabase에 연결하지 못했습니다: {e.reason}") from e


def _to_poem(row):
    return {
        "id": row["id"],
        "받은날짜": row["received_date"],
        "제목": row["title"],
        "작가": row["author"] or "",
        "본문": row["body"],
        "글끝날짜": row["end_date"] or "",
        "잘림": row["cut"],
        "프롬프트": "있음" if row["prompt"] else "없음",
        "프롬프트내용": row["prompt"] or "",
        "대상": bool(row.get("is_target")),  # 시화 대상 칸을 더하기 전의 표에는 칸이 없다 → 대상 아님
        "삭제됨": bool(row.get("is_deleted")),  # 삭제 칸을 더하기 전의 표에는 칸이 없다 → 삭제 안 함
    }


def fetch_poems():
    """모든 시를 받은날짜 최근 순으로 가져온다."""
    rows = _request("GET", "?select=*&order=received_date.desc,id.desc")
    return [_to_poem(r) for r in rows]


def _clean(text):
    return (text or "").replace(OBJECT_CHAR, "")


def insert_poem(poem):
    """시 한 편을 저장하고, 새로 생긴 줄의 번호(id)를 돌려준다."""
    rows = _request(
        "POST",
        body={
            "received_date": poem["받은날짜"],
            "title": _clean(poem["제목"]),
            "author": _clean(poem["작가"]),
            "body": _clean(poem["본문"]),
            "end_date": poem.get("글끝날짜") or None,
            "cut": poem["잘림"],
        },
        want_rows=True,
    )
    return rows[0]["id"]


def update_prompt(poem_id, prompt):
    """그 편에 수채화 프롬프트를 시와 함께 저장한다."""
    _request("PATCH", f"?id=eq.{int(poem_id)}", body={"prompt": _clean(prompt)})


def update_targets(poem_ids, is_target):
    """고른 편들을 시화 대상으로 정하거나(True) 대상에서 뺀다(False). 이미 만든 프롬프트는 건드리지 않는다."""
    ids = ",".join(str(int(i)) for i in poem_ids)
    if not ids:
        return
    try:
        _request("PATCH", f"?id=in.({ids})", body={"is_target": bool(is_target)})
    except SupabaseError as e:
        if "is_target" in str(e):
            raise SupabaseError("표에 시화 대상 칸이 없습니다. supabase_add_target.sql을 먼저 실행해 주세요.") from e
        raise


def update_deleted(poem_ids, is_deleted):
    """고른 편들을 목록에서 삭제하거나(True) 되살린다(False). 표에서 지우지 않고 숨기기만 한다."""
    ids = ",".join(str(int(i)) for i in poem_ids)
    if not ids:
        return
    try:
        _request("PATCH", f"?id=in.({ids})", body={"is_deleted": bool(is_deleted)})
    except SupabaseError as e:
        if "is_deleted" in str(e):
            raise SupabaseError("표에 삭제 칸이 없습니다. supabase_add_deleted.sql을 먼저 실행해 주세요.") from e
        raise


def mark_checked(poem_ids):
    """고른 편들의 잘림 표시('확인 필요'·'잘림')를 확인이 끝난 것으로 지운다. 본문은 그대로 둔다."""
    ids = ",".join(str(int(i)) for i in poem_ids)
    if ids:
        _request("PATCH", f"?id=in.({ids})", body={"cut": "-"})


def update_body(poem_id, body):
    """그 편의 본문을 온전한 본문으로 덮어쓰고, 잘림 표시를 거둔다."""
    _request("PATCH", f"?id=eq.{int(poem_id)}", body={"body": _clean(body), "cut": "-"})
