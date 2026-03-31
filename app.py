import streamlit as st
import bcrypt
import os
from utils.supabase_client import supabase

# 設定頁面標題與佈局
st.set_page_config(page_title="教師管理後台", page_icon="🎓", layout="wide")

# 檢查密碼的輔助函數
def check_password(hashed_password: str, user_password: str) -> bool:
    """比對密碼。如果是 bcrypt hash 則比對，否則直接比對明文 (方便初期測試)"""
    try:
        return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        # 如果資料庫裡存的是明文 (測試期)，就直接比對字串
        return hashed_password == user_password

# 登入畫面
def login_page():
    st.title("🎓 工業電子丙級學科測試線上版 - 教師管理後台")
    st.write("請輸入您的教師帳號與密碼登入系統。")
    
    # 使用 columns 讓登入框置中
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            username = st.text_input("帳號 (Username)")
            password = st.text_input("密碼 (Password)", type="password")
            submit_button = st.form_submit_button("登入", use_container_width=True)
            
            if submit_button:
                if not username or not password:
                    st.warning("⚠️ 請輸入帳號與密碼")
                    return
                    
                # 1. 向 Supabase 查詢帳號
                response = supabase.table("teachers").select("*").eq("username", username).execute()
                users = response.data
                
                if not users:
                    st.error("❌ 帳號或密碼錯誤")
                    return
                    
                user = users[0]
                
                # 2. 檢查密碼
                is_valid = check_password(user['password'], password)
                    
                if is_valid:
                    # 檢查帳號是否被停用 (相容舊資料，若無此欄位則視為 True)
                    if user.get('is_active') is False:
                        st.error("❌ 此帳號已被停用，請聯絡系統管理員。")
                        return

                    # 3. 登入成功，將使用者資訊存入 Session State
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = user['username']
                    st.session_state['name'] = user['name']
                    # 如果資料庫沒有 role 欄位，預設為 teacher
                    st.session_state['role'] = user.get('role', 'teacher') 
                    
                    st.success("✅ 登入成功！正在為您跳轉...")
                    st.rerun()
                else:
                    st.error("❌ 帳號或密碼錯誤")

# 主程式邏輯
def main():
    # 初始化 Session State
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # 判斷是否已登入
    if not st.session_state['logged_in']:
        login_page()
    else:
        # 登入後的側邊欄 (Sidebar)
        st.sidebar.title(f"歡迎, {st.session_state.get('name', '老師')}")
        st.sidebar.write(f"權限: `{st.session_state.get('role', 'teacher')}`")
        st.sidebar.write(f"帳號: `{st.session_state.get('username', '')}`")
        
        st.sidebar.divider()
        
        # 🌟 建立左側功能導覽選單
        menu = ["📊 儀表板首頁", "📝 成績報表查詢", "👥 學生名冊管理", "📈 錯題弱點分析"]
        if st.session_state.get('role') == 'admin':
            menu.append("👨‍🏫 教師帳號管理")
            
        choice = st.sidebar.radio("功能選單", menu)
        
        st.sidebar.divider()
        
        # 登出按鈕
        if st.sidebar.button("登出", use_container_width=True):
            st.session_state.clear()
            st.rerun()
            
        # 🌟 根據選單選擇，載入對應的頁面內容
        if choice == "📊 儀表板首頁":
            st.title("📊 儀表板首頁")
            st.write("歡迎來到教師管理後台！請從左側選單選擇您要操作的功能。")
            
            # 顯示一些快速統計 (選做)
            col1, col2, col3 = st.columns(3)
            col1.metric("系統狀態", "正常運作中 🟢")
            col2.metric("目前登入身分", st.session_state.get('role', 'teacher'))
            
        elif choice == "📝 成績報表查詢":
            # 載入我們剛剛寫好的 score_report 模組
            from views import score_report
            score_report.show()
            
        elif choice == "👥 學生名冊管理":
            # 載入我們剛剛寫好的 student_management 模組
            from views import student_management
            student_management.show()
            
        elif choice == "📈 錯題弱點分析":
            from views import weakness_analysis
            weakness_analysis.show()
            
        elif choice == "👨‍🏫 教師帳號管理":
            from views import teacher_management
            teacher_management.show()

if __name__ == "__main__":
    main()
