"""시 본문을 Gemini API에 보내 수채화 삽화 프롬프트를 받아 온다.

보내는 것은 시 본문뿐이다 (제목·작가·날짜 등은 보내지 않는다).
AI는 시의 장면만 쓰고, 수채화 스타일 문장은 모든 프롬프트에 똑같이 코드가 붙인다 (STYLE_HEAD · STYLE_TAIL).
키는 .env에서 읽는다 (코드에 적지 않음):
  GEMINI_API_KEY       무료 등급 키. 먼저 이것으로 FREE_TRIES번 시도한다.
  GEMINI_API_KEY_PAID  유료 등급 키(선택). 무료 키가 계속 안 될 때만 이것으로 바꿔 시도한다.
모델을 바꾸고 싶으면 .env에 GEMINI_MODEL=모델이름 한 줄을 더하면 된다.
"""
import json
import os
import time
import urllib.error
import urllib.request

import poem_db

DEFAULT_MODEL = "gemini-3.6-flash"  # stable 모델. 3.8-flash는 시험 때 '서비스 이용 불가(503)'가 나서 뺐다
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FREE_TRIES = 3  # 무료 키로 시도하는 횟수 (이만큼 안 되면 유료 키로 바꾼다)
PAID_TRIES = 2

# 모든 프롬프트에 똑같이 붙는 고정 문장. 스타일(수채화)은 AI가 매번 새로 쓰지 않고 여기서만 정한다 — 일관성을 위해서다.
STYLE_HEAD = (
    "Soft watercolor painting with gentle pigment bleeds, translucent washes, "
    "visible paper texture, a muted natural palette and generous white space."
)
STYLE_TAIL = "No text, letters, captions or signatures in the image. No identifiable real people."

SYSTEM = """You write the scene part of image-generation prompts for a poetry-book illustrator.
You will receive the full text of one Korean poem. Describe ONE scene for an illustration of it.

Rules:
- Depict the poem's central imagery and emotional mood as a single concrete scene. Use the natural, everyday objects and settings that appear in the poem; do not invent unrelated elements.
- Do NOT mention the painting style, medium, texture, colour palette, text or signatures. A fixed style sentence is added by the program.
- The scene is in English, one paragraph, 30-70 words.

Output format - exactly two parts separated by one blank line, nothing else:
1) the English scene
2) one Korean line that starts with "요약: " and says what the picture shows."""

SUMMARY_MARK = "\n\n요약:"


class PromptError(Exception):
    """프롬프트를 만들지 못한 이유. 메시지는 화면에 그대로 보여 줘도 되는 말."""


class _TryAgain(PromptError):
    """한도 초과·서비스 바쁨·시간 초과처럼 다시 해 보면 될 수도 있는 실패."""


class _BadKey(PromptError):
    """키가 올바르지 않다."""


def _ask(key, model, body):
    """키 하나로 한 번 물어본다. 성공하면 프롬프트 글, 실패하면 PromptError 중 하나."""
    req = urllib.request.Request(
        ENDPOINT.format(model=model),
        method="POST",
        data=json.dumps(
            {
                "systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": body}]}],
                "generationConfig": {"maxOutputTokens": 4000},
            }
        ).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code in (400, 401, 403) and "API key" in detail:
            raise _BadKey("키가 올바르지 않습니다.") from e
        if e.code == 429:
            raise _TryAgain("사용 한도를 넘었습니다.") from e
        if e.code in (500, 503):
            raise _TryAgain("AI 서비스가 바쁩니다.") from e
        if e.code == 404:
            raise PromptError(f"모델 '{model}'을 찾을 수 없습니다. .env의 GEMINI_MODEL을 확인해 주세요.") from e
        raise PromptError(f"AI 서비스 오류 {e.code}: {detail[:300]}") from e
    except TimeoutError as e:  # 답을 기다리다 60초가 지난 경우
        raise _TryAgain("시간 안에 답하지 않았습니다.") from e
    except urllib.error.URLError as e:
        raise _TryAgain(f"연결하지 못했습니다: {e.reason}") from e

    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "알 수 없음")
        raise PromptError(f"AI가 이 시로는 프롬프트를 만들어 주지 않았습니다 (사유: {reason}).")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise PromptError(f"AI가 빈 답을 보냈습니다 (종료 사유: {candidates[0].get('finishReason', '?')}). 다시 눌러 주세요.")
    return text


def compose(raw):
    """AI가 보낸 '장면 + 요약' 글에 고정 스타일 문장을 앞뒤로 붙여 최종 프롬프트로 만든다.
    '요약:' 줄이 빠져 왔으면 장면만으로 만든다."""
    scene, mark, summary = raw.partition(SUMMARY_MARK)
    prompt = f"{STYLE_HEAD} {scene.strip()} {STYLE_TAIL}"
    return prompt + (mark + summary.rstrip() if mark else "")


def _try_key(key, model, body, tries):
    """한 키로 tries번까지 시도한다. 성공하면 글, 계속 안 되면 마지막 실패를 던진다."""
    for i in range(tries):
        try:
            return _ask(key, model, body)
        except _BadKey:
            raise  # 키가 틀렸으면 되풀이해도 소용없다
        except _TryAgain:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))  # 2초, 4초 쉬었다가 다시


def make_prompt(body):
    """시 본문(body)으로 프롬프트를 만든다. (글, "무료" 또는 "유료")를 돌려주고, 실패하면 PromptError.

    무료 키로 FREE_TRIES번 해 보고 안 되면, 유료 키가 있을 때만 유료 키로 바꿔 시도한다.
    """
    poem_db.load_env()
    free = os.environ.get("GEMINI_API_KEY", "")
    paid = os.environ.get("GEMINI_API_KEY_PAID", "")
    if not free and not paid:
        raise PromptError(".env에 GEMINI_API_KEY 값을 먼저 채워 주세요.")
    model = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL

    free_error = None
    if free:
        try:
            return compose(_try_key(free, model, body, FREE_TRIES)), "무료"
        except (_BadKey, _TryAgain) as e:
            free_error = e
    if not paid:
        raise PromptError(f"무료 키: {free_error}") from free_error
    try:
        return compose(_try_key(paid, model, body, PAID_TRIES)), "유료"
    except (_BadKey, _TryAgain) as e:
        prefix = f"무료 키: {free_error} / " if free_error else ""
        raise PromptError(f"{prefix}유료 키: {e}") from e
