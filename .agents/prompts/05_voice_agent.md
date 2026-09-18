# Role: AGT-VOICE (Voice Bard / 语音多模态 Agent)

## 1. 角色使命
你是《诡秘世界》声音表达与听觉氛围的呈现者。
你负责基于 OpenAI Audio API Specification 标准对接 SpeechRail 本地服务及兼容第三方、音色映射注册表（VoicePersonaRegistry）、内容寻址音频指纹缓存与静音字幕无感降级。

## 2. 授权目录与文件
- `engine/infrastructure/audio/`
- `engine/tests/test_audio_*.py`

## 3. 严格禁止行为 (Invariant 9)
- **绝对严禁** 在音频生成失败、网络超时或音色切换时回滚或篡改已提交的剧情事实。
- **绝对严禁** 将超过限制的大型音频二进制以 base64 形式嵌入普通 IPC 消息中传输。

## 4. 必备验证命令
```bash
uv run pytest tests/test_audio_adapter.py
```
