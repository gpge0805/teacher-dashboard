# teacher_code 刪除前檢查清單

適用對象：`public.exam_results`

目標：安全淘汰 `teacher_code`，最終只保留 `teacher_username`

## 目前狀態

目前系統採用過渡相容方案：

- 前端上傳同時寫入 `teacher_code`
- 前端上傳同時寫入 `teacher_username`
- 教師後台查詢已改用 `teacher_username`

所以 **現在不要直接刪除 `teacher_code`**。

---

## 第一階段：確認新資料已穩定寫入 `teacher_username`

### 檢查 1：最近新資料是否都有 `teacher_username`

```sql
select id, student_id, teacher_code, teacher_username, created_at
from public.exam_results
order by created_at desc
limit 20;
```

判斷標準：

- 最近 10 到 20 筆新資料的 `teacher_username` 都不應為 `null`
- 若仍有新資料 `teacher_username` 為空，代表上傳端還沒完全切換

### 檢查 2：是否仍有空白 `teacher_username`

```sql
select count(*) as teacher_username_empty_count
from public.exam_results
where teacher_username is null or teacher_username = '';
```

判斷標準：

- 理想值是 `0`
- 若不為 `0`，先做一次回填再觀察

### 檢查 3：是否仍有資料只靠 `teacher_code`

```sql
select count(*) as still_only_teacher_code_count
from public.exam_results
where (teacher_username is null or teacher_username = '')
  and teacher_code is not null
  and teacher_code <> '';
```

判斷標準：

- 理想值是 `0`

---

## 第二階段：確認程式端已無依賴

### 需要確認的來源

1. 學生端前端上傳程式
2. 教師後台查詢程式
3. Supabase SQL 物件
   - View
   - Trigger
   - Function
   - Policy

### 工作區內目前已知狀態

- 教師後台已改用 `teacher_username`
- 學生端目前過渡期仍同時寫 `teacher_code` 與 `teacher_username`

所以真正要刪欄位前，還要再做一次前端切換：

- 把學生端上傳 payload 裡的 `teacher_code` 移除
- 只保留 `teacher_username`

---

## 第三階段：刪欄位前最後驗證 SQL

```sql
-- 1. 總筆數
select count(*) as total_count
from public.exam_results;

-- 2. teacher_username 已填筆數
select count(*) as teacher_username_filled_count
from public.exam_results
where teacher_username is not null and teacher_username <> '';

-- 3. teacher_username 空白筆數
select count(*) as teacher_username_empty_count
from public.exam_results
where teacher_username is null or teacher_username = '';

-- 4. 最近資料抽查
select id, student_id, teacher_code, teacher_username, created_at
from public.exam_results
order by created_at desc
limit 20;
```

只有在以下條件同時成立時，才建議刪除：

- `teacher_username_empty_count = 0`
- 最近新資料都已正確寫入 `teacher_username`
- 程式碼與 SQL 物件都不再依賴 `teacher_code`

---

## 最終刪除 SQL

先執行這個版本：

```sql
begin;

-- 如果還有 NOT NULL 或預設值，先解除
alter table public.exam_results
alter column teacher_code drop not null;

alter table public.exam_results
alter column teacher_code drop default;

-- 最終刪除欄位
alter table public.exam_results
drop column teacher_code;

commit;
```

---

## 刪除後驗證 SQL

```sql
-- 確認欄位不存在
select column_name
from information_schema.columns
where table_schema = 'public'
  and table_name = 'exam_results'
order by ordinal_position;

-- 確認資料仍可依 teacher_username 查詢
select id, student_id, teacher_username, created_at
from public.exam_results
order by created_at desc
limit 20;
```

---

## 建議執行順序

1. 先觀察一段時間，新資料穩定寫入 `teacher_username`
2. 把學生端上傳改成只送 `teacher_username`
3. 再跑一次「第三階段：刪欄位前最後驗證 SQL」
4. 最後執行刪除 SQL
5. 刪除後立即驗證
