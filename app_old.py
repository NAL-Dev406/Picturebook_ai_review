import streamlit as st
import requests
import time
import os
from supabase import create_client, Client

# --- 1. 配置与环境初始化 ---
st.set_page_config(page_title="NAL | 绘本 AI 深度评审系统", page_icon="🏛️", layout="wide")

# 请确保在 Streamlit Cloud 或本地 .env 中配置了这些环境变量
# 或者直接在此处填入您的凭证（生产环境建议使用 st.secrets）
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "您的SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "您的SUPABASE_KEY")
API_BASE_URL = "https://pb-api.nal-ai.org" # 您的 Render 后端地址

# 初始化 Supabase 客户端（用于上传图片）
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. 核心函数：上传图片至存储桶 ---
def upload_images_to_nal_storage(files):
    """
    将上传的文件推送到 Supabase 'nal_images' 存储桶并返回公开 URL
    """
    public_urls = []
    for file in files:
        try:
            # 构造唯一文件名：review_images/时间戳_文件名
            file_path = f"review_images/{int(time.time())}_{file.name}"
            file_content = file.getvalue()
            
            # 执行上传
            supabase.storage.from_("nal_images").upload(
                path=file_path,
                file=file_content,
                file_options={"content-type": file.type}
            )
            
            # 获取公开链接
            url_res = supabase.storage.from_("nal_images").get_public_url(file_path)
            public_urls.append(url_res)
        except Exception as e:
            st.error(f"⚠️ 文件 {file.name} 上传失败: {e}")
    return public_urls

# --- 3. UI 界面设计 ---
st.title("🏛️ NewArtLiterature Collective")
st.subheader("绘本视觉叙事深度评审引擎 (v65)")

with st.sidebar:
    st.header("评审参数配置")
    award_type = st.selectbox("目标奖项", [
        "陈伯吹国际儿童文学奖", 
        "NAL 艺术绘本金奖", 
        "图文平衡叙事奖"
    ])
    st.divider()
    st.markdown("""
    **评估模型权重 (4:3:3)：**
    - 视觉对撞 (40%)
    - 创意维度 (30%)
    - 叙事平衡 (30%)
    """)
    st.caption("当前引擎版本: v2.0.0-v65")

# 主界面：上传区
st.write("### 🖼️ 绘本内页采样上传")
uploaded_files = st.file_uploader(
    "支持上传 JPG, PNG 格式，建议上传包含典型图文关系的页面", 
    accept_multiple_files=True
)

if st.button("🚀 提交学术评审任务", type="primary"):
    if not uploaded_files:
        st.warning("请至少上传一张图片以供分析。")
    else:
        # 第一步：上传素材并获取真实 URL
        with st.spinner("📦 正在将视觉素材同步至 NAL 存储库..."):
            image_urls = upload_images_to_nal_storage(uploaded_files)
        
        if not image_urls:
            st.error("素材同步失败，请检查数据库存储配置。")
        else:
            try:
                # 第二步：向后端发起任务
                with st.spinner("📡 正在启动后台 v65 深度评审引擎..."):
                    payload = {
                        "award_type": award_type,
                        "image_urls": image_urls
                    }
                    resp = requests.post(f"{API_BASE_URL}/PB/api/evaluate", json=payload, timeout=15)
                
                if resp.status_code == 200:
                    row_id = resp.json().get("row_id")
                    st.toast(f"✅ 任务立项成功！记录 ID: {row_id}", icon="🤖")
                    
                    # 第三步：进入轮询监控状态
                    status_area = st.empty()
                    progress_bar = st.progress(0)
                    start_time = time.time()
                    
                    quotes = [
                        "正在解析色彩张力与构图对比...",
                        "正在评估视觉隐喻的原创性...",
                        "正在计算图文协同的叙事节奏...",
                        "学术评审报告撰写中..."
                    ]
                    
                    while True:
                        # 获取任务状态
                        status_resp = requests.get(f"{API_BASE_URL}/PB/api/status/{row_id}")
                        if status_resp.status_code == 200:
                            data = status_resp.json()
                            status = data.get("status")
                            
                            if status == "completed":
                                progress_bar.progress(100)
                                status_area.success("🎯 评审已完成！")
                                
                                # 展示评审结果
                                st.divider()
                                col_score, col_report = st.columns([1, 2])
                                
                                with col_score:
                                    score = data.get("v65_visual_score", 0)
                                    st.metric("v65 综合评分", f"{score} / 10")
                                    st.write("**权重分布：**")
                                    st.caption(f"视觉: 4.0 | 创意: 3.0 | 叙事: 3.0")
                                    
                                with col_report:
                                    st.markdown("### 🏛️ 学术评审报告 (Synergy Report)")
                                    st.info(data.get("v65_synergy_report", "未提取到报告文本内容"))
                                break
                                
                            elif status == "failed":
                                st.error("❌ 评审任务处理失败，请检查后端日志。")
                                break
                            else:
                                # 动态更新 UI
                                elapsed = int(time.time() - start_time)
                                q_idx = (elapsed // 10) % len(quotes)
                                status_area.info(f"⏳ {quotes[q_idx]} (已耗时 {elapsed}s)")
                                progress_bar.progress(min(elapsed * 2, 95)) # 模拟进度到 95%
                                
                        time.sleep(5) # 每 5 秒轮询一次
                else:
                    st.error(f"后端 API 拒绝了请求 (状态码: {resp.status_code})")
            except Exception as e:
                st.error(f"连接后端服务失败: {e}")

# --- 4. 底部版权信息 ---
st.divider()
st.caption("© 2026 NewArtLiterature Collective | 艺术文献与数字学术平台")
