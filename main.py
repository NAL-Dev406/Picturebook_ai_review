import os
import uuid
import httpx
from io import BytesIO
from PIL import Image
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai
from fastapi.middleware.cors import CORSMiddleware

# --- 1. 初始化与配置 ---
app = FastAPI(title="NAL Vision & Synergy Engine (Stateless)", version="v2.2.0")

# 配置 CORS
origins = [
    "https://nal-ai.org",
    "https://pb.nal-ai.org",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("PB_AI_GEMINI_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# --- 2. 内存任务池 (替代数据库) ---
# 用于在前端轮询期间临时保存任务状态和生成的报告
TASK_STORE = {}
BUCKET_NAME = "nal_images"

# --- 3. 数据通信模型 ---
class EvalRequest(BaseModel):
    work_type: str        
    script_text: str      
    image_urls: List[str] 

# --- 4. 核心工具库 ---
async def fetch_images_as_pil(urls: List[str]) -> List[Image.Image]:
    pil_images = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for url in urls:
            try:
                print(f"🔄 下载缓存: {url}")
                resp = await client.get(url, timeout=20.0)
                
                if resp.status_code == 200:
                    img = Image.open(BytesIO(resp.content))
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    max_size = 1600
                    if max(img.width, img.height) > max_size:
                        scale = max_size / max(img.width, img.height)
                        new_size = (int(img.width * scale), int(img.height * scale))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)

                    pil_images.append(img)
                    del resp
            except Exception as e:
                print(f"⚠️ 下载异常: {url} -> {str(e)}")
                
    return pil_images

# --- 5. NAL 核心学术引擎 (后台任务) ---
async def run_nal_engine(task_id: str, payload: dict):
    try:
        print(f"🧠 [NAL Engine] 唤醒引擎... 虚拟ID: {task_id}")
        
        images = await fetch_images_as_pil(payload['image_urls'])
        if not images:
            raise Exception("无法提取有效视觉素材。")

        script_text = payload.get("script_text", "无文本")
        
        # 构建 Prompt (保持你原有的学术设定)
        if payload['work_type'] == "picture_book":
            prompt = f"""
            你现在是 NAL (NewArtLiterature) 平台的首席结构派绘本研究员。
            请对附件中的【跨页图像】和以下【文字脚本】进行深度的图文协同（Synergy）分析。
            
            【配套文字脚本/意图】：
            "{script_text}"
            
            【NAL 4:3:3 核心评估准则】：
            1. 视觉对撞 (40%): 色彩张力与跨页构图。
            2. 创意维度 (30%): 拒绝平庸图解，图像是否在脚本之外创造了第二层隐喻？
            3. 叙事平衡 (30%): v5 脚本缺口测试——画面是否有效地填充了文字留下的呼吸空间与心理外化？
            
            【格式要求】请直接输出：
            评分: [基于10分制的综合数字，例如 8.5]
            评价: [300-400字的专业学术分析，严厉且中肯，重点阐述图文协同关系。]
            """
        else:
            prompt = f"""
            你现在是 NAL (NewArtLiterature) 平台的视觉艺术评论家。
            请对附件中的【插画原图】进行评估。
            
            【作者创作意图/背景】：
            "{script_text}"
            
            【NAL 4:3:3 核心评估准则】：
            1. 视觉对撞 (40%): 色彩饱和度、光影调度与情绪对撞。
            2. 创意维度 (30%): 空间切割与视觉语言的独特性。
            3. 意图契合 (30%): 核心拷问——这幅画面是克制且精准地传递了上述创作意图，还是偏离了文本，陷入了“无意义的炫技”？
            
            【格式要求】请直接输出：
            评分: [基于10分制的综合数字，例如 8.0]
            评价: [300-400字的专业学术分析，重点阐述构图隐喻以及对创作意图的响应。]
            """

        model = genai.GenerativeModel('gemini-2.5-flash')
        contents = [prompt] + images
        
        response = await model.generate_content_async(contents)
        result_text = response.text
        
        score_val = 7.5
        if "评分:" in result_text:
            try:
                score_str = result_text.split("评分:")[1].split("\n")[0].replace("分", "").strip()
                score_val = float(score_str)
            except Exception:
                pass

        # 写入内存，供前端轮询拉取
        TASK_STORE[task_id].update({
            "status": "completed",
            "v65_visual_score": score_val,
            "v65_synergy_report": result_text
        })
        print(f"🎯 [NAL Engine] 任务 {task_id} 评审结案。")

    except Exception as e:
        print(f"❌ [NAL Engine ERROR] 任务 {task_id} 崩溃: {str(e)}")
        TASK_STORE[task_id].update({
            "status": "failed",
            "v65_synergy_report": f"引擎分析失败: {str(e)}"
        })

    finally:
        # 🧹 【核心新增：阅后即焚清理机制】
        # 无论成功或失败，都在最后强制删除 Supabase Bucket 中的文件
        for url in payload.get('image_urls', []):
            try:
                # 提取文件相对路径: url 格式通常为 https://.../public/nal_images/review_images/123.jpg
                file_path = url.split(f"/{BUCKET_NAME}/")[-1]
                supabase.storage.from_(BUCKET_NAME).remove([file_path])
                print(f"🗑️ [阅后即焚] 已销毁云端缓存: {file_path}")
            except Exception as delete_err:
                print(f"⚠️ [阅后即焚] 清理失败: {delete_err}")

# --- 6. API 路由接口 ---

@app.post("/PB/api/evaluate")
async def evaluate(request: EvalRequest, background_tasks: BackgroundTasks):
    try:
        # 使用 UUID 生成虚拟的任务 ID，替代原来的数据库自增 ID
        task_id = uuid.uuid4().hex
        
        # 初始化内存状态
        TASK_STORE[task_id] = {
            "status": "processing",
            "work_type": request.work_type
        }
        
        payload_dict = request.dict()
        background_tasks.add_task(run_nal_engine, task_id, payload_dict)

        return {"row_id": task_id, "message": "学术分析已立项并进入无痕模式"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/PB/api/status/{task_id}")
async def get_status(task_id: str):
    """
    前端心跳轮询接口 (纯内存读取)
    """
    task_data = TASK_STORE.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="未找到该档案或由于重启已丢失")
    return task_data

@app.get("/")
def health_check():
    return {
        "status": "online", 
        "architecture": "NAL Stateless Engine", 
        "privacy": "Zero-Retention (Burn after reading)"
    }
