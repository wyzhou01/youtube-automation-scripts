#!/usr/bin/env python3
"""
YouTube OAuth Multi-Project Manager
支持在多个 Google Cloud 项目间自动切换，配额耗尽时 failover
凭证从环境变量读取（运行时从 ~/.openclaw/youtube_projects.json 读取本地版本）
"""
import os, json, pickle, requests, subprocess
from datetime import datetime, timezone, timedelta

TOKEN_DIR = os.path.expanduser('~/.openclaw')
PROJECTS_FILE = os.path.join(TOKEN_DIR, 'youtube_projects.json')

def load_projects():
    """从本地配置文件加载项目凭证"""
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE) as f:
            return json.load(f)
    # 回退：从环境变量
    return [{
        'name': 'default',
        'project_id': os.getenv('YOUTUBE_PROJECT_ID', 'unknown'),
        'client_id': os.getenv('YOUTUBE_CLIENT_ID', ''),
        'client_secret': os.getenv('YOUTUBE_CLIENT_SECRET', ''),
        'token_file': 'youtube_token.pickle',
        'keychain_account': 'bot-refresh-token',
    }]

def _load_state():
    state_file = os.path.join(TOKEN_DIR, 'youtube_project_state.json')
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    return {'active_index': 0}

def _save_state(state):
    state_file = os.path.join(TOKEN_DIR, 'youtube_project_state.json')
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

def get_active_project():
    state = _load_state()
    projects = load_projects()
    idx = state.get('active_index', 0) % len(projects)
    return projects[idx], state

def switch_project(reason=''):
    state = _load_state()
    projects = load_projects()
    old_idx = state['active_index']
    new_idx = (old_idx + 1) % len(projects)
    state['active_index'] = new_idx
    _save_state(state)
    old_proj = projects[old_idx]
    new_proj = projects[new_idx]
    print(f"Switching: {old_proj['name']} -> {new_proj['name']} ({reason})")
    return new_proj

def get_token_for_project(project):
    token_file = os.path.join(TOKEN_DIR, project.get('token_file', 'youtube_token.pickle'))
    try:
        with open(token_file, 'rb') as f:
            creds = pickle.load(f)
    except:
        result = subprocess.run(
            ['security', 'find-generic-password', '-s', 'youtube-token-openclaw',
             '-a', project.get('keychain_account', 'bot-refresh-token'), '-w'],
            capture_output=True, text=True
        )
        rt = result.stdout.strip()
        resp = requests.post('https://oauth2.googleapis.com/token', data={
            'client_id': project['client_id'],
            'client_secret': project['client_secret'],
            'refresh_token': rt,
            'grant_type': 'refresh_token'
        }, timeout=30)
        if resp.status_code != 200:
            return None
        d = resp.json()
        creds = {
            'access_token': d['access_token'],
            'refresh_token': rt,
            'expiry': (datetime.now(timezone.utc) + timedelta(seconds=d.get('expires_in', 3600))).isoformat(),
        }
        with open(token_file, 'wb') as f:
            pickle.dump(creds, f)
    
    expiry = datetime.fromisoformat(creds.get('expiry', ''))
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) + timedelta(minutes=5) > expiry:
        resp = requests.post('https://oauth2.googleapis.com/token', data={
            'client_id': project['client_id'],
            'client_secret': project['client_secret'],
            'refresh_token': creds.get('refresh_token', ''),
            'grant_type': 'refresh_token'
        }, timeout=30)
        if resp.status_code != 200:
            return None
        d = resp.json()
        creds = {
            'access_token': d['access_token'],
            'refresh_token': creds.get('refresh_token', ''),
            'expiry': (datetime.now(timezone.utc) + timedelta(seconds=d.get('expires_in', 3600))).isoformat(),
        }
        with open(token_file, 'wb') as f:
            pickle.dump(creds, f)
    return creds.get('access_token')

def get_current_token():
    proj, _ = get_active_project()
    return get_token_for_project(proj)

def is_quota_error(resp):
    return resp.status_code == 403 and 'quota' in resp.text.lower()

def api_request_with_failover(url, method='GET', **kwargs):
    tried = []
    projects = load_projects()
    for attempt in range(len(projects)):
        proj, state = get_active_project()
        token = get_token_for_project(proj)
        if not token:
            tried.append(f"{proj['name']}: no token")
            switch_project('no token')
            continue
        kwargs.setdefault('headers', {})['Authorization'] = f'Bearer {token}'
        kwargs.setdefault('timeout', 30)
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 200:
            return resp
        if is_quota_error(resp) and attempt < len(projects) - 1:
            tried.append(f"{proj['name']}: quota exceeded")
            switch_project('quota exceeded')
            continue
        return resp
    return resp

if __name__ == '__main__':
    projects = load_projects()
    print(f"Projects loaded: {len(projects)}")
    for i, p in enumerate(projects):
        state = _load_state()
        marker = " <- ACTIVE" if state.get('active_index') == i else ""
        print(f"  {i+1}. {p['name']}{marker}")
    token = get_current_token()
    if token:
        print(f"Token: {token[:20]}...")
