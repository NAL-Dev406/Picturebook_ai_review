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
import json # 别忘了在 main.py 顶部确认导入了 json

async def run_nal_engine(task_id: str, payload: dict):
    try:
        print(f"🧠 [NAL Engine] 唤醒引擎... 虚拟ID: {task_id}")
        
        images = await fetch_images_as_pil(payload['image_urls'])
        if not images:
            raise Exception("无法提取有效视觉素材。")

        script_text = payload.get("script_text", "无文本")
        
        # --- 优化点 1：重构 Prompt，加入强制对齐约束 ---
        base_prompt = f"""
        你现在是 NAL (NewArtLiterature) 平台的首席结构派视觉叙事研究员。
        
        【配套文本/创作意图】：
        "{script_text}"
        
        【NAL 4:3:3 核心评估准则】：
        1. 视觉对撞 (40%): 色彩张力、光影调度与构图隐喻。
        2. 创意维度 (30%): 拒绝平庸图解，空间切割与视觉语言的独特性。
        3. 意图契合与叙事平衡 (30%): 画面是否克制且精准地传递了创作意图？是否陷入了“无意义的炫技”？
        """

        alignment_rules = """
        【⛔ 强制对齐与逻辑约束（最高优先级）】：
        请严格遵循“先出具诊断评语，再推导最终分数”的逻辑。你的【分数】必须与你的【评语语气】绝对一致：
        - [9.0 - 10.0分]：评语必须是极度赞赏，认为其具有极高艺术价值与协同度，几乎无懈可击。
        - [8.0 - 8.9分]：评语应以专业肯定为主，画面优秀，但可指出微小瑕疵或改进空间。
        - [7.0 - 7.9分]：评语必须明确指出结构、色彩或图文协同上的明显缺陷，语气客观、克制甚至严厉。
        - [7.0分以下]：评语必须以严肃批评为主，指出其完全背离意图或存在严重的技术/审美硬伤。

        【输出格式要求】：
        必须严格返回合法的 JSON 格式，不可包含 Markdown 代码块标记（如 ```json），只需纯 JSON：
        {
            "synergy_report": "300-400字的专业学术分析，严格遵守上述语气约束...",
            "score": 8.5
        }
        """
        
        prompt = base_prompt + alignment_rules

        model = genai.GenerativeModel('gemini-2.5-flash')
        contents = [prompt] + images
        
        # --- 优化点 2：锁定温度与强制 JSON 输出 ---
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,  # 📉 将温度降到极低 (0.1)，极大提高评审结果的稳定性
            top_p=0.8,
            response_mime_type="application/json", # 🚀 强制模型输出标准 JSON，避免正则解析失败
        )
        
        response = await model.generate_content_async(
            contents, 
            generation_config=generation_config
        )
        
        # 解析返回的 JSON
        try:
            result_data = json.loads(response.text)
            report_text = result_data.get("synergy_report", "报告生成异常。")
            score_val = float(result_data.get("score", 7.5))
        except json.JSONDecodeError:
            # 极端情况下的 fallback
            report_text = response.text
            score_val = 7.5

        # 写入内存，供前端轮询拉取
        TASK_STORE[task_id].update({
            "status": "completed",
            "v65_visual_score": score_val,
            "v65_synergy_report": report_text
        })
        print(f"🎯 [NAL Engine] 任务 {task_id} 评审结案。得分: {score_val}")

    except Exception as e:
        print(f"❌ [NAL Engine ERROR] 任务 {task_id} 崩溃: {str(e)}")
        TASK_STORE[task_id].update({
            "status": "failed",
            "v65_synergy_report": f"引擎分析失败: {str(e)}"
        })

    finally:
        # 阅后即焚清理逻辑保持不变...
        for url in payload.get('image_urls', []):
            try:
                file_path = url.split(f"/{BUCKET_NAME}/")[-1]
                supabase.storage.from_(BUCKET_NAME).remove([file_path])
            except Exception:
                pass

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
