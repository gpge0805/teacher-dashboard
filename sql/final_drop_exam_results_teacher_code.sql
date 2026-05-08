begin;

alter table public.exam_results
alter column teacher_code drop not null;

alter table public.exam_results
alter column teacher_code drop default;

alter table public.exam_results
drop column teacher_code;

commit;
