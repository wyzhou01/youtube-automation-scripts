#!/usr/bin/env python3
"""
YouTube Video Upload Script
用法: python3 upload_video.py <video.mp4> <title> [description] [tags...]
"""
import os, pickle, requests, sys, json, subprocess
from datetime import datetime, timezone, timedelta

TOKEN_FILE = os.path.expanduser('~/.openclaw/youtube_token.pickle')
CLIENT_ID = '${YOUTUBE_CLIENT_ID}'
CLIENT_SECRET = '${YOUTUBE_CLIENT_SECRET}'
VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else '/tmp/test_video.mp4'
TITLE = sys.argv[2] if len(sys.argv) > 2 else 'AI ToolBox 测试视频'
DESC = sys.argv[3] if len(sys.argv) > 3 else 'AI ToolBox 频道测试视频'
TAGS = sys.argv[4:] if len(sys.argv) > 4 else ['AI工具', '测试']

def get_valid_token():
    """获取有效token，自动刷新过期token"""
    with open(TOKEN_FILE, 'rb') as f:
        creds = pickle.load(f)
    
    access_token = creds.get('access_token')
    refresh_token = creds.get('refresh_token')
    expiry_str = creds.get('expiry')
    
    # 检查是否即将过期（<5分钟）
    if expiry_str:
        expiry = datetime.fromisoformat(expiry_str)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        # 提前5分钟刷新
        if datetime.now(timezone.utc) + timedelta(minutes=5) > expiry:
            # token快过期，尝试刷新
            if refresh_token:
                print('🔄 Token即将过期，刷新中...')
                rt = refresh_token
            else:
                # 尝试从Keychain获取refresh_token
                result = subprocess.run(
                    ['security', 'find-generic-password', '-s', 'youtube-token-openclaw', '-a', 'bot-refresh-token', '-w'],
                    capture_output=True, text=True
                )
                rt = result.stdout.strip() if result.returncode == 0 else None
            
            if rt:
                resp = requests.post('https://oauth2.googleapis.com/token', data={
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'refresh_token': rt,
                    'grant_type': 'refresh_token'
                })
                if resp.status_code == 200:
                    d = resp.json()
                    new_expiry = (datetime.now(timezone.utc) + timedelta(seconds=d['expires_in'])).isoformat()
                    new_data = {
                        'access_token': d['access_token'],
                        'refresh_token': rt,
                        'expiry': new_expiry,
                        'scope': creds.get('scope', ''),
                    }
                    with open(TOKEN_FILE, 'wb') as f:
                        pickle.dump(new_data, f)
                    print('✅ Token已刷新')
                    return d['access_token']
            print('⚠️ Token刷新失败，使用现有token')
    
    return access_token

token = get_valid_token()

with open(VIDEO_PATH, 'rb') as f:
    video_content = f.read()

metadata = {
    'snippet': {
        'title': TITLE,
        'description': DESC,
        'tags': TAGS,
        'categoryId': '28',
    },
    'status': {
        'privacyStatus': 'private',
        'selfDeclaredMadeForKids': False,
    }
}

print(f"📤 上传: {os.path.basename(VIDEO_PATH)} ({len(video_content):,} bytes)")

# 初始化
init_resp = requests.post(
    'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'X-Upload-Content-Length': str(len(video_content))},
    json=metadata
)

if init_resp.status_code not in [200, 201]:
    print(f"❌ 初始化失败: {init_resp.text[:200]}")
    exit(1)

upload_url = init_resp.headers['Location']

# 上传
upload_resp = requests.put(upload_url, headers={'Content-Type': 'video/mp4'}, data=video_content)

if upload_resp.status_code == 200:
    result = upload_resp.json()
    video_id = result['id']
    print(f"✅ 上传成功!")
    print(f"   ID: {video_id}")
    print(f"   https://youtube.com/watch?v={video_id}")
else:
    print(f"❌ 上传失败: {upload_resp.text[:200]}")
    exit(1)
