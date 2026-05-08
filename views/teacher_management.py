import streamlit as st
import pandas as pd
import bcrypt
from utils.supabase_client import supabase

def hash_password(password: str) -> str:
    """將密碼加密"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def show():
    st.header("👨‍🏫 教師帳號管理 - 技能檢定學科測驗互動系統")
    st.write("管理者可以在此建立新教師帳號，並設定權限與啟用狀態。")
    
    # 雙重檢查：確保只有 admin 可以訪問
    if st.session_state.get('role') != 'admin':
        st.error("⚠️ 您沒有權限訪問此頁面。")
        return
        
    tab1, tab2 = st.tabs(["📋 教師名單與權限設定", "➕ 新增教師帳號"])
    
    with tab1:
        st.subheader("目前教師名單")
        response = supabase.table("teachers").select("*").execute()
        if response.data:
            df = pd.DataFrame(response.data)
            
            # 確保有 is_active 欄位 (相容舊資料)
            if 'is_active' not in df.columns:
                df['is_active'] = True
            else:
                df['is_active'] = df['is_active'].fillna(True).astype(bool)
                
            display_cols = {
                'username': '帳號 (不可改)',
                'name': '姓名',
                'role': '權限',
                'is_active': '啟用狀態'
            }
            
            # 準備編輯用的 DataFrame
            edit_df = df[['username', 'name', 'role', 'is_active']].copy()
            edit_df = edit_df.rename(columns=display_cols)
            
            st.write("💡 提示：您可以直接在表格中修改「姓名」、「權限」與「啟用狀態」，修改後請點擊下方按鈕儲存。")
            
            edited_df = st.data_editor(
                edit_df,
                use_container_width=True,
                hide_index=True,
                disabled=['帳號 (不可改)'],
                column_config={
                    "權限": st.column_config.SelectboxColumn(
                        "權限",
                        help="admin: 管理者 (可看全部), teacher: 一般教師 (只能看自己)",
                        options=["admin", "teacher"],
                        required=True
                    ),
                    "啟用狀態": st.column_config.CheckboxColumn(
                        "啟用狀態",
                        help="取消勾選將禁止該帳號登入",
                        default=True
                    )
                }
            )
            
            if st.button("💾 儲存變更", type="primary"):
                try:
                    with st.spinner("正在儲存變更..."):
                        # 找出有差異的資料並更新
                        for index, row in edited_df.iterrows():
                            orig_row = edit_df.iloc[index]
                            if not row.equals(orig_row):
                                update_data = {
                                    "name": row['姓名'],
                                    "role": row['權限'],
                                    "is_active": bool(row['啟用狀態'])
                                }
                                supabase.table("teachers").update(update_data).eq("username", row['帳號 (不可改)']).execute()
                        st.success("✅ 變更已成功儲存！")
                except Exception as e:
                    st.error(f"❌ 儲存失敗：{e}")
        else:
            st.info("目前沒有教師資料。")

    with tab2:
        st.subheader("新增教師帳號")
        with st.form("add_teacher_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("帳號 (Username) *必填")
                new_password = st.text_input("密碼 (Password) *必填", type="password")
            with col2:
                new_name = st.text_input("教師姓名 *必填")
                new_role = st.selectbox("權限角色", ["teacher", "admin"])
                
            submitted = st.form_submit_button("建立帳號")
            if submitted:
                if not new_username or not new_password or not new_name:
                    st.warning("⚠️ 請填寫所有必填欄位！")
                else:
                    try:
                        # 檢查帳號是否已存在
                        check_res = supabase.table("teachers").select("username").eq("username", new_username).execute()
                        if check_res.data:
                            st.error(f"❌ 帳號 '{new_username}' 已經存在！")
                        else:
                            # 密碼加密
                            hashed_pw = hash_password(new_password)
                            new_data = {
                                "username": new_username,
                                "password": hashed_pw,
                                "name": new_name,
                                "role": new_role,
                                "is_active": True
                            }
                            supabase.table("teachers").insert(new_data).execute()
                            st.success(f"✅ 成功建立教師帳號：{new_name} ({new_username})")
                    except Exception as e:
                        st.error(f"❌ 建立失敗：{e}")
