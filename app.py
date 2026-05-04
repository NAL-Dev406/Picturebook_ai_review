import streamlit as st
import requests
import time

# --- 1. 配置与初始化 ---
st.set_page_config(page_title="NAL | 绘本 AI 深度评审系统", page_icon="🏛️", layout="wide")

# API 地址（请替换为您在 Render 上的实际后端域名）
API_BASE_URL = "https://pb-api.nal-ai.org" 

st.title("🏛️ NewArtLiterature Collective")
st.subheader("绘本视觉叙事深度评审引擎 (v65)")

# --- 2. 侧边栏：评审配置 ---
with st.sidebar:
    st.header("评审设置")
    award_type = st.selectbox("参评奖项", ["陈伯吹新儿童文学奖", "NAL 艺术绘本奖", "年度最佳图文平衡奖"])
    st.divider()
    st.info("当前算法：v65 4:3:3 深度评估模型\n- 视觉对撞 (40%)\n- 创意维度 (30%)\n- 叙事平衡 (30%)")

# --- 3. 核心功能区：文件上传 ---
st.write("### 🖼️ 上传绘本内页采样")
uploaded_files = st.file_uploader("支持多图上传 (JPG/PNG)", accept_multiple_files=True)

if st.button("🚀 启动深度学术评审", type="primary"):
    if not uploaded_files:
        st.warning("请先上传需要评审的绘本图像。")
    else:
        # 模拟：此处通常需要先将图片传至 Supabase Storage 获取公网 URL
        # 为演示完整链路，假设图片已处理并获得 URL 列表
        # 实际开发中请结合您的存储逻辑
        dummy_urls = ["https://example.com/sample_page_1.jpg"] # 替换为真实上传后的链接列表
        
        payload = {
            "award_type": award_type,
            "image_urls": dummy_urls
        }
        
        try:
            with st.spinner("正在向后端 API 发送任务..."):
                resp = requests.post(f"{API_BASE_URL}/PB/api/evaluate", json=payload, timeout=10)
                
            if resp.status_code == 200:
                result = resp.json()
                row_id = result.get("row_id")
                
                # --- 4. 实时轮询逻辑 ---
                st.toast(f"✅ 任务已立项，数据库 ID: {row_id}", icon='🤖')
                
                status_container = st.empty()
                progress_bar = st.progress(0)
                
                # 轮询提示词（增加学术仪式感）
                quotes = [
                    "正在通过 4:3:3 模型建立视觉权重坐标...",
                    "正在分析图像中的色彩张力与视觉隐喻...",
                    "正在进行图文协同 (Synergy) 深度扫描...",
                    "正在撰写学术评审报告摘要..."
                ]
                
                start_time = time.time()
                timeout_limit = 120  # 设置 2 分钟超时
                
                while True:
                    # 检查是否超时
                    if time.time() - start_time > timeout_limit:
                        st.error("⌛ 评审时间过长，请稍后在历史记录中查看。")
                        break
                        
                    # 获取最新状态
                    status_resp = requests.get(f"{API_BASE_URL}/PB/api/status/{row_id}")
                    if status_resp.status_code == 200:
                        data = status_resp.json()
                        current_status = data.get("status")
                        
                        if current_status == "completed":
                            progress_bar.progress(100)
                            status_container.success("🎯 评审报告生成完毕！")
                            
                            # --- 5. 结果展示区 ---
                            st.divider()
                            col1, col2 = st.columns([1, 2])
                            
                            with col1:
                                visual_score = data.get("v65_visual_score", 0)
                                st.metric("v65 视觉综合得分", f"{visual_score}/10")
                                st.write("**评估维度：**")
                                st.caption("- 视觉对撞 (40%)")
                                st.caption("- 创意维度 (30%)")
                                st.caption("- 叙事平衡 (30%)")
                                
                            with col2:
                                st.markdown("### 🏛️ 学术评审报告 (Synergy Report)")
                                report_text = data.get("v65_synergy_report", "暂无报告内容")
                                st.info(report_text)
                            break
                            
                        elif current_status == "failed":
                            st.error("❌ 后端模型分析失败。")
                            break
                        else:
                            # 动态更新进度条文字
                            idx = int((time.time() - start_time) // 10) % len(quotes)
                            status_container.info(f"⏳ {quotes[idx]}")
                            # 进度条模拟（前 90%）
                            progress_val = min(int((time.time() - start_time) / 60 * 100), 90)
                            progress_bar.progress(progress_val)
                    
                    time.sleep(5) # 每 5 秒轮询一次
                    
            else:
                st.error(f"📡 API 响应异常: {resp.status_code}")
                
        except Exception as e:
            st.error(f"📡 无法连接到后端服务: {e}")

# --- 6. 页脚 ---
st.divider()
st.caption("© 2026 NewArtLiterature Collective | 数字化学术评审平台")
