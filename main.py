import os
import time
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List
from supabase import create_client, Client
import google.generativeai as genai

app = FastAPI()

# --- 1. 环境配置 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("PB_AI_GEMINI_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ 错误：环境变量配置不全！")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# --- 2. 数据模型 ---
class EvalRequest(BaseModel):
    award_type: str
    image_urls: List[str]

# --- 3. 核心功能：4:3:3 深度评审任务 ---
async def deep_evaluation_process(row_id: int, image_urls: List[str]):
    """
    在后台运行的深度模型分析任务
    """
    try:
        print(f"🧠 [Gemini] 开始分析评审记录 ID: {row_id}")
        model = genai.GenerativeModel('gemini-1.5-flash') # 使用 Flash 兼顾速度与深度
        
        # 构建符合 NAL 4:3:3 权重的学术 Prompt
        prompt = f"""
        作为 NewArtLiterature (NAL) 的专业评审专家，请对以下绘本图像进行深度评估。
        评估标准（4:3:3 权重）：
        1. 视觉对撞 (40%): 色彩张力、构图对比、图像隐喻。
        2. 创意维度 (30%): 题材独特性、视觉语言的原创性。
        3. 叙事平衡 (30%): 图文协同的节奏感、翻页带来的叙事推动。
        
        请直接给出评分（0-10分）和一份 300 字以内的学术评价报告。
        格式要求：
        评分: [数字]
        评价: [文本内容]
        """
        
        # 准备图片内容 (假设是 URL 模式，这里需要先下载或由 Gemini 直接访问)
        # 注意：这里简化了图片处理逻辑，实际开发中建议转换为 PIL Image
        contents = [prompt] + image_urls 
        
        response = model.generate_content(contents)
        result_text = response.text
        
        # 解析评分（简单示例：提取第一行数字）
        try:
            score = float(result_text.split('\n')[0].replace("评分:", "").strip())
        except:
            score = 7.5 # 兜底分

        # 回填数据库
        supabase.table("nal_reviews").update({
            "v65_visual_score": score,
            "v65_synergy_report": result_text,
            "status": "completed"
        }).eq("id", row_id).execute()
        
        print(f"✅ [SUCCESS] ID {row_id} 评审完成并存入数据库")

    except Exception as e:
        print(f"❌ [GEMINI/DB ERROR] ID {row_id} 处理失败: {e}")
        supabase.table("nal_reviews").update({"status": "failed"}).eq("id", row_id).execute()

# --- 4. API 路由 ---

@app.post("/PB/api/evaluate")
async def evaluate(request: EvalRequest, background_tasks: BackgroundTasks):
    """
    接收评审请求：先存库，拿 ID，再开后台任务
    """
    try:
        # 1. 准备初始数据
        insert_data = {
            "award_type": request.award_type,
            "image_urls": request.image_urls,
            "status": "processing",
            "created_at": "now()" # 让数据库处理时间
        }

        # 2. 执行写入 (关键：必须先写入并拿到返回数据)
        res = supabase.table("nal_reviews").insert(insert_data).execute()
        
        if not res.data:
            raise HTTPException(status_code=500, detail="数据库写入失败，未返回记录")

        # 3. 获取真实的、唯一的数据库自增 ID
        actual_id = res.data[0]['id']
        print(f"📡 [API] 已成功创建评审任务，ID: {actual_id}")

        # 4. 开启后台异步评审任务
        background_tasks.add_task(deep_evaluation_process, actual_id, request.image_urls)

        # 5. 返回给前端真实的 ID
        return {"row_id": actual_id}

    except Exception as e:
        print(f"❌ [CRITICAL] 接口崩溃: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/PB/api/status/{row_id}")
async def get_status(row_id: int):
    """
    供前端轮询进度
    """
    res = supabase.table("nal_reviews").select("*").eq("id", row_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="记录不存在")
    return res.data[0]

@app.get("/")
def home():
    return {"status": "NAL API is Online"}
