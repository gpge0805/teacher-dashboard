-- 每位老師自訂成績統計週期設定 migration
-- 執行位置：Supabase SQL Editor
-- 在 weekly_stats_settings 表新增三個欄位，並允許 setting_key 為教師帳號

alter table public.weekly_stats_settings
  add column if not exists week_start_weekday integer not null default 2,
  add column if not exists primary_slot_start_hour integer not null default 15,
  add column if not exists primary_slot_end_hour integer not null default 16;

-- 確保 global 預設值存在且欄位已填入
insert into public.weekly_stats_settings (
  setting_key, pass_score, week_start_weekday, primary_slot_start_hour, primary_slot_end_hour
)
values ('global', 60, 2, 15, 16)
on conflict (setting_key) do update
  set week_start_weekday = excluded.week_start_weekday,
      primary_slot_start_hour = excluded.primary_slot_start_hour,
      primary_slot_end_hour = excluded.primary_slot_end_hour;
