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

        # 3. 提交给 Gemini (2.5 Flash)
        model = genai.GenerativeModel('gemini-2.5-flash')
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
