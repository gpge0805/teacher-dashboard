import streamlit as st
import bcrypt
import os
from datetime import datetime, timedelta, timezone
from utils.supabase_client import supabase

# 設定頁面標題與佈局
st.set_page_config(page_title="技能檢定學科測驗互動系統 - 教師管理後台", page_icon="🎓", layout="wide")


def get_deploy_time_text() -> str:
    # Allow manual override in deployment platform secrets if needed.
    deploy_time = os.getenv("APP_DEPLOY_TIME")
    if deploy_time:
        return deploy_time

    try:
        utc8 = timezone(timedelta(hours=8))
        modified = datetime.fromtimestamp(os.path.getmtime(__file__), tz=timezone.utc).astimezone(utc8)
        return modified.strftime("%Y-%m-%d %H:%M")
    except OSError:
        return "未知"


def render_footer():
    st.markdown("---")
    st.markdown(
        f"<p style='text-align: center; color: #666; font-size: 0.9rem;'>© 2026 Design by yucs. All rights reserved. | 部署時間：{get_deploy_time_text()}（UTC+8）</p>",
        unsafe_allow_html=True,
    )

# 檢查密碼的輔助函數
def check_password(hashed_password: str, user_password: str) -> bool:
    """比對密碼（僅支援 bcrypt hash）"""
    try:
        return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except (ValueError, TypeError):
        return False

# 登入畫面
def login_page():
    st.markdown("<h1 style='text-align: center;'>🎓 技能檢定學科測驗互動系統 - 教師管理後台</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>請輸入您的教師帳號與密碼登入系統。</p>", unsafe_allow_html=True)
    
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
    query_params = st.query_params
    public_view = str(query_params.get('view', ''))

    if public_view == 'student-weekly':
        from views import student_weekly_query
        student_weekly_query.show()
        render_footer()
        return

    # 初始化 Session State
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # 判斷是否已登入
    if not st.session_state['logged_in']:
        login_page()
        render_footer()
    else:
        # 登入後的側邊欄 (Sidebar)
        st.sidebar.title(f"歡迎, {st.session_state.get('name', '老師')}")
        st.sidebar.write(f"權限: `{st.session_state.get('role', 'teacher')}`")
        st.sidebar.write(f"帳號: `{st.session_state.get('username', '')}`")
        
        st.sidebar.divider()
        
        # 🌟 建立左側功能導覽選單
        menu = ["📊 儀表板首頁", "📝 成績報表查詢", "📅 每週成績統計", "👥 學生名冊管理", "📈 錯題弱點分析"]
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
            st.write("歡迎來到技能檢定學科測驗互動系統 - 教師管理後台！請從左側選單選擇您要操作的功能。")
            
            # 顯示一些快速統計 (選做)
            col1, col2, col3 = st.columns(3)
            col1.metric("系統狀態", "正常運作中 🟢")
            col2.metric("目前登入身分", st.session_state.get('role', 'teacher'))
            
        elif choice == "📝 成績報表查詢":
            # 載入我們剛剛寫好的 score_report 模組
            from views import score_report
            score_report.show()

        elif choice == "📅 每週成績統計":
            from views import weekly_stats
            weekly_stats.show()
            
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

        render_footer()

if __name__ == "__main__":
    main()
