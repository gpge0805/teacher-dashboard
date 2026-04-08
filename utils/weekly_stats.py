import math
from datetime import datetime, timedelta

import pandas as pd


LOCAL_TZ = "Asia/Taipei"
WEEK_START_WEEKDAY = 2  # Wednesday, Monday=0
PRIMARY_SLOT_START_HOUR = 15
PRIMARY_SLOT_END_HOUR = 16
DEFAULT_WEEKLY_PASS_SCORE = 60


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


def get_week_bounds(reference_time=None):
    if reference_time is None:
        local_now = current_local_time()
    else:
        local_now = pd.Timestamp(reference_time)
        if local_now.tzinfo is None:
            local_now = local_now.tz_localize(LOCAL_TZ)
        else:
            local_now = local_now.tz_convert(LOCAL_TZ)

    local_date = local_now.date()
    days_since_wednesday = (local_date.weekday() - WEEK_START_WEEKDAY) % 7
    week_start_date = local_date - timedelta(days=days_since_wednesday)
    week_start_dt = pd.Timestamp(datetime.combine(week_start_date, datetime.min.time()), tz=LOCAL_TZ)
    week_end_dt = week_start_dt + pd.Timedelta(days=7)
    return week_start_dt, week_end_dt


def format_week_label(week_start_dt, week_end_dt):
    local_end = week_end_dt - pd.Timedelta(seconds=1)
    return f"{week_start_dt.strftime('%Y-%m-%d %H:%M')} ~ {local_end.strftime('%Y-%m-%d %H:%M')}"


def prepare_results_dataframe(results_df):
    if results_df is None or results_df.empty:
        return pd.DataFrame()

    df = results_df.copy()
    if 'created_at' not in df.columns:
        df['created_at'] = None

    df['created_at_dt'] = pd.to_datetime(df['created_at'], utc=True, errors='coerce')
    df = df[df['created_at_dt'].notna()].copy()
    if df.empty:
        return df

    df['created_at_local'] = df['created_at_dt'].dt.tz_convert(LOCAL_TZ)
    df['created_date_local'] = df['created_at_local'].dt.date
    df['created_hour_local'] = df['created_at_local'].dt.hour
    df['score_num'] = pd.to_numeric(df.get('score'), errors='coerce').fillna(0.0)
    df['correct_count_num'] = pd.to_numeric(df.get('correct_count'), errors='coerce').fillna(0.0)
    return df


def filter_week_results(results_df, week_start_dt, week_end_dt):
    if results_df is None or results_df.empty:
        return pd.DataFrame()
    df = prepare_results_dataframe(results_df)
    if df.empty:
        return df
    return df[(df['created_at_local'] >= week_start_dt) & (df['created_at_local'] < week_end_dt)].copy()


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


def compute_student_weekly_stats(student_row, results_df, week_start_dt, week_end_dt, pass_score=60, override_rows=None):
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
        primary_slot_df = wednesday_df[
            (wednesday_df['created_hour_local'] >= PRIMARY_SLOT_START_HOUR) &
            (wednesday_df['created_hour_local'] < PRIMARY_SLOT_END_HOUR)
        ].copy()
        primary_record = _pick_best_record(primary_slot_df)
        if primary_record:
            primary_source = '週三 15:00-15:59'

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


def build_weekly_summary(students_df, results_df, week_start_dt, week_end_dt, pass_score=60, override_rows=None):
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


def load_weekly_pass_score(supabase_client):
    try:
        response = (
            supabase_client.table("weekly_stats_settings")
            .select("pass_score")
            .eq("setting_key", "global")
            .limit(1)
            .execute()
        )
        data = response.data or []
        if not data:
            return DEFAULT_WEEKLY_PASS_SCORE
        return int(normalize_score(data[0].get('pass_score', DEFAULT_WEEKLY_PASS_SCORE)))
    except Exception:
        return DEFAULT_WEEKLY_PASS_SCORE


def save_weekly_pass_score(supabase_client, pass_score, teacher_username=""):
    payload = {
        "setting_key": "global",
        "pass_score": int(normalize_score(pass_score)),
        "updated_by": safe_str(teacher_username),
        "updated_at": current_local_time().tz_convert('UTC').isoformat(),
    }
    supabase_client.table("weekly_stats_settings").upsert(payload, on_conflict="setting_key").execute()
