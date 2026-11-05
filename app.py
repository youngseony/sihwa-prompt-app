import csv
import html
import io
import os
import zipfile
from datetime import datetime

import streamlit as st

import poem_db
import prompt_maker
from poem_parser import OBJECT_CHAR, parse_file, parse_message

st.set_page_config(page_title="시화 프롬프트 제작")

def _is_local():
    """내 컴퓨터에서 직접 열었는가 (주소가 localhost일 때). 알 수 없으면 아니라고 본다."""
    try:
        host = st.context.headers.get("Host", "")
    except Exception:
        return False
    return host.split(":")[0] in ("localhost", "127.0.0.1")


def _login_configured():
    """구글 로그인 설정([auth], Secrets 또는 .streamlit/secrets.toml)이 있는가."""
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _allowed_emails():
    """들어올 수 있는 구글 계정 목록. 환경변수 ALLOWED_EMAILS에 쉼표로 적는다 (코드에 적지 않음)."""
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()} | _admin_emails()  # 관리자는 항상 들어올 수 있다


def _admin_emails():
    """관리자 메일 목록. 설정(st.secrets)의 ADMIN_EMAILS에서 읽는다 (쉼표로 이은 글 또는 목록 모두 가능)."""
    try:
        raw = st.secrets.get("ADMIN_EMAILS", "")
    except Exception:
        return set()
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    return {str(e).strip().lower() for e in items if str(e).strip()}


def is_admin():
    """지금 들어온 사람이 관리자인가. 로그인한 구글 메일(확인된 것만)이 관리자 목록에 있어야 한다."""
    if not _login_configured() or not st.user.is_logged_in:
        return False
    email = str(st.user.get("email", "")).lower()
    return bool(email) and bool(st.user.get("email_verified", False)) and email in _admin_emails()


def require_login():
    """허락된 구글 계정으로 로그인하기 전에는 앱의 나머지(시 · 프롬프트)를 보여 주지 않는다.

    구글 로그인 설정은 [auth] (.streamlit/secrets.toml 또는 Streamlit Cloud의 Secrets),
    들어올 계정은 ALLOWED_EMAILS에서 읽는다. 로그인 설정이 없으면, 내 컴퓨터에서 직접 열 때만
    그냥 열리고 그 밖의 주소에서는 열리지 않는다.
    """
    poem_db.load_env()
    if not _login_configured():
        if _is_local():
            return
        st.title("시화 프롬프트 제작")
        st.error("구글 로그인이 설정되지 않아 열 수 없습니다. 설정(Secrets)에 [auth]를 추가해 주세요.")
        st.stop()
    if not st.user.is_logged_in:
        st.title("시화 프롬프트 제작")
        st.caption("구글 계정으로 로그인해 주세요.")
        st.button("구글로 로그인", on_click=st.login, args=["google"])
        st.stop()
    email = str(st.user.get("email", "")).lower()
    verified = st.user.get("email_verified", False)
    if not (email and verified and email in _allowed_emails()):
        st.title("시화 프롬프트 제작")
        st.error("이 계정은 들어올 수 없습니다. 허락된 계정으로 다시 로그인해 주세요.")
        st.button("로그아웃", on_click=st.logout)
        st.stop()


require_login()

if _login_configured():
    who = st.user.get("name") or st.user.get("email", "")
    st.caption(f"{who}님 로그인 중")

# 시 목록은 Supabase의 poems 표에 있다 (poem_db.py). 여기에는 화면 상태만 둔다
if "screen" not in st.session_state:
    st.session_state.screen = 0  # 앱을 열면 첫 화면(히어로)이 먼저 보이고, 시작하기를 누르면 시 목록(화면 3)으로 간다
if "err" not in st.session_state:
    st.session_state.err = ""


def go(n):
    st.session_state.screen = n
    st.session_state.err = ""
    st.session_state.notice = ""
    st.session_state.list_result = None


# ---- 첫 화면 (히어로) ----
HERO_TITLE = "시를 시화로"
HERO_SUBTITLE = "시 한 편을 넣으면, 그 시에 어울리는 수채화 삽화 프롬프트를 만들어 드립니다."

HERO_STYLE = """
<style>
/* 바탕: 영상이 뜨기 전에도 하얗게 번쩍이지 않도록 같은 푸른색을 깔고, 앱의 기본 배경은 투명하게 한다 */
html, body { background: #075985 !important; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"], .main {
    background: transparent !important;
}
.hero-bg {
    position: fixed; inset: 0; width: 100vw; height: 100vh;
    object-fit: cover; z-index: -1; pointer-events: none;
}
.st-key-hero {
    min-height: 80vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center; text-align: center; gap: 1.4rem;
}
[data-testid="stToolbar"] { display: none; }  /* 첫 화면에서는 Streamlit 도구 막대(Deploy, 점 세 개)를 숨긴다 */
.st-key-hero [data-testid="stMarkdownContainer"] { width: 100%; text-align: center; }
.st-key-hero .hero-title {
    color: #fff !important; font-size: clamp(2.8rem, 8vw, 5.6rem) !important; font-weight: 800 !important;
    letter-spacing: -0.02em; line-height: 1.1 !important; margin: 0 !important; padding: 0 !important;
    text-align: center; text-shadow: 0 2px 28px rgba(3, 44, 76, 0.5);
}
.st-key-hero .hero-sub {
    color: rgba(255, 255, 255, 0.94) !important; font-size: clamp(1.05rem, 2.4vw, 1.5rem) !important;
    margin: 1.1rem auto 0 !important; max-width: 36em; text-align: center;
    word-break: keep-all; text-wrap: balance;  /* 낱말 중간에서 줄을 바꾸지 않고, 두 줄이면 길이를 비슷하게 */
    text-shadow: 0 1px 18px rgba(3, 44, 76, 0.55);
}
.st-key-hero_start button {
    background: #fff; color: #075985; border: none; border-radius: 999px;
    padding: 0.9rem 3.2rem; box-shadow: 0 10px 30px rgba(3, 44, 76, 0.38);
}
.st-key-hero_start button p { color: #075985; font-size: 1.2rem; font-weight: 700; }
.st-key-hero_start button:hover { background: #E0F2FE; transform: translateY(-1px); }
@media (prefers-reduced-motion: reduce) { .hero-bg { display: none; } }  /* 움직임을 줄이도록 설정한 사람에게는 영상을 끈다 */
</style>
<video class="hero-bg" autoplay muted loop playsinline preload="auto" aria-hidden="true">
    <source src="app/static/hero.mp4" type="video/mp4">
</video>
"""


def hero():
    """첫 화면: 영상 배경 위에 큰 제목 · 한 줄 소개 · 시작하기 버튼. 시작하기를 누르면 기능 화면(시 목록)으로 간다."""
    st.markdown(HERO_STYLE, unsafe_allow_html=True)
    with st.container(key="hero"):
        st.markdown(
            f'<h1 class="hero-title">{HERO_TITLE}</h1><p class="hero-sub">{HERO_SUBTITLE}</p>',
            unsafe_allow_html=True,
        )
        st.button("시작하기", key="hero_start", on_click=go, args=(3,))


if st.session_state.screen == 0:
    hero()
    st.stop()  # 첫 화면에서는 아래의 화면 이동 버튼 · 저작권 줄을 그리지 않는다


def open_poem(poem_id):
    """목록에서 줄을 누르면 그 편(표의 id)을 골라 화면 2로 간다."""
    st.session_state.sel = poem_id
    go(2)


def load_or_stop():
    """시 목록을 Supabase에서 가져온다. 실패하면 이유를 보여 주고 화면 그리기를 멈춘다."""
    try:
        return poem_db.fetch_poems()
    except poem_db.SupabaseError as e:
        st.error(str(e))
        st.stop()


# ---- 화면 4 · 관리 (관리자만) ----
def screen4():
    """관리 화면. 관리자만 열 수 있고, 관리자가 아니면 이 함수는 실행되지 않는다."""
    st.write("관리자만 보는 화면입니다")


# ---- 화면 1 · 시 넣기 ----
def parse_input(date, text):
    """붙여넣은 글을 시 한 편(dict)으로 나눈다. 안 되면 (None, 안내 문구)."""
    result = parse_message(text)  # 카카오톡 맨 앞 줄이 붙어 있는 글
    if result is None:
        # 첫 줄 "제목 / 작가" 모양: 받은날짜 칸의 날짜로 맨 앞 줄을 만들어 같은 방식으로 나눈다
        if not date:
            return None, "받은날짜를 YYYY-MM-DD 모양으로 적어 주세요."
        y, m, d = date.split("-")
        result = parse_message(f"{y}년 {int(m)}월 {int(d)}일 오전 9:00, 나 : {text}")
    elif date:
        result["받은날짜"] = date  # 칸에 직접 적은 날짜가 우선
    if result is None or not result["제목"]:
        return None, "첫 줄을 '제목 / 작가' 모양으로 적어 주세요."
    result["프롬프트"] = "없음"
    return result, ""


def submit_poem():
    date = st.session_state.in_date.strip()
    text = st.session_state.in_text.replace(OBJECT_CHAR, "").strip()  # 사진 자리 표시(보이지 않는 글자)는 지운다
    if not text:
        st.session_state.err = "시를 붙여넣어 주세요."
        return
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            st.session_state.err = "받은날짜를 YYYY-MM-DD 모양으로 적어 주세요."
            return
    poem, err = parse_input(date, text)
    if poem is None:
        st.session_state.err = err
        return
    try:
        poem_id = poem_db.insert_poem(poem)  # 같은 받은날짜·제목이면 표가 막아 준다
    except poem_db.SupabaseError as e:
        st.session_state.err = str(e)
        return
    open_poem(poem_id)  # 목록에 쌓고 화면 2로


def screen1():
    st.title("시 넣기")
    st.caption("시 한 편을 직접 붙여넣는 화면입니다. 카카오톡 파일로 한꺼번에 넣으려면 위의 '시 목록'으로 가세요.")

    st.caption("받은날짜 — 시를 받은 날 (오늘 아님)")
    st.text_input(
        "받은날짜",
        key="in_date",
        placeholder="YYYY-MM-DD",
        label_visibility="collapsed",
    )

    st.caption("시 한 편 붙여넣기")
    st.text_area(
        "시 한 편",
        key="in_text",
        placeholder="첫 줄 — 제목 / 작가\n\n본문 — 한 칸에 전부",
        height=300,
        label_visibility="collapsed",
    )

    st.button("넣기", on_click=submit_poem)
    if st.session_state.err:
        st.error(st.session_state.err)

# ---- 화면 2 · 한 편 화면 ----
def make_prompt(poem_id, body):
    """만들기: 시 본문만 AI에 보내 프롬프트를 받아 오고, 받은 프롬프트는 바로 그 시와 함께 저장한다."""
    try:
        text, tier = prompt_maker.make_prompt(body)
        poem_db.update_prompt(poem_id, text)
    except (prompt_maker.PromptError, poem_db.SupabaseError) as e:
        st.session_state.err = str(e)
        return
    st.session_state.err = ""
    # 무료 키가 안 돼서 유료 키로 만들었으면 알려 준다 (요금이 나가므로)
    st.session_state.notice = "무료 키가 안 돼서 유료 키로 만들었습니다 (요금이 나옵니다)." if tier == "유료" else ""


def prompt_only(text):
    """복사할 부분: 그림 도구에 붙여 넣을 영문 프롬프트만 (뒤의 '요약:' 한 줄은 뺀다)."""
    return text.split("\n\n요약:")[0].strip()


def export_name(poem):
    """내려받을 파일 이름: 받은날짜_시제목_수채화.txt (제목의 \\ / : * ? " < > | 는 -로 바꾼다)."""
    title = poem["제목"]
    for ch in '\\/:*?"<>|':
        title = title.replace(ch, "-")
    return f"{poem['받은날짜']}_{title}_수채화.txt"


def backup_csv(poems):
    """전체 백업: 삭제한 시까지 포함한 모든 시를 엑셀에서도 열리는 CSV 하나의 바이트로 만든다 (맨 앞에 한글 표시 BOM)."""
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(["받은날짜", "제목", "작가", "본문", "글끝날짜", "잘림", "시화 대상", "삭제", "프롬프트"])
    for p in poems:
        out.writerow([
            p["받은날짜"], p["제목"], p["작가"], p["본문"], p["글끝날짜"], p["잘림"],
            "예" if p["대상"] else "아니오", "예" if p["삭제됨"] else "아니오", p["프롬프트내용"],
        ])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def export_zip(items):
    """(시, 프롬프트 글) 목록을 파일 이름 규칙대로 담은 압축 파일의 바이트를 만든다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for poem, text in items:
            z.writestr(export_name(poem), prompt_only(text))
    return buf.getvalue()


def overwrite_body(poem_id):
    """덮어쓸 칸의 글로 그 편의 본문을 바꾼다 (잘림 표시도 거둔다). 화면은 그대로."""
    text = st.session_state.overwrite_text.replace(OBJECT_CHAR, "").strip()  # 사진 자리 표시(보이지 않는 글자)는 지운다
    if text:
        try:
            poem_db.update_body(poem_id, text)
        except poem_db.SupabaseError as e:
            st.session_state.err = str(e)
            return
        st.session_state.overwrite_text = ""


def toggle_target(poem_id):
    """화면 2의 시화 대상 체크칸을 바꾸면 그 편을 대상으로 정하거나 대상에서 뺀다."""
    key = f"target_{poem_id}"
    flag = st.session_state[key]
    try:
        poem_db.update_targets([poem_id], flag)
    except poem_db.SupabaseError as e:
        st.session_state[key] = not flag  # 저장하지 못했으면 체크를 원래대로 돌린다
        st.session_state.err = str(e)
        return
    st.session_state.err = ""


def confirm_poem(poem_id):
    """화면 2의 확인 완료: 본문을 확인했으니 이 편의 잘림 표시를 지운다. 화면은 그대로."""
    try:
        poem_db.mark_checked([poem_id])
    except poem_db.SupabaseError as e:
        st.session_state.err = str(e)
        return
    st.session_state.err = ""


def screen2():
    poems = [p for p in load_or_stop() if not p["삭제됨"]]
    if not poems:
        st.info("아직 넣은 시가 없습니다. '시 넣기'에서 시를 넣어 주세요.")
        return
    # 고른 편이 없거나 사라졌으면 받은날짜가 가장 최근인 편 (목록이 최근 순이라 맨 앞)
    ex = next((p for p in poems if p["id"] == st.session_state.get("sel")), poems[0])
    prompt_text = ex["프롬프트내용"]
    has_prompt = bool(prompt_text)

    st.title(ex["제목"])
    st.write(f"받은날짜 {ex['받은날짜']}")
    st.checkbox("시화 대상", value=ex["대상"], key=f"target_{ex['id']}", on_change=toggle_target, args=(ex["id"],))
    if has_prompt:
        st.caption("대상에서 빼도 이미 만든 프롬프트는 지워지지 않습니다.")
    if ex["잘림"] != "-":
        st.info(f"본문 상태: {ex['잘림']} — 본문을 확인해서 온전하면 '확인 완료'를 눌러 표시를 지워 주세요.")
        st.button("확인 완료", key="confirm", on_click=confirm_poem, args=(ex["id"],))

    st.caption("본문")
    # 드래그로 복사할 수 있고, 상자 오른쪽 위의 복사 아이콘으로 통째로도 복사된다 (프롬프트 상자와 같은 모양)
    st.code(ex["본문"], language=None, wrap_lines=True, height=220)

    st.caption("프롬프트")
    if has_prompt:
        # 글을 드래그해서 복사할 수 있고, 상자 오른쪽 위의 복사 아이콘으로 통째로도 복사된다
        st.code(prompt_text, language=None, wrap_lines=True, height=160)
    else:
        st.text_area("수채화 프롬프트", "", height=160, disabled=True, label_visibility="collapsed")  # 빈 글상자 자리

    st.caption("잘린 본문 덮어쓸 붙여넣기 칸")
    st.text_area(
        "덮어쓸 본문",
        key="overwrite_text",
        placeholder="여기에 온전한 본문 붙여넣기",
        height=100,
        label_visibility="collapsed",
    )

    # 작업 버튼(만들기 · 덮어쓰기 · 파일로 내보내기)은 왼쪽부터, 목록으로는 오른쪽 끝에 놓는다
    left = [1, 1.4] if has_prompt else [1, 1, 1.4]
    cols = st.columns(left + [max(0.2, 5.4 - sum(left)), 1])
    work = cols[: len(left)]
    if not has_prompt:
        # 프롬프트가 없는 편은 만들기가 보인다 (화면을 여는 것만으로는 만들어지지 않는다)
        work.pop(0).button("만들기", key="make", on_click=make_prompt, args=(ex["id"], ex["본문"]), use_container_width=True)
    work[0].button("덮어쓰기", key="overwrite", on_click=overwrite_body, args=(ex["id"],), use_container_width=True)
    # 프롬프트가 없으면 누를 수 없다
    work[1].download_button(
        "파일로 내보내기",
        prompt_only(prompt_text) if has_prompt else "",
        file_name=export_name(ex),
        mime="text/plain",
        key="export",
        disabled=not has_prompt,
        use_container_width=True,
    )
    cols[-1].button("목록으로", key="to_list", on_click=go, args=(3,), use_container_width=True)
    if st.session_state.err:
        st.error(st.session_state.err)
    if st.session_state.get("notice"):
        st.warning(st.session_state.notice)


# ---- 화면 3 · 시 목록 ----
def read_upload(uploaded):
    """고른 파일의 글을 읽는다. 카카오톡 내보내기는 보통 UTF-8, 옛 파일은 cp949. 못 읽으면 None."""
    raw = uploaded.getvalue()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def import_file(uploaded):
    """파일 넣기: 파일 안의 글을 한 편씩 잘라 표에 쌓는다. (종류, 알림 문구)를 돌려준다."""
    if uploaded is None:
        return "error", "카카오톡 대화 파일(.txt)을 먼저 골라 주세요."
    text = read_upload(uploaded)
    if text is None:
        return "error", "파일의 글자를 읽지 못했습니다. 카카오톡에서 내보낸 .txt 파일인지 확인해 주세요."
    result = parse_file(text)
    if not result["poems"]:
        return "warning", f"넣을 시를 찾지 못했습니다 (글이 아니라서 뺀 메시지 {result['skipped']}개)."
    added, already = 0, result["duplicates"]
    with st.spinner("시를 목록에 쌓는 중입니다..."):
        for poem in result["poems"]:
            try:
                poem_db.insert_poem(poem)
                added += 1
            except poem_db.DuplicateError:
                already += 1  # 이미 목록에 있는 편은 기존 것을 두고 새것을 버린다
            except poem_db.SupabaseError as e:
                return "error", f"{added}편을 넣은 뒤 멈췄습니다: {e}"
    note = f"{added}편을 목록에 넣었습니다."
    if already:
        note += f" 이미 있어서 뺀 편 {already}개."
    if result["skipped"]:
        note += f" 글이 아니라서 뺀 메시지 {result['skipped']}개."
    return "success", note


MAX_FAILS_IN_A_ROW = 3  # 이만큼 연달아 실패하면 (키 문제 등) 더 시도하지 않고 멈춘다


def make_batch():
    """시화 프롬프트 생성: 시화 대상 가운데 프롬프트가 없는 편을 한 편씩 만들어 바로 저장한다.
    잘림 표시가 붙은 편은 건너뛰고(잘린 본문으로는 시 전체를 담지 못한다), 실패한 편도 건너뛰고 계속한다.
    (종류, 알림 문구)를 돌려준다."""
    try:
        poems = poem_db.fetch_poems()
    except poem_db.SupabaseError as e:
        return "error", str(e)
    targets = [p for p in poems if p["대상"] and not p["삭제됨"]]
    if not targets:
        return "warning", "시화 대상으로 정한 편이 없습니다. 줄 앞 체크칸으로 고른 뒤 '시화 대상 선택'을 눌러 주세요."
    have = [p for p in targets if p["프롬프트내용"]]
    cut = [p for p in targets if not p["프롬프트내용"] and p["잘림"] == "잘림"]
    todo = [p for p in targets if not p["프롬프트내용"] and p["잘림"] != "잘림"]
    done = failed = streak = 0
    first_error = ""
    paid = False
    with st.spinner("프롬프트를 한 편씩 만드는 중입니다..."):
        for p in todo:
            if streak >= MAX_FAILS_IN_A_ROW:
                break
            try:
                text, tier = prompt_maker.make_prompt(p["본문"])
                poem_db.update_prompt(p["id"], text)
            except (prompt_maker.PromptError, poem_db.SupabaseError) as e:
                failed += 1
                streak += 1
                first_error = first_error or str(e)[:120]
                continue
            streak = 0
            done += 1
            paid = paid or tier == "유료"
    note = f"대상 {len(targets)}편 중 {done}편의 프롬프트를 만들어 저장했습니다."
    if have:
        note += f" 이미 있어서 건너뛴 편 {len(have)}개."
    if cut:
        note += f" 본문이 잘린 편 {len(cut)}개는 건너뛰었습니다 ('시 한 편'에서 온전한 본문으로 덮어쓴 뒤 다시 눌러 주세요)."
    if failed:
        note += f" 실패 {failed}편 (프롬프트 칸이 '대기'로 남아 있습니다): {first_error}"
    untried = len(todo) - done - failed
    if untried:
        note += f" 연달아 실패해서 나머지 {untried}편은 시도하지 않고 멈췄습니다."
    if paid:
        note += " 무료 키가 안 돼서 유료 키가 쓰였습니다 (요금이 나옵니다)."
    return ("success" if not (failed or untried or cut) else "warning"), note


def set_targets(flag):
    """고르기 칸에 체크한 편을 시화 대상으로 정하거나(True) 대상에서 뺀다(False).
    대상에서 빼도 이미 만든 프롬프트는 지워지지 않는다. (종류, 알림 문구)를 돌려준다."""
    try:
        poems = poem_db.fetch_poems()
        picked = [p for p in poems if st.session_state.get(f"pick{p['id']}") and not p["삭제됨"]]
        if not picked:
            return "warning", "줄 앞 체크칸에서 먼저 편을 골라 주세요."
        changing = [p for p in picked if p["대상"] != flag]
        poem_db.update_targets([p["id"] for p in changing], flag)
    except poem_db.SupabaseError as e:
        return "error", str(e)
    for p in picked:
        st.session_state[f"pick{p['id']}"] = False  # 처리한 편은 체크를 푼다
    same = len(picked) - len(changing)
    if flag:
        note = f"{len(changing)}편을 시화 대상으로 정했습니다."
        if same:
            note += f" 이미 대상이었던 편 {same}개."
    else:
        note = f"{len(changing)}편을 시화 대상에서 뺐습니다. 이미 만든 프롬프트는 그대로 남아 있습니다."
        if same:
            note += f" 원래 대상이 아니었던 편 {same}개."
    return "success", note


def set_checked():
    """고르기 칸에 체크한 편의 잘림 표시('확인 필요'·'잘림')를 확인 완료로 지운다. (종류, 알림 문구)를 돌려준다."""
    try:
        poems = poem_db.fetch_poems()
        picked = [p for p in poems if st.session_state.get(f"pick{p['id']}") and not p["삭제됨"]]
        if not picked:
            return "warning", "줄 앞 체크칸에서 먼저 편을 골라 주세요."
        marked = [p for p in picked if p["잘림"] != "-"]
        poem_db.mark_checked([p["id"] for p in marked])
    except poem_db.SupabaseError as e:
        return "error", str(e)
    for p in picked:
        st.session_state[f"pick{p['id']}"] = False  # 처리한 편은 체크를 푼다
    note = f"{len(marked)}편의 잘림 표시를 확인 완료로 지웠습니다."
    if len(picked) > len(marked):
        note += f" 원래 표시가 없던 편 {len(picked) - len(marked)}개."
    return "success", note


def set_deleted(flag):
    """고르기 칸에 체크한 편을 목록에서 삭제하거나(True) 되살린다(False). 표에서 지우지 않고 숨기기만 한다.
    (종류, 알림 문구)를 돌려준다."""
    try:
        poems = poem_db.fetch_poems()
        picked = [p for p in poems if st.session_state.get(f"pick{p['id']}") and p["삭제됨"] != flag]
        if not picked:
            return "warning", "줄 앞 체크칸에서 먼저 편을 골라 주세요."
        poem_db.update_deleted([p["id"] for p in picked], flag)
    except poem_db.SupabaseError as e:
        return "error", str(e)
    for p in picked:
        st.session_state[f"pick{p['id']}"] = False  # 처리한 편은 체크를 푼다
    if flag:
        note = f"{len(picked)}편을 목록에서 삭제했습니다. 보기에서 '삭제한 시'를 고르면 되살릴 수 있습니다."
        with_prompt = sum(1 for p in picked if p["프롬프트내용"])
        if with_prompt:
            note += f" (만든 프롬프트가 있는 편 {with_prompt}개 포함 — 프롬프트도 함께 숨겨집니다.)"
    else:
        note = f"{len(picked)}편을 되살렸습니다."
    return "success", note


def shiwha_label(p):
    """목록의 시화 칸: 시화로 만들 편(대상)인지 아닌지."""
    return "대상" if p["대상"] else "대상 아님"


def prompt_label(p):
    """목록의 프롬프트 칸: 프롬프트가 만들어져 있으면 완료, 대상인데 아직이면 대기, 대상도 아니고 없으면 -."""
    if p["프롬프트내용"]:
        return "완료"
    return "대기" if p["대상"] else "-"


def center(col, text, bold=False):
    """목록 칸의 글을 가운데 정렬로 보여 준다."""
    text = html.escape(str(text))
    col.markdown(f'<div style="text-align:center">{"<b>" + text + "</b>" if bold else text}</div>', unsafe_allow_html=True)


BUTTON_COLS = [1, 1.3, 1.4, 1.3]  # 화면 3 버튼 두 줄의 칸 너비 (셋째 칸에 "삭제 취소 (되살리기)", 둘째 칸에 "시화 프롬프트 생성"이 한 줄로 들어가는 너비)


def screen3():
    st.title("시 목록")

    st.caption("카카오톡 대화 파일 고르기")
    uploaded = st.file_uploader("카카오톡 대화 파일", type=["txt"], label_visibility="collapsed")

    # 버튼 두 줄은 같은 칸 너비(BUTTON_COLS)를 쓰고 버튼을 칸 가득 채워서, 줄과 열이 반듯하게 맞는다
    # 윗줄: 시를 넣고 내보내는 버튼 / 아랫줄: 고른 시를 시화로 만드는 버튼
    c1, c2, c3, c4 = st.columns(BUTTON_COLS)
    export_slot = c3.empty()  # 내려받기 버튼은 아래에서 목록을 불러온 뒤 채운다
    backup_slot = c4.empty()
    # 아래 목록은 이 뒤에 불러와서, 새로 쌓이거나 바뀐 것이 바로 보인다
    if c1.button("파일 넣기", key="file_in", use_container_width=True):
        st.session_state.list_result = import_file(uploaded)
    c2.button("시 한 편 넣기", key="poem_in", on_click=go, args=(1,), use_container_width=True)

    # 시화 대상에서 빼는 일은 화면 2의 '시화 대상' 체크를 풀어서 한다
    d1, d2, d3, d4 = st.columns(BUTTON_COLS)
    if d1.button("시화 대상 선택", key="target_on", use_container_width=True):
        st.session_state.list_result = set_targets(True)
    if d2.button("시화 프롬프트 생성", key="batch_make", use_container_width=True):
        st.session_state.list_result = make_batch()
    if d3.button("잘림 확인 완료", key="mark_checked", use_container_width=True):
        st.session_state.list_result = set_checked()
    if st.session_state.get("view_filter") == "삭제한 시":  # 삭제한 시를 보는 중이면 삭제 대신 되살리기
        if d4.button("삭제 취소 (되살리기)", key="undelete", use_container_width=True):
            st.session_state.list_result = set_deleted(False)
    elif d4.button("선택한 시 삭제", key="delete", use_container_width=True):
        st.session_state.list_result = set_deleted(True)

    kind, note = st.session_state.get("list_result") or (None, "")
    if kind:
        getattr(st, kind)(note)

    # 받은날짜 최근 순 (와이어프레임과 같게) — 표에서 가져올 때 이미 정렬되어 있다
    all_poems = load_or_stop()
    poems = [p for p in all_poems if not p["삭제됨"]]  # 삭제한 시는 '삭제한 시' 보기에서만 보인다
    deleted = len(all_poems) - len(poems)
    targets = [p for p in poems if p["대상"]]
    made = sum(1 for p in targets if p["프롬프트내용"])
    status = f"전체 {len(poems)}편 · 시화 대상 {len(targets)}편 (프롬프트 완료 {made} · 대기 {len(targets) - made})"
    # 현황 줄은 "시 목록" 제목(44px)의 절반 크기(22px)로, 굵게 보여 준다
    st.markdown(
        f'<div style="font-size:22px;font-weight:700;line-height:1.4;margin-bottom:12px">'
        f'{status}{f" · 삭제한 시 {deleted}편" if deleted else ""}</div>',
        unsafe_allow_html=True,
    )

    # 고른 편 가운데 프롬프트가 있는 편을 압축 파일 하나로 내려받는다
    picked_items = []
    for p in poems:
        text = p["프롬프트내용"]
        if st.session_state.get(f"pick{p['id']}") and text:
            picked_items.append((p, text))
    export_slot.download_button(
        f"선택한 시 내려받기 ({len(picked_items)}편)",
        export_zip(picked_items) if picked_items else b"",
        file_name=f"시화프롬프트_{datetime.now():%Y-%m-%d}.zip",
        mime="application/zip",
        key="export_zip",
        disabled=not picked_items,
        use_container_width=True,
    )
    # 전체 백업: 고른 것과 상관없이 삭제한 시까지 모든 시와 프롬프트를 CSV 하나로 내려받는다
    backup_slot.download_button(
        "전체 백업 내려받기",
        backup_csv(all_poems),
        file_name=f"시_백업_{datetime.now():%Y-%m-%d}.csv",
        mime="text/csv",
        key="backup_csv",
        use_container_width=True,
    )

    # 목록 위 조건 영역은 세 묶음(보기 · 찾기 · 연도/월)으로 나누고, 묶음마다 테두리 상자로 구분한다
    # 맨 위는 연도 · 월 상자다. 자리만 먼저 잡아 두고, 안의 내용은 아래에서 조건에 맞는 시를 가린 뒤 채운다
    # 세로 길이를 줄이려고 상자 제목 줄은 두지 않는다 (상자의 내용이 곧 이름이다)
    date_box = st.container(border=True)
    see_box = st.container(border=True)
    v1, v2 = see_box.columns([3, 2.4])
    view = v1.radio("시화", ["전체", "대상만", "대상 아님", "삭제한 시"], horizontal=True, key="view_filter")
    prompt_view = v2.radio("프롬프트", ["전체", "완료", "대기", "-"], horizontal=True, key="prompt_filter")
    find_box = st.container(border=True)
    q1, q2, q3 = find_box.columns([2.6, 1.8, 2], vertical_alignment="center")
    query = q1.text_input("제목 찾기", key="title_query", placeholder="제목 찾기 (일부만 써도 됩니다)", label_visibility="collapsed")
    order = q2.radio("정렬", ["최근 순", "오래된 순"], horizontal=True, key="sort_order", label_visibility="collapsed")
    hide_cut = q3.checkbox("잘림 · 확인 필요 숨기기", key="hide_cut")
    pool = [p for p in all_poems if p["삭제됨"]] if view == "삭제한 시" else poems
    base = [
        p for p in pool
        if (view in ("전체", "삭제한 시") or p["대상"] == (view == "대상만"))
        and (prompt_view == "전체" or prompt_label(p) == prompt_view)
        and query.strip() in p["제목"]
        and not (hide_cut and p["잘림"] != "-")
    ]

    # 월별 탭으로 나누어 보기: 위의 조건에 맞는 시를 받은날짜의 월로 묶고, 처음에는 시가 있는 가장 최근 달이 열린다.
    # 연도를 먼저 고른다 (1월~12월 탭은 한 해 안에서만 나눈다). 2026~2028년은 시가 없어도 항상 보인다
    data_years = {p["받은날짜"][:4] for p in base}
    year_options = sorted({"2026", "2027", "2028"} | data_years)
    if st.session_state.get("year_filter") not in year_options:
        st.session_state.pop("year_filter", None)  # 조건을 바꿔서 사라진 연도가 골라져 있으면 처음 상태로
    year = date_box.radio(
        "연도",
        year_options,
        index=year_options.index(max(data_years)) if data_years else 0,  # 처음에는 시가 있는 가장 최근 연도
        horizontal=True,
        label_visibility="collapsed",
        key="year_filter",
        format_func=lambda y: f"{y}년",
    )
    by_month = {m: [p for p in base if p["받은날짜"][:4] == year and int(p["받은날짜"][5:7]) == m] for m in range(1, 13)}
    latest = max((m for m, rows in by_month.items() if rows), default=1)

    # 맨 앞의 좁은 칸은 여러 편을 고르는 체크칸이다 (정보 칸이 아니라서 목록 칸 5개에 세지 않는다)
    widths = [0.35, 1.0, 4.2, 0.8, 0.9, 0.9, 0.8]  # 제목 칸을 가장 넓게 (칸 사이 간격은 4px)

    if not all_poems:
        date_box.info("아직 넣은 시가 없습니다.")
    elif not base:
        date_box.info("조건에 맞는 시가 없습니다.")
    # 월 탭은 맨 위 상자에 두고 탭 안은 비워 둔다. 열린 탭의 월만 아래 목록에 보인다
    tabs = date_box.tabs([f"{m}월" for m in range(1, 13)], default=f"{latest}월", key="month_tabs", on_change="rerun")
    month = next((m for m, tab in zip(range(1, 13), tabs) if tab.open), latest)

    # 다른 달의 체크 표시는 목록에 그려지지 않아도 지워지지 않게 붙들어 둔다
    for p in base:
        key = f"pick{p['id']}"
        if p not in by_month[month] and key in st.session_state:
            st.session_state[key] = st.session_state[key]

    # 같은 날짜는 넣은 순서(번호)로 가른다. 편수는 월 탭 바로 아래(연도 · 월 상자 안)에 보인다
    rows = sorted(by_month[month], key=lambda p: (p["받은날짜"], p["id"]), reverse=(order == "최근 순"))
    # 편수는 열린 월 탭 글자 바로 아래에 굵게 붙인다 (탭 글자 밑에 덧붙는 글로 그린다)
    date_box.markdown(
        '<style>.st-key-month_tabs div{overflow:visible !important}'
        '.st-key-month_tabs [role="tablist"]::after{display:none !important}'  # 월 탭 아래 회색 줄은 없앤다
        '.st-key-month_tabs [role="tab"][aria-selected="true"]{position:relative}'
        '.st-key-month_tabs [role="tab"][aria-selected="true"]::after{'
        'position:absolute;top:100%;left:50%;transform:translateX(-50%);margin-top:6px;white-space:nowrap;font-weight:700;'
        f'content:"{len(rows)}편"}}</style>',
        unsafe_allow_html=True,
    )
    if not rows:
        st.caption(f"{month}월에는 조건에 맞는 시가 없습니다.")
    else:
        # 열 이름은 굵게, 이름과 아래 줄 사이는 좁게 붙인다
        with st.container(gap=None, key="poem_head"):
            head = st.columns(widths, gap="xxsmall")
            for col, name in zip(head[1:], ["받은날짜", "제목", "작가", "잘림", "시화", "프롬프트"]):
                center(col, name, bold=True)  # 열 이름은 모두 가운데 정렬 (값은 제목만 왼쪽)
            # 열 이름과 첫 줄 사이 간격 (구분선은 없다). 같은 자리에 목록 모양 설정(스타일)도 둔다
            st.markdown(
                "<div style='height:36px'></div><style>"
                ".mob-only{display:none}"
                # 받은날짜와 제목 사이를 넓히려고 제목 버튼을 오른쪽으로 32px 민다
                "[class*='st-key-row']{margin-left:32px}"
                # 휴대폰(폭 640px 이하): 열 이름 줄은 감추고, 한 줄을 [체크 · 날짜와 상태 · 제목] 세 칸으로 줄인다
                "@media (max-width: 640px){"
                ".st-key-poem_head{display:none}"
                ".st-key-poem_rows [data-testid='stHorizontalBlock']{flex-wrap:nowrap !important}"
                ".st-key-poem_rows [data-testid='stColumn']{min-width:0 !important}"
                ".st-key-poem_rows [data-testid='stColumn']:nth-child(n+4){display:none !important}"
                "[class*='st-key-row']{margin-left:6px !important}"
                ".mob-only{display:block !important;font-size:12px;opacity:.75}"
                "}</style>",
                unsafe_allow_html=True,
            )
        with st.container(key="poem_rows"):
            for p in rows:
                cols = st.columns(widths, gap="xxsmall")
                cols[0].checkbox("고르기", key=f"pick{p['id']}", label_visibility="collapsed")
                # 연 · 월은 위의 탭에 있으니 월-일만. 휴대폰에서는 감춘 칸의 내용(시화 · 프롬프트 · 잘림)을 날짜 아래 작은 글씨로 보여 준다
                status = " · ".join([shiwha_label(p)] + ([prompt_label(p)] if prompt_label(p) != "-" else []) + ([p["잘림"]] if p["잘림"] != "-" else []))
                cols[1].markdown(
                    f'<div style="text-align:center">{html.escape(p["받은날짜"][5:])}'
                    f'<span class="mob-only">{html.escape(status)}</span></div>',
                    unsafe_allow_html=True,
                )
                if p["삭제됨"]:
                    cols[2].write(p["제목"])  # 삭제한 시는 열 수 없다 (되살린 뒤에 연다)
                else:
                    cols[2].button(p["제목"], key=f"row{p['id']}", on_click=open_poem, args=(p["id"],))
                center(cols[3], p["작가"])
                center(cols[4], p["잘림"])
                center(cols[5], shiwha_label(p))
                center(cols[6], prompt_label(p))


# ---- 공통: 맨 위 안내 + 화면 이동 ----
n1, n2, n3 = st.columns(3)
n1.button("시 넣기", key="nav1", on_click=go, args=(1,), use_container_width=True)
n2.button("시 한 편", key="nav2", on_click=go, args=(2,), use_container_width=True)
n3.button("시 목록", key="nav3", on_click=go, args=(3,), use_container_width=True)

admin = is_admin()
if admin:
    st.sidebar.button("관리", key="nav_admin", on_click=go, args=(4,), use_container_width=True)
elif st.session_state.screen == 4:
    st.session_state.screen = 3  # 관리자가 아니면 관리 화면 대신 시 목록으로


screens = {1: screen1, 2: screen2, 3: screen3}
if admin:
    screens[4] = screen4  # 관리자일 때만 관리 화면을 화면 목록에 올린다
screens[st.session_state.screen]()

# ---- 맨 아래 저작권 한 줄 ----
st.caption(
    '<div style="text-align:right">© 2026 시화 프롬프트 생성 웹앱</div>',
    unsafe_allow_html=True,
)
