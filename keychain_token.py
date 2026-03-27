#!/usr/bin/env python3
"""
YouTube Token Keychain 存储/读取工具
安全存储OAuth refresh_token
"""
import os, pickle, subprocess, json

TOKEN_FILE = os.path.expanduser('~/.openclaw/youtube_token.pickle')
KEYCHAIN_SERVICE = 'youtube-token-openclaw'
KEYCHAIN_ACCOUNT = 'bot-refresh-token'

def save_to_keychain():
    """把refresh_token存入Keychain"""
    if not os.path.exists(TOKEN_FILE):
        print("❌ 没有Token文件")
        return False
    
    with open(TOKEN_FILE, 'rb') as f:
        creds = pickle.load(f)
    
    if isinstance(creds, dict):
        refresh_token = creds.get('refresh_token')
        token_data = creds
    else:
        refresh_token = creds.refresh_token if hasattr(creds, 'refresh_token') else None
        token_data = {
            'access_token': creds.token if hasattr(creds, 'token') else None,
            'refresh_token': refresh_token,
            'expiry': str(creds.expiry) if hasattr(creds, 'expiry') else None,
            'scope': ' '.join(creds.scopes) if hasattr(creds, 'scopes') and creds.scopes else None
        }
    
    if not refresh_token:
        print("❌ 没有refresh_token")
        return False
    
    # 存Keychain
    result = subprocess.run(
        ['security', 'add-generic-password',
         '-s', KEYCHAIN_SERVICE,
         '-a', KEYCHAIN_ACCOUNT,
         '-w', refresh_token,
         '-U'],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        print(f"✅ refresh_token已存入Keychain")
        
        # 同时存完整token数据到文件
        token_data['_in_keychain'] = True
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(token_data, f)
        print(f"✅ Token元数据已更新")
        return True
    else:
        print(f"❌ Keychain存储失败: {result.stderr}")
        return False

def load_from_keychain():
    """从Keychain读取refresh_token"""
    result = subprocess.run(
        ['security', 'find-generic-password',
         '-s', KEYCHAIN_SERVICE,
         '-a', KEYCHAIN_ACCOUNT,
         '-w'],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        return result.stdout.strip()
    return None

def delete_from_keychain():
    """从Keychain删除"""
    result = subprocess.run(
        ['security', 'delete-generic-password',
         '-s', KEYCHAIN_SERVICE,
         '-a', KEYCHAIN_ACCOUNT],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"✅ Keychain已删除")
    else:
        print(f"⚠️ {result.stderr}")

def save_current_token():
    """保存当前token到Keychain"""
    save_to_keychain()

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python3 keychain_token.py [save|load|delete]")
        print("  save   - 存当前token到Keychain")
        print("  load   - 从Keychain读取")
        print("  delete - 删除Keychain")
        exit(1)
    
    cmd = sys.argv[1]
    if cmd == 'save':
        save_to_keychain()
    elif cmd == 'load':
        token = load_from_keychain()
        if token:
            print(f"Token: {token[:20]}...")
        else:
            print("❌ 没有找到")
    elif cmd == 'delete':
        delete_from_keychain()
