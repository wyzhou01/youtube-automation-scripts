#!/usr/bin/env python3
"""
Fallback Tool Registry - 备选工具链自动切换
每个工具类记录: primary, fallback1, fallback2
每个工具有 health_check() 和 invoke() 方法
"""
import os
import requests
import subprocess
import time
import base64
import json
import re

# ===== ENV HELPERS =====

def get_env(key):
    """从 ~/.openclaw/.env 读取环境变量"""
    try:
        result = os.popen(f'grep {key} ~/.openclaw/.env 2>/dev/null | cut -d= -f2').read().strip()
        return result if result else None
    except Exception:
        return None


def get_dashscope_key():
    return get_env('DASHSCOPE_API_KEY') or get_env('DASHSCOPE_KEY')


def get_hyperbolic_key():
    return get_env('HYPERBOLIC_API_KEY')


def get_pexels_key():
    return get_env('PEXELS_API_KEY')


# ===== VIDEO SOURCE =====

def pexels_search(query, count=3):
    """从 Pexels 搜索视频"""
    api_key = get_pexels_key()
    if not api_key:
        raise Exception("PEXELS_API_KEY not found in .env")

    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": count, "orientation": "portrait"}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Pexels API error: {resp.status_code} {resp.text}")
    data = resp.json()
    videos = []
    for v in data.get("videos", [])[:count]:
        # 取最优质量的 mp4 URL
        video_files = v.get("video_files", [])
        best = min(video_files, key=lambda x: abs(x.get("width", 0) - 720), default=None) if video_files else None
        if best:
            videos.append({
                "url": best.get("link"),
                "duration": v.get("duration"),
                "width": best.get("width"),
                "height": best.get("height"),
                "id": v.get("id"),
            })
    return videos


def coverr_search(query, count=3):
    """从 Coverr 搜索免费视频"""
    # Coverr Public API - 免 key
    url = f"https://api.coverr.co/v1/search?q={requests.utils.quote(query)}&limit={count}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", []) if isinstance(data, dict) else []
            return [{"url": v.get("url") or v.get("src"), "duration": None, "id": v.get("id")} for v in results[:count]]
    except Exception:
        pass
    # Fallback: Coverr 首页搜索（网页爬取）
    search_url = f"https://coverr.co/s?q={requests.utils.quote(query)}"
    resp = requests.get(search_url, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Coverr search failed: {resp.status_code}")
    # 简单正则提取视频页面链接
    links = re.findall(r'href="(/videos/[^"]+)"', resp.text)
    videos = []
    for link in links[:count]:
        full_url = f"https://coverr.co{link}"
        videos.append({"url": full_url, "duration": None, "id": link})
    return videos


VIDEO_SOURCES = [
    {
        "name": "pexels",
        "primary": True,
        "check": lambda: bool(get_pexels_key()),
        "search": lambda q, n: pexels_search(q, n),
    },
    {
        "name": "coverr",
        "fallback_to": "pexels",
        "check": lambda: True,  # 公开API，无需key
        "search": lambda q, n: coverr_search(q, n),
    },
]


# ===== TTS VOICE =====

def edge_tts_speak(text, voice="AriaNeural", output_path="/tmp/tts_output.mp3"):
    """使用 edge-tts 生成语音"""
    import asyncio

    async def _run():
        cmd = [
            "edge-tts",
            "--text", text,
            "--voice", voice,
            "--write-media", output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise Exception(f"edge-tts failed: {stderr.decode()}")

    asyncio.run(_run())
    return output_path


def bailian_tts_speak(text, voice="Ethan", output_path="/tmp/tts_output_bailian.mp3"):
    """使用百炼 qwen3-tts-flash 生成语音"""
    api_key = get_dashscope_key()
    if not api_key:
        raise Exception("DASHSCOPE_API_KEY not found in .env")

    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "qwen3-tts-flash",
        "input": {"text": text[:600]},  # 限制600字符
        "voice": voice,
        "response_format": "mp3",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Bailian TTS error: {resp.status_code} {resp.text}")
    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path


TTS_SOURCES = [
    {
        "name": "edge-tts",
        "primary": True,
        "check": lambda: bool(os.popen("which edge-tts").read().strip()),
        "speak": lambda text, voice: edge_tts_speak(text, voice),
    },
    {
        "name": "bailian-tts",
        "fallback_to": "edge-tts",
        "check": lambda: bool(get_dashscope_key()),
        "speak": lambda text, voice: bailian_tts_speak(text, voice),
    },
]


# ===== IMAGE GENERATION =====

def hyperbolic_gen(prompt, output_path="/tmp/img_gen.png", size=1024):
    """使用 Hyperbolic SDXL-turbo 生成图片"""
    api_key = get_hyperbolic_key()
    if not api_key:
        raise Exception("HYPERBOLIC_API_KEY not found in .env")

    url = "https://api.hyperbolic.xyz/v1/image/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model_name": "SDXL-turbo",
        "prompt": prompt,
        "height": size,
        "width": size,
        "steps": 1,  # turbo 只需1步
        "rompt_extension": False,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        raise Exception(f"Hyperbolic error: {resp.status_code} {resp.text}")
    data = resp.json()
    images = data.get("images", [])
    if not images:
        raise Exception("No images returned from Hyperbolic")
    b64 = images[0].get("image", "")
    if not b64:
        raise Exception("Empty image data from Hyperbolic")
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(b64))
    return output_path


def bailian_image_gen(prompt, output_path="/tmp/img_gen_bailian.png"):
    """使用百炼 qwen-image-2.0-pro 生成图片"""
    api_key = get_dashscope_key()
    if not api_key:
        raise Exception("DASHSCOPE_API_KEY not found in .env")

    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "qwen-image-2.0-pro",
        "input": {"prompt": prompt},
        "parameters": {"size": "1024*1024", "prompt_extend": True},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code not in (200, 201):
        raise Exception(f"Bailian image error: {resp.status_code} {resp.text}")

    # 异步轮询
    task_id = None
    try:
        result = resp.json()
        task_id = result.get("id") or result.get("task_id")
    except Exception:
        task_id = None

    if task_id:
        for _ in range(30):
            time.sleep(3)
            status_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            sr = requests.get(status_url, headers=headers, timeout=15)
            if sr.status_code == 200:
                sd = sr.json()
                if sd.get("status") == "SUCCEEDED":
                    img_data = sd.get("output", {}).get("results", [{}])
                    if img_data and "image_url" in img_data[0]:
                        img_resp = requests.get(img_data[0]["image_url"], timeout=30)
                        with open(output_path, "wb") as f:
                            f.write(img_resp.content)
                        return output_path
                elif sd.get("status") == "FAILED":
                    raise Exception(f"Bailian image task failed: {sd}")
    raise Exception("Bailian image: task polling timed out")


def pollinations_gen(prompt, output_path="/tmp/img_gen_pollinations.png"):
    """使用 Polinations.ai 免费生成图片（公开API，无需key）"""
    safe_prompt = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&model=flux"
    resp = requests.get(url, timeout=60, allow_redirects=True)
    if resp.status_code != 200:
        raise Exception(f"Pollinations error: {resp.status_code}")
    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type and len(resp.content) < 1000:
        raise Exception(f"Pollinations returned non-image: {content_type}")
    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path


IMAGE_SOURCES = [
    {
        "name": "hyperbolic",
        "primary": True,
        "check": lambda: bool(get_hyperbolic_key()),
        "generate": lambda prompt: hyperbolic_gen(prompt),
    },
    {
        "name": "bailian-image",
        "fallback_to": "hyperbolic",
        "check": lambda: bool(get_dashscope_key()),
        "generate": lambda prompt: bailian_image_gen(prompt),
    },
    {
        "name": "pollinations",
        "fallback_to": "hyperbolic",
        "check": lambda: True,  # 公开API
        "generate": lambda prompt: pollinations_gen(prompt),
    },
]


# ===== CORE FUNCTIONS =====

def get_healthy_tool(tool_category):
    """返回可用的工具，尝试主工具，失败则依次试fallback"""
    tools = {
        "video": VIDEO_SOURCES,
        "tts": TTS_SOURCES,
        "image": IMAGE_SOURCES,
    }.get(tool_category, [])

    for tool in tools:
        try:
            if tool["check"]():
                return tool
        except Exception:
            pass

    # 全挂了，返回主工具（让调用方处理错误）
    return tools[0] if tools else None


def video_search(query, count=3):
    tool = get_healthy_tool("video")
    if not tool:
        return None, "所有视频源都不可用"
    try:
        result = tool["search"](query, count)
        return result, None
    except Exception as e:
        return None, str(e)


def tts_speak(text, voice="AriaNeural", output_path="/tmp/tts_output.mp3"):
    tool = get_healthy_tool("tts")
    if not tool:
        return None, "所有TTS源都不可用"
    try:
        result = tool["speak"](text, voice, output_path)
        return result, None
    except Exception as e:
        return None, str(e)


def image_generate(prompt, output_path="/tmp/img_gen.png"):
    tool = get_healthy_tool("image")
    if not tool:
        return None, "所有图片源都不可用"
    try:
        result = tool["generate"](prompt, output_path)
        return result, None
    except Exception as e:
        return None, str(e)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "video"
    q = sys.argv[2] if len(sys.argv) > 2 else "nature"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    if cmd == "video":
        r, err = video_search(q, n)
        print(r if r else f"Error: {err}")
    elif cmd == "image":
        r, err = image_generate(q)
        print(r if r else f"Error: {err}")
    elif cmd == "tts":
        r, err = tts_speak(q)
        print(r if r else f"Error: {err}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
