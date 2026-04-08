-- 每週成績統計支援表
-- 執行位置：Supabase SQL Editor

create table if not exists public.weekly_primary_overrides (
  id uuid default gen_random_uuid() primary key,
  student_id text not null,
  week_start_date date not null,
  selected_exam_result_id uuid not null,
  teacher_username text,
  note text,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create unique index if not exists ux_weekly_primary_overrides_student_week
on public.weekly_primary_overrides (student_id, week_start_date);

create index if not exists idx_weekly_primary_overrides_selected_result
on public.weekly_primary_overrides (selected_exam_result_id);

alter table public.weekly_primary_overrides
  add constraint fk_weekly_primary_overrides_student
  foreign key (student_id)
  references public.students(student_id)
  on delete cascade;

alter table public.weekly_primary_overrides
  add constraint fk_weekly_primary_overrides_exam_result
  foreign key (selected_exam_result_id)
  references public.exam_results(id)
  on delete cascade;

alter table public.weekly_primary_overrides enable row level security;

drop policy if exists "service_role_full_access_weekly_primary_overrides" on public.weekly_primary_overrides;
create policy "service_role_full_access_weekly_primary_overrides" on public.weekly_primary_overrides
  for all using (auth.role() = 'service_role');

create table if not exists public.weekly_stats_settings (
  setting_key text primary key,
  pass_score integer not null default 60,
  updated_by text,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

insert into public.weekly_stats_settings (setting_key, pass_score)
values ('global', 60)
on conflict (setting_key) do nothing;

alter table public.weekly_stats_settings enable row level security;

drop policy if exists "service_role_full_access_weekly_stats_settings" on public.weekly_stats_settings;
create policy "service_role_full_access_weekly_stats_settings" on public.weekly_stats_settings
  for all using (auth.role() = 'service_role');
