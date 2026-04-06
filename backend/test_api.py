"""API 接口测试脚本"""
import requests
import json
import sys

BASE = "http://localhost:8000"
TOKEN = None
SESSION_ID = None

def test(name, method, path, **kwargs):
    """通用测试函数"""
    url = f"{BASE}{path}"
    headers = kwargs.pop("headers", {})
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        r = getattr(requests, method)(url, headers=headers, timeout=15, **kwargs)
        ok = r.status_code < 400
        try:
            body = r.json()
        except:
            body = r.text[:200]
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name} -> {r.status_code}: {json.dumps(body, ensure_ascii=False)[:150]}")
        return ok, body
    except Exception as e:
        print(f"[ERROR] {name} -> {e}")
        return False, None

print("=" * 60)
print("  AI Voice Assistant API 测试")
print("=" * 60)

# 1. 健康检查
print("\n--- 1. 健康检查 ---")
test("Health Check", "get", "/api/health")

# 2. 注册（可能已存在）
print("\n--- 2. 用户认证 ---")
ok, body = test("Register", "post", "/api/auth/register", json={"username": "apitest", "password": "Pass1234"})
if ok:
    TOKEN = body["access_token"]
else:
    # 尝试登录
    ok, body = test("Login", "post", "/api/auth/login", json={"username": "apitest", "password": "Pass1234"})
    if ok:
        TOKEN = body["access_token"]

# 3. 获取当前用户
test("Get Me", "get", "/api/auth/me")

# 4. 会话管理
print("\n--- 3. 会话管理 ---")
ok, body = test("Create Session", "post", "/api/sessions", json={"title": "测试会话"})
if ok:
    SESSION_ID = body.get("id")

test("List Sessions", "get", "/api/sessions")

if SESSION_ID:
    test("Get Session", "get", f"/api/sessions/{SESSION_ID}")
    test("Update Session", "put", f"/api/sessions/{SESSION_ID}", json={"title": "修改标题"})

# 5. 设置
print("\n--- 4. 用户设置 ---")
test("Get Settings", "get", "/api/settings/tts")
test("Update Settings", "put", "/api/settings/tts", json={"voice": "Ethan", "speed": 1.2, "pitch": 1.0, "volume": 80})
test("Get Settings After Update", "get", "/api/settings/tts")

# 6. 文本对话（SSE流式）
print("\n--- 5. 文本对话 (SSE) ---")
if SESSION_ID:
    try:
        r = requests.post(
            f"{BASE}/api/chat/text",
            json={"session_id": SESSION_ID, "message": "你好，请简短回复"},
            headers={"Authorization": f"Bearer {TOKEN}"},
            stream=True, timeout=30
        )
        print(f"[{'PASS' if r.status_code == 200 else 'FAIL'}] Text Chat SSE -> {r.status_code}")
        full_text = ""
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    if "content" in chunk:
                        full_text += chunk["content"]
                except:
                    pass
        print(f"  LLM回复: {full_text[:100]}...")
    except Exception as e:
        print(f"[ERROR] Text Chat SSE -> {e}")

# 7. 删除会话
print("\n--- 6. 清理 ---")
if SESSION_ID:
    test("Delete Session", "delete", f"/api/sessions/{SESSION_ID}")

print("\n" + "=" * 60)
print("  测试完成!")
print("=" * 60)
