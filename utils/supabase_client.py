import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def init_connection() -> Client:
    """初始化 Supabase 連線，並快取資源以提升效能"""
    
    try:
        # 直接從 Streamlit Secrets 讀取
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except KeyError as e:
        st.error(f"❌ 找不到 Supabase 連線資訊！請確認 .streamlit/secrets.toml 中是否設定了 {e}")
        st.stop()
    except Exception as e:
        st.error(f"❌ 初始化 Supabase 時發生錯誤: {e}")
        st.stop()

# 建立全域的 supabase 客戶端
supabase = init_connection()