# 시화 프롬프트 제작

시를 한 편씩 저장하고 관리하면서, 시마다 수채화 시화 프롬프트를 일관된 스타일로 만들어 주는 Streamlit 앱입니다.
이미지를 만들거나 저장하는 일은 하지 않습니다. 만든 프롬프트는 복사해서 다른 그림 도구에 붙여 씁니다.

## 하는 일

- 시를 한 편씩 붙여넣거나 카카오톡 대화 내보내기 파일에서 한꺼번에 가져와 목록으로 쌓기
- 본문이 잘린 것으로 보이는 시 표시, 온전한 본문으로 덮어쓰기
- 시화로 만들 시를 고르고, 고른 시마다 Gemini API로 프롬프트 만들기 (수채화 스타일 문장은 앱이 똑같이 붙임)
- 목록을 연도 · 월로 나눠 보고, 정렬 · 걸러 보기 · 제목 찾기
- 프롬프트 파일(한 편 / 여러 편 압축)과 전체 백업(CSV) 내려받기
- 비밀번호를 입력해야 시와 프롬프트가 보이는 화면

## 쓰는 법

1. `pip install -r requirements.txt`
2. Supabase에 표 만들기: `supabase_setup.sql`을 SQL Editor에서 실행합니다 (그 뒤 `supabase_lock.sql`로 공개 권한을 닫습니다).
3. 설정(환경변수)을 채웁니다. 이름만 적습니다. 값은 `.env` 파일이나 배포 서비스의 Secrets에 넣고 저장소에는 올리지 않습니다.
   - `SUPABASE_URL`, `SUPABASE_SECRET_KEY` — 시를 저장하는 Supabase 접속 정보
   - `GEMINI_API_KEY` (선택: `GEMINI_API_KEY_PAID`, `GEMINI_MODEL`) — 프롬프트를 만드는 Gemini 키
   - `APP_PASSWORD` — 앱 비밀번호 (길게 정하세요). 없으면 이 컴퓨터(`localhost`)에서만 열립니다.
4. `python -m streamlit run app.py`

## 올릴 때 지킬 것

- 키 값과 비밀번호는 코드나 저장소에 넣지 않습니다.
- 시 본문은 저장소가 아니라 Supabase에만 둡니다.
- `sample/test_poem.txt`는 시험용으로 허락받고 올린 시 한 편입니다.
