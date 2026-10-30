-- Supabase 대시보드 → SQL Editor 에 통째로 붙여 넣고 Run 을 한 번 누르세요.
-- drafts 표(시 한 편이 한 줄)를 만들고, 앱이 읽고·넣고·고칠 수 있게 권한을 엽니다.
--
-- 이미 poems 표를 만들어 쓰고 있다면, 이 파일 대신 아래 한 줄만 실행하세요
-- (표 안의 글과 권한 설정은 그대로 따라옵니다):
--     alter table poems rename to drafts;

create table if not exists drafts (
  id            bigint generated always as identity primary key,
  received_date date   not null,            -- 받은날짜
  title         text   not null,            -- 제목
  author        text   not null default '', -- 작가
  body          text   not null,            -- 본문
  end_date      date,                       -- 글끝날짜 (없을 수 있음)
  cut           text   not null default '-',-- 잘림: '-' / '확인 필요' / '잘림'
  prompt        text,                       -- 수채화 프롬프트 (아직 없으면 비어 있음)
  is_target     boolean not null default false, -- 시화 대상으로 정한 시인가 (이미 만든 표라면 supabase_add_target.sql)
  is_deleted    boolean not null default false, -- 목록에서 삭제한(숨긴) 시인가 (이미 만든 표라면 supabase_add_deleted.sql)
  created_at    timestamptz not null default now(),
  unique (received_date, title)             -- 받은날짜와 제목이 같으면 중복
);

alter table drafts enable row level security;

create policy "drafts 읽기"   on drafts for select using (true);
create policy "drafts 넣기"   on drafts for insert with check (true);
create policy "drafts 고치기" on drafts for update using (true) with check (true);
