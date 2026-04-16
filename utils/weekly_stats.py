import math
from datetime import datetime, timedelta

import pandas as pd


LOCAL_TZ = "Asia/Taipei"
WEEK_START_WEEKDAY = 2  # Wednesday, Monday=0
PRIMARY_SLOT_START_HOUR = 15
PRIMARY_SLOT_END_HOUR = 16
DEFAULT_WEEKLY_PASS_SCORE = 60

WEEKDAY_LABELS = {
    0: '星期一', 1: '星期二', 2: '星期三',
    3: '星期四', 4: '星期五', 5: '星期六', 6: '星期日',
}

# 週統計只計算「全選(所有項目)」且 80 題的正式考試
FULL_EXAM_QUESTION_COUNT = 80
FULL_EXAM_CATEGORIES_LABEL = "全選 (所有項目)"
REQUIRED_RESULT_COLUMNS = [
    'id',
    'student_id',
    'created_at',
    'created_at_dt',
    'created_at_local',
    'created_date_local',
    'created_hour_local',
    'score',
    'score_num',
    'correct_count',
    'correct_count_num',
    'total_questions',
    'categories',
]


def _ensure_result_columns(df):
    if df is None:
        df = pd.DataFrame()
    for col in REQUIRED_RESULT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def _is_full_exam_categories(val):
    """判斷 categories 欄位是否包含「全選(所有項目)」標記。"""
    if isinstance(val, (list, tuple)):
        return any(FULL_EXAM_CATEGORIES_LABEL in str(item) for item in val)
    if val is None:
        return False
    try:
        import json
        parsed = json.loads(val) if isinstance(val, str) else None
        if isinstance(parsed, list):
            return any(FULL_EXAM_CATEGORIES_LABEL in str(item) for item in parsed)
    except (ValueError, TypeError):
        pass
    return FULL_EXAM_CATEGORIES_LABEL in str(val)


def _filter_full_exam_only(df):
    """只保留 total_questions==80 且 categories 含「全選(所有項目)」的成績。"""
    if df.empty:
        return df

    if 'total_questions' in df.columns:
        total_q = pd.to_numeric(df['total_questions'], errors='coerce').fillna(0)
        mask_q = (total_q == FULL_EXAM_QUESTION_COUNT)
    else:
        mask_q = pd.Series(False, index=df.index)

    if 'categories' in df.columns:
        mask_cat = df['categories'].apply(_is_full_exam_categories)
    else:
        mask_cat = pd.Series(False, index=df.index)

    return df[mask_q & mask_cat].copy()


def safe_str(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_score(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def current_local_time():
    return pd.Timestamp.now(tz=LOCAL_TZ)


def get_week_bounds(reference_time=None, week_start_weekday=None):
    """回傳 (week_start_dt, week_end_dt)。
    week_start_weekday: 0=一, 1=二, 2=三, ..., 6=日；None 時用模組預設值。
    """
    if week_start_weekday is None:
        week_start_weekday = WEEK_START_WEEKDAY

    if reference_time is None:
        local_now = current_local_time()
    else:
        local_now = pd.Timestamp(reference_time)
        if local_now.tzinfo is None:
            local_now = local_now.tz_localize(LOCAL_TZ)
        else:
            local_now = local_now.tz_convert(LOCAL_TZ)

    local_date = local_now.date()
    days_since_start = (local_date.weekday() - week_start_weekday) % 7
    week_start_date = local_date - timedelta(days=days_since_start)
    week_start_dt = pd.Timestamp(datetime.combine(week_start_date, datetime.min.time()), tz=LOCAL_TZ)
    week_end_dt = week_start_dt + pd.Timedelta(days=7)
    return week_start_dt, week_end_dt


def format_week_label(week_start_dt, week_end_dt):
    local_end = week_end_dt - pd.Timedelta(seconds=1)
    return f"{week_start_dt.strftime('%Y-%m-%d %H:%M')} ~ {local_end.strftime('%Y-%m-%d %H:%M')}"


def prepare_results_dataframe(results_df):
    if results_df is None or results_df.empty:
        return _ensure_result_columns(pd.DataFrame())

    df = _ensure_result_columns(results_df.copy())
    if 'created_at' not in df.columns:
        df['created_at'] = None

    df['created_at_dt'] = pd.to_datetime(df['created_at'], utc=True, errors='coerce')
    df = df[df['created_at_dt'].notna()].copy()
    if df.empty:
        return _ensure_result_columns(df)

    df['created_at_local'] = df['created_at_dt'].dt.tz_convert(LOCAL_TZ)
    df['created_date_local'] = df['created_at_local'].dt.date
    df['created_hour_local'] = df['created_at_local'].dt.hour
    df['score_num'] = pd.to_numeric(df.get('score'), errors='coerce').fillna(0.0)
    df['correct_count_num'] = pd.to_numeric(df.get('correct_count'), errors='coerce').fillna(0.0)

    # 只計算「全選(所有項目)」80題正式考試
    df = _filter_full_exam_only(df)
    return _ensure_result_columns(df)


def filter_week_results(results_df, week_start_dt, week_end_dt):
    if results_df is None or results_df.empty:
        return _ensure_result_columns(pd.DataFrame())
    df = prepare_results_dataframe(results_df)
    if df.empty:
        return _ensure_result_columns(df)
    filtered_df = df[(df['created_at_local'] >= week_start_dt) & (df['created_at_local'] < week_end_dt)].copy()
    return _ensure_result_columns(filtered_df)


def _pick_best_record(records_df):
    if records_df.empty:
        return None
    sorted_df = records_df.sort_values(
        by=['score_num', 'correct_count_num', 'created_at_local', 'id'],
        ascending=[False, False, True, True],
        na_position='last',
    )
    return sorted_df.iloc[0].to_dict()


def _pad_scores(scores, target_count):
    padded = list(scores[:target_count])
    if len(padded) < target_count:
        padded.extend([0.0] * (target_count - len(padded)))
    return padded


def _override_lookup(override_rows):
    lookup = {}
    if not override_rows:
        return lookup

    for row in override_rows:
        student_id = safe_str(row.get('student_id'))
        week_start_date = row.get('week_start_date')
        if not student_id or not week_start_date:
            continue
        lookup[(student_id, str(week_start_date))] = row
    return lookup


def compute_student_weekly_stats(student_row, results_df, week_start_dt, week_end_dt, pass_score=60, override_rows=None,
                                 primary_slot_start_hour=None, primary_slot_end_hour=None):
    student_id = safe_str(student_row.get('student_id'))
    student_name = safe_str(student_row.get('name') or student_row.get('student_name'))

    student_week_df = filter_week_results(results_df, week_start_dt, week_end_dt)
    if not student_week_df.empty:
        student_week_df = student_week_df[student_week_df['student_id'].astype(str) == student_id].copy()

    week_start_date_str = week_start_dt.date().isoformat()
    override_map = _override_lookup(override_rows)
    override_row = override_map.get((student_id, week_start_date_str))

    wednesday_date = week_start_dt.date()
    wednesday_df = student_week_df[student_week_df['created_date_local'] == wednesday_date].copy()

    primary_record = None
    primary_source = '無'

    if override_row:
        override_result_id = override_row.get('selected_exam_result_id')
        override_match = wednesday_df[wednesday_df['id'].astype(str) == safe_str(override_result_id)]
        primary_record = _pick_best_record(override_match)
        if primary_record:
            primary_source = '教師指定'

    if primary_record is None:
        slot_start = primary_slot_start_hour if primary_slot_start_hour is not None else PRIMARY_SLOT_START_HOUR
        slot_end = primary_slot_end_hour if primary_slot_end_hour is not None else PRIMARY_SLOT_END_HOUR
        primary_slot_df = wednesday_df[
            (wednesday_df['created_hour_local'] >= slot_start) &
            (wednesday_df['created_hour_local'] < slot_end)
        ].copy()
        primary_record = _pick_best_record(primary_slot_df)
        if primary_record:
            primary_source = f'關鍵時段 {slot_start:02d}:00-{slot_end:02d}:00'

    primary_score = normalize_score(primary_record.get('score_num') if primary_record else 0.0)
    primary_component = primary_score * 0.5

    remaining_df = student_week_df.copy()
    if primary_record is not None:
        remaining_df = remaining_df[remaining_df['id'].astype(str) != safe_str(primary_record.get('id'))].copy()

    other_sorted = remaining_df.sort_values(
        by=['score_num', 'correct_count_num', 'created_at_local', 'id'],
        ascending=[False, False, True, True],
        na_position='last',
    )
    top_other_df = other_sorted.head(4).copy()
    top_other_scores = [normalize_score(x) for x in top_other_df['score_num'].tolist()]
    padded_other_scores = _pad_scores(top_other_scores, 4)
    other_average = sum(padded_other_scores) / 4
    other_component = other_average * 0.5

    total_score = round(primary_component + other_component, 2)
    pass_threshold = normalize_score(pass_score)
    is_pass = total_score >= pass_threshold

    return {
        'student_id': student_id,
        'student_name': student_name,
        'class_name': safe_str(student_row.get('class_name')),
        'seat_number': safe_str(student_row.get('seat_number')),
        'week_start_date': week_start_date_str,
        'week_range_label': format_week_label(week_start_dt, week_end_dt),
        'primary_score': primary_score,
        'primary_component': round(primary_component, 2),
        'primary_source': primary_source,
        'primary_record_id': safe_str(primary_record.get('id')) if primary_record else '',
        'primary_record_time': primary_record.get('created_at_local').strftime('%Y-%m-%d %H:%M:%S') if primary_record else '',
        'other_scores': padded_other_scores,
        'other_average': round(other_average, 2),
        'other_component': round(other_component, 2),
        'other_selected_count': len(top_other_scores),
        'other_missing_count': max(0, 4 - len(top_other_scores)),
        'total_score': total_score,
        'pass_score': pass_threshold,
        'is_pass': is_pass,
        'status_text': '及格' if is_pass else '不及格',
        'weekly_record_count': len(student_week_df),
        'wednesday_record_count': len(wednesday_df),
        'available_wednesday_records': wednesday_df.sort_values(by='created_at_local', ascending=True).to_dict('records'),
        'selected_other_records': top_other_df.sort_values(by='created_at_local', ascending=True).to_dict('records'),
    }


def build_weekly_summary(students_df, results_df, week_start_dt, week_end_dt, pass_score=60, override_rows=None,
                         primary_slot_start_hour=None, primary_slot_end_hour=None):
    if students_df is None or students_df.empty:
        return []

    summaries = []
    for _, student_row in students_df.iterrows():
        summaries.append(
            compute_student_weekly_stats(
                student_row=student_row,
                results_df=results_df,
                week_start_dt=week_start_dt,
                week_end_dt=week_end_dt,
                pass_score=pass_score,
                override_rows=override_rows,
                primary_slot_start_hour=primary_slot_start_hour,
                primary_slot_end_hour=primary_slot_end_hour,
            )
        )
    return summaries


def build_other_scores_display(other_scores):
    if not other_scores:
        return '0, 0, 0, 0'
    return ', '.join(str(int(score) if float(score).is_integer() else round(score, 2)) for score in other_scores)


def build_primary_candidate_label(record):
    score = normalize_score(record.get('score_num', record.get('score')))
    created_at_local = record.get('created_at_local')
    time_label = created_at_local.strftime('%Y-%m-%d %H:%M:%S') if hasattr(created_at_local, 'strftime') else safe_str(record.get('created_at'))
    return f"{time_label} | 分數 {score:g} | 答對 {normalize_score(record.get('correct_count_num', record.get('correct_count'))):g}"


def _get_settings_row(supabase_client, setting_key):
    """讀取 weekly_stats_settings 中指定 key 的整列，找不到回傳 None。"""
    try:
        response = (
            supabase_client.table("weekly_stats_settings")
            .select("*")
            .eq("setting_key", setting_key)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None
    except Exception:
        return None


def load_teacher_settings(supabase_client, teacher_username="", class_name=""):
    """載入老師班級設定，支援班級粒度。查詢優先順序：teacher:class → teacher → global → 預設值。
    
    Args:
        supabase_client: Supabase 客戶端
        teacher_username: 老師帳號
        class_name: 班級名稱（可選，若提供則優先查班級設定）
    
    回傳 dict：pass_score, week_start_weekday, primary_slot_start_hour, primary_slot_end_hour
    """
    defaults = {
        'pass_score': DEFAULT_WEEKLY_PASS_SCORE,
        'week_start_weekday': WEEK_START_WEEKDAY,
        'primary_slot_start_hour': PRIMARY_SLOT_START_HOUR,
        'primary_slot_end_hour': PRIMARY_SLOT_END_HOUR,
    }
    row = None
    
    # 優先查詢班級特定設定（teacher_username:class_name）
    if safe_str(teacher_username) and safe_str(class_name):
        class_key = f"{safe_str(teacher_username)}:{safe_str(class_name)}"
        row = _get_settings_row(supabase_client, class_key)
    
    # 回退到老師全局設定（teacher_username）
    if row is None and safe_str(teacher_username):
        row = _get_settings_row(supabase_client, safe_str(teacher_username))
    
    # 回退到全球設定（global）
    if row is None:
        row = _get_settings_row(supabase_client, 'global')
    
    # 若皆無則使用程式預設值
    if row is None:
        return defaults
    
    return {
        'pass_score': int(normalize_score(row.get('pass_score', defaults['pass_score']))),
        'week_start_weekday': int(row.get('week_start_weekday', defaults['week_start_weekday'])),
        'primary_slot_start_hour': int(row.get('primary_slot_start_hour', defaults['primary_slot_start_hour'])),
        'primary_slot_end_hour': int(row.get('primary_slot_end_hour', defaults['primary_slot_end_hour'])),
    }


def save_teacher_settings(supabase_client, teacher_username, pass_score, week_start_weekday,
                          primary_slot_start_hour, primary_slot_end_hour, class_name=""):
    """儲存老師班級設定（支援班級粒度，upsert 以組合 key 進行）。
    
    Args:
        supabase_client: Supabase 客戶端
        teacher_username: 老師帳號
        pass_score: 及格標準
        week_start_weekday: 週開始日（0-6）
        primary_slot_start_hour: 關鍵時段開始時期
        primary_slot_end_hour: 關鍵時段結束時期
        class_name: 班級名稱（可選）
    """
    if safe_str(class_name):
        setting_key = f"{safe_str(teacher_username)}:{safe_str(class_name)}"
    else:
        setting_key = safe_str(teacher_username)
    
    payload = {
        "setting_key": setting_key,
        "pass_score": int(normalize_score(pass_score)),
        "week_start_weekday": int(week_start_weekday),
        "primary_slot_start_hour": int(primary_slot_start_hour),
        "primary_slot_end_hour": int(primary_slot_end_hour),
        "updated_by": safe_str(teacher_username),
        "updated_at": current_local_time().tz_convert('UTC').isoformat(),
    }
    supabase_client.table("weekly_stats_settings").upsert(payload, on_conflict="setting_key").execute()


# ── 向下相容舊介面 ──────────────────────────────────────────────────────────────
def load_weekly_pass_score(supabase_client):
    return load_teacher_settings(supabase_client).get('pass_score', DEFAULT_WEEKLY_PASS_SCORE)


def save_weekly_pass_score(supabase_client, pass_score, teacher_username=""):
    """保留舊介面；只更新 global 的 pass_score，不動其他欄位。"""
    row = _get_settings_row(supabase_client, 'global') or {}
    payload = {
        "setting_key": "global",
        "pass_score": int(normalize_score(pass_score)),
        "week_start_weekday": int(row.get('week_start_weekday', WEEK_START_WEEKDAY)),
        "primary_slot_start_hour": int(row.get('primary_slot_start_hour', PRIMARY_SLOT_START_HOUR)),
        "primary_slot_end_hour": int(row.get('primary_slot_end_hour', PRIMARY_SLOT_END_HOUR)),
        "updated_by": safe_str(teacher_username),
        "updated_at": current_local_time().tz_convert('UTC').isoformat(),
    }
    supabase_client.table("weekly_stats_settings").upsert(payload, on_conflict="setting_key").execute()
