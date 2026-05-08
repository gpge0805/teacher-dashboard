-- ============================================
-- Supabase RLS (Row Level Security) 設定
-- 請到 Supabase Dashboard → SQL Editor 貼上執行
-- ============================================

-- 1. 啟用 RLS
ALTER TABLE public.teachers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.students ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_results ENABLE ROW LEVEL SECURITY;

-- 2. teachers: anon 完全不能存取（只有 service_role 可以）
--    → 防止前端 anon key 讀取教師帳號密碼
DROP POLICY IF EXISTS "service_role_full_access_teachers" ON public.teachers;
CREATE POLICY "service_role_full_access_teachers" ON public.teachers
  FOR ALL USING (auth.role() = 'service_role');

-- 3. students: anon 可以 SELECT（前端查學號用），不可 INSERT/UPDATE/DELETE
--    → 前端輸入學號後查詢學生名冊
DROP POLICY IF EXISTS "anon_select_students" ON public.students;
CREATE POLICY "anon_select_students" ON public.students
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "service_role_full_access_students" ON public.students;
CREATE POLICY "service_role_full_access_students" ON public.students
  FOR ALL USING (auth.role() = 'service_role');

-- 4. exam_results: anon 可以 INSERT（前端上傳成績），不可 SELECT/UPDATE/DELETE
--    → 前端考完試後上傳成績，但不能讀取或刪改別人的成績
DROP POLICY IF EXISTS "anon_insert_exam_results" ON public.exam_results;
CREATE POLICY "anon_insert_exam_results" ON public.exam_results
  FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_full_access_exam_results" ON public.exam_results;
CREATE POLICY "service_role_full_access_exam_results" ON public.exam_results
  FOR ALL USING (auth.role() = 'service_role');
