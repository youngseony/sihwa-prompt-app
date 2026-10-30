-- Supabase 대시보드 → SQL Editor 에 통째로 붙여 넣고 Run 을 한 번 누르세요.
-- drafts 표에 "삭제함" 칸을 더합니다. 삭제한 시는 표에서 지우지 않고 목록에서만 숨깁니다.
-- (같은 카카오톡 파일을 다시 넣어도 삭제한 시가 되살아나지 않고, 나중에 되살릴 수도 있습니다.)
-- 몇 번 Run 해도 안전합니다. 표 안의 글·프롬프트·권한 설정은 그대로입니다.

alter table drafts add column if not exists is_deleted boolean not null default false;
