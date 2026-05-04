import streamlit as st
import requests
import time
from supabase import create_client
from PIL import Image

# --- 1. 页面配置与学术风样式 ---
st.set_page_config(page_title="NAL | 绘本智能评审系统", layout="wide")

# 自定义 CSS 营造学术感
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Serif SC', serif;
    }
    .stTitle {
        font-weight: 500;
        color: #1a1a1a;
        border-bottom: 2px solid #eee;
        padding-bottom: 10px;
    }
    .report-card {
        background-color: #fdfdfd;
        padding: 25px;
        border: 1px solid #e0e0e0;
        border-radius: 2px;
        line-height: 1.8;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 初始化 ---
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
API_BASE_URL = "https://pb-api.nal-ai.org/PB/api"
supabase = create_client(URL, KEY)

# --- 3. 侧边栏：评审说明 ---
with st.sidebar:
    st.markdown("### 🏛️ NAL 评审准则")
    st.info("""
    本系统采用 **4:3:3 权重模型**:
    *   **视觉对撞 (40%):** 画面叙事与隐喻。
    *   **创意维度 (30%):** 构思独特性。
    *   **文本叙事 (30%):** 语言与节奏。
    """)
    st.divider()
    st.caption("NewArtLiterature Collective (NAL) | 2026")

# --- 4. 主界面布局 ---
st.title("NewArtLiterature 绘本自动化评审平台")

# 文件上传区
uploaded_files = st.file_uploader(
    "上传绘本页面 (支持批量 JPG/PNG 扫描件)", 
    accept_multiple_files=True,
    help="请上传高清晰度页面以保证视觉分析精度"
)

if uploaded_files and st.button("🏛️ 提交学术评审"):
    image_urls = []
    total_files = len(uploaded_files)
    
    # 1. 创建进度条和占位符
    progress_bar = st.progress(0)
    status_text = st.empty() 
    
    with st.status("正在启动云端传输...", expanded=True) as status:
        for i, file in enumerate(uploaded_files):
            # 更新当前状态文字
            current_count = i + 1
            status_text.markdown(f"**正在传输第 {current_count}/{total_files} 张:** `{file.name}`")
            
            # 执行上传
            file_path = f"eval_queue/{int(time.time())}_{file.name}"
            try:
                # 显式指定类型并处理上传
                supabase.storage.from_("book_samples").upload(
                    file_path, 
                    file.getvalue(), 
                    {"upsert": "true", "content-type": "image/jpeg"}
                )
                url = supabase.storage.from_("book_samples").get_public_url(file_path)
                image_urls.append(url)
                
                # 2. 更新进度条高度
                progress_bar.progress(current_count / total_files)
                
            except Exception as e:
                st.error(f"传输第 {current_count} 张时失败: {e}")
                continue # 某一张失败则跳过，继续下一张
        
        status_text.success(f"✅ 全案共 {total_files} 张图像已成功进入云端队列")
        status.update(label="图像传输完毕，正在唤醒 Gemini 评审大脑...", state="running")

    # 接下来的 API 调用逻辑...
            
            # Step B: 唤醒评审大脑
            payload = {
                "id": int(time.time()),
                "award_type": "绘本奖",
                "image_urls": image_urls
            }
            
            try:
                response = requests.post(f"{API_BASE_URL}/evaluate", json=payload)
                if response.status_code == 200:
                    row_id = response.json().get("row_id")
                    status.update(label="模型计算中：正在进行视觉对撞与文本协同分析...", state="running")
                    
                    # Step C: 轮询结果 (优化界面)
                    progress_bar = st.progress(0)
                    for percent_complete in range(100):
                        time.sleep(0.3)  # 模拟进度或根据实际 API 反馈
                        progress_bar.progress(percent_complete + 1)
                        
                        # 每隔 5 秒查询一次真实数据
                        if percent_complete % 15 == 0:
                            res_status = requests.get(f"{API_BASE_URL}/status/{row_id}")
                            data = res_status.json()
                            if data.get("v65_visual_score"):
                                break
                    
                    status.update(label="评审报告已生成", state="complete")
                    
                    # --- 5. 结果展示区 ---
                    st.divider()
                    st.markdown("### 📊 评审结果摘要")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("视觉评分", f"{data['v65_visual_score']}/10", help="基于 40% 权重")
                    with c2:
                        st.metric("创意得分", "--", delta="待综合") # 根据你数据库字段调整
                    with c3:
                        st.metric("叙事平衡", "--")

                    # 学术报告区域
                    st.markdown('<div class="report-card">', unsafe_allow_html=True)
                    st.markdown(f"#### 📖 深度综合评价 (Synergy Report)")
                    # 假设你数据库里有 synergy_report 这个字段
                    report_text = data.get('synergy_report', "报告生成中，请刷新查询...")
                    st.markdown(report_text)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                else:
                    st.error(f"通信异常: {response.text}")
            except Exception as e:
                st.error(f"系统错误: {str(e)}")
