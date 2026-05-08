-- 新增 certification_id 欄位至 exam_results 資料表
-- 用於記錄學生考的是哪一種檢定
-- 值域：'industrial' | 'digital-b' | 'industrial-wiring-c' | 'computer-hardware-b' | 'computer-hardware-c' | NULL（舊資料）

ALTER TABLE exam_results
  ADD COLUMN IF NOT EXISTS certification_id TEXT;

-- 舊資料回填（優先）：從 exam_settings JSONB 欄位萃取 certificationId 填入
UPDATE exam_results
SET certification_id = exam_settings->>'certificationId'
WHERE certification_id IS NULL
  AND exam_settings IS NOT NULL
  AND exam_settings->>'certificationId' IN ('industrial', 'digital-b', 'industrial-wiring-c', 'computer-hardware-b', 'computer-hardware-c');

-- 舊資料回填（次要）：若 categories 出現「工作項目10」則視為數乙
-- 注意：這是保守推斷，只回填可確定的 digital-b，其餘維持 NULL
UPDATE exam_results
SET certification_id = 'digital-b'
WHERE certification_id IS NULL
  AND categories IS NOT NULL
  AND categories::text LIKE '%工作項目10%';

-- 新資料保底：若前端漏傳 certification_id，嘗試由 exam_settings 自動補值
CREATE OR REPLACE FUNCTION set_exam_results_certification_id()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.certification_id IS NULL
     AND NEW.exam_settings IS NOT NULL
     AND (NEW.exam_settings->>'certificationId') IN ('industrial', 'digital-b', 'industrial-wiring-c', 'computer-hardware-b', 'computer-hardware-c') THEN
    NEW.certification_id := NEW.exam_settings->>'certificationId';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_set_exam_results_certification_id ON exam_results;
CREATE TRIGGER trg_set_exam_results_certification_id
BEFORE INSERT OR UPDATE ON exam_results
FOR EACH ROW
EXECUTE FUNCTION set_exam_results_certification_id();

-- （選用）建立索引以加速教師端依檢定種類篩選
CREATE INDEX IF NOT EXISTS idx_exam_results_certification_id
  ON exam_results (certification_id);
