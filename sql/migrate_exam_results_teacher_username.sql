-- Safe migration for exam_results: teacher_code -> teacher_username
-- Run in Supabase SQL Editor (or psql) step by step.

begin;

-- 1) Add new column if it does not exist.
alter table public.exam_results
add column if not exists teacher_username text;

-- 2) Backfill from students mapping (preferred source).
update public.exam_results er
set teacher_username = s.teacher_username
from public.students s
where er.student_id = s.student_id
  and (er.teacher_username is null or er.teacher_username = '');

-- 3) Fallback: if still empty, reuse teacher_code value.
update public.exam_results
set teacher_username = teacher_code
where (teacher_username is null or teacher_username = '')
  and teacher_code is not null
  and teacher_code <> '';

-- 4) Optional index for faster teacher-based filtering.
create index if not exists idx_exam_results_teacher_username
on public.exam_results (teacher_username);

commit;

-- Validation queries:
-- select count(*) as total from public.exam_results;
-- select count(*) as teacher_username_filled from public.exam_results where teacher_username is not null and teacher_username <> '';
-- select count(*) as teacher_username_empty from public.exam_results where teacher_username is null or teacher_username = '';

-- After all write paths are switched and observed stable, you can drop old column:
-- alter table public.exam_results drop column teacher_code;
