"""檢查並設定 Supabase RLS"""
import requests
import json

SUPABASE_URL = "https://lmwngzkioqhqatkhlqmy.supabase.co"
SERVICE_KEY = "REDACTED_SUPABASE_SERVICE_ROLE_JWT"
ANON_KEY = "REDACTED_SUPABASE_ANON_JWT"

service_headers = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

anon_headers = {
    "apikey": ANON_KEY,
    "Authorization": f"Bearer {ANON_KEY}",
    "Content-Type": "application/json"
}

def test_anon_access(label):
    print(f"\n=== {label}: anon key access test ===")
    for table in ["teachers", "students", "exam_results"]:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?select=*&limit=1", headers=anon_headers)
        print(f"  SELECT {table}: {r.status_code} {'OPEN' if r.status_code == 200 and r.json() else 'BLOCKED/EMPTY'}")
    # Test insert exam_results
    r = requests.post(f"{SUPABASE_URL}/rest/v1/exam_results", headers=anon_headers, json={
        "student_id": "TEST_RLS_CHECK",
        "student_name": "RLS_TEST",
        "score": 0,
        "correct_count": 0,
        "total_questions": 0
    })
    print(f"  INSERT exam_results: {r.status_code} {'ALLOWED' if r.status_code in [200,201] else 'BLOCKED'}")
    # Clean up test record
    if r.status_code in [200, 201]:
        requests.delete(f"{SUPABASE_URL}/rest/v1/exam_results?student_id=eq.TEST_RLS_CHECK", headers=service_headers)

# --- RLS SQL ---
RLS_SQL = """
-- 1. Enable RLS on all tables
ALTER TABLE public.teachers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.students ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_results ENABLE ROW LEVEL SECURITY;

-- 2. teachers: anon 完全不能存取（只有 service_role 可以）
DROP POLICY IF EXISTS "service_role_full_access_teachers" ON public.teachers;
CREATE POLICY "service_role_full_access_teachers" ON public.teachers
  FOR ALL USING (auth.role() = 'service_role');

-- 3. students: anon 可以 SELECT（前端查學號用），不可 INSERT/UPDATE/DELETE
DROP POLICY IF EXISTS "anon_select_students" ON public.students;
CREATE POLICY "anon_select_students" ON public.students
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "service_role_full_access_students" ON public.students;
CREATE POLICY "service_role_full_access_students" ON public.students
  FOR ALL USING (auth.role() = 'service_role');

-- 4. exam_results: anon 可以 INSERT（前端上傳成績），不可 SELECT/UPDATE/DELETE
DROP POLICY IF EXISTS "anon_insert_exam_results" ON public.exam_results;
CREATE POLICY "anon_insert_exam_results" ON public.exam_results
  FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_full_access_exam_results" ON public.exam_results;
CREATE POLICY "service_role_full_access_exam_results" ON public.exam_results
  FOR ALL USING (auth.role() = 'service_role');
"""

test_anon_access("Before RLS")

print("\n--- Applying RLS policies via SQL ---")
# Execute SQL via Supabase's pg_meta or rpc
# Try using the query endpoint
r = requests.post(
    f"{SUPABASE_URL}/rest/v1/rpc/",
    headers=service_headers,
    json={}
)
print(f"RPC endpoint test: {r.status_code}")

# Output SQL for manual execution if needed
print("\n=== SQL to execute in Supabase SQL Editor ===")
print(RLS_SQL)
print("=== End SQL ===")

