import os
import asyncio
import httpx
from io import BytesIO
from PIL import Image
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai

# --- 1. 初始化与配置 ---
app = FastAPI(title="NAL Vision & Synergy Engine", version="v2.1.0")

# 环境变量 (Render 后台配置)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 初始化客户端
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# --- 2. 数据通信模型 ---
class EvalRequest(BaseModel):
    work_type: str        # 'picture_book' 或 'illustration'
    script_text: str      # 文本脚本 或 创作意图
    image_urls: List[str] # Supabase 存储桶中的公网链接

# --- 3. 核心工具库 ---
async def fetch_images_as_pil(urls: List[str]) -> List[Image.Image]:
    """
    异步下载 Supabase 图片并转换为 Gemini 可直接处理的 PIL 对象
    """
    pil_images = []
    async with httpx.AsyncClient() as client:
        for url in urls:
            try:
                resp = await client.get(url, timeout=15.0)
                if resp.status_code == 200:
                    img = Image.open(BytesIO(resp.content))
                    # 转换为 RGB 以防 PNG 透明通道导致报错
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    pil_images.append(img)
                else:
                    print(f"⚠️ 图片下载失败 (HTTP {resp.status_code}): {url}")
            except Exception as e:
                print(f"⚠️ 图片处理异常: {url} -> {str(e)}")
    return pil_images

# --- 4. NAL 核心学术引擎 (v5 文本 + v65 视觉) ---
async def run_nal_engine(row_id: int, payload: dict):
    try:
        print(f"🧠 [NAL Engine] 唤醒引擎... 档案ID: {row_id} | 模式: {payload['work_type']}")
        
        # 1. 预处理视觉素材
        images = await fetch_images_as_pil(payload['image_urls'])
        if not images:
            raise Exception("无法提取有效视觉素材，请检查存储策略。")

        # 2. 组装深度学术 Instruction (Prompt Engineering)
        script_text = payload.get("script_text", "无文本")
        
        if payload['work_type'] == "picture_book":
            # 绘本模式：强化图文协同与跨页节奏
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
            # 插画模式：强化意图契合与视觉张力
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

        # 3. 提交给 Gemini 模型进行多模态计算
        # 确保传入的是 Prompt (文本) + PIL Image (图像) 的混合列表
        model = genai.GenerativeModel('gemini-1.5-flash')
        contents = [prompt] + images
        
        # 使用 to_thread 防止网络 IO 阻塞 FastAPI 主线程
        response = await asyncio.to_thread(model.generate_content, contents)
        result_text = response.text
        
        # 4. 解析结果
        score_val = 7.5 # 保底默认分
        if "评分:" in result_text:
            try:
                # 简单粗暴的切割提取数字
                score_str = result_text.split("评分:")[1].split("\n")[0].replace("分", "").strip()
                score_val = float(score_str)
            except Exception as e:
                print(f"⚠️ 分数解析警告: {e}")

        # 5. 回填至 Supabase (nal_evaluations_v2)
        supabase.table("nal_evaluations_v2").update({
            "v65_visual_score": score_val,
            "v65_synergy_report": result_text,
            "status": "completed"
        }).eq("id", row_id).execute()
        
        print(f"🎯 [NAL Engine] 档案 {row_id} 评审结案。")

    except Exception as e:
        print(f"❌ [NAL Engine ERROR] 档案 {row_id} 崩溃: {str(e)}")
        # 失败状态回填
        supabase.table("nal_evaluations_v2").update({
            "status": "failed",
            "v65_synergy_report": f"引擎分析失败: {str(e)}"
        }).eq("id", row_id).execute()

# --- 5. API 路由接口 ---

@app.post("/PB/api/evaluate")
async def evaluate(request: EvalRequest, background_tasks: BackgroundTasks):
    try:
        # 1. 初始化数据库记录 (获取自增 bigint ID)
        insert_data = {
            "award_type": "picture_book" if request.work_type == "picture_book" else "illustration",
            "image_urls": request.image_urls,
            "status": "processing"
        }
        
        res = supabase.table("nal_evaluations_v2").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="数据库建立档案失败")

        db_id = res.data[0]['id']
        
        # 2. 压入后台处理队列
        payload_dict = request.dict()
        background_tasks.add_task(run_nal_engine, db_id, payload_dict)

        # 3. 即时返回通行凭证给前端
        return {"row_id": db_id, "message": "学术分析已立项"}

    except Exception as e:
        print(f"❌ [API] /evaluate 路由错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/PB/api/status/{row_id}")
async def get_status(row_id: int):
    """
    前端心跳轮询接口
    """
    res = supabase.table("nal_evaluations_v2").select("*").eq("id", row_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="未找到该档案")
    return res.data[0]

@app.get("/")
def health_check():
    return {
        "status": "online", 
        "architecture": "NAL Dual Engine (v5+v65)", 
        "location": "Richmond Hill Data Node"
    }
