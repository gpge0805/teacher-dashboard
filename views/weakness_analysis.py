import streamlit as st
import pandas as pd
import json
import os
from collections import Counter
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
    # 讀取題庫 JSON 檔案
    # 嘗試多種可能的位置，以適應本機與上傳後的環境
    base_dir = os.path.dirname(__file__)
    possible_paths = [
        os.path.abspath(os.path.join(base_dir, '..', 'questions.json')), # teacher-dashboard 根目錄（Streamlit Cloud 部署用）
        os.path.abspath(os.path.join(base_dir, '..', '..', '工業電子丙級學科互動式題庫v1-0331', 'src', 'data', 'questions.json')), # 根目錄下的 v1-0331
        os.path.abspath(os.path.join(base_dir, '..', '..', 'src', 'data', 'questions.json')), # 本機開發環境 (從 views 回推兩層到根目錄)
        os.path.abspath(os.path.join(base_dir, '..', 'src', 'data', 'questions.json')), # 某些部署環境
        os.path.abspath(os.path.join(os.getcwd(), '工業電子丙級學科互動式題庫v1-0331', 'src', 'data', 'questions.json')), # 從根目錄執行
        os.path.abspath(os.path.join(os.getcwd(), '..', 'src', 'data', 'questions.json')), # 從 teacher-dashboard 執行
        os.path.abspath(os.path.join(os.getcwd(), 'src', 'data', 'questions.json')), # 從根目錄執行
        os.path.abspath(os.path.join(os.getcwd(), 'questions.json')), # 當前目錄
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

def show():
    st.header("📈 錯題弱點分析")
    st.write("分析學生在測驗中最常答錯的題目，幫助您掌握教學重點。")
    
    # 1. 撈取測驗成績資料
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
    
    # 【權限控管】如果是一般老師，只能看到自己學生的成績
    if st.session_state.get('role') != 'admin':
        # 先查出該老師的所有學生學號
        student_res = supabase.table("students").select("student_id").eq("teacher_username", st.session_state.get('username')).execute()
        my_student_ids = [s['student_id'] for s in student_res.data]
        # 過濾成績表
        df = df[df['student_id'].isin(my_student_ids)]
        
        if df.empty:
            st.info("💡 您的學生目前還沒有任何測驗成績紀錄。")
            return
            
    # 2. 建立篩選器
    st.markdown("### 🔍 分析範圍篩選")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        classes = ["全部"] + list(df['class_name'].dropna().unique())
        selected_class = st.selectbox("選擇班級", classes)

    with col2:
        all_work_items = sorted({item for items in df['category_list'] for item in items if item})
        selected_work_items = st.multiselect("選擇工作項目", all_work_items)

    valid_dates = df['created_at_dt'].dropna()
    if valid_dates.empty:
        today = pd.Timestamp.now(tz='Asia/Taipei').date()
        min_date = today
        max_date = today
    else:
        min_date = valid_dates.dt.tz_convert('Asia/Taipei').dt.date.min()
        max_date = valid_dates.dt.tz_convert('Asia/Taipei').dt.date.max()

    with col3:
        st.caption("時間區段")
        start_date = st.date_input(
            "開始日期",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            format="YYYY-MM-DD",
            key="weakness_start_date"
        )
        end_date = st.date_input(
            "結束日期",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            format="YYYY-MM-DD",
            key="weakness_end_date"
        )
        
    # 應用班級篩選
    if selected_class != "全部":
        df = df[df['class_name'] == selected_class]

    if selected_work_items:
        selected_work_items_set = set(selected_work_items)
        df = df[df['category_list'].apply(lambda items: bool(set(items) & selected_work_items_set))]

    if start_date > end_date:
        st.warning("開始日期晚於結束日期，系統已自動交換區間。")
        start_date, end_date = end_date, start_date

    local_dates = df['created_at_dt'].dt.tz_convert('Asia/Taipei').dt.date
    df = df[(local_dates >= start_date) & (local_dates <= end_date)]
        
    if df.empty:
        st.warning("⚠️ 目前篩選條件下沒有測驗紀錄。")
        return
        
    # 3. 統計錯題
    wrong_ids_list = []
    for index, row in df.iterrows():
        # 確保 wrong_question_ids 存在且為列表
        wrong_ids = row.get('wrong_question_ids', [])
        # 相容性處理：若 DB 回傳的是 JSON 字串而非解析好的 list，手動解析
        if isinstance(wrong_ids, str):
            try:
                wrong_ids = json.loads(wrong_ids)
            except (json.JSONDecodeError, ValueError):
                wrong_ids = []
        if isinstance(wrong_ids, list):
            wrong_ids_list.extend(wrong_ids)
            
    if not wrong_ids_list:
        st.success("🎉 太棒了！在目前的篩選範圍內，學生沒有任何錯題紀錄。")
        return
        
    # 計算每個錯題的出現次數
    wrong_counts = Counter(wrong_ids_list)
    
    # 4. 載入題庫並對應資料
    questions = load_questions()
    if not questions:
        return

    # 建立題庫查找表，優先使用「分類 + 題號」對應前端複合題號
    category_question_lookup = {}
    id_lookup = {}
    duplicate_ids = set()
    for question in questions:
        question_id = str(question.get('id', '')).strip()
        category = str(question.get('category', '')).strip()
        if category and question_id:
            category_question_lookup[(category, question_id)] = question

        if question_id in id_lookup:
            duplicate_ids.add(question_id)
        else:
            id_lookup[question_id] = question

    # 整理分析結果
    analysis_data = []
    for q_id, count in wrong_counts.most_common():
        category, local_id, raw_id = parse_wrong_question_id(q_id)

        q_info = None
        if category:
            q_info = category_question_lookup.get((category, local_id))
        elif local_id not in duplicate_ids:
            q_info = id_lookup.get(local_id)

        if q_info:
            correct_ans_text = get_correct_answer_text(q_info)

            analysis_data.append({
                '錯誤次數': count,
                '工作項目': q_info.get('category', '未知'),
                '題號': local_id,
                '備註': raw_id,
                '題目': q_info.get('question', ''),
                '正確答案': correct_ans_text
            })
            
    if not analysis_data:
        st.warning("⚠️ 無法將錯題紀錄對應到題庫，可能是題庫版本不一致。")
        return
        
    analysis_df = pd.DataFrame(analysis_data)
    
    # 5. 顯示分析結果
    st.markdown(f"### 📊 錯題排行榜 (共分析 {len(df)} 筆測驗紀錄)")
    
    # 顯示前 10 大錯題的長條圖
    st.write("#### 🏆 Top 10 最常錯題目")
    top10_df = analysis_df.head(10).copy()
    # 圖表索引要唯一，避免截斷後同名題目被合併加總而產生錯誤次數偏大
    top10_df['題目簡稱'] = top10_df['題目'].apply(lambda x: x[:15] + '...' if len(x) > 15 else x)
    top10_df['圖表標籤'] = top10_df.apply(lambda row: f"{row['備註']}｜{row['題目簡稱']}", axis=1)
    st.bar_chart(data=top10_df.set_index('圖表標籤')['錯誤次數'])
    
    # 顯示完整表格
    st.write("#### 📋 完整錯題清單")
    st.dataframe(
        analysis_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "錯誤次數": st.column_config.NumberColumn(
                "錯誤次數",
                help="該題目被答錯的總次數",
                format="%d 次"
            )
        }
    )
    
    # 匯出功能
    csv = analysis_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 匯出錯題分析報表 (Excel/CSV)",
        data=csv,
        file_name='錯題弱點分析報表.csv',
        mime='text/csv',
    )
