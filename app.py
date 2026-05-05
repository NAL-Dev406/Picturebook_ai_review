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
# --- 修改 main.py 中的核心评审逻辑 ---

class EvalRequest(BaseModel):
    work_type: str # 'picture_book' 或 'illustration'
    script_text: str = ""
    image_urls: List[str]

async def run_nal_engine(row_id: int, payload: dict):
    try:
        print(f"🧠 启动 NAL 评审引擎，ID: {row_id}，模式: {payload['work_type']}")
        
        # 1. 转换图片为对象 (假设你已经有了 httpx 下载逻辑)
        processed_images = await download_images(payload['image_urls']) 
        
        # 2. 根据作品形态，组装深度 Instruction
        if payload['work_type'] == "picture_book":
            # 【绘本模式：v5 + v65 协同】
            prompt = f"""
            你现在是 NAL (NewArtLiterature) 平台的首席结构派绘本研究员。
            请对附件中的【图片】和以下【文字脚本】进行深度的图文协同（Synergy）分析。
            
            【文字脚本】：
            {payload['script_text']}
            
            【评估准则（必须严格执行）】：
            1. 拒绝“插画中心主义”：不要孤立地评价画得美不美。
            2. v5 脚本缺口测试：文字是否留有呼吸感？画面是否仅仅在“图解”文字，还是创造了第二层文本（例如外化了角色的深层心理学特征）？
            3. v65 视觉协同：评估翻页间的色彩情绪流变。
            
            请输出：
            协同评分: [数字0-10]
            评价: [300字以内的专业学术分析，重点阐述图文关系]
            """
        else:
            # 【插画模式：纯 v65 视觉】
            prompt = """
            你现在是 NAL (NewArtLiterature) 平台的视觉艺术评论家。
            请对附件中的插画作品进行纯粹的视觉叙事评估。
            
            【评估准则（必须严格执行）】：
            1. 视觉张力：分析色彩饱和度与光影对比带来的情绪对撞。
            2. 构图隐喻：画面中的空间切割、视角选择是否具有隐喻性？
            3. 独立叙事性：作为单幅作品，它是否能在没有文字辅助的情况下，通过视觉元素完整传达一种情境或理念？
            
            请输出：
            视觉评分: [数字0-10]
            评价: [300字以内的专业学术分析，重点阐述构图与视觉张力]
            """

        # 3. 提交给 Gemini (1.5 Flash 或 Pro)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = await asyncio.to_thread(model.generate_content, [prompt] + processed_images)
        result_text = response.text
        
        # 4. 解析分数 (通用提取)
        score_val = 8.0
        if "评分:" in result_text:
            try:
                score_val = float(result_text.split("评分:")[1].split("\n")[0].strip())
            except: pass

        # 5. 回填数据库 (nal_evaluations_v2 表)
        supabase.table("nal_evaluations_v2").update({
            "v65_visual_score": score_val,
            "v65_synergy_report": result_text,
            "status": "completed"
        }).eq("id", row_id).execute()

    except Exception as e:
        print(f"❌ 引擎崩溃: {e}")
        supabase.table("nal_evaluations_v2").update({"status": "failed"}).eq("id", row_id).execute()
        
# --- 4. 底部版权信息 ---
st.divider()
st.caption("© 2026 NewArtLiterature Collective | 艺术文献与数字学术平台")
