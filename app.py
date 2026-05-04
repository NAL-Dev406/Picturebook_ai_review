import streamlit as st
import requests
import time
import io
import fitz  # PyMuPDF
from supabase import create_client

# --- 1. 页面配置与学术感样式 ---
st.set_page_config(page_title="NAL | 绘本智能评审系统", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;500&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Serif SC', serif; }
    .stTitle { font-weight: 500; color: #1a1a1a; border-bottom: 2px solid #eee; padding-bottom: 10px; }
    .report-card { background-color: #fdfdfd; padding: 25px; border: 1px solid #e0e0e0; border-radius: 4px; line-height: 1.8; margin-top: 20px; }
    .metric-box { text-align: center; padding: 15px; background: #f8f9fa; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 初始化环境 (从 Secrets 读取) ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    API_BASE_URL = "https://pb-api.nal-ai.org/PB/api"
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error("配置缺失：请检查 Streamlit Secrets 中的 Supabase 凭证。")
    st.stop()

# --- 3. 辅助函数：上传到存储桶 ---
def upload_to_supabase(file_data, file_name):
    """处理单张图像上传"""
    file_path = f"eval_queue/{int(time.time())}_{file_name}"
    try:
        # 注意：upsert 使用小写字符串 "true" 以兼顾不同版本的 SDK 兼容性
        supabase.storage.from_("book_samples").upload(
            file_path, 
            file_data, 
            {"upsert": "true", "content-type": "image/jpeg"}
        )
        return supabase.storage.from_("book_samples").get_public_url(file_path)
    except Exception as e:
        st.error(f"传输失败 {file_name}: {str(e)}")
        return None

# --- 4. 侧边栏：评审准则 ---
with st.sidebar:
    st.markdown("### 🏛️ NAL 评审准则")
    st.info("本系统采用 **4:3:3 权重模型**：\n- **视觉对撞 (40%)**\n- **创意维度 (30%)**\n- **文本叙事 (30%)**")
    st.divider()
    st.caption("NewArtLiterature Collective | 2026")

# --- 5. 主界面布局 ---
st.title("NewArtLiterature 绘本自动化评审平台")
st.markdown("请上传绘本页面，系统将自动进行图像分析与叙事评估。")

uploaded_files = st.file_uploader(
    "支持 PDF 或 批量图片 (JPG/PNG)", 
    type=["pdf", "jpg", "png", "jpeg"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("🏛️ 提交学术评审", use_container_width=True):
        image_urls = []
        
        # 使用 status 容器保持界面整洁
        with st.status("正在启动云端传输与图像处理...", expanded=True) as status:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 处理所有上传文件
            processed_count = 0
            # 预计算总数（如果是 PDF 则需要展开计算）
            total_task_units = len(uploaded_files) 

            for file in uploaded_files:
                # 情况 A: 处理 PDF
                if file.name.lower().endswith(".pdf"):
                    status_text.markdown(f"📄 正在拆解 PDF: `{file.name}`")
                    doc = fitz.open(stream=file.read(), filetype="pdf")
                    for page_num in range(len(doc)):
                        page = doc.load_page(page_num)
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img_bytes = pix.tobytes("jpg")
                        
                        url = upload_to_supabase(img_bytes, f"{file.name}_p{page_num}.jpg")
                        if url: image_urls.append(url)
                    doc.close()
                
                # 情况 B: 处理普通图片
                else:
                    status_text.markdown(f"📸 正在传输图片: `{file.name}`")
                    url = upload_to_supabase(file.getvalue(), file.name)
                    if url: image_urls.append(url)
                
                processed_count += 1
                progress_bar.progress(processed_count / total_task_units)

            status_text.success(f"✅ 图像传输完毕，共计 {len(image_urls)} 个采样点")
            
            # --- 6. 调用评审 API ---
            status.update(label="正在唤醒远端 Gemini 评审大脑...", state="running")
            payload = {
                "id": int(time.time()),
                "award_type": "绘本奖",
                "image_urls": image_urls
            }
            
            try:
                resp = requests.post(f"{API_BASE_URL}/evaluate", json=payload, timeout=10)
                if resp.status_code == 200:
                    row_id = resp.json().get("row_id")
                    
                    # --- 7. 结果轮询 (Polling) ---
                    status.update(label="模型深度分析中，预计需要 30-60 秒...", state="running")
                    start_time = time.time()
                    
                    while time.time() - start_time < 120: # 2分钟超时限制
                        time.sleep(5)
                        res_status = requests.get(f"{API_BASE_URL}/status/{row_id}")
                        data = res_status.json()
                        
                        # 检查数据库中是否已填入视觉分
                        if data.get("v65_visual_score"):
                            status.update(label="评审报告已生成", state="complete")
                            st.balloons()
                            
                            # --- 8. 结果展示 ---
                            st.divider()
                            st.markdown("### 📊 评审结果摘要")
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                                st.metric("视觉评分 (40%)", f"{data['v65_visual_score']}/10")
                                st.markdown('</div>', unsafe_allow_html=True)
                            with c2:
                                st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                                st.metric("创意维度 (30%)", "--")
                                st.markdown('</div>', unsafe_allow_html=True)
                            with c3:
                                st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                                st.metric("叙事平衡 (30%)", "--")
                                st.markdown('</div>', unsafe_allow_html=True)

                            st.markdown('<div class="report-card">', unsafe_allow_html=True)
                            st.markdown("#### 📖 深度综合评价 (Synergy Report)")
                            # 假设你的数据库列名为 synergy_report
                            report_text = data.get('synergy_report', "报告已存入数据库，请查阅后台。")
                            st.markdown(report_text)
                            st.markdown('</div>', unsafe_allow_html=True)
                            break
                else:
                    st.error(f"远端大脑响应异常: {resp.text}")
            except Exception as e:
                st.error(f"API 通信失败: {str(e)}")
