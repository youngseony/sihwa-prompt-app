-- drafts 표의 "누구나" 권한을 닫습니다. 이 뒤로는 .env의 SUPABASE_SECRET_KEY(비밀 키)를 가진 앱만
-- 표를 읽고·넣고·고칠 수 있습니다. (공개용 키로는 아무것도 못 합니다.)
--
-- 순서: ① .env의 SUPABASE_SECRET_KEY에 secret 키를 먼저 붙여 넣고 앱이 도는지 확인
--       ② 그다음 이 파일을 SQL Editor에서 Run
-- 순서를 바꾸면 앱이 "권한 없음" 오류를 냅니다.

-- 표 이름을 poems에서 drafts로 바꿀 때 권한 이름은 안 바뀌었으므로 두 이름을 다 지웁니다.
drop policy if exists "poems 읽기"     on drafts;
drop policy if exists "poems 넣기"     on drafts;
drop policy if exists "poems 고치기"   on drafts;
drop policy if exists "drafts 읽기"    on drafts;
drop policy if exists "drafts 넣기"    on drafts;
drop policy if exists "drafts 고치기"  on drafts;

-- 권한(policy)이 하나도 없고 RLS가 켜져 있으면 공개용 키는 전부 막힙니다.
alter table drafts enable row level security;
