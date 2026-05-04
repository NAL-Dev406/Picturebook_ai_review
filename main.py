import os
import json
import time
import httpx
import PIL.Image
from io import BytesIO
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl
from google import genai
from google.genai import types
from supabase import create_client

# ================= 1. 环境配置 (从 Render 环境变量读取) =================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("PB_AI_GEMINI_KEY")
MODEL_ID = "gemini-2.5-flash"

# 初始化客户端
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai_client = genai.Client(api_key=GEMINI_API_KEY)

# 修改 FastAPI 初始化，确保 docs 和 openapi 路径一致
app = FastAPI(
    docs_url="/PB/docs", 
    openapi_url="/PB/openapi.json"
)

# --- 新增：处理根路径，解决 Render 日志中的 404 ---
@app.get("/")
async def root_health():
    """
    让 Render 的 HEAD / 和 GET / 检查通过
    """
    return {"message": "NAL PB API is running", "docs": "/PB/docs"}

# --- 原有的路由保持不变 ---
@app.post("/PB/api/evaluate")
async def post_evaluate(req: EvaluationRequest, background_tasks: BackgroundTasks):

# ================= 2. Schema 定义 =================
NAL_V5_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'final_score': {'type': 'NUMBER'},
        'final_critique': {'type': 'STRING'},
        'award_prediction': {'type': 'STRING'},
        'dispute_analysis': {'type': 'STRING'}
    },
    'required': ['final_score', 'final_critique', 'award_prediction', 'dispute_analysis']
}

NAL_SCHEMA_V65 = {
    'type': 'OBJECT',
    'properties': {
        'v65_visual_score': {'type': 'NUMBER'},
        'v65_critique': {'type': 'STRING'},
        'v65_prediction': {'type': 'STRING'},
        'v65_synergy_report': {'type': 'STRING'}
    },
    'required': ['v65_visual_score', 'v65_critique', 'v65_prediction', 'v65_synergy_report']
}

class EvaluationRequest(BaseModel):
    id: int
    award_type: str
    image_urls: list[HttpUrl]

# ================= 3. 核心工具逻辑 =================
async def fetch_and_resize(urls: list[HttpUrl], max_dim=1536):
    """远程图片处理：流式下载与内存压缩"""
    images = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for url in urls:
            try:
                resp = await client.get(str(url))
                if resp.status_code == 200:
                    img = PIL.Image.open(BytesIO(resp.content))
                    if max(img.size) > max_dim:
                        img.thumbnail((max_dim, max_dim), PIL.Image.Resampling.LANCZOS)
                    images.append(img.convert("RGB"))
            except Exception as e:
                print(f"图片处理异常: {url} | {e}")
    return images

# ================= 4. 异步任务编排 =================
async def run_pb_review_workflow(row_id: int, award_type: str, urls: list[HttpUrl]):
    """执行 V5+V6.5 对撞评审流"""
    try:
        # 获取作品基础信息
        res = supabase.table("nal_reviews").select("*").eq("id", row_id).single().execute()
        db_data = res.data

        # Step 1: V5 文本分析 (侧重叙事潜力)
        v5_resp = genai_client.models.generate_content(
            model=MODEL_ID,
            contents=f"标题: {db_data['title']}\n梗概: {db_data.get('sketch', '')}",
            config=types.GenerateContentConfig(
                system_instruction="你现在是 NAL 终审主席。评审重点：1.视觉代偿预留 2.翻页动力钩子 3.意象隐喻基底。",
                response_mime_type='application/json',
                response_schema=NAL_V5_SCHEMA,
                temperature=0
            )
        )
        v5_out = json.loads(v5_resp.text)

        # Step 2: V6.5 视觉对撞 (4:3:3 权重)
        imgs = await fetch_and_resize(urls)
        v65_resp = genai_client.models.generate_content(
            model=MODEL_ID,
            contents=[f"作品: {db_data['title']}"] + imgs,
            config=types.GenerateContentConfig(
                system_instruction=f"评审【{award_type}】视觉画面。严格按 4:3:3 权重（艺术表现:40%, 创意隐喻:30%, 叙事节奏:30%）给出分值与深度报告。",
                response_mime_type='application/json',
                response_schema=NAL_SCHEMA_V65,
                temperature=0.1
            )
        )
        v65_out = json.loads(v65_resp.text)

        # Step 3: 数据聚合回填
        update_payload = {
            "final_score": float(v5_out.get('final_score', 0)),
            "final_critique": v5_out.get('final_critique', ""),
            "dispute_analysis": v5_out.get('dispute_analysis', ""),
            "v65_visual_score": float(v65_out.get('v65_visual_score', 0)),
            "v65_critique": v65_out.get('v65_critique', ""),
            "v65_prediction": v65_out.get('v65_prediction', ""),
            "v65_synergy_report": v65_out.get('v65_synergy_report', ""),
            "is_evaluated": True
        }
        supabase.table("nal_reviews").update(update_payload).eq("id", row_id).execute()

    except Exception as e:
        print(f"ID {row_id} 评审任务失败: {e}")

# ================= 5. API 路由 =================
@app.post("/PB/api/evaluate")
async def post_evaluate(req: EvaluationRequest, background_tasks: BackgroundTasks):
    """启动异步评审"""
    background_tasks.add_task(run_pb_review_workflow, req.id, req.award_type, req.image_urls)
    return {"status": "started", "row_id": req.id}

@app.get("/PB/api/status/{row_id}")
async def get_status(row_id: int):
    """供前端轮询评审状态"""
    res = supabase.table("nal_reviews").select("v65_visual_score, is_evaluated").eq("id", row_id).execute()
    return res.data[0] if res.data else {"error": "not found"}

@app.get("/PB/health")
async def health():
    return {"status": "ok"}
