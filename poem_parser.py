"""카카오톡 메시지를 받은날짜 / 제목 / 작가 / 본문 / 글끝날짜 / 잘림으로 나눈다.

parse_message : 메시지 한 편을 나눈다 (화면 1).
parse_file    : 카카오톡에서 내보낸 대화 파일 전체를 한 편씩 잘라 나눈다 (화면 3 파일 넣기).
"""
import re
from collections import Counter

OBJECT_CHAR = chr(0xFFFC)  # 사진 자리에 찍히는 보이지 않는 글자 (카카오톡에서 복사하면 섞여 들어온다)

# 맨 앞 줄: "2026년 1월 22일 오전 9:10, 보낸사람 :     제목 /작가"  (글 내용이 다음 줄부터 시작하기도 한다)
HEADER = re.compile(
    r"^\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(?:오전|오후)\s*\d{1,2}:\d{2},\s*(.+?)\s:\s*(.*)$"
)
# 글 맨 끝 날짜 서명: "2026. 9. 12." (뒤에 ", 읽지않음" 같은 말이 붙기도 한다)
END_DATE = re.compile(r"(?:^|\s)(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?(?:\s*,[^\n]*)?\s*$")
# 서명 뒤에 딸려 붙는 찌꺼기 줄: " 1, 오후 1시45분" / "63 14 14"
JUNK_TAIL = re.compile(r"^\s*\d+,\s*(?:오전|오후)\s*\d+시\s*\d+분\s*$|^[\d\s]+$")

# 파일 안에 끼어 있는 날짜 구분선·삭제 안내·입장 안내 줄 (글이 아니라서 버린다)
SKIP_LINE = re.compile(
    r"^[-\s]*\d{4}년\s*\d{1,2}월\s*\d{1,2}일\s*(?:[월화수목금토일]요일|(?:오전|오후)\s*\d{1,2}:\d{2})?[-\s]*$"
    r"|^메시지가 삭제되었습니다\.?$|님이 (?:들어왔|나갔)습니다\.$|님을 초대했습니다\.$"
)
# "제목 /작가" 모양의 줄 (제목 /작가 사이 띄어쓰기는 있어도 없어도 된다)
TITLE_FORM = re.compile(r"^(?P<title>[^/]{1,100}?)\s*/\s*(?P<author>[^/]{0,30}?)\s*$")
# 제목 줄 바로 아래에 따로 적힌 작가: "/송ㅇㅇ" 또는 "**송ㅇㅇ**"
AUTHOR_SLASH_LINE = re.compile(r"^[^/\s]{0,4}\s*/\s*\**[^/*\s]{1,20}\**$")  # 제목 끝이 줄바꿈으로 넘어온 ") /송ㅇㅇ"도 허용
AUTHOR_STAR_LINE = re.compile(r"^\*\*[^*]{1,20}\*\*$")
# 제목 줄 끝에 별표로 작가가 붙은 모양: "제목 **송ㅇㅇ**"
TITLE_STAR_END = re.compile(r"^(?P<title>.+?)\s*\*\*(?P<author>[^*]{1,20})\*\*\s*$")
# 글이 아닌 메시지: 사진·동영상·이모티콘·파일
NOT_A_POEM = re.compile(r"^(?:사진(?: \d+장)?|동영상|이모티콘|음성메시지|파일:.*)$")

LENGTH_NEAR_CUT = 450  # 카톡 "전체보기" 잘림 지점 언저리 (실제 내보내기 파일에서 본문이 약 500자에서 잘렸다)
SHORT_TALK_MAX = 40  # 제목 줄이 없는 메시지가 이 글자 수보다 짧으면 안부 대화로 본다
SLASHLESS_MIN = 200  # 시인이 따로 정해진 파일에서, 제목 줄이 없는 글을 글로 인정하는 최소 글자 수
SENTENCE_ENDS = ".?!…\"'”’)"


def _iso(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _split_signature(body):
    """본문 맨 끝의 날짜 서명을 떼어 (본문, 글끝날짜)로 돌려준다. 없으면 글끝날짜는 빈 글자."""
    lines = body.rstrip().split("\n")
    while lines and JUNK_TAIL.match(lines[-1]):
        lines.pop()
    if not lines:
        return "", ""
    sig = END_DATE.search(lines[-1])
    if not sig:
        return "\n".join(lines).strip(), ""
    lines[-1] = lines[-1][: sig.start()].rstrip()
    return "\n".join(lines).strip(), _iso(*sig.groups())


def _build(iso_date, title_line, body_lines):
    """첫 줄(제목 /작가)과 그 아래 줄들로 시 한 편(dict)을 만든다."""
    # 제목은 첫 번째 "/" 앞, 작가는 뒤 (**굵게** 표기도 작가로 본다)
    title, _, author = title_line.partition("/")
    title = title.strip()
    author = author.replace("*", "").strip()

    # 글끝날짜 서명이 있으면 본문에서 떼어 따로 보관 (있을 때만 글끝 적용)
    body, end_date = _split_signature("\n".join(body_lines))

    # 잘림 판정: 세 조건 모두 → 잘림, 하나 또는 둘 → 확인 필요
    hits = [
        len(body) >= LENGTH_NEAR_CUT,
        not end_date,
        bool(body) and body[-1] not in SENTENCE_ENDS,
    ]
    count = sum(hits)
    cut = "잘림" if count == 3 else "확인 필요" if count else "-"

    return {
        "받은날짜": iso_date,
        "제목": title,
        "작가": author,
        "본문": body,
        "글끝날짜": end_date,
        "잘림": cut,
        "맞은조건": {"길이": hits[0], "글끝날짜없음": hits[1], "마침표없음": hits[2]},
    }


def _is_link(line):
    return "http://" in line or "https://" in line or "www." in line


def _head(lines):
    """한 글의 줄들에서 (종류, 제목 /작가 줄, 본문 줄들)을 가려낸다.

    종류: "title" = 제목 /작가 줄이 있다, "plain" = 제목 줄 없이 그냥 쓴 글.
    제목 줄이 두 줄에 걸친 경우("제목" 다음 줄 "/작가", 또는 "제목" 다음 줄 "**작가**")도 알아본다.
    """
    lines = list(lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "plain", "", []
    first = lines[0].strip()
    nxt = lines[1].strip() if len(lines) > 1 else ""
    if not _is_link(first):
        form = TITLE_FORM.match(first)
        if form and form.group("author").replace("*", "").strip():
            return "title", first, lines[1:]
        star_end = TITLE_STAR_END.match(first)
        if star_end:
            return "title", f"{star_end.group('title')} /{star_end.group('author')}", lines[1:]
        if nxt and AUTHOR_SLASH_LINE.match(nxt):
            return "title", first + nxt, lines[2:]
        if nxt and AUTHOR_STAR_LINE.match(nxt):
            return "title", first + " /" + nxt, lines[2:]
    return "plain", first, lines[1:]


def parse_message(text):
    """분석 결과를 dict로 돌려준다. 맨 앞 줄이 카카오톡 모양이 아니면 None."""
    lines = text.replace(OBJECT_CHAR, "").strip().splitlines()
    if not lines:
        return None
    head = HEADER.match(lines[0])
    if not head:
        return None
    y, m, d, _sender, first = head.groups()
    _kind, title_line, body = _head([first] + lines[1:])
    return _build(_iso(y, m, d), title_line, body)


# ---- 대화 파일 전체 ----
def _split_messages(text):
    """파일을 맨 앞 줄(날짜 · 보낸 사람)이 나올 때마다 잘라 메시지 목록으로 만든다."""
    messages = []
    for line in text.replace(OBJECT_CHAR, "").splitlines():  # OBJECT_CHAR: 사진 자리에 찍히는 보이지 않는 표시
        head = HEADER.match(line)
        if head:
            y, m, d, sender, first = head.groups()
            messages.append({"date": _iso(y, m, d), "sender": sender.strip(), "lines": [first]})
        elif messages and not SKIP_LINE.search(line.strip()):
            messages[-1]["lines"].append(line)  # 맨 앞 줄이 없는 줄은 앞 메시지에 이어 붙는다
    return messages


def _split_by_title(lines, known_authors):
    """한 메시지 안에 (빈 줄 다음) 제목/작가 줄이 다시 나오면 거기서부터 다른 글로 나눈다.
    작가 이름이 이 파일의 다른 글에서 이미 본 작가일 때만 새 글의 시작으로 본다."""
    starts = [0]
    for i in range(1, len(lines)):
        line = lines[i].strip()
        form = TITLE_FORM.match(line)
        if not form or _is_link(line) or lines[i - 1].strip():
            continue
        if form.group("author").replace("*", "").strip() in known_authors:
            starts.append(i)
    return [lines[a:b] for a, b in zip(starts, starts[1:] + [len(lines)])]


def _is_poem(kind, lines, has_poet):
    """사진 · 동영상 · 링크 · 짧은 안부 대화가 아니면 글로 본다."""
    first = lines[0].strip() if lines else ""
    if not first or NOT_A_POEM.match(first):
        return False
    words = " ".join(lines).split()
    if words and all(w.lower().startswith(("http://", "https://", "www.")) for w in words):
        return False  # 링크만 있는 메시지
    if kind == "title":
        return True
    if _is_link(first):
        return False  # 글 설명과 링크가 한 줄에 붙은 메시지
    size = len("\n".join(lines).strip())
    return size >= (SLASHLESS_MIN if has_poet else SHORT_TALK_MAX)


def parse_file(text):
    """카카오톡 대화 파일 글을 시 목록으로 나눈다.

    대화 상대가 여럿이면, "제목 /작가" 줄을 가장 많이 보낸 사람을 시인으로 보고 그 사람의 글만 본다.
    돌려주는 값: {"poems": 시 목록(dict), "skipped": 글이 아니라 뺀 수, "duplicates": 중복이라 뺀 수}
    """
    messages = _split_messages(text)

    # 1차: 어떤 사람이 "제목 /작가" 줄로 글을 보내는지, 작가 이름은 무엇인지 모은다
    senders, known_authors = Counter(), set()
    for message in messages:
        kind, title_line, _ = _head(message["lines"])
        if kind == "title":
            senders[message["sender"]] += 1
            known_authors.add(title_line.partition("/")[2].replace("*", "").strip())
    poet = senders.most_common(1)[0][0] if senders else None

    # 2차: 한 편씩 자르고 글이 아닌 것을 거른다
    poems, seen = [], set()
    skipped = duplicates = 0
    for message in messages:
        if poet and message["sender"] != poet:
            skipped += 1  # 시인이 아닌 사람의 대화
            continue
        lines = list(message["lines"])
        while lines and not lines[0].strip():
            lines.pop(0)
        for chunk in _split_by_title(lines, known_authors):
            kind, title_line, body = _head(chunk)
            if not _is_poem(kind, chunk if kind == "plain" else [title_line], bool(poet)):
                skipped += 1
                continue
            poem = _build(message["date"], title_line, body)
            key = (poem["받은날짜"], poem["제목"])
            if key in seen:  # 제목과 받은날짜가 같으면 나중 것을 중복으로 본다
                duplicates += 1
                continue
            seen.add(key)
            poems.append(poem)
    return {"poems": poems, "skipped": skipped, "duplicates": duplicates}
