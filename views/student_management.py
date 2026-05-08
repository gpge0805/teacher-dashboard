import streamlit as st
import pandas as pd
from utils.supabase_client import supabase
import io

def show():
    st.header("👥 學生名冊管理")
    st.write("您可以在此查看、新增或批次匯入學生名單。")
    
    # 建立三個分頁
    tab1, tab2, tab3 = st.tabs(["📋 目前名單", "➕ 單筆新增 / 修改", "📁 批次匯入 (Excel/CSV)"])
    
    # ==========================================
    # Tab 1: 目前名單
    # ==========================================
    with tab1:
        st.subheader("目前系統中的學生名單")
        
        # 從資料庫讀取學生資料
        query = supabase.table("students").select("*")
        if st.session_state.get('role') != 'admin':
            query = query.eq("teacher_username", st.session_state.get('username'))
        response = query.order("class_name").order("seat_number").execute()
        students_data = response.data
        
        if students_data:
            df_students = pd.DataFrame(students_data)
            
            # 篩選器
            col1, col2 = st.columns(2)
            with col1:
                classes = ["全部"] + list(df_students['class_name'].dropna().unique())
                selected_class = st.selectbox("篩選班級", classes, key="filter_class")
            with col2:
                search_text = st.text_input("搜尋姓名或學號", key="search_student")
                
            filtered_df = df_students.copy()
            if selected_class != "全部":
                filtered_df = filtered_df[filtered_df['class_name'] == selected_class]
            if search_text:
                filtered_df = filtered_df[
                    filtered_df['name'].str.contains(search_text, na=False) | 
                    filtered_df['student_id'].str.contains(search_text, na=False)
                ]
                
            # 加入「選取」核取方塊欄位
            filtered_df.insert(0, '選取', False)
                
            display_cols = {
                '選取': '選取',
                'class_name': '班級',
                'seat_number': '座號',
                'student_id': '學號',
                'name': '姓名',
                'teacher_username': '指導教師',
                'created_at': '建檔時間'
            }
            
            # 轉換時間格式
            filtered_df['created_at'] = pd.to_datetime(filtered_df['created_at']).dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d')
            
            st.write("💡 提示：勾選最左側的核取方塊，可以批次刪除學生。")
            edited_df = st.data_editor(
                filtered_df[list(display_cols.keys())].rename(columns=display_cols),
                use_container_width=True,
                hide_index=True,
                disabled=['班級', '座號', '學號', '姓名', '指導教師代碼', '建檔時間']
            )
            
            # 處理刪除邏輯
            selected_rows = edited_df[edited_df['選取'] == True]
            if not selected_rows.empty:
                st.warning(f"⚠️ 您已選取 {len(selected_rows)} 名學生")
                if st.button("🗑️ 刪除選取的學生", type="primary"):
                    try:
                        student_ids_to_delete = selected_rows['學號'].tolist()
                        for sid in student_ids_to_delete:
                            supabase.table("students").delete().eq("student_id", sid).execute()
                        st.success(f"✅ 成功刪除 {len(student_ids_to_delete)} 名學生！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 刪除失敗：{e}")
                        
            st.caption(f"共計 {len(filtered_df)} 名學生")
        else:
            st.info("目前系統中沒有任何學生資料。")

    # ==========================================
    # Tab 2: 單筆新增 / 修改
    # ==========================================
    with tab2:
        st.subheader("新增或修改單一學生")
        st.info("💡 提示：如果輸入的「學號」已經存在，系統會自動更新該學生的資料。")
        with st.form("add_single_student_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_student_id = st.text_input("學號 (必填)*")
                new_name = st.text_input("姓名 (必填)*")
                new_class = st.text_input("班級 (例如: 電子一甲)")
            with col2:
                new_seat = st.number_input("座號", min_value=1, max_value=100, value=1, step=1)
                # 預設帶入目前登入老師的帳號
                new_teacher = st.text_input("指導教師帳號", value=st.session_state.get('username', ''))
                
            submitted = st.form_submit_button("新增學生")
            if submitted:
                if not new_student_id or not new_name:
                    st.error("⚠️ 學號與姓名為必填欄位！")
                else:
                    try:
                        # 寫入 Supabase
                        new_data = {
                            "student_id": new_student_id,
                            "name": new_name,
                            "class_name": new_class,
                            "seat_number": new_seat,
                            "teacher_username": new_teacher
                        }
                        # upsert: 如果學號已存在則更新，不存在則新增
                        supabase.table("students").upsert(new_data, on_conflict="student_id").execute()
                        st.success(f"✅ 成功新增學生：{new_name} ({new_student_id})")
                    except Exception as e:
                        st.error(f"❌ 新增失敗：{e}")

    # ==========================================
    # Tab 3: 批次匯入
    # ==========================================
    with tab3:
        st.subheader("批次匯入學生名單")
        st.write("請下載範本檔案，填寫完畢後上傳。系統會自動以「學號」為基準，新增或更新學生資料。")
        
        # 1. 提供範本下載
        template_data = {
            "學號": ["112001", "112002"],
            "姓名": ["王小明", "陳小華"],
            "班級": ["電子一甲", "電子一甲"],
            "座號": [1, 2],
            "教師代碼": ["T001", "T001"]
        }
        df_template = pd.DataFrame(template_data)
        csv_template = df_template.to_csv(index=False).encode('utf-8-sig')
        
        st.download_button(
            label="📥 下載 CSV 匯入範本",
            data=csv_template,
            file_name="學生匯入範本.csv",
            mime="text/csv"
        )
        
        st.divider()
        
        # 2. 檔案上傳區
        uploaded_file = st.file_uploader("上傳填寫好的 CSV 或 Excel 檔案", type=['csv', 'xlsx'])
        
        if uploaded_file is not None:
            try:
                # 讀取檔案 (強制所有欄位讀取為字串，避免學號或班級變成 111.0)
                if uploaded_file.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_file, dtype=str)
                else:
                    df_upload = pd.read_excel(uploaded_file, dtype=str)
                    
                # 移除完全空白的列 (避免 Excel 殘留的空行被計算進去)
                df_upload = df_upload.dropna(how='all')
                # 將 NaN 替換為空字串，避免後續處理出錯
                df_upload = df_upload.fillna("")
                    
                total_rows = len(df_upload)
                st.info(f"📄 檔案讀取成功！共計 **{total_rows}** 筆資料。以下為前 5 筆預覽：")
                st.dataframe(df_upload.head(5), use_container_width=True)
                
                # 檢查必要欄位
                required_cols = ["學號", "姓名"]
                if not all(col in df_upload.columns for col in required_cols):
                    st.error(f"❌ 檔案缺少必要欄位！請確保標題列包含：{', '.join(required_cols)}")
                else:
                    if st.button("🚀 確認並匯入資料", type="primary"):
                        with st.spinner('正在匯入資料到資料庫...'):
                            # 整理資料格式以符合 Supabase Table
                            records_to_insert = []
                            for index, row in df_upload.iterrows():
                                # 確保學號和姓名有值
                                student_id = str(row.get('學號', '')).strip()
                                name = str(row.get('姓名', '')).strip()
                                
                                if not student_id or not name:
                                    continue
                                    
                                record = {
                                    "student_id": student_id,
                                    "name": name,
                                    "class_name": str(row.get('班級', '')).strip() if row.get('班級') else None,
                                    "seat_number": int(float(row.get('座號'))) if row.get('座號') else None,
                                    "teacher_username": str(row.get('教師代碼', '')).strip() if row.get('教師代碼') else None
                                }
                                records_to_insert.append(record)
                            
                            if records_to_insert:
                                # 批次 Upsert
                                result = supabase.table("students").upsert(records_to_insert, on_conflict="student_id").execute()
                                st.success(f"✅ 成功匯入/更新 {len(records_to_insert)} 筆學生資料！")
                            else:
                                st.warning("⚠️ 沒有找到有效的資料列可供匯入。")
                                
            except Exception as e:
                st.error(f"❌ 處理檔案時發生錯誤：{e}")
