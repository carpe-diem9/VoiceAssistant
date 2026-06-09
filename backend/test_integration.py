"""完整集成测试 - 测试所有API接口 + 语音端到端流程"""
import requests
import json
import base64
import sys
import os
sys.path.insert(0, '.')

BASE = "http://localhost:8000"
TOKEN = None
SESSION_ID = None
PASS_COUNT = 0
FAIL_COUNT = 0

def test(name, method, path, **kwargs):
    global PASS_COUNT, FAIL_COUNT
    url = f"{BASE}{path}"
    headers = kwargs.pop("headers", {})
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        r = getattr(requests, method)(url, headers=headers, timeout=60, **kwargs)
        ok = r.status_code < 400
        try:
            body = r.json()
        except:
            body = r.text[:200]
        status = "PASS" if ok else "FAIL"
        if ok:
            PASS_COUNT += 1
        else:
            FAIL_COUNT += 1
        print(f"  [{status}] {name} -> {r.status_code}")
        return ok, body, r
    except Exception as e:
        FAIL_COUNT += 1
        print(f"  [ERROR] {name} -> {e}")
        return False, None, None

print("=" * 60)
print("  AI Voice Assistant - 完整集成测试")
print("=" * 60)

# ===== 1. 健康检查 =====
print("\n1. 健康检查")
ok, body, _ = test("Health Check", "get", "/api/health")
if ok:
    print(f"     ASR: {body['asr_model']}, TTS: {body['tts_model']}, LLM: {body['llm_model']}")

# ===== 2. 用户认证 =====
print("\n2. 用户认证")
ok, body, _ = test("Register new user", "post", "/api/auth/register",
                    json={"username": "integtest", "password": "Test1234"})
if ok:
    TOKEN = body["access_token"]
    print(f"     User ID: {body['user']['id']}")
else:
    ok, body, _ = test("Login existing", "post", "/api/auth/login",
                        json={"username": "integtest", "password": "Test1234"})
    if ok:
        TOKEN = body["access_token"]

ok, body, _ = test("Get current user", "get", "/api/auth/me")

# ===== 3. 会话管理 =====
print("\n3. 会话管理 CRUD")
ok, body, _ = test("Create session", "post", "/api/sessions", json={"title": "集成测试会话"})
if ok:
    SESSION_ID = body["id"]
test("List sessions", "get", "/api/sessions")
if SESSION_ID:
    test("Get session detail", "get", f"/api/sessions/{SESSION_ID}")
    test("Update session title", "put", f"/api/sessions/{SESSION_ID}", json={"title": "更新后的标题"})

# ===== 4. 用户设置 =====
print("\n4. 用户设置")
test("Get TTS settings", "get", "/api/settings/tts")
test("Update TTS settings", "put", "/api/settings/tts",
     json={"voice": "Serena", "speed": 1.5, "pitch": 1.0, "volume": 70})
ok, body, _ = test("Verify TTS update", "get", "/api/settings/tts")
if ok and body.get("voice") == "Serena" and body.get("speed") == 1.5:
    PASS_COUNT += 1
    print(f"  [PASS] Settings verified: voice={body['voice']}, speed={body['speed']}")
else:
    FAIL_COUNT += 1
    print(f"  [FAIL] Settings not updated correctly")
test("Get models", "get", "/api/settings/models")

# ===== 5. 文本对话 (SSE流式) =====
print("\n5. 文本对话 (SSE 流式)")
if SESSION_ID:
    try:
        r = requests.post(
            f"{BASE}/api/chat/text",
            json={"session_id": SESSION_ID, "message": "你好，请用一句话介绍自己"},
            headers={"Authorization": f"Bearer {TOKEN}"},
            stream=True, timeout=120
        )
        full_text = ""
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data = line[6:]
                try:
                    chunk = json.loads(data)
                    if chunk.get("type") == "text":
                        full_text += chunk["content"]
                    elif chunk.get("type") == "done":
                        break
                except:
                    pass
        if full_text:
            PASS_COUNT += 1
            print(f"  [PASS] Text Chat SSE -> LLM回复({len(full_text)}字): {full_text[:80]}...")
        else:
            FAIL_COUNT += 1
            print(f"  [FAIL] Text Chat SSE -> 未收到回复")
    except Exception as e:
        FAIL_COUNT += 1
        print(f"  [ERROR] Text Chat SSE -> {e}")

# ===== 6. 语音对话 (ASR + LLM + TTS 端到端) =====
print("\n6. 语音对话 端到端 (TTS生成音频 -> ASR识别 -> LLM回复 -> TTS合成)")

# 先用TTS生成测试音频
import asyncio
sys.path.insert(0, os.path.dirname(__file__))

async def generate_test_audio():
    from services.tts_service import tts_service
    result = await tts_service.synthesize("今天天气怎么样", voice="Cherry")
    return result["audio_data"]

try:
    test_audio = asyncio.run(generate_test_audio())
    print(f"  [INFO] 生成测试音频: {len(test_audio)} bytes")
    
    if SESSION_ID:
        # 通过voice接口测试
        import io
        files = {"audio": ("test.wav", io.BytesIO(test_audio), "audio/wav")}
        data = {"session_id": str(SESSION_ID)}
        r = requests.post(
            f"{BASE}/api/chat/voice",
            files=files, data=data,
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=120
        )
        if r.status_code == 200:
            result = r.json()
            PASS_COUNT += 1
            print(f"  [PASS] Voice Chat:")
            print(f"     ASR文本: {result.get('asr_text', 'N/A')}")
            print(f"     LLM回复: {result.get('reply_text', 'N/A')[:80]}...")
            audio_b64 = result.get('audio_base64', '')
            if audio_b64:
                audio_size = len(base64.b64decode(audio_b64))
                print(f"     TTS音频: {audio_size} bytes")
            else:
                print(f"     TTS音频: 无")
        else:
            FAIL_COUNT += 1
            print(f"  [FAIL] Voice Chat -> {r.status_code}: {r.text[:200]}")
except Exception as e:
    FAIL_COUNT += 1
    print(f"  [ERROR] Voice E2E -> {e}")

# ===== 7. Deep Research =====
print("\n7. Deep Research (SSE)")
if SESSION_ID:
    try:
        r = requests.post(
            f"{BASE}/api/chat/deep-research",
            json={"session_id": SESSION_ID, "question": "Python和JavaScript的主要区别是什么？简要回答"},
            headers={"Authorization": f"Bearer {TOKEN}"},
            stream=True, timeout=120
        )
        steps = []
        final = ""
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    chunk = json.loads(line[6:])
                    if chunk.get("type") == "step":
                        steps.append(chunk.get("title", ""))
                    elif chunk.get("type") == "final":
                        final = chunk.get("content", "")
                except:
                    pass
        if final:
            PASS_COUNT += 1
            print(f"  [PASS] Deep Research: {len(steps)}个推理步骤")
            print(f"     最终结果({len(final)}字): {final[:80]}...")
        else:
            FAIL_COUNT += 1
            print(f"  [FAIL] Deep Research 无结果")
    except Exception as e:
        FAIL_COUNT += 1
        print(f"  [ERROR] Deep Research -> {e}")

# ===== 8. 清理 =====
print("\n8. 清理测试数据")
if SESSION_ID:
    test("Delete session", "delete", f"/api/sessions/{SESSION_ID}")

# ===== 汇总 =====
print("\n" + "=" * 60)
total = PASS_COUNT + FAIL_COUNT
print(f"  测试完成: {PASS_COUNT}/{total} 通过, {FAIL_COUNT} 失败")
print("=" * 60)
