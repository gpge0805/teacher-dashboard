import pandas as pd
import streamlit as st

from utils.supabase_client import supabase
from utils.weekly_stats import (
    build_other_scores_display,
    build_primary_candidate_label,
    build_weekly_summary,
    current_local_time,
    get_week_bounds,
    load_weekly_pass_score,
    save_weekly_pass_score,
    safe_str,
)


def _load_visible_students():
    query = supabase.table("students").select("student_id,name,class_name,seat_number,teacher_username")
    if st.session_state.get('role') != 'admin':
        query = query.eq("teacher_username", st.session_state.get('username'))
    response = query.order("class_name").order("seat_number").execute()
    return pd.DataFrame(response.data or [])


def _load_week_results(student_ids, week_start_dt, week_end_dt):
    if not student_ids:
        return pd.DataFrame()

    utc_start = week_start_dt.tz_convert('UTC').isoformat()
    utc_end = week_end_dt.tz_convert('UTC').isoformat()
    response = (
        supabase.table("exam_results")
        .select("*")
        .in_("student_id", student_ids)
        .gte("created_at", utc_start)
        .lt("created_at", utc_end)
        .order("created_at", desc=False)
        .execute()
    )
    return pd.DataFrame(response.data or [])


def _load_week_overrides(student_ids, week_start_dt):
    if not student_ids:
        return []

    try:
        response = (
            supabase.table("weekly_primary_overrides")
            .select("*")
            .in_("student_id", student_ids)
            .eq("week_start_date", week_start_dt.date().isoformat())
            .execute()
        )
        return response.data or []
    except Exception as exc:
        st.error(
            "❌ 讀取 weekly_primary_overrides 失敗。請先到 Supabase 執行 weekly_stats_setup.sql。"
        )
        st.caption(str(exc))
        return []


def _upsert_override(student_id, week_start_dt, selected_exam_result_id, note):
    payload = {
        "student_id": student_id,
        "week_start_date": week_start_dt.date().isoformat(),
        "selected_exam_result_id": selected_exam_result_id,
        "teacher_username": st.session_state.get('username'),
        "note": note,
        "updated_at": current_local_time().tz_convert('UTC').isoformat(),
    }
    supabase.table("weekly_primary_overrides").upsert(
        payload,
        on_conflict="student_id,week_start_date",
    ).execute()


def _clear_override(student_id, week_start_dt):
    supabase.table("weekly_primary_overrides").delete().eq(
        "student_id", student_id
    ).eq(
        "week_start_date", week_start_dt.date().isoformat()
    ).execute()


def show():
    st.header("📅 每週成績統計")
    st.write("統計規則：每週三 00:00 到下週二 23:59:59；週三關鍵成績占 50%，其餘最高 4 筆占 50%。")
    st.caption("學生公開查詢連結格式：正式後台網址後加上 ?view=student-weekly")

    week_start_dt, week_end_dt = get_week_bounds()
    st.info(f"本週統計區間：{week_start_dt.strftime('%Y-%m-%d %H:%M')} ~ {(week_end_dt - pd.Timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M')}")

    students_df = _load_visible_students()
    if students_df.empty:
        st.info("目前沒有可統計的學生資料。")
        return

    top_col1, top_col2 = st.columns([2, 1])
    with top_col1:
        class_options = ["全部"] + sorted([x for x in students_df['class_name'].dropna().unique().tolist() if safe_str(x)])
        selected_class = st.selectbox("班級篩選", class_options)
    with top_col2:
        current_pass_score = load_weekly_pass_score(supabase)
        pass_score = st.number_input("及格線", min_value=0, max_value=100, value=current_pass_score, step=1)
        if st.button("儲存及格線", use_container_width=True):
            try:
                save_weekly_pass_score(supabase, pass_score, st.session_state.get('username', ''))
                st.success("✅ 已更新全域及格線設定。")
                st.rerun()
            except Exception as exc:
                st.error("❌ 儲存及格線失敗，請先確認 Supabase 已執行 weekly_stats_setup.sql。")
                st.caption(str(exc))

    visible_students_df = students_df.copy()
    if selected_class != "全部":
        visible_students_df = visible_students_df[visible_students_df['class_name'] == selected_class].copy()

    student_ids = [safe_str(sid) for sid in visible_students_df['student_id'].tolist() if safe_str(sid)]
    results_df = _load_week_results(student_ids, week_start_dt, week_end_dt)
    override_rows = _load_week_overrides(student_ids, week_start_dt)

    summaries = build_weekly_summary(
        students_df=visible_students_df,
        results_df=results_df,
        week_start_dt=week_start_dt,
        week_end_dt=week_end_dt,
        pass_score=pass_score,
        override_rows=override_rows,
    )

    summary_df = pd.DataFrame([
        {
            '班級': item['class_name'],
            '座號': item['seat_number'],
            '學號': item['student_id'],
            '姓名': item['student_name'],
            '關鍵成績': item['primary_score'],
            '關鍵來源': item['primary_source'],
            '其他4筆': build_other_scores_display(item['other_scores']),
            '其他平均': item['other_average'],
            '總成績': item['total_score'],
            '結果': item['status_text'],
            '本週筆數': item['weekly_record_count'],
        }
        for item in summaries
    ])

    st.markdown(f"### 本週統計表（{len(summary_df)} 人）")
    if summary_df.empty:
        st.info("本週沒有可顯示的統計結果。")
    else:
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 老師手動指定週三關鍵成績")
    st.caption("用於學生請假或補測情況。只能從該學生本週三的成績中指定 1 筆作為關鍵成績。")

    summary_map = {f"{item['class_name']}｜{item['seat_number']}｜{item['student_id']}｜{item['student_name']}": item for item in summaries}
    if not summary_map:
        st.info("目前沒有可指定的學生。")
        return

    selected_student_label = st.selectbox("選擇學生", list(summary_map.keys()))
    selected_summary = summary_map[selected_student_label]
    wednesday_records = selected_summary['available_wednesday_records']

    if not wednesday_records:
        st.warning("這位學生本週三沒有任何成績紀錄，無法手動指定。")
        return

    record_options = {
        build_primary_candidate_label(record): safe_str(record.get('id'))
        for record in wednesday_records
    }

    current_primary_id = safe_str(selected_summary.get('primary_record_id'))
    option_labels = list(record_options.keys())
    default_index = 0
    for index, label in enumerate(option_labels):
        if record_options[label] == current_primary_id:
            default_index = index
            break

    selected_record_label = st.radio(
        "指定為本週關鍵成績的週三紀錄",
        option_labels,
        index=default_index,
    )
    note = st.text_input("備註（選填）", value="")

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("💾 儲存本週關鍵成績指定", use_container_width=True):
            try:
                _upsert_override(
                    student_id=selected_summary['student_id'],
                    week_start_dt=week_start_dt,
                    selected_exam_result_id=record_options[selected_record_label],
                    note=note,
                )
                st.success("✅ 已儲存本週關鍵成績指定。")
                st.rerun()
            except Exception as exc:
                st.error("❌ 儲存失敗，請先確認 Supabase 已執行 weekly_stats_setup.sql。")
                st.caption(str(exc))

    with action_col2:
        if st.button("🗑️ 清除本週手動指定", use_container_width=True):
            try:
                _clear_override(selected_summary['student_id'], week_start_dt)
                st.success("✅ 已清除本週手動指定，系統將回到自動判定。")
                st.rerun()
            except Exception as exc:
                st.error("❌ 清除失敗。")
                st.caption(str(exc))
