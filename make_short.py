#!/usr/bin/env python3
"""
AI ToolBox Shorts Pipeline v3 - 竖屏短视频(9:16, ≤60秒)
Pexels真实视频 + 百炼TTS配音 + FFmpeg合成
用法: python3 make_short.py [标题] [描述] [标签...]
"""
import os, sys, pickle, requests, time, subprocess
OUT_DIR = os.path.expanduser('~/Desktop/OpenClaw')
os.makedirs(OUT_DIR, exist_ok=True)
from datetime import datetime

TOKEN_FILE = os.path.expanduser('~/.openclaw/youtube_token.pickle')

# ============ CONFIG ENV PATH (auto-detected) ============
# 尝试 ~/.openclaw/.env 和 ~/.openclaw_.env，preflight_check() 会设置正确的路径
CONFIG_ENV_PATH = None  # 全局存储，_get_env() 会优先使用

def _get_env(key):
    """读取配置 key，优先使用 preflight_check() 检测到的 CONFIG_ENV_PATH"""
    # 优先用 preflight_check() 确定的路径
    if CONFIG_ENV_PATH:
        try:
            val = os.popen(f'grep {key} {CONFIG_ENV_PATH} | cut -d= -f2').read().strip()
            if val:
                return val
        except:
            pass
    # 回退：尝试两个标准路径
    for path in ['~/.openclaw/.env', '~/.openclaw_.env']:
        try:
            val = os.popen(f'grep {key} {path} | cut -d= -f2').read().strip()
            if val:
                return val
        except:
            pass
    return ''

HYPERBOLIC_KEY = _get_env('HYPERBOLIC')

SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
MAX_DURATION = 28   # 目标25-28s:最佳完成率区间

TOPIC = sys.argv[1] if len(sys.argv) > 1 else "3 AI Tips in 60 Seconds!"
DESC = sys.argv[2] if len(sys.argv) > 2 else "Quick AI tips that save you hours every week! #Shorts #AI #Productivity"
TAGS = sys.argv[3:] if len(sys.argv) > 3 else ["AI Tips", "Shorts", "Productivity", "AI", "2026"]

def log(m): print(f"  {m}")

# ============ TOKEN ============
def get_token():
    from datetime import datetime, timezone, timedelta
    CLIENT_ID = '${YOUTUBE_CLIENT_ID}'
    CLIENT_SECRET = '${YOUTUBE_CLIENT_SECRET}'
    TOKEN_FILE = os.path.expanduser('~/.openclaw/youtube_token.pickle')

    result = subprocess.run(
        ['security', 'find-generic-password', '-s', 'youtube-token-openclaw', '-a', 'bot-refresh-token', '-w'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        refresh_token = result.stdout.strip()
        resp = requests.post('https://oauth2.googleapis.com/token', data={
            'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
            'refresh_token': refresh_token, 'grant_type': 'refresh_token'
        })
        if resp.status_code == 200:
            d = resp.json()
            d['expiry'] = (datetime.now(timezone.utc) + timedelta(seconds=d['expires_in'])).isoformat()
            with open(TOKEN_FILE, 'wb') as f:
                pickle.dump(d, f)
            return d.get('access_token')

    with open(TOKEN_FILE, 'rb') as f:
        creds = pickle.load(f)
    return creds.token if hasattr(creds, 'token') else creds.get('access_token')

# ============ PEXELS 真实视频(Primary)============
PEXELS_KEY = _get_env('PEXELS')

TOPIC_VIDEO_MAP = {
    "email": 'technology workspace computer',
    "chatgpt": 'chatgpt phone screen',
    "gpt": 'chatgpt phone screen',
    "productivity": 'focused work creative professional office',
    "code": 'computer screen code',
    "programming": 'computer screen code',
    "data": 'data analytics visualization',
    "analytics": 'data analytics visualization',
    "robot": 'robot artificial intelligence',
    "automation": 'robot artificial intelligence',
    "learn": 'technology learning education',
    "study": 'technology learning education',
    "business": 'business office meeting',
    "app": 'technology app screen',
    "ai": 'AI technology futuristic',
    "default": 'AI technology workspace',
}

def get_video_for_topic():
    """根据标题自动选择Pexels搜索关键词"""
    topic_lower = TOPIC.lower()
    for key, query in TOPIC_VIDEO_MAP.items():
        if key != "default" and key in topic_lower:
            return query
    return TOPIC_VIDEO_MAP["default"]

def search_pexels(query, per_page=5):
    r = requests.get(
        f'https://api.pexels.com/videos/search?query={requests.utils.quote(query)}'
        f'&per_page={per_page}&orientation=portrait&max_duration=20&min_duration=8',
        headers={'Authorization': PEXELS_KEY}, timeout=15
    )
    if r.status_code != 200:
        log(f"Pexels搜索失败: {r.status_code}")
        return None
    return r.json().get('videos', [])

def download_video(url, path):
    r = requests.get(url, stream=True, timeout=120)
    if r.status_code != 200:
        return False
    with open(path, 'wb') as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk)
    return os.path.getsize(path) > 10000

def get_best_hd_link(videos):
    """找最佳HD竖屏链接"""
    for v in videos:
        hd_files = [f for f in v.get('video_files', [])
                    if f.get('quality') == 'hd'
                    and f.get('width', 0) >= 720
                    and f.get('height', 0) >= 1280]
        if hd_files:
            best = max(hd_files, key=lambda x: x.get('width', 0))
            return v, best
    return None, None

def gen_video():
    """下载Pexels真实竖屏视频(Primary),下载多个并拼接"""
    log("获取真实视频素材 (Pexels)...")
    query = get_video_for_topic()
    videos = search_pexels(query) or []

    # 尝试多个关键词找足够素材
    if len(videos) < 2:
        alt_videos = search_pexels('technology AI robot', per_page=3)
        if alt_videos:
            videos = (videos or []) + alt_videos

    if not videos:
        log("  ❌ Pexels失败")
        return None

    # 获取多个视频,凑够时长
    clips = []
    seen_ids = set()
    for v in videos:
        if v['id'] in seen_ids:
            continue
        seen_ids.add(v['id'])
        _, best = get_best_hd_link([v])
        if not best:
            continue
        path = f'{OUT_DIR}/pexels_clip_{len(clips)}.mp4'
        log(f"  下载视频{v['duration']}s...")
        if download_video(best['link'], path):
            clips.append(path)
            if len(clips) >= 3:  # 最多3个,足够凑45秒
                break

    if not clips:
        log("  ❌ 无合适视频")
        return None

    # 合并多个视频
    if len(clips) == 1:
        return clips[0]

    # 拼接(统一格式后concat copy)
    log(f"  拼接{len(clips)}个视频片段...")
    normalized = []
    for i, c in enumerate(clips):
        out = f'{OUT_DIR}/pexels_norm_{i}.mp4'
        r = subprocess.run([
            'ffmpeg', '-y', '-i', c,
            '-vf', f'scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,format=yuv420p',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '25',
            '-c:a', 'aac', '-ar', '44100',
            out
        ], capture_output=True)
        if r.returncode == 0:
            normalized.append(out)

    if len(normalized) == 1:
        return normalized[0]

    # 去掉每个片段的音轨(防止拼接时混乱)
    silent_clips = []
    for i, n in enumerate(normalized):
        silent = f'{OUT_DIR}/pexels_silent_{i}.mp4'
        r = subprocess.run([
            'ffmpeg', '-y', '-i', n, '-c:v', 'copy', '-an', silent
        ], capture_output=True)
        if r.returncode == 0:
            silent_clips.append(silent)

    if len(silent_clips) < 2:
        return normalized[0] if normalized else None

    # Concat无声视频
    with open(OUT_DIR + '/concat_list.txt', 'w') as f:
        for s in silent_clips:
            f.write(f"file '{s}'\n")
    r = subprocess.run([
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', OUT_DIR + '/concat_list.txt',
        '-c', 'copy', OUT_DIR + '/short_video.mp4'
    ], capture_output=True)
    if r.returncode == 0:
        size = os.path.getsize(OUT_DIR + '/short_video.mp4') // 1024 // 1024
        log(f"  ✅ 拼接完成: {size:.1f}MB (无声)")
        return OUT_DIR + '/short_video.mp4'

    return normalized[0] if normalized else None

# ============ 配音(百炼TTS Primary)============
def gen_voice():
    log("生成配音 (百炼 qwen3-tts-flash Ethan)...")
    try:
        import json as json_lib
        token = _get_env('DASHSCOPE')

        # 根据标题生成配音文本
        voice_text = generate_voice_text()

        payload = {
            'model': 'qwen3-tts-flash',
            'input': {
                'text': voice_text,
                'voice': 'Ethan',
                'language_type': 'English'
            }
        }
        h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        r = requests.post(
            'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation',
            headers=h, json=payload, timeout=30
        )
        if r.status_code != 200:
            log(f"  ❌ 百炼TTS失败: {r.status_code}")
            return gen_voice_fallback()

        audio_url = r.json()['output']['audio']['url']
        audio_resp = requests.get(audio_url, timeout=30)
        if audio_resp.status_code != 200:
            log("  ❌ 音频下载失败")
            return False

        with open(OUT_DIR + '/short_voice.mp3', 'wb') as f:
            f.write(audio_resp.content)
        size = os.path.getsize(OUT_DIR + '/short_voice.mp3') // 1024
        log(f"  ✅ 配音: {size}KB (qwen3-tts-flash Ethan)")
        return True
    except Exception as e:
        log(f"  ⚠️ 异常: {e},使用备用")
        return gen_voice_fallback()

def generate_voice_text():
    topic_lower = TOPIC.lower()
    if 'email' in topic_lower:
        return "AI can save you hours every week. Here is how. Tip one: use AI to write your emails. Instead of spending thirty minutes on one message, let AI draft it in seconds. Just give it the key points and edit to match your style. Tip two: use AI to summarize long documents. Paste in any article or report and get a clear summary in seconds. Tip three: when learning something new, ask AI to explain it simply. Complex topics become easy. Three tips. Subscribe for more AI hacks!"
    elif 'chatgpt' in topic_lower or 'gpt' in topic_lower:
        return "ChatGPT can do so much more than you think. Tip one: use it as your personal editor. Paste anything you've written and ask for feedback. Tip two: turn it into a learning coach. Ask it to explain topics like you're five years old. Tip three: use it to brainstorm fast. Give it a problem, get dozens of ideas in seconds. Three ChatGPT tips that will change how you work. Subscribe for more!"
    elif '10x' in topic_lower or 'productivity' in topic_lower or 'productive' in topic_lower:
        # Hook: 立即给价值,subscribe CTA
        return "Stop wasting hours on busy work. Here is how to 10x your productivity using AI. Tip one: automate your emails. Give AI your bullet points, get a polished draft in seconds, edit your voice in minutes. Tip two: summarize anything instantly. Paste any document, get the key points in one paragraph. Tip three: learn anything faster. Ask AI to explain complex topics in simple terms. Three AI productivity tips that save me twenty hours every week. Subscribe now for more!"
    else:
        return "AI is changing how we work. Here are three tips that save me hours every week. Tip number one: use AI to draft your emails. Give it a few bullet points and let it write the full message. Edit for your voice, but the first draft is done in seconds. Tip number two: paste in any long document and ask for a one paragraph summary. It extracts the key points instantly. Tip number three: when you encounter something new, ask AI to explain it simply. Complex topics become clear in minutes. That's three tips that can save you hours every week. Subscribe for more AI productivity hacks!"

def gen_voice_fallback():
    log("生成配音 (edge-tts JennyNeural 备用)...")
    try:
        text_file = OUT_DIR + '/short_voice.txt'
        mp3_file = OUT_DIR + '/short_voice.mp3'
        with open(text_file, 'w') as f:
            f.write(generate_voice_text())
        r = os.system(
            f'/usr/local/bin/edge-tts '
            f'-f {text_file} --write-media {mp3_file} -v "en-US-JennyNeural" --rate +15% > /dev/null 2>&1'
        )
        if r == 0 and os.path.exists(mp3_file) and os.path.getsize(mp3_file) > 1000:
            size = os.path.getsize(mp3_file) // 1024
            log(f"  ✅ 备用配音: {size}KB (JennyNeural)")
            return True
    except: pass
    return False

# ============ 字幕烧录(ffmpeg drawtext方案) ============
import re

def _build_srt(text, wpm=140):
    """从配音文本生成SRT文件(供后续使用)"""
    import re
    text = re.sub(r'[\♪♫🎵🎶]', '', text)
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    sents = [s.strip() for s in sents if s.strip()]
    entries = []
    t = 1.0
    for s in sents:
        words = len(s.split())
        dur = max(words * 60.0 / wpm, 1.8)
        entries.append((t, t + dur - 0.1, s))
        t += dur + 0.15
    return entries

def _burn_subs_saf(audio_dur, text):
    """字幕方案:每句一张PNG叠加(homebrew FFmpeg无libass,只有此方案可用)

    改进v3: 字体28pt加粗(对比22pt)、描边增强、黑底透明、每字幕超时20s
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except:
        log("  PIL不可用,跳过字幕")
        return False

    entries = _build_srt(text)
    log(f"  生成{len(entries)}条字幕...")

    # 找可用字体
    font_path = None
    for fp in [
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Helvetica Bold.ttc',
        '/System/Library/Fonts/Helvetica.ttc',
    ]:
        if os.path.exists(fp):
            font_path = fp
            break

    sub_clips = []
    for i, (s, e, txt) in enumerate(entries):
        # 字幕底栏:640x80,半透明黑底白字
        fontsize = 28
        line_h = fontsize + 8
        w, h = 660, 90
        img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w-1, h-1], radius=10, fill=(0, 0, 0, 168))

        font = ImageFont.load_default()
        if font_path:
            try:
                font = ImageFont.truetype(font_path, fontsize)
            except:
                pass

        # 限制22字/行
        words = txt.split()
        if len(words) > 22:
            mid = len(words) // 2
            lines_txt = [' '.join(words[:mid]), ' '.join(words[mid:])]
        else:
            lines_txt = [txt]

        total_h = len(lines_txt) * line_h
        start_y = (h - total_h) // 2
        for j, line in enumerate(lines_txt):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            y = start_y + j * line_h
            # 黑描边 + 白字(户外可读)
            for dx, dy in [(1,1),(-1,-1),(1,-1),(-1,1),(0,0)]:
                draw.text((x+dx, y+dy), line, fill=(0, 0, 0, 255), font=font)
            draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)

        png = f'{OUT_DIR}/subv3_{i:04d}.png'
        img.save(png)
        dur = max(e - s, 1.0)
        out_mp4 = f'{OUT_DIR}/subv3c_{i:04d}.mp4'

        r = subprocess.run([
            'ffmpeg', '-y', '-loop', '1', '-i', png,
            '-t', str(dur),
            '-vf', f'scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,crop={SHORT_WIDTH}:{SHORT_HEIGHT},format=yuv420p',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
            '-pix_fmt', 'yuv420p', '-r', '24', '-threads', '1',
            out_mp4
        ], capture_output=True, timeout=20)

        os.remove(png)
        if r.returncode == 0:
            sub_clips.append(out_mp4)

    if not sub_clips:
        log("  字幕全部失败")
        return False

    # 拼接
    concat_file = OUT_DIR + '/subv3_concat.txt'
    with open(concat_file, 'w') as f:
        for c in sub_clips:
            f.write("file '" + c + "'\n")

    sub_video = OUT_DIR + '/subv3_video.mp4'
    r = subprocess.run([
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
        '-c', 'copy', sub_video
    ], capture_output=True, timeout=30)

    if r.returncode != 0:
        for c in sub_clips:
            os.remove(c)
        return False

    # overlay
    out = OUT_DIR + '/output_short_subtitled.mp4'
    r = subprocess.run([
        'ffmpeg', '-y',
        '-i', OUT_DIR + '/output_short.mp4',
        '-i', sub_video,
        '-filter_complex', '[0:v][1:v]overlay=0:0[out]',
        '-map', '[out]', '-map', '0:a',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
        '-threads', '2',
        '-t', str(min(audio_dur, 60)),
        out
    ], capture_output=True, timeout=120)

    for c in sub_clips:
        os.remove(c)

    if r.returncode == 0 and os.path.exists(out):
        os.replace(out, OUT_DIR + '/output_short.mp4')
        return True
    log("  字幕overlay失败")
    return False


# ============ 字幕预渲染(单Pass用)============
# Hook生成:从通用Hook库中选(根据topic)
_HOOK_POOL = [
    "STOP DOING THIS!",
    "YOU'RE DOING IT WRONG!",
    "THIS CHANGES EVERYTHING",
    "99% MISS THIS!",
    "SAVE HOURS DAILY",
]

def _gen_hook_image(text, duration=2.5, font_size=64):
    """生成首2.5秒Pattern Interrupt大文字全屏叠加"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except:
        return None

    w, h = SHORT_WIDTH, SHORT_HEIGHT
    img = Image.new('RGBA', (w, h), (0, 0, 0, 200))  # 半透明黑底
    draw = ImageDraw.Draw(img)

    # 找粗体字体
    font = None
    for fp in [
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Helvetica Bold.ttc',
    ]:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except: pass
    if not font:
        font = ImageFont.load_default()

    # 拆行（最多2行）
    words = text.split()
    if len(words) > 4:
        mid = len(words)//2
        lines_txt = [' '.join(words[:mid]), ' '.join(words[mid:])]
    else:
        lines_txt = [text]
    
    lh = font_size + 15
    total = len(lines_txt) * lh
    start_y = h//2 - total//2
    for line in lines_txt:
        bbox = draw.textbbox((0,0), line, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        tx = (w - tw)//2
        ty = start_y
        # 黑描边 + 白字
        for dx,dy in [(3,3),(-3,-3),(3,-3),(-3,3),(2,0),(-2,0),(0,2),(0,-2)]:
            draw.text((tx+dx,ty+dy), line, fill=(0,0,0,255), font=font)
        draw.text((tx,ty), line, fill=(255,255,255,255), font=font)
        start_y += lh

    png = OUT_DIR + '/hook_img.png'
    img.save(png)
    out = OUT_DIR + '/hook_clip.mp4'
    r = subprocess.run([
        'ffmpeg','-y','-loop','1','-i',png,
        '-t', str(duration),
        '-vf',f'scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,crop={SHORT_WIDTH}:{SHORT_HEIGHT},format=yuv420p',
        '-c:v','libx264','-preset','ultrafast','-crf','20',
        '-pix_fmt','yuv420p','-r','24','-threads','2',out
    ], capture_output=True, timeout=30)
    os.remove(png)
    return out if r.returncode==0 else None

def _gen_cta_image(text, duration=2.0, font_size=48):
    """生成CTA尾板文字叠加(最后2秒)"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except:
        return None

    w, h = SHORT_WIDTH, SHORT_HEIGHT
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    # 底部半透明黑色条
    draw.rectangle([0, h*2//3, w-1, h-1], fill=(0,0,0,190))

    font = None
    for fp in ['/System/Library/Fonts/Supplemental/Arial Bold.ttf','/System/Library/Fonts/Helvetica Bold.ttc']:
        if os.path.exists(fp):
            try: font = ImageFont.truetype(fp, font_size); break
            except: pass
    if not font: font = ImageFont.load_default()

    bbox = draw.textbbox((0,0), text, font=font)
    tw = bbox[2]-bbox[0]
    tx = (w-tw)//2
    ty = h*2//3 + 20
    for dx,dy in [(2,2),(-2,-2),(2,-2),(-2,2)]:
        draw.text((tx+dx,ty+dy), text, fill=(0,0,0,255), font=font)
    draw.text((tx,ty), text, fill=(255,255,255,255), font=font)

    png = OUT_DIR + '/cta_img.png'
    img.save(png)
    out = OUT_DIR + '/cta_clip.mp4'
    r = subprocess.run([
        'ffmpeg','-y','-loop','1','-i',png,
        '-t', str(duration),
        '-vf',f'scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,crop={SHORT_WIDTH}:{SHORT_HEIGHT},format=yuv420p',
        '-c:v','libx264','-preset','ultrafast','-crf','20',
        '-pix_fmt','yuv420p','-r','24','-threads','2',out
    ], capture_output=True, timeout=20)
    os.remove(png)
    return out if r.returncode==0 else None

def _prepare_subs_video(text, audio_dur, topic=''):
    """字幕预渲染单Pass: Hook(0-2.5s) + 字幕(2.5s~CTA前) + CTA(末2s)

    逻辑:
    1. Hook: 固定2.5s,Pattern Interrupt
    2. 字幕: 按SRT时间偏移(+2.5s),时长不变
    3. CTA: 填满剩余时间(audio_dur - hook_dur - sum(字幕时长))
    4. Concat: hook + 字幕 + CTA
    5. Trim final: 截到audio_dur
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except:
        log("PIL不可用,跳过字幕")
        return False

    entries = _build_srt(text)
    HOOK_DUR = 2.5
    CTA_DUR = 2.0

    # 选hook文字(根据topic关键词)
    topic_l = topic.lower()
    hook_txt = "STOP DOING THIS!"
    if 'email' in topic_l: hook_txt = "STOP TYPING SO MUCH!"
    elif 'chatgpt' in topic_l or 'gpt' in topic_l: hook_txt = "YOU'RE USING CHATGPT WRONG!"
    elif '10x' in topic_l or 'productiv' in topic_l: hook_txt = "STOP WASTING HOURS!"
    elif 'hack' in topic_l: hook_txt = "3 HACKS THAT WORK!"

    hook_clip = _gen_hook_image(hook_txt, HOOK_DUR)
    if not hook_clip:
        log("Hook生成失败,跳过字幕")
        return False
    log(f"Hook: '{hook_txt}' ({HOOK_DUR}s)")

    # 字幕片段时长:总时长 - hook - CTA
    total_sub_time = audio_dur - HOOK_DUR - CTA_DUR
    if total_sub_time < 5:
        total_sub_time = audio_dur - HOOK_DUR
        CTA_DUR = 0

    # 按entries分配时间
    sub_clips = []
    t = HOOK_DUR  # 字幕从hook之后开始
    for i, (s, e, txt) in enumerate(entries):
        word_count = len(txt.split())
        sub_dur = max(word_count * 60.0 / 140, 1.5)
        if t + sub_dur > audio_dur - CTA_DUR:
            sub_dur = max(audio_dur - CTA_DUR - t, 0.5)
        if sub_dur < 0.5:
            break

        fontsize = 28
        lh = fontsize + 8
        iw, ih = 660, 90
        img = Image.new('RGBA', (iw, ih), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0,0,iw-1,ih-1], radius=10, fill=(0,0,0,168))

        font = None
        for fp in ['/System/Library/Fonts/Supplemental/Arial Bold.ttf','/System/Library/Fonts/Helvetica Bold.ttc']:
            if os.path.exists(fp):
                try: font = ImageFont.truetype(fp, fontsize); break
                except: pass
        if not font: font = ImageFont.load_default()

        words = txt.split()
        if len(words) > 22:
            mid = len(words)//2
            lines_txt = [' '.join(words[:mid]), ' '.join(words[mid:])]
        else:
            lines_txt = [txt]

        th2 = len(lines_txt)*lh
        sy = (ih-th2)//2
        for j, line in enumerate(lines_txt):
            bbox = draw.textbbox((0,0), line, font=font)
            tw = bbox[2]-bbox[0]
            tx = (iw-tw)//2
            ty2 = sy + j*lh
            for dx,dy in [(1,1),(-1,-1),(1,-1),(-1,1),(0,0)]:
                draw.text((tx+dx,ty2+dy), line, fill=(0,0,0,255), font=font)
            draw.text((tx,ty2), line, fill=(255,255,255,255), font=font)

        png = f'{OUT_DIR}/subr6_{i:04d}.png'
        img.save(png)
        mp4 = f'{OUT_DIR}/subr6c_{i:04d}.mp4'
        r = subprocess.run([
            'ffmpeg','-y','-loop','1','-i',png,
            '-t', str(sub_dur),
            '-vf',f'scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,crop={SHORT_WIDTH}:{SHORT_HEIGHT},format=yuv420p',
            '-c:v','libx264','-preset','ultrafast','-crf','28',
            '-pix_fmt','yuv420p','-r','24','-threads','1',mp4
        ], capture_output=True, timeout=20)
        os.remove(png)
        if r.returncode == 0:
            sub_clips.append(mp4)
        t += sub_dur + 0.1

    log(f"字幕{len(sub_clips)}条,CTA {CTA_DUR}s")

    # CTA片段: 用hook文字呼头(loop效果)+ subscribe
    cta_clip = None
    if CTA_DUR > 0:
        # 尝试用hook文字作CTA(loop效果)
        cta_clip = _gen_cta_image(hook_txt + " #AI", CTA_DUR)
        if not cta_clip:
            cta_clip = _gen_cta_image("SUBSCRIBE FOR MORE!", CTA_DUR)

    # 拼接:hook + subs + cta
    concat_list = OUT_DIR + '/subs_r6_concat.txt'
    with open(concat_list, 'w') as f:
        f.write("file '" + hook_clip + "'\n")
        for c in sub_clips:
            f.write("file '" + c + "'\n")
        if cta_clip:
            f.write("file '" + cta_clip + "'\n")

    tmp1 = OUT_DIR + '/subs_r6_raw.mp4'
    r = subprocess.run([
        'ffmpeg','-y','-f','concat','-safe','0','-i',concat_list,
        '-c','copy',tmp1
    ], capture_output=True, timeout=30)

    # 清理
    for c in sub_clips: os.remove(c)
    if cta_clip: os.remove(cta_clip)

    if r.returncode != 0:
        os.remove(hook_clip)
        return False

    # 截取到audio_dur
    out = OUT_DIR + '/sub_single_pass.mp4'
    r2 = subprocess.run([
        'ffmpeg','-y','-i',tmp1,
        '-t', str(audio_dur),
        '-c','copy',out
    ], capture_output=True, timeout=20)
    os.remove(tmp1); os.remove(hook_clip)
    return r2.returncode==0 and os.path.exists(out)

# ============ 水印叠加 ============
def _add_watermark(video_path, wm_path=None, margin=12):
    """给视频右下角叠加半透明"AI ToolBox"水印

    水印位置: 右下角, margin像素边距
    """
    if wm_path is None:
        wm_path = OUT_DIR + '/watermark.png'

    if not os.path.exists(wm_path):
        # 动态生成水印
        try:
            from PIL import Image, ImageDraw, ImageFont
            wm_w, wm_h = 130, 42
            img = Image.new('RGBA', (wm_w, wm_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            font = None
            for fp in ['/System/Library/Fonts/Supplemental/Arial Bold.ttf',
                       '/System/Library/Fonts/Helvetica Bold.ttc']:
                if os.path.exists(fp):
                    try: font = ImageFont.truetype(fp, 18); break
                    except: pass
            if not font: font = ImageFont.load_default()
            text = "AI ToolBox"
            bbox = draw.textbbox((0,0), text, font=font)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            tx, ty = (wm_w-tw)//2, (wm_h-th)//2
            for dx,dy in [(1,1),(-1,-1),(1,-1),(-1,1)]:
                draw.text((tx+dx,ty+dy), text, fill=(0,0,0,180), font=font)
            draw.text((tx,ty), text, fill=(255,255,255,200), font=font)
            img.save(wm_path)
            log(f"  水印动态生成: {wm_w}x{wm_h}")
        except:
            log("  ⚠️ 无法生成水印,跳过")
            return False

    # 叠加水印 (右下角)
    pos_x = SHORT_WIDTH - 130 - margin
    pos_y = SHORT_HEIGHT - 42 - margin

    tmp = OUT_DIR + '/output_short_wm_tmp.mp4'
    r = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-i', wm_path,
        '-filter_complex',
        f'[0:v][1:v]overlay={pos_x}:{pos_y}[out]',
        '-map', '[out]', '-map', '0:a',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
        '-threads', '2',
        tmp
    ], capture_output=True, timeout=60)

    if r.returncode == 0:
        os.replace(tmp, video_path)
        return True
    log(f"  ⚠️ 水印失败({r.returncode})")
    if os.path.exists(tmp): os.remove(tmp)
    return False

# ============ 视频合成 ============
def make_video(video_path):
    log("合成视频...")
    import json as json_lib

    result = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', OUT_DIR + '/short_voice.mp3'],
        capture_output=True, text=True)
    try:
        audio_dur = float(json_lib.loads(result.stdout)['format']['duration'])
    except:
        audio_dur = 30.0
    audio_dur = min(audio_dur, MAX_DURATION)
    log(f"  目标时长: {audio_dur:.1f}秒")

    if video_path and os.path.exists(video_path):
        # 先生成字幕视频(pre-render)
        voice_text = generate_voice_text()
        sub_ok = _prepare_subs_video(voice_text, audio_dur, topic=TOPIC)

        # 生成背景音乐(粉噪音+低通=柔和ambient bed)
        log("  生成背景音乐...")
        bgm_ok = False
        try:
            fade_out_start = max(audio_dur - 1.5, 0.5)
            # 先生成纯bgm(无滤镜,后处理时再加)
            r_bgm = subprocess.run([
                'ffmpeg', '-y',
                '-f', 'lavfi',
                '-i', f'anoisesrc=color=pink:sample_rate=44100:duration={int(audio_dur)+1}',
                '-af', f'lowpass=f=300,volume=0.18,afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start}:d=1.5',
                '-t', str(audio_dur),
                '-q:a', '2',
                OUT_DIR + '/short_bgm_raw.mp3'
            ], capture_output=True, timeout=20)
            if r_bgm.returncode == 0 and os.path.exists(OUT_DIR + '/short_bgm_raw.mp3'):
                # 混合配音(100%)+ 背景音乐(~18%)
                r_mix = subprocess.run([
                    'ffmpeg', '-y',
                    '-i', OUT_DIR + '/short_voice.mp3',
                    '-i', OUT_DIR + '/short_bgm_raw.mp3',
                    '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=shortest:dropout_transition=0:weights=1.0 0.15[aout]',
                    '-map', '[aout]', '-ar', '44100', OUT_DIR + '/short_mixed.mp3'
                ], capture_output=True, timeout=20)
                os.remove(OUT_DIR + '/short_bgm_raw.mp3')
                if r_mix.returncode == 0 and os.path.exists(OUT_DIR + '/short_mixed.mp3'):
                    bgm_ok = True
                    log("  ✅ 背景音乐已混合")
                else:
                    log(f"  ⚠️ 混合失败({r_mix.returncode})")
        except Exception as e:
            log(f"  ⚠️ 背景音乐失败: {e}")

        mixed_mp3 = OUT_DIR + '/short_mixed.mp3' if bgm_ok else OUT_DIR + '/short_voice.mp3'
        if sub_ok:
            # 单Pass: Ken Burns + 字幕overlay + 配音 一次完成(防质量损失)
            log("  单Pass合成(Ken Burns + 字幕)...")
            kb_w = int(SHORT_WIDTH * 1.12)
            kb_h = int(SHORT_HEIGHT * 1.12)
            r = subprocess.run([
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', mixed_mp3,
                '-i', OUT_DIR + '/sub_single_pass.mp4',
                '-filter_complex',
                # 关键修复: sub_single_pass.mp4 是 yuv420p(无alpha)，用 extractplanes=y + alphamerge
                # 将字幕视频的白字变透明，黑底保留，仅文字区域遮挡 Ken Burns 背景
                f'[0:v]scale={kb_w}:{kb_h}:force_original_aspect_ratio=increase,crop={SHORT_WIDTH}:{SHORT_HEIGHT},format=yuva420p[kb];'
                f'[2:v]extractplanes=y[ymask];[kb][ymask]alphamerge[out]',
                '-map', '[out]', '-map', '1:a',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
                '-c:a', 'aac', '-b:a', '128k',
                '-threads', '2',
                '-t', str(audio_dur),
                OUT_DIR + '/output_short.mp4'
            ], capture_output=True, timeout=180)
            if r.returncode == 0:
                size = os.path.getsize(OUT_DIR + '/output_short.mp4') // 1024
                log(f"  ✅ 单Pass完成: {size}KB")
                # ===== 水印叠加(第3步)=====
                wm_ok = _add_watermark(OUT_DIR + '/output_short.mp4')
                if wm_ok:
                    sz2 = os.path.getsize(OUT_DIR + '/output_short.mp4') // 1024
                    log(f"  ✅ 水印已添加 ({sz2}KB)")
                return True
            else:
                log(f"  单Pass失败,fallback两Pass: {r.stderr.decode()[-150:]}")

        # Fallback: 两Pass(Ken Burns + 字幕overlay分开)
        r = subprocess.run([
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', mixed_mp3,
            '-vf', f'scale={int(SHORT_WIDTH*1.12)}:{int(SHORT_HEIGHT*1.12)}:force_original_aspect_ratio=increase,crop={SHORT_WIDTH}:{SHORT_HEIGHT},format=yuv420p',
            '-map', '0:v:0', '-map', '1:a:0',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '25',
            '-c:a', 'aac', '-b:a', '128k',
            '-t', str(audio_dur),
            OUT_DIR + '/output_short.mp4'
        ], capture_output=True)

        if r.returncode == 0:
            size = os.path.getsize(OUT_DIR + '/output_short.mp4') // 1024
            log(f"  ✅ 视频合成: {size}KB")
            srt_ok = _burn_subs_saf(audio_dur, voice_text if 'voice_text' in dir() else generate_voice_text())
            if srt_ok:
                sz2 = os.path.getsize(OUT_DIR + '/output_short.mp4') // 1024
                log(f"  ✅ 字幕已烧录 ({sz2}KB)")
            wm_ok = _add_watermark(OUT_DIR + '/output_short.mp4')
            if wm_ok:
                log(f"  ✅ 水印已添加")
            return True
        else:
            log(f"  合成失败: {r.stderr.decode()[-200:]}")

    log("  ❌ 视频合成失败")
    return False

# ============ 上传（带自动重试）============
def upload():
    """上传Shorts，配额/Token过期自动重试（最多3次）"""
    for attempt in range(1, 4):
        log(f"上传Shorts... (第{attempt}次)")
        token = get_token()
        with open(OUT_DIR + '/output_short.mp4', 'rb') as f:
            video_content = f.read()
        metadata = {
            'snippet': {'title': TOPIC[:100], 'description': DESC, 'tags': TAGS[:15], 'categoryId': '22'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
        }
        init = requests.post(
            'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                     'X-Upload-Content-Length': str(len(video_content))},
            json=metadata, timeout=30
        )
        if init.status_code not in [200, 201]:
            log(f"  ❌ 初始化失败: {init.status_code} {init.text[:100]}")
            # 401=Token失效，不重试
            if init.status_code == 401:
                return None
            continue
        uri = init.headers['Location']
        up = requests.put(uri, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'video/mp4'},
                         data=video_content, timeout=120)
        if up.status_code == 200:
            vid = up.json().get('id')
            log("  ✅ 上传成功!")
            return vid
        log(f"  ❌ 上传失败: {up.status_code} {up.text[:100]}")
        # 403=配额超限，等30秒后重试
        if up.status_code == 403:
            log("  ⏳ 配额超限，30秒后重试...")
            time.sleep(30)
            continue
        # 其他错误（400/500等），不等直接重试
        if attempt < 3:
            log(f"  ⏳ 10秒后重试...")
            time.sleep(10)
            continue
    log("  ❌ 上传失败，已用尽重试次数")
    return None

# ============ PRE-FLIGHT CHECK (Task 1) ============
def preflight_check():
    """
    启动前自检，返回 issues 列表（空=全部正常）。
    会自动修复可修复的问题。
    关键问题（无PEXELS且无网络）会阻塞执行。
    """
    global CONFIG_ENV_PATH, PEXELS_KEY, HYPERBOLIC_KEY
    issues = []
    log("🚀 启动前自检...")

    # 1. Fix .env path
    env_paths_to_try = [
        os.path.expanduser('~/.openclaw/.env'),
        os.path.expanduser('~/.openclaw_.env'),
    ]
    found_env = None
    for p in env_paths_to_try:
        if os.path.exists(p):
            found_env = p
            break

    if found_env:
        CONFIG_ENV_PATH = found_env
        log(f"  📄 .env 已定位: {found_env}")
    else:
        issues.append(f"⚠️ .env 未找到（尝试了 {env_paths_to_try}）")
        # 尝试在系统中搜索任何 .env 文件
        try:
            result = os.popen('find ~ -maxdepth 3 -name ".env" -o -name ".openclaw.env" 2>/dev/null | head -5').read().strip()
            if result:
                log(f"  发现可能相关: {result}")
                issues.append(f"  候选: {result}")
        except:
            pass

    # 2. Fix missing refresh_token in pickle
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
            rt = creds.get('refresh_token')
            if not rt or rt is None or rt == '':
                log("  🔧 pickle 中缺 refresh_token，尝试从 Keychain 补全...")
                result = subprocess.run(
                    ['security', 'find-generic-password', '-s', 'youtube-token-openclaw', '-a', 'bot-refresh-token', '-w'],
                    capture_output=True, text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    refresh_from_kc = result.stdout.strip()
                    # Patch pickle
                    try:
                        # 需要重新加载并保存（pickle可能不可写）
                        with open(TOKEN_FILE, 'rb') as f:
                            creds = pickle.load(f)
                        creds['refresh_token'] = refresh_from_kc
                        with open(TOKEN_FILE, 'wb') as f:
                            pickle.dump(creds, f)
                        log("  🔧 已补全缺失的 refresh_token")
                    except Exception as e:
                        log(f"  ⚠️ 补全 refresh_token 失败: {e}")
                        issues.append(f"⚠️ refresh_token 缺失且无法补全")
                else:
                    issues.append("⚠️ refresh_token 缺失且 Keychain 为空")
        except Exception as e:
            issues.append(f"⚠️ Token文件读取失败: {e}")

    # 3. Validate API keys (lightweight)
    PEXELS_KEY = _get_env('PEXELS')
    DASHSCOPE_KEY = _get_env('DASHSCOPE')
    HYPERBOLIC_KEY = _get_env('HYPERBOLIC')

    # PEXELS: lightweight API check
    if PEXELS_KEY:
        try:
            r = requests.get(
                'https://api.pexels.com/videos/search?query=test',
                headers={'Authorization': PEXELS_KEY},
                timeout=10
            )
            if r.status_code == 200:
                log("  ✅ PEXELS_KEY 有效")
            elif r.status_code in [401, 403]:
                issues.append(f"⚠️ PEXELS_KEY 无效 ({r.status_code})，将使用 fallback 模式")
                log(f"  ⚠️ PEXELS_KEY 无效 ({r.status_code})，fallback 模式")
            else:
                issues.append(f"⚠️ PEXELS_KEY 异常 ({r.status_code})")
        except Exception as e:
            issues.append(f"⚠️ PEXELS 网络检测失败: {e}，fallback 模式")
            log(f"  ⚠️ PEXELS 网络检测失败: {e}")
    else:
        issues.append("⚠️ PEXELS_KEY 缺失，将使用 fallback 模式")
        log("  ⚠️ PEXELS_KEY 缺失，fallback 模式")

    # DASHSCOPE: just check exists
    if DASHSCOPE_KEY:
        log("  ✅ DASHSCOPE_KEY 有值")
    else:
        issues.append("⚠️ DASHSCOPE_KEY 缺失，TTS 将回退到 edge-tts")
        log("  ⚠️ DASHSCOPE_KEY 缺失")

    # HYPERBOLIC: just check exists
    if HYPERBOLIC_KEY:
        log("  ✅ HYPERBOLIC_KEY 有值")
    else:
        issues.append("⚠️ HYPERBOLIC_KEY 缺失，图片生成将使用备选方案")
        log("  ⚠️ HYPERBOLIC_KEY 缺失")

    # Critical: no PEXELS AND no internet
    internet_ok = True
    try:
        requests.get('https://www.google.com', timeout=3)
    except:
        internet_ok = False

    if not PEXELS_KEY and not internet_ok:
        critical_issue = "🚨 关键问题：无 PEXELS_KEY 且无网络连接，无法继续"
        issues.append(critical_issue)
        log(f"  {critical_issue}")
        return issues  # 阻塞执行

    if issues:
        log(f"  📋 自检发现问题 {len(issues)} 项（可继续，非阻塞）")
    else:
        log("  ✅ 自检通过")

    return issues

# ============ AUTO-FIX (Task 3 helper) ============
def _auto_fix():
    """
    静默尝试自动修复所有已知问题。
    返回 True = 至少修复了一个问题并成功
    返回 False = 无法自动修复
    """
    fixed_something = False
    fixes = []

    # Fix 1: Token 过期 → 刷新
    try:
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
        from datetime import datetime, timezone
        expiry_str = creds.get('expiry')
        if expiry_str:
            expiry = datetime.fromisoformat(expiry_str)
            if expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= expiry:
                log("  🔧 [AutoFix] Token 过期，尝试刷新...")
                new_token = get_token()
                if new_token:
                    fixes.append("Token 已刷新")
                    fixed_something = True
                    log("  ✅ [AutoFix] Token 刷新成功")
    except Exception as e:
        log(f"  ⚠️ [AutoFix] Token 修复跳过: {e}")

    # Fix 2: Missing refresh_token in pickle → 从 Keychain 补全
    try:
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
        rt = creds.get('refresh_token')
        if not rt or rt is None or rt == '':
            log("  🔧 [AutoFix] refresh_token 缺失，从 Keychain 补全...")
            result = subprocess.run(
                ['security', 'find-generic-password', '-s', 'youtube-token-openclaw', '-a', 'bot-refresh-token', '-w'],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                refresh_from_kc = result.stdout.strip()
                with open(TOKEN_FILE, 'rb') as f:
                    creds = pickle.load(f)
                creds['refresh_token'] = refresh_from_kc
                with open(TOKEN_FILE, 'wb') as f:
                    pickle.dump(creds, f)
                fixes.append("refresh_token 已从 Keychain 补全")
                fixed_something = True
                log("  ✅ [AutoFix] refresh_token 已补全")
    except Exception as e:
        log(f"  ⚠️ [AutoFix] refresh_token 修复失败: {e}")

    # Fix 3: Keychain 为空 → 生成 OAuth URL
    try:
        result = subprocess.run(
            ['security', 'find-generic-password', '-s', 'youtube-token-openclaw', '-a', 'bot-refresh-token', '-w'],
            capture_output=True, text=True
        )
        if result.returncode != 0 or not result.stdout.strip():
            log("  ⚠️ [AutoFix] Keychain 无 refresh_token，需要人工授权")
            # 生成 OAuth URL
            from urllib.parse import urlencode
            CLIENT_ID = '${YOUTUBE_CLIENT_ID}'
            scopes = [
                'https://www.googleapis.com/auth/youtube',
                'https://www.googleapis.com/auth/youtube.readonly',
                'https://www.googleapis.com/auth/yt-analytics.readonly',
            ]
            params = {
                'client_id': CLIENT_ID,
                'redirect_uri': 'http://localhost:8080',
                'response_type': 'code',
                'scope': ' '.join(scopes),
                'access_type': 'offline',
                'prompt': 'consent'
            }
            oauth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)
            log(f"  🔗 OAuth URL: {oauth_url}")
            # 通知 Telegram
            _notify_blocker([
                "⚠️ Keychain 无 refresh_token，需要人工授权",
                f"请访问: {oauth_url}",
                "授权后将 token 存入 Keychain: python3 keychain_token.py save"
            ])
    except Exception as e:
        log(f"  ⚠️ [AutoFix] Keychain 检查失败: {e}")

    # Fix 4: .env missing → 尝试找系统中的 .env
    if CONFIG_ENV_PATH is None:
        try:
            result = os.popen('find ~ -maxdepth 4 -name ".env" 2>/dev/null | head -5').read().strip()
            if result:
                log(f"  🔧 [AutoFix] 发现 .env 候选: {result}")
                # 第一个有效路径
                for line in result.split('\n'):
                    p = line.strip()
                    if os.path.exists(p):
                        CONFIG_ENV_PATH = p
                        fixes.append(f".env 已定位: {p}")
                        fixed_something = True
                        log(f"  ✅ [AutoFix] .env 已使用: {p}")
                        break
        except Exception as e:
            log(f"  ⚠️ [AutoFix] .env 查找失败: {e}")

    # Fix 5: PEXELS key bad → 切换 fallback 模式（已有 fallback 逻辑，这里只记录）
    if not PEXELS_KEY:
        log("  🔧 [AutoFix] PEXELS_KEY 缺失，fallback 模式已准备就绪")

    if fixed_something:
        log(f"  ✅ AutoFix 完成: {', '.join(fixes)}")
    else:
        log("  ℹ️ AutoFix 无可自动修复的问题")

    return fixed_something

# ============ UPGRADED DIAGNOSTICS (Task 2) ============
def _run_diagnostics():
    """3次失败后运行系统诊断，尝试自动修复问题，返回 (error_type, detail, can_retry)"""
    import json, pickle
    log("  🔍 运行系统诊断...")
    issues = []
    can_retry = True

    # 1. 检查Token
    try:
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
        access_token = creds.get('access_token')
        refresh_token = creds.get('refresh_token')
        expiry_str = creds.get('expiry')
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if expiry_str:
            expiry = datetime.fromisoformat(expiry_str)
            if expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
            token_ok = now < expiry
        else:
            token_ok = False
        issues.append(f"  • Token: {'✅ 有效' if token_ok else '❌ 过期/无效'}")
        issues.append(f"  • RefreshToken: {'✅ 有' if refresh_token else '❌ 缺失'}")

        if not token_ok:
            can_retry = False
            # ---- Auto-fix: 尝试刷新 token ----
            log("  🔧 [诊断] Token 过期，尝试刷新...")
            new_token = get_token()
            if new_token:
                issues.append("  • → Token 刷新成功！")
                can_retry = True  # 刷新成功后可以重试
                log("  ✅ Token 刷新成功")
            else:
                issues.append("  • → Token 刷新失败，需要人工介入")
                log("  ❌ Token 刷新失败")
    except Exception as e:
        issues.append(f"  • Token文件: ❌ {e}")
        can_retry = False

    # 2. 检查 Keychain
    try:
        result = subprocess.run(
            ['security', 'find-generic-password', '-s', 'youtube-token-openclaw', '-a', 'bot-refresh-token', '-w'],
            capture_output=True, text=True
        )
        kc_ok = result.returncode == 0 and result.stdout.strip()
        issues.append(f"  • Keychain: {'✅ 有refresh_token' if kc_ok else '❌ 无'}")
        if not kc_ok:
            # ---- Auto-fix: 缺少 Keychain → 生成 OAuth URL 并通知 ----
            log("  ⚠️ [诊断] Keychain 空，需要人工授权...")
            from urllib.parse import urlencode
            CLIENT_ID = '${YOUTUBE_CLIENT_ID}'
            scopes = [
                'https://www.googleapis.com/auth/youtube',
                'https://www.googleapis.com/auth/youtube.readonly',
                'https://www.googleapis.com/auth/yt-analytics.readonly',
            ]
            params = {
                'client_id': CLIENT_ID,
                'redirect_uri': 'http://localhost:8080',
                'response_type': 'code',
                'scope': ' '.join(scopes),
                'access_type': 'offline',
                'prompt': 'consent'
            }
            oauth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)
            issues.append(f"  • ⚠️ 需要人工授权: {oauth_url}")
            _notify_blocker([
                "⚠️ Keychain 无 refresh_token，需要人工授权",
                f"🔗 {oauth_url}",
                "授权后运行: python3 keychain_token.py save"
            ])
            can_retry = False
    except Exception as e:
        issues.append(f"  • Keychain: ⚠️ {e}")

    # 3. 检查 API 配额 / Token 401
    try:
        if access_token:
            headers = {'Authorization': f'Bearer {access_token}'}
            test = requests.get(
                'https://youtube.googleapis.com/youtube/v3/channels',
                headers=headers, params={'part': 'snippet', 'mine': 'true'}, timeout=10
            )
            issues.append(f"  • Data API: {test.status_code}")
            if test.status_code == 403:
                issues.append(f"    → 配额超限，30分钟后自动重试")
                can_retry = True  # 配额问题是时间问题，可以等
            elif test.status_code == 401:
                # ---- Auto-fix: 401 → 刷新 Keychain token 再试一次 ----
                log("  🔧 [诊断] 401 Token 失效，尝试刷新...")
                result = subprocess.run(
                    ['security', 'find-generic-password', '-s', 'youtube-token-openclaw', '-a', 'bot-refresh-token', '-w'],
                    capture_output=True, text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    from datetime import timedelta
                    resp = requests.post('https://oauth2.googleapis.com/token', data={
                        'client_id': '${YOUTUBE_CLIENT_ID}',
                        'client_secret': '${YOUTUBE_CLIENT_SECRET}',
                        'refresh_token': result.stdout.strip(),
                        'grant_type': 'refresh_token'
                    })
                    if resp.status_code == 200:
                        d = resp.json()
                        with open(TOKEN_FILE, 'rb') as f:
                            creds = pickle.load(f)
                        creds['access_token'] = d.get('access_token')
                        creds['expiry'] = (datetime.now(timezone.utc) + timedelta(seconds=d['expires_in'])).isoformat()
                        with open(TOKEN_FILE, 'wb') as f:
                            pickle.dump(creds, f)
                        issues.append("  • → Token 刷新成功！")
                        log("  ✅ 401 修复成功")
                        can_retry = True
                    else:
                        issues.append("  • → Token 刷新仍失败，需要人工介入")
                        log("  ❌ 401 Token 刷新仍失败")
                        can_retry = False
                        _notify_blocker(["401 Token 刷新失败，请重新授权", oauth_url if 'oauth_url' in dir() else "请运行 oauth_diagnose.py"])
                else:
                    can_retry = False
    except Exception as e:
        issues.append(f"  • API测试: ⚠️ {e}")

    # 4. 检查 .env 配置
    env_found = []
    for path in ['~/.openclaw/.env', '~/.openclaw_.env']:
        p = os.path.expanduser(path)
        if os.path.exists(p):
            env_found.append(p)
    if env_found:
        issues.append(f"  • .env: ✅ 找到 {env_found[0]}")
        global CONFIG_ENV_PATH
        if CONFIG_ENV_PATH is None:
            CONFIG_ENV_PATH = env_found[0]
    else:
        # ---- Auto-fix: 尝试找系统中的 .env ----
        issues.append("  • .env: ❌ 未找到")
        try:
            result = os.popen('find ~ -maxdepth 4 -name ".env" 2>/dev/null | head -5').read().strip()
            if result:
                found = result.split('\n')[0].strip()
                issues.append(f"    → 发现候选: {found}")
                log(f"  🔧 .env 候选: {found}")
                CONFIG_ENV_PATH = found
                fixed_something = True
        except:
            pass

    # 5. 检查 API keys
    for key_name, key_val in [('PEXELS', PEXELS_KEY), ('DASHSCOPE', _get_env('DASHSCOPE')), ('HYPERBOLIC', _get_env('HYPERBOLIC'))]:
        issues.append(f"  • {key_name}: {'✅ 有' if key_val else '❌ 缺失'}")

    for line in issues:
        log(line)

    if can_retry:
        log("  → 结论: 问题可自动修复，可以重试")
    else:
        log("  → 结论: 需要人工介入，无法自动修复")
        _notify_blocker(issues)

    return can_retry

def _notify_blocker(issues):
    """通知用户有阻塞性问题"""
    try:
        import urllib.request, urllib.parse
        bot_token = '8653763166:AAGm_dzI1nWBvxOISbjJfaes3TB7x6Ohrpc'
        chat_id = '299246410'
        msg = f"🚨 AI ToolBox Shorts 上传阻塞，需要人工介入\n\n" + "\n".join(issues) + f"\n\n请检查以上问题。"
        data = urllib.parse.urlencode({'text': msg, 'chat_id': chat_id}).encode()
        req = urllib.request.Request(f'https://api.telegram.org/bot{bot_token}/sendMessage', data=data)
        urllib.request.urlopen(req, timeout=10)
        log("  📱 已通知Telegram")
    except Exception as e:
        log(f"  ⚠️ 通知失败: {e}")

# ============ UPGRADED QUEUE RETRY (Task 3) ============
def _queue_retry_cron():
    """上传失败后：先自动修复，修复成功则立即重试，修复失败才排队30分钟后重试"""
    import json

    # 先尝试自动修复
    log("  🔧 尝试自动修复...")
    fix_ok = _auto_fix()

    if fix_ok:
        # 修复成功，立即执行一次 upload
        log("  ✅ 自动修复成功，立即重试上传...")
        vid = upload()
        if vid:
            print(f"\n🎉 重试成功! https://youtube.com/shorts/{vid}")
            notify(vid)
            return
        # 重试仍失败，继续走正常诊断流程
        log("  ⚠️ 自动修复后仍失败，继续诊断...")

    # 走诊断流程
    can_retry = _run_diagnostics()
    if not can_retry:
        log("  ⏸️ 阻塞性问题已通知，停止自动重试")
        return

    job = {
        "name": f"Shorts重试-{datetime.now().strftime('%H%M%S')}",
        "schedule": {"kind": "every", "everyMs": 30 * 60 * 1000},
        "payload": {
            "kind": "agentTurn",
            "message": f"运行Shorts补传（重试队列）:\n\ncd ~/.openclaw && ~/.openclaw/venv/youtube/bin/python3 workspace/scripts/youtube/make_short.py \"{TOPIC}\" \"{DESC}\" {' '.join(TAGS)}\n\n只重试一次，失败不再递归重试。",
            "timeoutSeconds": 600
        },
        "sessionTarget": "isolated",
        "delivery": {"mode": "announce", "channel": "telegram", "to": "299246410"}
    }
    try:
        import urllib.request
        req = urllib.request.Request(
            'http://localhost:18789/cron/jobs',
            data=json.dumps(job).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        urllib.request.urlopen(req, timeout=5)
        log("  📋 已排队30分钟后重试")
    except Exception as e:
        log(f"  ⚠️ 排队失败（需手动处理）: {e}")

def notify(vid):
    log("Telegram通知...")
    try:
        import urllib.request, urllib.parse
        bot_token = '8653763166:AAGm_dzI1nWBvxOISbjJfaes3TB7x6Ohrpc'
        chat_id = '299246410'
        msg = f"🎬 AI ToolBox Shorts 已发布!\n\n{TOPIC}\nhttps://youtube.com/shorts/{vid}\n\n#Shorts #AI"
        data = urllib.parse.urlencode({'text': msg, 'chat_id': chat_id}).encode()
        req = urllib.request.Request(f'https://api.telegram.org/bot{bot_token}/sendMessage', data=data)
        urllib.request.urlopen(req, timeout=10)
        log("  ✅ 已发送")
    except Exception as e:
        log(f"  ⚠️ Telegram失败: {e}")

def main():
    print(f"{'='*50}")
    print(f"AI ToolBox Shorts Pipeline v3")
    print(f"{'='*50}")
    print(f"  模式: Pexels真实视频 + 百炼TTS")
    print(f"  格式: {SHORT_WIDTH}x{SHORT_HEIGHT} (9:16 竖屏)")
    print(f"  标题: {TOPIC}")
    print(f"{'='*50}\n")

    # ===== TASK 1: Pre-Flight Check (在最前面执行) =====
    issues = preflight_check()
    if issues:
        # 检查是否有阻塞性问题
        critical = any('🚨' in i or ('无 PEXELS' in i and '无网络' in i) for i in issues)
        if critical:
            log("🚨 关键问题阻塞执行，已排队 cron 重试")
            _queue_retry_cron()
            return
        # 非阻塞问题，继续执行（fallback 会处理）
        for iss in issues:
            log(f"  继续: {iss}")

    video_path = gen_video()
    if not gen_voice():
        log("❌ 配音失败")
        return
    if not make_video(video_path):
        return
    vid = upload()
    if vid:
        print(f"\n🎉 完成! https://youtube.com/shorts/{vid}")
        notify(vid)
    else:
        print("\n❌ 发布失败，已自动排队30分钟后重试")
        _queue_retry_cron()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AI ToolBox Shorts Pipeline')
    parser.add_argument('--diagnose', action='store_true', help='只运行诊断和自检，不执行pipeline')
    parser.add_argument('--refresh-token', action='store_true', help='只刷新token，不执行pipeline')
    args = parser.parse_args()

    if args.diagnose:
        print("🔍 运行系统诊断...")
        issues = preflight_check()
        if not issues:
            print("✅ 所有检查通过，无问题")
        else:
            print(f"⚠️ 发现 {len(issues)} 个问题:")
            for iss in issues:
                print(f"  - {iss}")
        _run_diagnostics()
        exit(0)

    if args.refresh_token:
        print("🔄 刷新Token...")
        token = get_token()
        print(f"✅ Token已刷新: {token[:20]}...")
        exit(0)

    main()
