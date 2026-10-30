-- Supabase 대시보드 → SQL Editor 에 통째로 붙여 넣고 Run 을 한 번 누르세요.
-- drafts 표에 "시화 대상" 칸을 더합니다. (이미 있는 시 245편은 모두 "대상 아님(false)"으로 시작합니다.)
-- 몇 번 Run 해도 안전합니다. 표 안의 글·프롬프트·권한 설정은 그대로입니다.

alter table drafts add column if not exists is_target boolean not null default false;
