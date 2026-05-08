import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
from utils.supabase_client import supabase
from utils.weekly_stats import save_teacher_settings, load_teacher_settings


def _safe_str(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_compare_value(value):
    value_str = _safe_str(value)
    if not value_str:
        return ""

    try:
        numeric_value = float(value_str)
        if numeric_value.is_integer():
            return str(int(numeric_value))
        return str(numeric_value)
    except ValueError:
        return value_str


def _parse_categories(value):
    if isinstance(value, list):
        return [_safe_str(item) for item in value if _safe_str(item)]
    if isinstance(value, tuple):
        return [_safe_str(item) for item in value if _safe_str(item)]
    # 某些資料來源可能回傳 numpy array，避免 pd.isna(array) 觸發歧義錯誤
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, dict)):
        list_value = value.tolist()
        if isinstance(list_value, list):
            return [_safe_str(item) for item in list_value if _safe_str(item)]
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [_safe_str(item) for item in parsed if _safe_str(item)]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return [_safe_str(part) for part in raw.split(',') if _safe_str(part)]
    return [_safe_str(value)] if _safe_str(value) else []


def _format_categories(value):
    categories = _parse_categories(value)
    return "、".join(categories) if categories else "未設定"


def _build_print_html(report_df):
    printable_df = report_df.fillna("")
    table_html = printable_df.to_html(index=False, escape=True)
    return f"""
    <html>
    <head>
        <meta charset=\"utf-8\" />
        <title>學生測驗成績報表</title>
        <style>
            body {{ font-family: 'Microsoft JhengHei', sans-serif; padding: 24px; }}
            h1 {{ margin-bottom: 8px; font-size: 24px; }}
            p {{ margin-top: 0; color: #555; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
            th, td {{ border: 1px solid #bbb; padding: 8px; font-size: 12px; text-align: left; }}
            th {{ background: #f3f3f3; }}
            @media print {{
                body {{ padding: 0; }}
                button {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <h1>學生測驗成績報表</h1>
        <p>共 {len(printable_df)} 筆資料</p>
        {table_html}
        <script>
            window.onload = function() {{
                window.print();
            }};
        </script>
    </body>
    </html>
    """


def _build_status_text(score_value, pass_score):
    if pd.isna(score_value) or _safe_str(score_value) == "":
        return "無成績"

    try:
        return "不及格" if float(score_value) < float(pass_score) else ""
    except (TypeError, ValueError):
        return ""


def _style_report_row(row):
    remark = row.get("備註", "")
    if remark == "無成績":
        return ["background-color: #fff3cd"] * len(row)
    if remark == "不及格":
        return ["background-color: #f8d7da"] * len(row)
    return [""] * len(row)


def _find_invalid_exam_rows(result_df, students_df):
    """找出無法與 students 核對的成績資料。"""
    if result_df.empty:
        return pd.DataFrame()

    student_lookup = {}
    for _, row in students_df.iterrows():
        sid = _safe_str(row.get("student_id"))
        if sid and sid not in student_lookup:
            student_lookup[sid] = {
                "student_name": _safe_str(row.get("student_name") or row.get("name")),
                "class_name": _safe_str(row.get("class_name")),
                "seat_number": _safe_str(row.get("seat_number")),
                "teacher_username": _safe_str(row.get("teacher_username")),
            }

    invalid_rows = []
    for _, row in result_df.iterrows():
        sid = _safe_str(row.get("student_id"))
        student = student_lookup.get(sid)

        if not student:
            invalid_rows.append({**row.to_dict(), "invalid_reason": "學生資料不存在（學號查無對應）"})
            continue

        mismatch_fields = []
        result_name = _normalize_compare_value(row.get("student_name") or row.get("name"))
        if result_name and result_name != _normalize_compare_value(student["student_name"]):
            mismatch_fields.append("姓名")
        if _normalize_compare_value(row.get("class_name")) and _normalize_compare_value(row.get("class_name")) != _normalize_compare_value(student["class_name"]):
            mismatch_fields.append("班級")
        if _normalize_compare_value(row.get("seat_number")) and _normalize_compare_value(row.get("seat_number")) != _normalize_compare_value(student["seat_number"]):
            mismatch_fields.append("座號")

        if mismatch_fields:
            invalid_rows.append({**row.to_dict(), "invalid_reason": f"學生資料欄位不一致（{'、'.join(mismatch_fields)}）"})

    if not invalid_rows:
        return pd.DataFrame()

    return pd.DataFrame(invalid_rows)


def _find_duplicate_exam_rows(result_df, window_seconds=60):
    """找出疑似重複上傳的成績資料（同學號且時間落在同一群組）。

    群組規則：同一 student_id，前後時間差 <= window_seconds 視為同一重複群。
    保留規則：每群保留分數最高；同分再比答對題數；再同則保留最早一筆。
    """
    if result_df.empty or 'id' not in result_df.columns:
        return pd.DataFrame()

    work_df = result_df.copy()

    if 'created_at_dt' in work_df.columns:
        work_df['_created_at_dt'] = pd.to_datetime(work_df['created_at_dt'], utc=True, errors='coerce')
    else:
        work_df['_created_at_dt'] = pd.to_datetime(work_df.get('created_at'), utc=True, errors='coerce')

    for col in ['student_id', 'score', 'correct_count', 'time_spent', 'total_questions', 'student_name', 'class_name', 'seat_number']:
        if col not in work_df.columns:
            work_df[col] = None

    work_df = work_df[work_df['student_id'].notna() & work_df['_created_at_dt'].notna()].copy()
    if work_df.empty:
        return pd.DataFrame()

    work_df['student_id'] = work_df['student_id'].astype(str)
    work_df['_score_num'] = pd.to_numeric(work_df['score'], errors='coerce').fillna(-1)
    work_df['_correct_num'] = pd.to_numeric(work_df['correct_count'], errors='coerce').fillna(-1)

    work_df = work_df.sort_values(by=['student_id', '_created_at_dt', 'id'], ascending=[True, True, True])

    group_ids = []
    current_group = 0
    last_sid = None
    last_time = None

    for _, row in work_df.iterrows():
        sid = row['student_id']
        t = row['_created_at_dt']

        if last_sid is None or sid != last_sid:
            current_group += 1
        else:
            diff_seconds = abs((t - last_time).total_seconds())
            if diff_seconds > window_seconds:
                current_group += 1

        group_ids.append(current_group)
        last_sid = sid
        last_time = t

    work_df['_dup_group_id'] = group_ids
    work_df['_dup_group_size'] = work_df.groupby('_dup_group_id')['id'].transform('count')

    grouped_df = work_df[work_df['_dup_group_size'] > 1].copy()
    if grouped_df.empty:
        return pd.DataFrame()

    grouped_df = grouped_df.sort_values(
        by=['_dup_group_id', '_score_num', '_correct_num', '_created_at_dt', 'id'],
        ascending=[True, False, False, True, True]
    )
    grouped_df['_keep_rank'] = grouped_df.groupby('_dup_group_id').cumcount() + 1
    grouped_df = grouped_df.sort_values(by=['student_id', '_created_at_dt', 'id'], ascending=[True, True, True])

    grouped_df['_is_keep'] = grouped_df['_keep_rank'] == 1
    grouped_df['_delete_recommended'] = ~grouped_df['_is_keep']
    grouped_df['duplicate_reason'] = grouped_df.apply(
        lambda row: f"同學號且前後 {window_seconds} 秒內重複上傳（群組 {int(row['_dup_group_id'])}）",
        axis=1
    )

    return grouped_df

def show():
    st.header("📝 成績報表查詢")
    st.write("您可以在此查看學生的測驗成績，並進行篩選與匯出。")
    
    # 取得老師身份
    teacher_username = st.session_state.get('username', '')
    
    # 1. 從 Supabase 撈取成績資料 (依時間遞減排序)
    response = supabase.table("exam_results").select("*").order("created_at", desc=True).execute()
    data = response.data or []
        
    # 2. 將資料轉換為 Pandas DataFrame 以便處理
    df = pd.DataFrame(data)
    if df.empty:
        df = pd.DataFrame(columns=[
            'created_at', 'class_name', 'seat_number', 'student_id', 'student_name',
            'score', 'correct_count', 'time_spent', 'categories'
        ])
    
    # 先取得學生主檔，用來做權限與資料有效性核對
    students_res = supabase.table("students").select("student_id,name,class_name,seat_number,teacher_username").execute()
    students_df = pd.DataFrame(students_res.data or [])
    visible_students_df = students_df.copy()

    # exam_results 可能使用 name 或 student_name，統一成 student_name 供後續流程使用
    if 'student_name' not in df.columns and 'name' in df.columns:
        df['student_name'] = df['name']
    elif 'student_name' not in df.columns:
        df['student_name'] = ""

    for required_col in ['class_name', 'seat_number', 'student_id', 'score', 'correct_count', 'time_spent', 'created_at']:
        if required_col not in df.columns:
            df[required_col] = None

    if 'categories' not in df.columns:
        df['categories'] = [[] for _ in range(len(df))]

    df['category_list'] = df['categories'].apply(_parse_categories)
    df['work_items_display'] = df['category_list'].apply(_format_categories)
    df['created_at_dt'] = pd.to_datetime(df['created_at'], utc=True, errors='coerce')

    # 【權限控管】如果是一般老師，只能看到自己學生的成績
    if st.session_state.get('role') != 'admin':
        # 先查出該老師的所有學生學號
        my_student_ids = []
        if not visible_students_df.empty:
            visible_students_df = visible_students_df[visible_students_df['teacher_username'] == st.session_state.get('username')].copy()
            my_student_ids = [
                s for s in visible_students_df['student_id'].tolist()
                if s is not None
            ]
        # 過濾成績表
        df = df[df['student_id'].isin(my_student_ids)]

    if df.empty and visible_students_df.empty:
        st.info("💡 目前沒有可顯示的學生或測驗資料。")
        return

    # 2.5 找出無效資料，並提供刪除功能
    invalid_df = _find_invalid_exam_rows(df, students_df)
    if not invalid_df.empty:
        with st.expander(f"🧹 無效資料清理（{len(invalid_df)} 筆）", expanded=False):
            st.warning("以下紀錄無法和學生主檔核對，建議先清理。")

            invalid_display_cols = {
                'created_at': '測驗時間',
                'class_name': '班級',
                'seat_number': '座號',
                'student_id': '學號',
                'student_name': '姓名',
                'score': '分數',
                'invalid_reason': '無效原因'
            }

            show_cols = [c for c in invalid_display_cols.keys() if c in invalid_df.columns]
            st.dataframe(
                invalid_df[show_cols].rename(columns={k: v for k, v in invalid_display_cols.items() if k in show_cols}),
                use_container_width=True,
                hide_index=True
            )

            if 'id' not in invalid_df.columns:
                st.error("⚠️ exam_results 缺少 id 欄位，無法執行刪除。")
            else:
                target_invalid_df = invalid_df.copy()
                if st.session_state.get('role') != 'admin':
                    # 教師僅能刪除「自己學生」的無效紀錄
                    my_student_ids_set = set(df['student_id'].dropna().tolist())
                    target_invalid_df = target_invalid_df[target_invalid_df['student_id'].isin(my_student_ids_set)]

                if target_invalid_df.empty:
                    st.info("目前沒有可由您刪除的無效資料。")
                else:
                    preview_state_key = "invalid_delete_preview_ids"
                    ids_to_delete_now = [x for x in target_invalid_df['id'].tolist() if x is not None]
                    id_set_now = set(ids_to_delete_now)

                    st.caption("步驟 1：先產生預覽清單，再進行二次確認刪除。")
                    if st.button("📋 產生刪除預覽清單", use_container_width=True):
                        st.session_state[preview_state_key] = ids_to_delete_now

                    preview_ids = st.session_state.get(preview_state_key, [])
                    preview_ids = [x for x in preview_ids if x in id_set_now]

                    if preview_ids:
                        preview_df = target_invalid_df[target_invalid_df['id'].isin(preview_ids)].copy()
                        st.markdown(f"##### 預覽將刪除資料（共 {len(preview_df)} 筆）")
                        st.dataframe(
                            preview_df[show_cols].rename(columns={k: v for k, v in invalid_display_cols.items() if k in show_cols}),
                            use_container_width=True,
                            hide_index=True
                        )

                        st.caption("步驟 2：二次確認後才可刪除。")
                        confirm = st.checkbox("我確認要刪除以上預覽資料")
                        confirm_text = st.text_input("請輸入 DELETE 進行二次確認", value="")
                        button_label = "🗑️ 刪除全部無效資料" if st.session_state.get('role') == 'admin' else "🗑️ 刪除我的學生無效資料"

                        can_delete = confirm and (confirm_text.strip().upper() == "DELETE")
                        if st.button(button_label, type="primary", disabled=not can_delete):
                            ids_to_delete = preview_ids
                            deleted_count = 0
                            error_message = None

                            for i in range(0, len(ids_to_delete), 100):
                                chunk = ids_to_delete[i:i + 100]
                                try:
                                    supabase.table("exam_results").delete().in_("id", chunk).execute()
                                    deleted_count += len(chunk)
                                except Exception as e:
                                    error_message = str(e)
                                    break

                            if error_message:
                                st.error(f"❌ 刪除失敗：{error_message}")
                            else:
                                st.session_state.pop(preview_state_key, None)
                                st.success(f"✅ 已刪除 {deleted_count} 筆無效資料。")
                                st.rerun()
                    else:
                        st.info("尚未建立刪除預覽清單。請先點擊「產生刪除預覽清單」。")

    # 2.6 找出重複上傳資料，並提供刪除功能
    duplicate_rule = st.selectbox(
        "重複成績判定規則",
        options=["同秒", "1分鐘內"],
        index=1,
        help="同學號在時間窗內視為同一次上傳群組；每群預設保留高分。",
    )
    duplicate_window_seconds = 0 if duplicate_rule == "同秒" else 60
    duplicate_df = _find_duplicate_exam_rows(df, window_seconds=duplicate_window_seconds)

    with st.expander(f"🔁 重複成績清理（{len(duplicate_df)} 筆）", expanded=False):
        st.caption(
            f"目前規則：同學號且前後時間差 <= {duplicate_window_seconds} 秒視為同群組；每群預設保留分數最高者。"
        )

        if duplicate_df.empty:
            st.info("目前未偵測到重複成績資料。")
        else:
            st.warning("請先確認勾選內容，刪除後將無法復原。系統已預設勾選建議刪除列。")

            target_duplicate_df = duplicate_df.copy()
            if st.session_state.get('role') != 'admin':
                my_students = set(
                    visible_students_df['student_id'].dropna().astype(str).tolist()
                )
                target_duplicate_df = target_duplicate_df[
                    target_duplicate_df['student_id'].astype(str).isin(my_students)
                ]

            if target_duplicate_df.empty:
                st.info("目前沒有可由您刪除的重複資料。")
            else:
                editor_df = target_duplicate_df.copy()
                editor_df['選取刪除'] = editor_df['_delete_recommended']
                editor_df['保留建議'] = editor_df['_is_keep'].apply(lambda x: '建議保留' if x else '')
                editor_df['測驗時間'] = pd.to_datetime(editor_df['created_at'], utc=True, errors='coerce').dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d %H:%M:%S')

                editable_cols = [
                    '選取刪除', '保留建議', '測驗時間', 'class_name', 'seat_number',
                    'student_id', 'student_name', 'score', 'correct_count', 'time_spent', 'duplicate_reason'
                ]
                editable_cols = [c for c in editable_cols if c in editor_df.columns]

                edited_df = st.data_editor(
                    editor_df[editable_cols],
                    use_container_width=True,
                    hide_index=True,
                    disabled=[c for c in editable_cols if c != '選取刪除'],
                    key='duplicate_rows_editor',
                )

                ids_map = editor_df.reset_index(drop=True)['id'].tolist()
                selected_ids = [
                    ids_map[idx]
                    for idx, row in edited_df.reset_index(drop=True).iterrows()
                    if bool(row.get('選取刪除', False))
                ]

                st.error("⚠️ 重要提醒：按下刪除後，資料會直接從 exam_results 移除且無法復原。")
                st.caption(f"目前勾選刪除筆數：{len(selected_ids)}")

                confirm_dup = st.checkbox("我已再次確認要刪除以上勾選資料")
                confirm_dup_text = st.text_input("請輸入 DELETE 進行二次確認", value="")
                dup_button_label = "🗑️ 刪除勾選的重複資料"

                can_delete_dup = (
                    len(selected_ids) > 0 and
                    confirm_dup and
                    (confirm_dup_text.strip().upper() == "DELETE")
                )

                if st.button(dup_button_label, type="primary", disabled=not can_delete_dup):
                    deleted_count = 0
                    error_message = None

                    for i in range(0, len(selected_ids), 100):
                        chunk = selected_ids[i:i + 100]
                        try:
                            supabase.table("exam_results").delete().in_("id", chunk).execute()
                            deleted_count += len(chunk)
                        except Exception as e:
                            error_message = str(e)
                            break

                    if error_message:
                        st.error(f"❌ 刪除失敗：{error_message}")
                    else:
                        st.success(f"✅ 已刪除 {deleted_count} 筆重複資料。")
                        st.rerun()
    
    # 轉換時間格式 (將 UTC 轉為台灣時間)
    df['created_at_display'] = df['created_at_dt'].dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # 3. 建立篩選器 (Filters)
    st.markdown("### 🔍 資料篩選")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 班級清單優先以學生名冊為主，避免「沒人測驗的班級」無法選取
        class_values = set(df['class_name'].dropna().unique())
        if not visible_students_df.empty:
            class_values.update(visible_students_df['class_name'].dropna().unique())
        classes = ["全部"] + sorted(class_values)
        selected_class = st.selectbox("選擇班級", classes)
        
    with col2:
        all_work_items = sorted({item for items in df['category_list'] for item in items if item})
        selected_work_items = st.multiselect("選擇工作項目", all_work_items)

    with col3:
        search_text = st.text_input("搜尋姓名或學號 (輸入關鍵字)")

    option_col1, option_col2 = st.columns(2)
    with option_col1:
        include_unscored_students = st.checkbox("補列未測學生", help="勾選後，會把所選班級中未出現在目前篩選結果內的學生一併列出，並標註為無成績。")
    with option_col2:
        # 根據選中的班級載入設定
        if selected_class != "全部":
            teacher_settings = load_teacher_settings(supabase, teacher_username, selected_class)
            current_class = selected_class
        else:
            # 如果是「全部」，載入老師全局設定
            teacher_settings = load_teacher_settings(supabase, teacher_username, "")
            current_class = None
        
        default_pass_score = teacher_settings['pass_score']
        
        def _on_pass_score_change():
            """及格標準改變時自動保存到資料庫"""
            new_pass_score = st.session_state.get('pass_score_input', default_pass_score)
            try:
                save_teacher_settings(
                    supabase,
                    teacher_username,
                    pass_score=new_pass_score,
                    week_start_weekday=teacher_settings['week_start_weekday'],
                    primary_slot_start_hour=teacher_settings['primary_slot_start_hour'],
                    primary_slot_end_hour=teacher_settings['primary_slot_end_hour'],
                    class_name=current_class or "",
                )
                class_label = f"【{current_class}】" if current_class else "【全局設定】"
                st.toast(f"✓ 及格標準已更新為 {new_pass_score} {class_label}", icon="✅")
            except Exception as e:
                st.error(f"保存及格標準時出錯: {e}")
        
        pass_score = st.number_input(
            "及格標準", 
            min_value=0, 
            max_value=100, 
            value=default_pass_score,
            step=1,
            key='pass_score_input',
            on_change=_on_pass_score_change,
            help=f"目前班級：{selected_class if selected_class != '全部' else '全局'}"
        )

    valid_dates = df['created_at_dt'].dropna()
    if valid_dates.empty:
        today = pd.Timestamp.now(tz='Asia/Taipei').date()
        min_date = today
        max_date = today
    else:
        min_date = valid_dates.dt.tz_convert('Asia/Taipei').dt.date.min()
        max_date = valid_dates.dt.tz_convert('Asia/Taipei').dt.date.max()

    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input(
            "開始日期",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            format="YYYY-MM-DD",
            key="score_report_start_date"
        )
    with date_col2:
        end_date = st.date_input(
            "結束日期",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            format="YYYY-MM-DD",
            key="score_report_end_date"
        )
        
    # 4. 應用篩選條件
    filtered_df = df.copy()
    if selected_class != "全部":
        filtered_df = filtered_df[filtered_df['class_name'] == selected_class]

    scoped_students_df = visible_students_df.copy()
    if selected_class != "全部" and not scoped_students_df.empty:
        scoped_students_df = scoped_students_df[scoped_students_df['class_name'] == selected_class].copy()

    if selected_work_items:
        selected_work_items_set = set(selected_work_items)
        filtered_df = filtered_df[
            filtered_df['category_list'].apply(lambda items: bool(set(items) & selected_work_items_set))
        ]

    if start_date > end_date:
        st.warning("開始日期晚於結束日期，系統已自動交換區間。")
        start_date, end_date = end_date, start_date

    if not filtered_df.empty:
        local_dates = filtered_df['created_at_dt'].dt.tz_convert('Asia/Taipei').dt.date
        filtered_df = filtered_df[(local_dates >= start_date) & (local_dates <= end_date)]
        
    if search_text:
        # 支援姓名或學號的模糊搜尋
        filtered_df = filtered_df[
            filtered_df['student_name'].str.contains(search_text, na=False) | 
            filtered_df['student_id'].str.contains(search_text, na=False)
        ]
        if not scoped_students_df.empty:
            scoped_students_df = scoped_students_df[
                scoped_students_df['name'].str.contains(search_text, na=False) |
                scoped_students_df['student_id'].astype(str).str.contains(search_text, na=False)
            ]

    if include_unscored_students:
        if selected_class == "全部":
            st.info("啟用「補列未測學生」時，請先選擇單一班級。")
        elif scoped_students_df.empty:
            st.info("這個班級沒有學生資料可供補列。")
        else:
            tested_ids = set(filtered_df['student_id'].dropna().astype(str).tolist())
            missing_students_df = scoped_students_df[
                ~scoped_students_df['student_id'].astype(str).isin(tested_ids)
            ].copy()

            if not missing_students_df.empty:
                missing_students_df['created_at_display'] = ""
                missing_students_df['work_items_display'] = "、".join(selected_work_items) if selected_work_items else "未測驗"
                missing_students_df['student_name'] = missing_students_df['name']
                missing_students_df['score'] = None
                missing_students_df['correct_count'] = None
                missing_students_df['time_spent'] = None
                missing_students_df['created_at_dt'] = pd.NaT
                filtered_df = pd.concat([
                    filtered_df,
                    missing_students_df[[
                        'created_at_display', 'class_name', 'work_items_display', 'seat_number',
                        'student_id', 'student_name', 'score', 'correct_count', 'time_spent', 'created_at_dt'
                    ]]
                ], ignore_index=True, sort=False)

    if 'created_at_display' not in filtered_df.columns:
        filtered_df['created_at_display'] = filtered_df['created_at_dt'].dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d %H:%M:%S')

    filtered_df['備註'] = filtered_df['score'].apply(lambda value: _build_status_text(value, pass_score))
    filtered_df = filtered_df.sort_values(
        by=['class_name', 'seat_number', 'created_at_dt'],
        ascending=[True, True, False],
        na_position='last'
    )
        
    # 5. 定義要顯示的欄位與中文名稱
    display_cols = {
        'created_at_display': '測驗時間',
        'class_name': '班級',
        'work_items_display': '工作項目',
        'seat_number': '座號',
        'student_id': '學號',
        'student_name': '姓名',
        'score': '分數',
        'correct_count': '答對題數',
        'time_spent': '花費時間(秒)',
        '備註': '備註'
    }
    
    st.markdown(f"### 📊 查詢結果 (共 {len(filtered_df)} 筆)")
    
    # 顯示資料表
    export_df = filtered_df[list(display_cols.keys())].rename(columns=display_cols)

    st.dataframe(
        export_df.style.apply(_style_report_row, axis=1),
        use_container_width=True,
        hide_index=True
    )

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("🖨️ 列印目前篩選結果", use_container_width=True):
            components.html(_build_print_html(export_df), height=0)
    with action_col2:
        st.download_button(
            label="📥 匯出為 Excel (CSV)",
            data=export_df.to_csv(index=False).encode('utf-8-sig'),
            file_name='學生測驗成績報表.csv',
            mime='text/csv',
            use_container_width=True,
        )
