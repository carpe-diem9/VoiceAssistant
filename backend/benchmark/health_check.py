"""
\u6240\u6709\u5916\u90e8 API \u8fde\u901a\u6027\u63a2\u6d3b\u3002\u4ee5\u6700\u5c0f\u4ee3\u4ef7\u5224\u65ad\u6bcf\u4e2a\u6e20\u9053\u662f\u5426\u53ef\u7528\u3002

\u68c0\u6d4b\u8303\u56f4\uff08\u4e0e settings \u4e2d\u51fa\u73b0\u7684\u6e20\u9053/\u6a21\u578b\u4e00\u4e00\u5bf9\u5e94\uff09\uff1a
  LLM:
    - DashScope (qwen3.5-plus)
    - DeepSeek  (deepseek-chat)
    - gpt.ge    (gpt-5.5)
    - gpt.ge    (gemini-3.1-pro-preview)
    - OpenRouter (tongyi-deepresearch, Deep Research)
  ASR:
    - DashScope (qwen3-asr-flash)
    - gpt.ge    (SenseVoiceSmall)
    - gpt.ge    (whisper-large-v3)
  TTS:
    - DashScope (qwen3-tts-instruct-flash)
    - gpt.ge    (CosyVoice2)
    - gpt.ge    (gemini-2.5-flash-preview-tts)

\u8fd0\u884c\uff1a
  cd backend
  python -m benchmark.health_check
"""
from __future__ import annotations

import sys
import time
import asyncio
import logging
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from openai import OpenAI  # noqa: E402
from config import settings  # noqa: E402
from services.tts_service import tts_service  # noqa: E402
from services.asr_service import asr_service  # noqa: E402

# \u9759\u9ed8 services \u7684 INFO/WARN/ERROR\uff0c\u907f\u514d\u672c\u811a\u672c\u8868\u683c\u88ab\u6df9\u6ca1
logging.basicConfig(level=logging.CRITICAL)


# ---------------- LLM \u63a2\u6d3b ----------------
def _ping_chat(name: str, base_url: str, api_key: str, model: str,
               extra_msg: str = "ping", timeout: float = 60.0) -> dict:
    """\u7528 OpenAI \u517c\u5bb9\u5ba2\u6237\u7aef\u5411\u6307\u5b9a\u6e20\u9053\u53d1\u4e00\u6b21\u6781\u7b80 chat completion\u3002"""
    row = {
        "type": "LLM",
        "channel": name,
        "model": model,
        "ok": False,
        "latency_s": None,
        "detail": "",
    }
    if not api_key:
        row["detail"] = "API key \u672a\u914d\u7f6e"
        return row
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        t0 = time.perf_counter()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": extra_msg}],
            max_tokens=8,
            stream=False,
        )
        dt = time.perf_counter() - t0
        content = (resp.choices[0].message.content or "").strip()
        row["ok"] = True
        row["latency_s"] = round(dt, 2)
        row["detail"] = content[:40] or "(\u7a7a\u8fd4\u56de\u4f46\u8bf7\u6c42\u6210\u529f)"
    except Exception as e:
        row["detail"] = f"{type(e).__name__}: {str(e)[:160]}"
    return row


# ---------------- TTS \u63a2\u6d3b ----------------
async def _ping_tts(model: str) -> dict:
    row = {
        "type": "TTS",
        "channel": "DashScope" if "qwen" in model.lower() else "gpt.ge",
        "model": model,
        "ok": False,
        "latency_s": None,
        "detail": "",
    }
    try:
        # \u5728 services.tts_service \u91cc\u6dfb\u52a0\u4e34\u65f6\u65e5\u5fd7\u62e6\u622a\uff0c\u68c0\u6d4b\u662f\u5426\u9759\u9ed8\u56de\u9000
        cap: list[str] = []
        class _H(logging.Handler):
            def emit(self, rec):
                cap.append(rec.getMessage())
        h = _H(level=logging.WARNING)
        logging.getLogger("services.tts_service").addHandler(h)
        try:
            t0 = time.perf_counter()
            result = await tts_service.synthesize("\u55e8", voice="Cherry", model=model)
            dt = time.perf_counter() - t0
            audio = result.get("audio_data") or b""
            is_gptge = tts_service._is_gptge_model(model)
            joined = "\n".join(cap)
            if is_gptge and ("\u56de\u9000" in joined or "fallback" in joined.lower()):
                row["detail"] = "\u9759\u9ed8\u56de\u9000 dashscope: " + (cap[-1][-140:] if cap else "")
            elif not audio:
                row["detail"] = "\u8fd4\u56de\u7a7a\u97f3\u9891"
            else:
                row["ok"] = True
                row["latency_s"] = round(dt, 2)
                row["detail"] = f"{len(audio)} bytes wav"
        finally:
            logging.getLogger("services.tts_service").removeHandler(h)
    except Exception as e:
        row["detail"] = f"{type(e).__name__}: {str(e)[:160]}"
    return row


# ---------------- ASR \u63a2\u6d3b ----------------
async def _prepare_ref_audio() -> bytes:
    """\u5148\u7528\u9ed8\u8ba4 dashscope TTS \u5408\u6210\u4e00\u6bb5 'hi' \u6765\u63a2 ASR\u3002"""
    res = await tts_service.synthesize("\u4f60\u597d", voice="Cherry",
                                       model=settings.TTS_MODEL)
    return res.get("audio_data") or b""


async def _ping_asr(model: str, audio: bytes) -> dict:
    row = {
        "type": "ASR",
        "channel": "DashScope" if "qwen" in model.lower() else "gpt.ge",
        "model": model,
        "ok": False,
        "latency_s": None,
        "detail": "",
    }
    if not audio:
        row["detail"] = "\u53c2\u8003\u97f3\u9891\u672a\u751f\u6210"
        return row
    try:
        t0 = time.perf_counter()
        text = await asr_service.recognize(audio, is_wav=True, language="zh", model=model)
        dt = time.perf_counter() - t0
        row["ok"] = True
        row["latency_s"] = round(dt, 2)
        row["detail"] = (text or "(\u7a7a\u8fd4\u56de)")[:40]
    except Exception as e:
        row["detail"] = f"{type(e).__name__}: {str(e)[:160]}"
    return row


# ---------------- \u4e3b\u8fdb\u7a0b ----------------
async def main():
    print("=" * 80)
    print(" API \u8fde\u901a\u6027\u68c0\u6d4b")
    print("=" * 80)
    rows: list[dict] = []

    # ----- LLM -----
    print("\n[LLM]")
    rows.append(_ping_chat("DashScope (Qwen)", settings.LLM_BASE_URL,
                            settings.LLM_API_KEY, "qwen3.5-plus"))
    rows.append(_ping_chat("DeepSeek", settings.DEEPSEEK_BASE_URL,
                            settings.DEEPSEEK_API_KEY, "deepseek-chat"))
    rows.append(_ping_chat("gpt.ge \u00b7 gpt-5.5", settings.GPTGE_BASE_URL,
                            settings.GPTGE_API_KEY, "gpt-5.5"))
    rows.append(_ping_chat("gpt.ge \u00b7 gemini-3.1-pro-preview", settings.GPTGE_BASE_URL,
                            settings.GPTGE_API_KEY, "gemini-3.1-pro-preview"))
    rows.append(_ping_chat("OpenRouter \u00b7 deep-research", settings.DEEPRESEARCH_BASE_URL,
                            settings.DEEPRESEARCH_API_KEY, settings.DEEPRESEARCH_MODEL))

    # ----- TTS -----
    print("[TTS]")
    for m in settings.AVAILABLE_TTS_MODELS:
        rows.append(await _ping_tts(m))

    # ----- ASR -----
    print("[ASR] \u9884\u751f\u6210\u53c2\u8003\u97f3\u9891 ...")
    audio = await _prepare_ref_audio()
    print(f"      \u53c2\u8003\u97f3\u9891 = {len(audio)} bytes")
    for m in settings.AVAILABLE_ASR_MODELS:
        rows.append(await _ping_asr(m, audio))

    # ----- \u8868\u683c\u8f93\u51fa -----
    print("\n" + "-" * 100)
    print(f"{'\u7c7b\u578b':<5} {'\u6e20\u9053':<32} {'\u6a21\u578b':<32} {'\u72b6\u6001':<6} {'\u5ef6\u8fdf':<8} \u8be6\u60c5")
    print("-" * 100)
    ok = fail = 0
    for r in rows:
        status = "\u2713 OK" if r["ok"] else "\u2717 FAIL"
        if r["ok"]:
            ok += 1
        else:
            fail += 1
        lat = (str(r["latency_s"]) + "s") if r["latency_s"] is not None else "-"
        print(f"{r['type']:<5} {r['channel']:<32} {r['model']:<32} {status:<6} {lat:<8} {r['detail']}")
    print("-" * 100)
    print(f"\u5408\u8ba1: {ok} \u4e2a\u8054\u901a, {fail} \u4e2a\u4e0d\u53ef\u7528  (\u603b {len(rows)})")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
