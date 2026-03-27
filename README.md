# YouTube AI ToolBox 自动化脚本

> YouTube Shorts 自动生成 + 上传工具（OpenClaw 版）

## 核心功能

- `make_short.py` — 完整 Shorts 制作 pipeline（Pexels 视频 + 百炼 TTS + FFmpeg 合成 + 上传）
- `upload_video.py` — 独立上传脚本（带自动 token 刷新）
- `fallback_registry.py` — 备选工具链（视频源 / TTS / 图片生成三层 fallback）
- `keychain_token.py` — YouTube OAuth Token 管理

## 自我修复能力

- **Pre-Flight Check** — 执行前检查并自动修复（.env 路径、token 补全、key 验证）
- **自动重试** — 403 等 30s、401 刷新 token、其他错误等 10s
- **全失败后自我修复** — 诊断 → 自动修复 → 验证 → 重试，无需人工干预

## 使用方法

```bash
# 生成 + 上传 Shorts
python3 make_short.py "标题" "描述" "标签..."

# 仅诊断
python3 make_short.py --diagnose

# 仅刷新 Token
python3 make_short.py --refresh-token
```
