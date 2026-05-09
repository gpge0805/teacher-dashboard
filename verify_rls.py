"""RLS 驗證腳本"""
import requests
import os

URL = os.getenv("SUPABASE_URL")
ANON = os.getenv("SUPABASE_ANON_KEY")
SVC = os.getenv("SUPABASE_KEY")

if not URL or not ANON or not SVC:
    raise RuntimeError(
        "Missing required env vars: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_KEY"
    )

anon_h = {"apikey": ANON, "Authorization": f"Bearer {ANON}", "Content-Type": "application/json", "Prefer": "return=minimal"}
svc_h = {"apikey": SVC, "Authorization": f"Bearer {SVC}", "Content-Type": "application/json"}

print("=== RLS Verification ===\n")

# 1. teachers: anon SELECT → should return empty
r = requests.get(f"{URL}/rest/v1/teachers?select=username,password&limit=1",
                 headers={"apikey": ANON, "Authorization": f"Bearer {ANON}"})
data = r.json()
status = "BLOCKED" if not data else "LEAK!"
print(f"1. teachers  SELECT (anon):   {r.status_code} -> {status}")
if data:
    print(f"   WARNING: got {data}")

# 2. students: anon SELECT → should return data
r = requests.get(f"{URL}/rest/v1/students?select=student_id,name&limit=1",
                 headers={"apikey": ANON, "Authorization": f"Bearer {ANON}"})
data = r.json()
status = "OK" if data else "PROBLEM"
print(f"2. students  SELECT (anon):   {r.status_code} -> {status}")

# 3. exam_results: anon INSERT → should succeed
r = requests.post(f"{URL}/rest/v1/exam_results", headers=anon_h, json={
    "student_id": "TEST_RLS_999",
    "student_name": "RLS_TEST",
    "class_name": "TEST",
    "seat_number": 99,
    "teacher_code": "test",
    "teacher_username": "test",
    "score": 0,
    "correct_count": 0,
    "total_questions": 10,
    "categories": ["test"],
    "time_spent": 0,
    "wrong_question_ids": [],
})
if r.status_code in [200, 201]:
    print(f"3. exam_results INSERT (anon):  {r.status_code} -> OK")
else:
    print(f"3. exam_results INSERT (anon):  {r.status_code} -> BLOCKED!")
    print(f"   Response: {r.text[:200]}")

# 4. exam_results: anon SELECT → should return empty
r = requests.get(f"{URL}/rest/v1/exam_results?select=student_id&limit=1",
                 headers={"apikey": ANON, "Authorization": f"Bearer {ANON}"})
data = r.json()
status = "BLOCKED" if not data else "LEAK!"
print(f"4. exam_results SELECT (anon):  {r.status_code} -> {status}")

# 5. service_role: should still have full access
r = requests.get(f"{URL}/rest/v1/teachers?select=username&limit=1", headers=svc_h)
data = r.json()
status = "OK" if data else "PROBLEM"
print(f"5. teachers  SELECT (service): {r.status_code} -> {status}")

r = requests.get(f"{URL}/rest/v1/exam_results?select=student_id&limit=1", headers=svc_h)
data = r.json()
status = "OK" if data else "PROBLEM"
print(f"6. exam_results SELECT (service): {r.status_code} -> {status}")

# Cleanup
requests.delete(f"{URL}/rest/v1/exam_results?student_id=eq.TEST_RLS_999", headers=svc_h)
print("\n   (test record cleaned up)")
print("\nDone.")
