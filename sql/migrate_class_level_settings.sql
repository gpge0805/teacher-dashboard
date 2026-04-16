-- 資料遷移腳本：從老師級設置遷移到班級級設置
-- 執行前請備份 weekly_stats_settings 表
-- 此指令碼會將現有的 teacher_username 設置複製到該老師的所有班級

-- 步驟 1：確認要迁移的老師列表及其班級
-- 執行此查詢查看遷移範圍：
/*
SELECT DISTINCT s.teacher_username, s.class_name, wss.setting_key
FROM students s
LEFT JOIN weekly_stats_settings wss 
  ON (wss.setting_key = s.teacher_username OR wss.setting_key LIKE s.teacher_username || ':%')
WHERE s.teacher_username IS NOT NULL
ORDER BY s.teacher_username, s.class_name;
*/

-- 步驟 2：執行遷移 - 將每個老師的全局設定複製到其所有班級
DO $$
DECLARE
  v_teacher_username TEXT;
  v_class_name TEXT;
  v_setting_key TEXT;
  v_existing_key TEXT;
  v_row RECORD;
BEGIN
  -- 遍歷所有 students 表中存在的「老師-班級」組合
  FOR v_row IN
    SELECT DISTINCT s.teacher_username, s.class_name
    FROM students s
    WHERE s.teacher_username IS NOT NULL AND s.class_name IS NOT NULL
    ORDER BY s.teacher_username, s.class_name
  LOOP
    v_teacher_username := v_row.teacher_username;
    v_class_name := v_row.class_name;
    v_setting_key := v_teacher_username || ':' || v_class_name;
    
    -- 檢查此班級是否已有特定設置
    SELECT setting_key INTO v_existing_key
    FROM weekly_stats_settings
    WHERE setting_key = v_setting_key
    LIMIT 1;
    
    IF v_existing_key IS NULL THEN
      -- 此班級還沒有特定設置，檢查老師是否有全局設置
      INSERT INTO weekly_stats_settings (
        setting_key,
        pass_score,
        week_start_weekday,
        primary_slot_start_hour,
        primary_slot_end_hour,
        updated_by,
        updated_at
      )
      SELECT
        v_setting_key,
        COALESCE(pass_score, 60),
        COALESCE(week_start_weekday, 2),
        COALESCE(primary_slot_start_hour, 15),
        COALESCE(primary_slot_end_hour, 16),
        updated_by,
        NOW() AT TIME ZONE 'Asia/Taipei'
      FROM weekly_stats_settings
      WHERE setting_key = v_teacher_username
      LIMIT 1;
      
      -- 如果老師也沒有全局設置，則插入默認值
      IF NOT FOUND THEN
        INSERT INTO weekly_stats_settings (
          setting_key,
          pass_score,
          week_start_weekday,
          primary_slot_start_hour,
          primary_slot_end_hour,
          updated_by,
          updated_at
        ) VALUES (
          v_setting_key,
          60,
          2,
          15,
          16,
          v_teacher_username || '_auto',
          NOW() AT TIME ZONE 'Asia/Taipei'
        );
      END IF;
    END IF;
  END LOOP;
  
  RAISE NOTICE '遷移完成！請驗證 weekly_stats_settings 表';
END
$$;

-- 步驟 3：驗證遷移結果
-- 執行此查詢驗證：
/*
SELECT setting_key, pass_score, week_start_weekday, 
       primary_slot_start_hour, primary_slot_end_hour,
       updated_at
FROM weekly_stats_settings
ORDER BY setting_key;
*/

-- 備註：
-- 1. 原有的 teacher_username 設置將保留，作為該老師的全局設定
-- 2. 新建的 teacher_username:class_name 設置將用於班級查詢
-- 3. 如果班級查詢找不到班級級設置，會自動回退到老師全局設置或 global 設置
-- 4. 管理員應定期檢查並清理重複的設置記錄
