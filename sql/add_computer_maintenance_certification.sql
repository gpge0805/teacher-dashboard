-- 新增電腦修護（computer-maintenance）職種至 certification_id 允許值
-- 更新 trigger 使新插入的電腦修護成績可正確補值

CREATE OR REPLACE FUNCTION set_exam_results_certification_id()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.certification_id IS NULL
     AND NEW.exam_settings IS NOT NULL
     AND (NEW.exam_settings->>'certificationId') IN (
       'industrial',
       'digital-b',
       'industrial-wiring-c',
       'computer-hardware-b',
       'computer-hardware-c',
       'computer-maintenance'
     ) THEN
    NEW.certification_id := NEW.exam_settings->>'certificationId';
  END IF;

  RETURN NEW;
END;
$$;
