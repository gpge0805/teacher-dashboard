import io

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.supabase_client import supabase
from utils.weekly_stats import (
    build_primary_candidate_label,
    build_weekly_summary,
    current_local_time,
    get_week_bounds,
    load_teacher_settings,
    load_weekly_pass_score,
    prepare_results_dataframe,
    save_teacher_settings,
    save_weekly_pass_score,
    safe_str,
    WEEKDAY_LABELS,
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


def _format_score_cell(value):
    num = pd.to_numeric(value, errors='coerce')
    if pd.isna(num):
        return "0"
    return str(int(num)) if float(num).is_integer() else f"{float(num):.2f}"


def _build_report_dataframe(summaries):
    rows = []
    for item in summaries:
        other_scores = list(item.get('other_scores', []))
        if len(other_scores) < 4:
            other_scores.extend([0.0] * (4 - len(other_scores)))
        rows.append(
            {
                '座號': safe_str(item.get('seat_number')),
                '姓名': safe_str(item.get('student_name')),
                '星期三成績1(50%)': _format_score_cell(item.get('primary_score', 0)),
                '成績2': _format_score_cell(other_scores[0]),
                '成績3': _format_score_cell(other_scores[1]),
                '成績4': _format_score_cell(other_scores[2]),
                '成績5': _format_score_cell(other_scores[3]),
                '總成績': _format_score_cell(item.get('total_score', 0)),
                '備註(及格不及格)': safe_str(item.get('status_text')),
            }
        )

    report_df = pd.DataFrame(rows)
    if report_df.empty:
        return report_df

    report_df['座號排序'] = pd.to_numeric(report_df['座號'], errors='coerce')
    report_df = report_df.sort_values(by=['座號排序', '座號', '姓名'], ascending=[True, True, True], na_position='last')
    return report_df.drop(columns=['座號排序'])


def _build_report_header_text(selected_class, week_start_dt, week_end_dt, pass_score):
    stats_time = f"{week_start_dt.strftime('%Y-%m-%d %H:%M')} ~ {(week_end_dt - pd.Timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M')}"
    print_time = current_local_time().strftime('%Y-%m-%d %H:%M:%S')
    class_text = selected_class if selected_class != "全部" else "全部班級"
    calc_text = "星期三成績1占50%，其餘成績2-5取本週最高4筆平均占50%，不足補0。"
    return {
        '班級': class_text,
        '統計時間': stats_time,
        '及格分數': str(int(pass_score) if float(pass_score).is_integer() else pass_score),
        '成績計算說明(簡略)': calc_text,
        '列印時間': print_time,
    }


def _render_print_section(report_df, header_info):
    if report_df.empty:
        return

    table_html = report_df.to_html(index=False, classes='report-table', border=1)
    html = f"""
    <div>
      <button onclick=\"window.print()\" style=\"margin-bottom:10px;padding:8px 14px;border:1px solid #999;border-radius:6px;background:#fff;cursor:pointer;\">列印目前報表</button>
      <div id=\"weekly-report\" style=\"font-family: 'Microsoft JhengHei', sans-serif; color:#111;\">
        <h3 style=\"margin:0 0 8px 0;\">每週班級成績報表</h3>
        <p style=\"margin:2px 0;\"><strong>班級：</strong>{header_info['班級']}</p>
        <p style=\"margin:2px 0;\"><strong>統計時間：</strong>{header_info['統計時間']}</p>
        <p style=\"margin:2px 0;\"><strong>及格分數：</strong>{header_info['及格分數']}</p>
        <p style=\"margin:2px 0;\"><strong>成績計算說明(簡略)：</strong>{header_info['成績計算說明(簡略)']}</p>
        <p style=\"margin:2px 0 10px 0;\"><strong>列印時間：</strong>{header_info['列印時間']}</p>
        {table_html}
      </div>
      <style>
        .report-table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
        .report-table th, .report-table td {{ border: 1px solid #333; padding: 6px 8px; text-align: center; }}
        .report-table th {{ background: #f0f0f0; }}
        @media print {{
          button {{ display: none !important; }}
        }}
      </style>
    </div>
    """
    components.html(html, height=700, scrolling=True)


def _to_excel_bytes(report_df, header_info):
    output = io.BytesIO()
    export_df = report_df.copy()
    for key, value in header_info.items():
        export_df.insert(len(export_df.columns), key if key not in export_df.columns else f"{key}_資訊", "")
        export_df.at[0, key if key not in export_df.columns else f"{key}_資訊"] = value

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='每週成績報表')
    output.seek(0)
    return output.getvalue()


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
    st.header("📅 每週成績統計")
    st.caption("學生公開查詢連結格式：正式後台網址後加上 ?view=student-weekly")

    teacher_username = st.session_state.get('username', '')
    
    # ── 全局周期設定區（不因班級改變）──────────────────────────────────────────
    ts_global = load_teacher_settings(supabase, teacher_username, "")

    with st.expander("⚙️ 成績統計週期設定", expanded=False):
        st.caption("設定儲存後，下方統計與學生查詢頁都會套用你的個人設定。")
        cfg_col1, cfg_col2, cfg_col3, cfg_col4 = st.columns(4)
        weekday_options = list(WEEKDAY_LABELS.keys())   # [0,1,2,3,4,5,6]
        with cfg_col1:
            cfg_weekday = st.selectbox(
                "週期起始星期",
                weekday_options,
                format_func=lambda d: WEEKDAY_LABELS[d],
                index=weekday_options.index(ts_global['week_start_weekday']),
                help="每週統計從哪天 00:00 開始",
            )
        with cfg_col2:
            cfg_slot_start = st.number_input(
                "關鍵時段（開始小時）", min_value=0, max_value=23,
                value=ts_global['primary_slot_start_hour'], step=1,
                help="例如 15 → 15:00",
            )
        with cfg_col3:
            cfg_slot_end = st.number_input(
                "關鍵時段（結束小時）", min_value=1, max_value=24,
                value=ts_global['primary_slot_end_hour'], step=1,
                help="例如 16 → 到 15:59 截止",
            )
        if st.button("💾 儲存週期設定", use_container_width=True):
            if int(cfg_slot_start) >= int(cfg_slot_end):
                st.error("關鍵時段結束小時必須大於開始小時。")
            else:
                try:
                    save_teacher_settings(
                        supabase, teacher_username,
                        pass_score=ts_global['pass_score'],
                        week_start_weekday=cfg_weekday,
                        primary_slot_start_hour=cfg_slot_start,
                        primary_slot_end_hour=cfg_slot_end,
                        class_name="",
                    )
                    st.success("✅ 週期設定已儲存。")
                    st.rerun()
                except Exception as exc:
                    st.error("❌ 儲存失敗，請先在 Supabase 執行 teacher_cycle_settings_migration.sql。")
                    st.caption(str(exc))

    week_start_weekday = ts_global['week_start_weekday']
    primary_slot_start = ts_global['primary_slot_start_hour']
    primary_slot_end = ts_global['primary_slot_end_hour']

    st.write(
        f"統計規則：每週 **{WEEKDAY_LABELS[week_start_weekday]}** 00:00 到下週"
        f" **{WEEKDAY_LABELS[(week_start_weekday + 6) % 7]}** 23:59:59；"
        f"關鍵時段 **{primary_slot_start:02d}:00–{primary_slot_end:02d}:00** 成績占 50%，其餘最高 4 筆占 50%。"
    )

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
    st.info(f"目前統計區間：{week_start_dt.strftime('%Y-%m-%d %H:%M')} ~ {(week_end_dt - pd.Timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M')}")

    students_df = _load_visible_students()
    if students_df.empty:
        st.info("目前沒有可統計的學生資料。")
        return

    class_options = sorted([x for x in students_df['class_name'].dropna().unique().tolist() if safe_str(x)])
    if not class_options:
        st.info("目前沒有可統計的班級資料。")
        return
    selected_class = st.selectbox("班級篩選", class_options)

    # ── 班級級及格標準設定區（根據選定班級變化）──────────────────────────────────────────
    ts_class = load_teacher_settings(supabase, teacher_username, selected_class)
    with st.expander(f"⚙️ 【{selected_class}】及格標準設定", expanded=False):
        st.caption(f"設定儲存後，該班級的成績統計與學生查詢會套用此及格標準。")
        pass_score_input = st.number_input(
            "及格標準（分數）", 
            min_value=0, max_value=100,
            value=ts_class['pass_score'], 
            step=1,
            help=f"預設值為全局設定 {ts_global['pass_score']} 分",
        )
        if st.button(f"💾 儲存【{selected_class}】設定", use_container_width=True):
            try:
                save_teacher_settings(
                    supabase, teacher_username,
                    pass_score=pass_score_input,
                    week_start_weekday=ts_global['week_start_weekday'],
                    primary_slot_start_hour=ts_global['primary_slot_start_hour'],
                    primary_slot_end_hour=ts_global['primary_slot_end_hour'],
                    class_name=selected_class,
                )
                st.success(f"✅ 【{selected_class}】及格標準已儲存為 {pass_score_input} 分。")
                st.rerun()
            except Exception as exc:
                st.error(f"❌ 儲存失敗，請確認班級名稱或聯絡系統管理員。")
                st.caption(str(exc))

    pass_score = ts_class['pass_score']

    visible_students_df = students_df[students_df['class_name'] == selected_class].copy()

    student_ids = [safe_str(sid) for sid in visible_students_df['student_id'].tolist() if safe_str(sid)]
    results_df = _load_week_results(student_ids, week_start_dt, week_end_dt)
    valid_results_df = prepare_results_dataframe(results_df)
    if valid_results_df.empty:
        st.info("當週沒有成績")
        return

    override_rows = _load_week_overrides(student_ids, week_start_dt)

    summaries = build_weekly_summary(
        students_df=visible_students_df,
        results_df=results_df,
        week_start_dt=week_start_dt,
        week_end_dt=week_end_dt,
        pass_score=pass_score,
        override_rows=override_rows,
        primary_slot_start_hour=primary_slot_start,
        primary_slot_end_hour=primary_slot_end,
    )

    report_df = _build_report_dataframe(summaries)
    header_info = _build_report_header_text(selected_class, week_start_dt, week_end_dt, pass_score)

    st.markdown(f"### 本週統計表（{len(report_df)} 人）")
    if report_df.empty:
        st.info("本週沒有可顯示的統計結果。")
    else:
        st.markdown("#### 報表資訊")
        info_df = pd.DataFrame([header_info])
        st.dataframe(info_df, use_container_width=True, hide_index=True)

        st.markdown("#### 班級成績總表")
        st.dataframe(report_df, use_container_width=True, hide_index=True)

        csv_data = report_df.to_csv(index=False).encode('utf-8-sig')
        report_time_key = current_local_time().strftime('%Y%m%d_%H%M%S')
        class_key = safe_str(header_info['班級']).replace(' ', '_') or 'all_classes'

        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                label="⬇️ 下載 CSV 報表",
                data=csv_data,
                file_name=f"weekly_report_{class_key}_{report_time_key}.csv",
                mime='text/csv',
                use_container_width=True,
            )
        with dl_col2:
            try:
                excel_data = _to_excel_bytes(report_df, header_info)
                st.download_button(
                    label="⬇️ 下載 Excel 報表",
                    data=excel_data,
                    file_name=f"weekly_report_{class_key}_{report_time_key}.xlsx",
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True,
                )
            except Exception as exc:
                st.warning("目前無法產生 Excel，請先安裝 openpyxl。可先使用 CSV 下載。")
                st.caption(str(exc))

        st.markdown("#### 列印報表")
        _render_print_section(report_df, header_info)

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
