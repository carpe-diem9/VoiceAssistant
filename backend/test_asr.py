"""测试 ASR 服务 - 使用 TTS 生成的音频来测试"""
import asyncio
import sys
sys.path.insert(0, '.')

async def test_asr():
    from services.tts_service import tts_service
    from services.asr_service import asr_service
    
    # 先用 TTS 生成一段音频
    print("1. 生成测试音频...")
    tts_result = await tts_service.synthesize("你好世界，今天天气很好", voice="Cherry")
    audio_data = tts_result["audio_data"]
    print(f"   音频大小: {len(audio_data)} bytes")
    
    # 用 ASR 识别
    print("2. ASR 识别中...")
    try:
        text = await asr_service.recognize(audio_data, is_wav=True)
        print(f"[PASS] ASR 识别结果: {text}")
    except Exception as e:
        print(f"[FAIL] ASR 错误: {e}")

asyncio.run(test_asr())
