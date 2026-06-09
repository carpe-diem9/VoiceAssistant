"""测试 TTS 服务"""
import asyncio
import sys
sys.path.insert(0, '.')

async def test_tts():
    from services.tts_service import tts_service
    print("测试 TTS 合成...")
    try:
        result = await tts_service.synthesize("你好，世界", voice="Cherry")
        if result["audio_data"]:
            size = len(result["audio_data"])
            print(f"[PASS] TTS 合成成功! 音频大小: {size} bytes, 格式: {result['format']}")
        else:
            print(f"[FAIL] TTS 返回空音频数据")
    except Exception as e:
        print(f"[FAIL] TTS 错误: {e}")

asyncio.run(test_tts())
