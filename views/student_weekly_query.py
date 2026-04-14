import pandas as pd
import streamlit as st

from utils.supabase_client import supabase
from utils.weekly_stats import (
    build_other_scores_display,
    compute_student_weekly_stats,
    current_local_time,
    get_week_bounds,
    load_teacher_settings,
    load_weekly_pass_score,
    safe_str,
    WEEKDAY_LABELS,
)


def _load_student(student_id):
    response = (
        supabase.table("students")
        .select("student_id,name,class_name,seat_number")
        .eq("student_id", student_id)
        .limit(1)
        .execute()
    )
    data = response.data or []
    return data[0] if data else None


def _load_week_results(student_id, week_start_dt, week_end_dt):
    utc_start = week_start_dt.tz_convert('UTC').isoformat()
    utc_end = week_end_dt.tz_convert('UTC').isoformat()
    response = (
        supabase.table("exam_results")
        .select("*")
        .eq("student_id", student_id)
        .gte("created_at", utc_start)
        .lt("created_at", utc_end)
        .order("created_at", desc=False)
        .execute()
    )
    return pd.DataFrame(response.data or [])


def _load_override(student_id, week_start_dt):
    try:
        response = (
            supabase.table("weekly_primary_overrides")
            .select("*")
            .eq("student_id", student_id)
            .eq("week_start_date", week_start_dt.date().isoformat())
            .limit(1)
            .execute()
        )
        return response.data or []
    except Exception:
        return []


def _build_week_options(num_weeks=12, week_start_weekday=2):
    """產生最近 num_weeks 週的選項清單，最新在前。"""
    current_week_start, _ = get_week_bounds(week_start_weekday=week_start_weekday)
    options = []
    for i in range(num_weeks):
        ws = current_week_start - pd.Timedelta(weeks=i)
        we = ws + pd.Timedelta(days=7)
        label = f"{ws.strftime('%Y-%m-%d')} ~ {(we - pd.Timedelta(seconds=1)).strftime('%Y-%m-%d')}"
        if i == 0:
            label += "（本週）"
        options.append((label, ws))
    return options


def show():
    st.title("📘 成績查詢")
    st.write("輸入學號後，可查看指定週次的統計成績。")

    # 嘗試從 query_params 取得 teacher_username，讓學生查詢頁套用正確老師設定
    query_params = st.query_params
    teacher_username = safe_str(query_params.get('teacher', '')) or st.session_state.get('username', '')
    ts = load_teacher_settings(supabase, teacher_username)

    week_start_weekday = ts['week_start_weekday']
    pass_score = ts['pass_score']
    primary_slot_start = ts['primary_slot_start_hour']
    primary_slot_end = ts['primary_slot_end_hour']

    week_options = _build_week_options(12, week_start_weekday=week_start_weekday)
    week_labels = [opt[0] for opt in week_options]
    selected_week_index = st.selectbox(
        "查詢週次",
        range(len(week_labels)),
        format_func=lambda i: week_labels[i],
        index=0,
    )
    selected_week_start = week_options[selected_week_index][1]
    week_start_dt, week_end_dt = get_week_bounds(reference_time=selected_week_start, week_start_weekday=week_start_weekday)
    week_label = f"{week_start_dt.strftime('%Y-%m-%d %H:%M')} ~ {(week_end_dt - pd.Timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M')}"
    st.info(f"目前統計區間：{week_label}（台灣時間）")

    default_student_id = safe_str(query_params.get('student_id', ''))
    student_id = st.text_input("請輸入學號", value=default_student_id)

    if st.button("查詢成績", type="primary"):
        if not safe_str(student_id):
            st.error("請輸入學號。")
            return

        student = _load_student(safe_str(student_id))
        if not student:
            st.error("查無此學號，請確認是否輸入正確。")
            return

        results_df = _load_week_results(safe_str(student_id), week_start_dt, week_end_dt)
        override_rows = _load_override(safe_str(student_id), week_start_dt)
        summary = compute_student_weekly_stats(
            student_row=student,
            results_df=results_df,
            week_start_dt=week_start_dt,
            week_end_dt=week_end_dt,
            pass_score=pass_score,
            override_rows=override_rows,
            primary_slot_start_hour=primary_slot_start,
            primary_slot_end_hour=primary_slot_end,
        )

        st.success(f"已更新：{current_local_time().strftime('%Y-%m-%d %H:%M:%S')}")
        top_col1, top_col2, top_col3 = st.columns(3)
        top_col1.metric("學號", summary['student_id'])
        top_col2.metric("姓名", summary['student_name'])
        top_col3.metric("班級", summary['class_name'] or '未設定')

        score_col1, score_col2, score_col3 = st.columns(3)
        score_col1.metric("本週總成績", summary['total_score'])
        score_col2.metric("及格線", summary['pass_score'])
        score_col3.metric("結果", summary['status_text'])

        st.markdown("### 成績組成")
        detail_df = pd.DataFrame([
            {
                '項目': '週三關鍵成績（50%）',
                '分數': summary['primary_score'],
                '採計來源': summary['primary_source'],
                '加權後': summary['primary_component'],
            },
            {
                '項目': '其他時段前 4 高分平均（50%）',
                '分數': summary['other_average'],
                '採計來源': build_other_scores_display(summary['other_scores']),
                '加權後': summary['other_component'],
            }
        ])
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

        if summary['other_missing_count'] > 0:
            st.warning(f"其餘時段不足 4 筆，已自動以 0 分補足 {summary['other_missing_count']} 筆。")

        if not summary['primary_record_id']:
            st.warning("本週尚未有關鍵時段成績，該部分目前以 0 分計算。")
