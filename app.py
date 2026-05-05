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

# --- 修改 app.py 的侧边栏和上传区逻辑 ---

with st.sidebar:
    st.header("评审参数配置")
    # 替换奖项为艺术形态
    work_type = st.selectbox("作品形态", ["绘本 (Picture Book)", "插画 (Illustration)"])
    st.divider()
    
    if "绘本" in work_type:
        st.markdown("**协同评估模型 (v5+v65)**\n- 文本逻辑分析\n- 视觉对撞评估\n- 图文叙事协同度")
    else:
        st.markdown("**视觉评估模型 (v65)**\n- 视觉对撞与张力\n- 构图隐喻\n- 艺术原创性")
    st.caption("当前引擎版本: v2.1.0-NAL")

# 主界面：动态上传区
st.write(f"### 🖼️ {work_type} 素材上传")

# 只有选择了“绘本”，才显示脚本输入框
script_text = ""
if "绘本" in work_type:
    script_text = st.text_area("✍️ 请输入对应的文字脚本 (v5 分析需要)", height=150, placeholder="例如：一天，岛上来了一只小船...")

uploaded_files = st.file_uploader(
    "支持上传 JPG, PNG 格式", 
    accept_multiple_files=True
)

if st.button("🚀 提交学术评审任务", type="primary"):
    # 增加校验：如果是绘本，最好有脚本
    if "绘本" in work_type and not script_text.strip():
        st.warning("建议输入文字脚本，以便进行完整的图文协同评估。")
        st.stop()
        
    if not uploaded_files:
        st.warning("请至少上传一张图片以供分析。")
        st.stop()
        
    # ... (随后的图片上传逻辑保持不变) ...
    
    # 组装新的 Payload 传给后端
    payload = {
        "work_type": "picture_book" if "绘本" in work_type else "illustration",
        "script_text": script_text,
        "image_urls": image_urls
    }
    # ... (请求后端逻辑不变) ...
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
