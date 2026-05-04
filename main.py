import os
import asyncio
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai

# --- 1. 初始化与配置 ---
app = FastAPI(title="NAL PictureBook AI Review API V2")

# 环境变量获取（请确保在 Render 后台已配置）
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("PB_AI_GEMINI_KEY")

# 初始化客户端
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# --- 2. 数据模型 ---
class EvalRequest(BaseModel):
    award_type: str
    image_urls: List[str]

# --- 3. 核心评审逻辑 (v65 4:3:3 权重模型) ---
async def run_v65_review(row_id: int, image_urls: List[str]):
    """
    异步执行 Gemini 深度评审任务
    """
    try:
        print(f"🧠 [v65] 启动深度评审任务，ID: {row_id}")
        
        # 配置模型
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 构建学术 Prompt (基于 NAL 4:3:3 评估体系)
        prompt = """
        请作为 NewArtLiterature (NAL) 专家评审，对提供的绘本图像进行深度学术评估。
        评估标准（4:3:3 权重）：
        1. 视觉对撞 (40%): 色彩张力、构图隐喻、图像叙事能效。
        2. 创意维度 (30%): 视觉语言的独特性与艺术原创性。
        3. 叙事平衡 (30%): 图文协同的节奏感与翻页带来的张力变化。
        
        请直接输出结果，格式要求如下：
        评分: [数字0-10]
        评价: [300字以内的专业学术评审报告]
        """
        
        # 准备分析内容
        # 注意：此处假设 image_urls 已是可访问的公网链接
        contents = [prompt] + image_urls
        
        # 模拟深度思考过程（Gemini 正常耗时 30-60秒）
        response = await asyncio.to_thread(model.generate_content, contents)
        result_text = response.text
        
        # 简单解析评分与报告
        score_val = 8.0 # 默认分
        if "评分:" in result_text:
            try:
                score_val = float(result_text.split("评分:")[1].split("\n")[0].strip())
            except: pass

        # 4. 回填数据库 (nal_evaluations_v2)
        supabase.table("nal_evaluations_v2").update({
            "v65_visual_score": score_val,
            "v65_synergy_report": result_text,
            "status": "completed"
        }).eq("id", row_id).execute()
        
        print(f"✅ [SUCCESS] 任务 {row_id} 评审完成")

    except Exception as e:
        print(f"❌ [v65 ERROR] 任务 {row_id} 失败: {str(e)}")
        supabase.table("nal_evaluations_v2").update({"status": "failed"}).eq("id", row_id).execute()

# --- 4. API 路由接口 ---

@app.post("/PB/api/evaluate")
async def evaluate(request: EvalRequest, background_tasks: BackgroundTasks):
    """
    接收请求：创建记录 -> 返回真 ID -> 开启异步评审
    """
    try:
        # 1. 准备入库数据 (不包含 ID，由 Supabase 自动生成)
        insert_data = {
            "award_type": request.award_type,
            "image_urls": request.image_urls,
            "status": "processing"
        }

        # 2. 执行插入并获取返回的数字 ID
        res = supabase.table("nal_evaluations_v2").insert(insert_data).execute()
        
        if not res.data:
            raise HTTPException(status_code=500, detail="数据库写入失败")

        # 获取自增生成的 bigint ID
        db_id = res.data[0]['id']
        print(f"📡 [API] 成功创建任务，获取数据库 ID: {db_id}")

        # 3. 启动后台异步任务
        background_tasks.add_task(run_v65_review, db_id, request.image_urls)

        # 4. 立即返回 ID 给前端，前端开始轮询
        return {"row_id": db_id}

    except Exception as e:
        print(f"❌ [CRITICAL] 接口崩溃: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/PB/api/status/{row_id}")
async def get_status(row_id: int):
    """
    前端轮询进度接口
    """
    res = supabase.table("nal_evaluations_v2").select("*").eq("id", row_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="记录不存在")
    return res.data[0]

@app.get("/")
def health_check():
    return {"status": "online", "version": "v2.0.0-v65"}
