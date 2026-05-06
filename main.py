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

import json

# --- 4. NAL 核心学术引擎 (注入 V5/V65 纯正学术理论版) ---
import json

async def run_nal_engine(task_id: str, payload: dict):
    try:
        print(f"🧠 [NAL Engine] 唤醒引擎... 虚拟ID: {task_id}")
        
        images = await fetch_images_as_pil(payload.get('image_urls', []))
        if not images:
            raise Exception("无法提取有效视觉素材。")

        script_text = payload.get("script_text", "无文本")
        
        if payload.get('work_type') == "picture_book":
            prompt = f"""
            你现在是 NAL (NewArtLiterature) 平台的首席结构派绘本研究员。
            请结合【陈晖《图文转化论》】、【葛承训《统合美学》】以及【巴德图画书理论】，对附件中的【跨页图像】和以下【文字脚本】进行深度的图文协同（Synergy）分析。
            
            【配套文字脚本/意图】：
            "{script_text}"
            
            【NAL 4:3:3 核心学术评估体系】：
            1. 画面艺术性 (40%)：
               - 陈晖视角：评估线条生命力、色彩契合度、造型独创性及全书风格稳定性。
               - 葛承训视角：评估画面中民族元素或艺术内核的现代活化能力。
            2. 创意与视觉隐喻 (30%)：
               - 评估画面意象的厚度。拒绝平庸图解，图像是否在脚本之外创造了第二层隐喻和多层解码空间？
            3. 叙事效率与节奏 (30%)：
               - 巴德视角：评估图文依存关系。画面是否有效填充了文字留下的“视觉代偿预留”？跨页翻页是否具备动力钩子与呼吸感？
            """
        else:
            prompt = f"""
            你现在是 NAL (NewArtLiterature) 平台的视觉艺术评论家。
            请结合【葛承训《统合美学》】与现代视觉隐喻理论，对附件中的【插画原图】进行深度的解构与评估。
            
            【作者创作意图/背景】：
            "{script_text}"
            
            【NAL 4:3:3 核心学术评估体系】：
            1. 画面艺术性 (40%)：
               - 评估色彩饱和度、光影调度、构图张力。其艺术内核是否具备现代审美的统合力？
            2. 创意维度 (30%)：
               - 空间切割与视觉语言的独特性。意象隐喻基底是否深厚？是否拒绝了平庸的图解式表达？
            3. 意图契合 (30%)：
               - 核心拷问——这幅画面是克制且精准地传递了上述创作意图，还是偏离了文本，陷入了“无意义的炫技”？
            """

        alignment_rules = """
        【⛔ 强制对齐与逻辑约束（最高优先级）】：
        请严格遵循“先出具诊断评语，再推导最终分数”的逻辑。你的【分数】必须与你的【评语语气】绝对一致：
        - [9.0 - 10.0分]：极高图文转化潜力的视觉杰作，无懈可击。
        - [8.0 - 8.9分]：专业水准卓越，但可指出微小瑕疵（如过渡页张力不足）。
        - [7.0 - 7.9分]：指出结构或图文协同上的明显缺陷，语气克制严厉。
        - [7.0分以下]：完全背离意图或存在严重审美硬伤，严肃批评。

        【输出格式要求】：
        必须严格返回合法的 JSON 格式，不可包含 Markdown 代码块标记，只需纯 JSON：
        {
            "v65_synergy_report": "集成以上学术视角的专业点评（300-400字）。【重要排版指令】：必须使用双换行符（\\n\\n）进行自然的段落切分，绝对不能输出挤在一起的文字墙！行文应如行云流水般融汇视觉与意图的分析。",
            "v65_visual_score": 8.5
        }
        """
        
        final_prompt = prompt + alignment_rules

        model = genai.GenerativeModel('gemini-2.5-flash')
        contents = [final_prompt] + images
        
        generation_config = genai.types.GenerationConfig(
            temperature=0.05, 
            top_p=0.8,
            response_mime_type="application/json"
        )
        
        response = await model.generate_content_async(
            contents,
            generation_config=generation_config
        )
        
        try:
            result_data = json.loads(response.text)
            report_text = result_data.get("v65_synergy_report", "报告生成异常。")
            score_val = float(result_data.get("v65_visual_score", 7.5))
        except json.JSONDecodeError:
            print(f"⚠️ JSON解析失败，原始文本: {response.text}")
            report_text = "系统解析引擎反馈异常，请检查输入或联系管理员。"
            score_val = 7.0

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
        for url in payload.get('image_urls', []):
            try:
                # 阅后即焚
                file_path = url.split(f"/{BUCKET_NAME}/")[-1]
                supabase.storage.from_(BUCKET_NAME).remove([file_path])
                print(f"🗑️ [阅后即焚] 已销毁云端缓存: {file_path}")
            except Exception as delete_err:
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
