import streamlit as st
import pandas as pd
import json
import os
from collections import Counter, defaultdict
from utils.supabase_client import supabase


def _safe_str(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _parse_categories(value):
    if isinstance(value, list):
        return [_safe_str(item) for item in value if _safe_str(item)]
    if isinstance(value, tuple):
        return [_safe_str(item) for item in value if _safe_str(item)]
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

def load_questions():
    base_dir = os.path.dirname(__file__)
    possible_paths = [
        os.path.abspath(os.path.join(base_dir, '..', 'questions.json')),
        os.path.abspath(os.path.join(base_dir, '..', '..', '工業電子丙級學科互動式題庫v1-0331', 'src', 'data', 'questions.json')),
        os.path.abspath(os.path.join(base_dir, '..', '..', 'src', 'data', 'questions.json')),
        os.path.abspath(os.path.join(base_dir, '..', 'src', 'data', 'questions.json')),
        os.path.abspath(os.path.join(os.getcwd(), '工業電子丙級學科互動式題庫v1-0331', 'src', 'data', 'questions.json')),
        os.path.abspath(os.path.join(os.getcwd(), '..', 'src', 'data', 'questions.json')),
        os.path.abspath(os.path.join(os.getcwd(), 'src', 'data', 'questions.json')),
        os.path.abspath(os.path.join(os.getcwd(), 'questions.json')),
    ]
    
    for file_path in possible_paths:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                st.error(f"讀取題庫檔案失敗 ({file_path}): {e}")
                return []
                
    st.error(f"找不到題庫檔案！已嘗試以下路徑: {possible_paths}")
    return []

def parse_wrong_question_id(question_id):
    """將前端錯題 ID 轉為可查題庫的鍵值。

    支援格式：
    - c_工作項目03_1 -> (工作項目03, 1)
    - 1 -> (None, 1)
    """
    question_id_str = str(question_id).strip()
    parts = question_id_str.split('_')

    if len(parts) >= 3 and parts[-1].isdigit():
        category = parts[-2]
        local_id = parts[-1]
        return category, local_id, question_id_str

    return None, question_id_str, question_id_str

def get_correct_answer_text(question_info):
    ans_idx_str = question_info.get('answer', '1')
    try:
        ans_idx = int(ans_idx_str) - 1
        options = question_info.get('options', [])
        return options[ans_idx] if 0 <= ans_idx < len(options) else "未知"
    except (TypeError, ValueError, IndexError):
        return "未知"


# ── 工作項目名稱對應表 ──────────────────────────────────
CATEGORY_DISPLAY_NAMES = {
    "工作項目01": "工作項目01：電子電機識圖",
    "工作項目02": "工作項目02：手工具及量具知識",
    "工作項目03": "工作項目03：零組件知識",
    "工作項目04": "工作項目04：裝配知識",
    "工作項目05": "工作項目05：電子儀表使用知識",
    "工作項目06": "工作項目06：測試知識",
    "工作項目07": "工作項目07：電工學",
    "工作項目08": "工作項目08：電子學",
    "工作項目09": "工作項目09：數位系統",
}


def _get_display_name(category):
    """取得工作項目的顯示名稱，共同科目保持原名。"""
    return CATEGORY_DISPLAY_NAMES.get(category, category)


def _normalize_category(cat_name):
    """將考試記錄中的長名稱（如「工作項目04：儀表操作」）正規化為題庫短名稱（如「工作項目04」）。
    共同科目保持原樣（題庫本身就是長名稱）。"""
    import re
    # 工作項目XX：描述 -> 工作項目XX
    m = re.match(r'^(工作項目\d+)', cat_name)
    if m:
        return m.group(1)
    return cat_name


def _severity_color(rate):
    """依錯誤率回傳嚴重程度 emoji。"""
    if rate >= 50:
        return "🔴"
    elif rate >= 30:
        return "🟡"
    return "🟢"


def show():
    st.header("📈 錯題弱點分析")
    st.write("分析學生在測驗中最常答錯的題目，幫助您掌握教學重點。")
    
    # ── 1. 撈取測驗成績資料 ──
    query = supabase.table("exam_results").select("*")
    response = query.execute()
    data = response.data
    
    if not data:
        st.info("💡 目前還沒有任何測驗成績紀錄，無法進行分析。")
        return
        
    df = pd.DataFrame(data)

    if 'categories' not in df.columns:
        df['categories'] = [[] for _ in range(len(df))]

    df['category_list'] = df['categories'].apply(_parse_categories)
    df['created_at_dt'] = pd.to_datetime(df['created_at'], utc=True, errors='coerce')
    
    # 【權限控管】一般老師只看自己學生
    if st.session_state. - 技能檢定學科測驗互動系統get('role') != 'admin':
        student_res = supabase.table("students").select("student_id").eq("teacher_username", st.session_state.get('username')).execute()
        my_student_ids = [s['student_id'] for s in student_res.data]
        df = df[df['student_id'].isin(my_student_ids)]
        if df.empty:
            st.info("💡 您的學生目前還沒有任何測驗成績紀錄。")
            return
            
    # ── 2. 篩選器 ──
    st.markdown("### 🔍 分析範圍篩選")
    col1, col2 = st.columns(2)
    
    with col1:
        classes = ["全部"] + sorted(df['class_name'].dropna().unique().tolist())
        selected_class = st.selectbox("選擇班級", classes)

    valid_dates = df['created_at_dt'].dropna()
    if valid_dates.empty:
        today = pd.Timestamp.now(tz='Asia/Taipei').date()
        min_date = today
        max_date = today
    else:
        min_date = valid_dates.dt.tz_convert('Asia/Taipei').dt.date.min()
        max_date = valid_dates.dt.tz_convert('Asia/Taipei').dt.date.max()

    with col2:
        date_range = st.date_input(
            "時間範圍",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="YYYY-MM-DD",
            key="weakness_date_range"
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date = end_date = date_range
        
    # 套用篩選
    if selected_class != "全部":
        df = df[df['class_name'] == selected_class]

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    local_dates = df['created_at_dt'].dt.tz_convert('Asia/Taipei').dt.date
    df = df[(local_dates >= start_date) & (local_dates <= end_date)]
        
    if df.empty:
        st.warning("⚠️ 目前篩選條件下沒有測驗紀錄。")
        return
        
    # ── 3. 載入題庫 & 建立查找表 ──
    questions = load_questions()
    if not questions:
        return

    category_question_lookup = {}
    id_lookup = {}
    duplicate_ids = set()
    # 統計每個工作項目的總題數
    category_total_questions = Counter()
    for question in questions:
        question_id = str(question.get('id', '')).strip()
        category = str(question.get('category', '')).strip()
        if category:
            category_total_questions[category] += 1
        if category and question_id:
            category_question_lookup[(category, question_id)] = question
        if question_id in id_lookup:
            duplicate_ids.add(question_id)
        else:
            id_lookup[question_id] = question

    # ── 4. 統計錯題，按工作項目分組 ──
    # 每個工作項目 -> Counter({題目ID: 錯誤次數})
    category_wrong_counts = defaultdict(Counter)
    # 每個工作項目被多少人作答（以 exam_results 中 categories 包含該項目為準）
    category_respondent_count = Counter()
    
    total_exams = len(df)

    for _, row in df.iterrows():
        # 統計作答人數（哪些工作項目被這次測驗涵蓋）
        cats_in_exam = _parse_categories(row.get('categories'))
        for cat in cats_in_exam:
            normalized = _normalize_category(cat)
            category_respondent_count[normalized] += 1

        wrong_ids = row.get('wrong_question_ids', [])
        if isinstance(wrong_ids, str):
            try:
                wrong_ids = json.loads(wrong_ids)
            except (json.JSONDecodeError, ValueError):
                wrong_ids = []
        if not isinstance(wrong_ids, list):
            continue
        for q_id in wrong_ids:
            category, local_id, raw_id = parse_wrong_question_id(q_id)
            q_info = None
            if category:
                q_info = category_question_lookup.get((category, local_id))
            elif local_id not in duplicate_ids:
                q_info = id_lookup.get(local_id)
            if q_info:
                cat = q_info.get('category', '未知')
                category_wrong_counts[cat][raw_id] += 1
            
    all_wrong_count = sum(c.total() for c in category_wrong_counts.values())
    if all_wrong_count == 0:
        st.success("🎉 太棒了！在目前的篩選範圍內，學生沒有任何錯題紀錄。")
        return

    # ── 5. 第一層：工作項目總覽 ──
    st.markdown(f"### 📊 工作項目錯題總覽（共 {total_exams} 筆測驗紀錄）")

    # 組合所有出現過的工作項目（題庫有的 + 被答錯過的）
    all_categories = sorted(set(category_total_questions.keys()) | set(category_wrong_counts.keys()))
    
    overview_rows = []
    for cat in all_categories:
        total_q = category_total_questions.get(cat, 0)
        wrong_q_count = len(category_wrong_counts.get(cat, {}))  # 有幾題被答錯過
        total_wrong_times = category_wrong_counts.get(cat, Counter()).total()  # 總錯誤次數
        respondents = category_respondent_count.get(cat, 0)
        # 錯誤率 = 總錯誤次數 / (作答人數 * 該項目總題數) * 100
        if respondents > 0 and total_q > 0:
            error_rate = round(total_wrong_times / (respondents * total_q) * 100, 1)
        else:
            error_rate = 0.0
        
        overview_rows.append({
            'category_key': cat,
            '工作項目': _get_display_name(cat),
            '總題數': total_q,
            '作答人次': respondents,
            '錯題數（不同題）': wrong_q_count,
            '總錯誤次數': total_wrong_times,
            '錯誤率 (%)': error_rate,
            '嚴重程度': _severity_color(error_rate),
        })
    
    overview_df = pd.DataFrame(overview_rows).sort_values('錯誤率 (%)', ascending=False).reset_index(drop=True)
    
    # 橫條圖
    chart_df = overview_df[['工作項目', '錯誤率 (%)']].set_index('工作項目').sort_values('錯誤率 (%)', ascending=True)
    st.bar_chart(chart_df, horizontal=True, color='#ef4444')
    
    # 表格
    display_overview = overview_df[['嚴重程度', '工作項目', '總題數', '作答人次', '錯題數（不同題）', '總錯誤次數', '錯誤率 (%)']].copy()
    st.dataframe(
        display_overview,
        use_container_width=True,
        hide_index=True,
        column_config={
            "錯誤率 (%)": st.column_config.ProgressColumn(
                "錯誤率 (%)",
                help="總錯誤次數 ÷ (作答人次 × 總題數) × 100",
                format="%.1f%%",
                min_value=0,
                max_value=100,
            ),
            "嚴重程度": st.column_config.TextColumn("", width="small"),
        }
    )

    st.caption("🔴 ≥50%　🟡 ≥30%　🟢 <30%　｜　錯誤率 = 總錯誤次數 ÷ (作答人次 × 該項目總題數)")

    # 匯出總覽
    csv_overview = display_overview.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 匯出工作項目總覽 (CSV)",
        data=csv_overview,
        file_name='工作項目錯題總覽.csv',
        mime='text/csv',
        key='export_overview'
    )
    
    # ── 6. 第二層：逐題分析（展開某工作項目）──
    st.markdown("---")
    st.markdown("### 🔎 各工作項目逐題分析")
    st.write("點選下方的工作項目，查看每一題的錯誤率與常見錯誤選項。")

    # 只列出有錯題的工作項目
    categories_with_errors = overview_df[overview_df['總錯誤次數'] > 0].sort_values('錯誤率 (%)', ascending=False)
    
    for _, cat_row in categories_with_errors.iterrows():
        cat_key = cat_row['category_key']
        cat_display = cat_row['工作項目']
        severity = cat_row['嚴重程度']
        error_rate = cat_row['錯誤率 (%)']
        respondents = cat_row['作答人次']
        
        with st.expander(f"{severity} {cat_display}　—　錯誤率 {error_rate}%　|　作答 {respondents} 人次", expanded=False):
            wrong_counter = category_wrong_counts.get(cat_key, Counter())
            
            # 組逐題資料
            detail_rows = []
            for raw_id, wrong_times in wrong_counter.most_common():
                category, local_id, _ = parse_wrong_question_id(raw_id)
                q_info = None
                if category:
                    q_info = category_question_lookup.get((category, local_id))
                elif local_id not in duplicate_ids:
                    q_info = id_lookup.get(local_id)
                
                if not q_info:
                    continue
                
                question_text = q_info.get('question', '')
                question_short = question_text[:25] + '...' if len(question_text) > 25 else question_text
                correct_ans = get_correct_answer_text(q_info)
                
                # 逐題錯誤率 = 該題錯誤次數 / 作答該工作項目的人數
                per_q_rate = round(wrong_times / respondents * 100, 1) if respondents > 0 else 0
                
                detail_rows.append({
                    '題號': f"第 {local_id} 題",
                    '題目摘要': question_short,
                    '完整題目': question_text,
                    '正確答案': correct_ans,
                    '答錯次數': wrong_times,
                    f'錯誤率 (共{respondents}人)': per_q_rate,
                })
            
            if not detail_rows:
                st.write("此工作項目沒有可對應的錯題資料。")
                continue
            
            detail_df = pd.DataFrame(detail_rows).sort_values(f'錯誤率 (共{respondents}人)', ascending=False).reset_index(drop=True)
            
            # Top 5 長條圖
            if len(detail_df) > 1:
                top_n = min(10, len(detail_df))
                chart_detail = detail_df.head(top_n)[['題號', f'錯誤率 (共{respondents}人)']].set_index('題號')
                st.bar_chart(chart_detail, color='#f97316')
            
            # 逐題表格（不含完整題目，點開才看到）
            st.dataframe(
                detail_df[['題號', '題目摘要', '正確答案', '答錯次數', f'錯誤率 (共{respondents}人)']],
                use_container_width=True,
                hide_index=True,
                column_config={
                    f'錯誤率 (共{respondents}人)': st.column_config.ProgressColumn(
                        f'錯誤率 (共{respondents}人)',
                        format="%.1f%%",
                        min_value=0,
                        max_value=100,
                    ),
                    '答錯次數': st.column_config.NumberColumn(format="%d 次"),
                }
            )
            
            # 展開查看完整題目
            with st.popover("📖 查看完整題目內容"):
                for _, r in detail_df.iterrows():
                    st.markdown(f"**{r['題號']}**：{r['完整題目']}")
                    st.caption(f"正確答案：{r['正確答案']}　|　答錯 {r['答錯次數']} 次")
                    st.markdown("---")

            # 匯出該工作項目
            csv_detail = detail_df.drop(columns=['完整題目']).to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 匯出「{cat_display}」錯題 (CSV)",
                data=csv_detail,
                file_name=f'錯題分析_{cat_key}.csv',
                mime='text/csv',
                key=f'export_{cat_key}'
            )
    
    # ── 7. 匯出全部（所有工作項目彙整）──
    st.markdown("---")
    all_detail_rows = []
    for cat_key, wrong_counter in category_wrong_counts.items():
        respondents = category_respondent_count.get(cat_key, 0)
        for raw_id, wrong_times in wrong_counter.most_common():
            category, local_id, _ = parse_wrong_question_id(raw_id)
            q_info = None
            if category:
                q_info = category_question_lookup.get((category, local_id))
            elif local_id not in duplicate_ids:
                q_info = id_lookup.get(local_id)
            if not q_info:
                continue
            per_q_rate = round(wrong_times / respondents * 100, 1) if respondents > 0 else 0
            all_detail_rows.append({
                '工作項目': _get_display_name(cat_key),
                '題號': local_id,
                '題目': q_info.get('question', ''),
                '正確答案': get_correct_answer_text(q_info),
                '答錯次數': wrong_times,
                '作答人次': respondents,
                '錯誤率 (%)': per_q_rate,
            })
    
    if all_detail_rows:
        all_detail_df = pd.DataFrame(all_detail_rows).sort_values(['工作項目', '錯誤率 (%)'], ascending=[True, False])
        csv_all = all_detail_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 匯出完整錯題分析報表 (CSV)",
            data=csv_all,
            file_name='錯題弱點分析_完整報表.csv',
            mime='text/csv',
            key='export_all'
        )
