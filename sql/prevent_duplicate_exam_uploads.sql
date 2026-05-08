-- 防止重複上傳成績：新增 upload_token 並建立唯一索引
-- 執行位置：Supabase SQL Editor

-- 1) 新增 upload_token 欄位（前端每次交卷固定一個 token）
alter table public.exam_results
add column if not exists upload_token text;

-- 2) 建立唯一索引，避免同一 token 重複寫入
create unique index if not exists ux_exam_results_upload_token
on public.exam_results (upload_token)
where upload_token is not null and upload_token <> '';

-- 3) 一次性清理歷史重複資料（保留每組最早一筆）
--   判斷條件：同學號、同秒、同分數、同答對題數、同耗時、同總題數、同工作項目
with ranked as (
  select
    id,
    row_number() over (
      partition by
        student_id,
        date_trunc('second', created_at),
        score,
        correct_count,
        time_spent,
        total_questions,
        coalesce(categories::text, '')
      order by created_at asc, id asc
    ) as rn
  from public.exam_results
)
delete from public.exam_results er
using ranked r
where er.id = r.id
  and r.rn > 1;

-- 4) 驗證是否仍有重複資料
-- select
--   student_id,
--   date_trunc('second', created_at) as created_at_sec,
--   score,
--   correct_count,
--   time_spent,
--   total_questions,
--   coalesce(categories::text, '') as categories_text,
--   count(*) as cnt
-- from public.exam_results
-- group by 1,2,3,4,5,6,7
-- having count(*) > 1
-- order by cnt desc, created_at_sec desc;
