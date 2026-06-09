"""
Deep Research 引擎 - 使用 DashScope SDK 调用 qwen-deep-research 模型
qwen-deep-research 采用两阶段调用流程：
1. 第一阶段：模型反问确认（获取研究方向的澄清）
2. 第二阶段：深入研究（执行多步搜索和分析）

注意：
- 该模型仅支持 DashScope 原生 API，不支持 OpenAI 兼容接口。
- DashScope SDK 的 Generation.call() 是同步阻塞调用，必须在独立线程中运行，
  否则会阻塞 FastAPI 的 asyncio 事件循环，导致整个服务器卡死。
- 修复方案：threading + asyncio.Queue，同步迭代在子线程运行，结果通过队列
  异步传回，事件循环全程不阻塞。
"""
import asyncio
import threading
import logging
from typing import List, Dict, AsyncGenerator, Optional
from config import settings

logger = logging.getLogger(__name__)


async def _dashscope_stream_async(api_key: str, model: str, messages: list):
    """
    将同步的 DashScope Generation.call(stream=True) 包装为异步生成器。

    核心机制：
    1. 在独立守护线程中运行同步阻塞的 Generation.call 迭代
    2. 通过 loop.call_soon_threadsafe + asyncio.Queue 将结果传回异步侧
    3. 主协程 `await q.get()` 挂起等待，不占用事件循环，其他请求正常处理

    Yields: DashScope response 对象
    """
    from dashscope import Generation

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run_in_thread():
        try:
            responses = Generation.call(
                api_key=api_key,
                model=model,
                messages=messages,
                stream=True,
            )
            for resp in responses:
                loop.call_soon_threadsafe(q.put_nowait, ("item", resp))
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(q.put_nowait, ("done", None))

    # 启动守护线程，主线程（事件循环）不阻塞
    threading.Thread(target=_run_in_thread, daemon=True).start()

    while True:
        kind, value = await q.get()
        if kind == "done":
            break
        elif kind == "error":
            raise value
        else:
            yield value


class DeepResearchService:
    """Deep Research 服务 - 基于 DashScope qwen-deep-research 的深度研究"""

    def __init__(self):
        self._api_key = settings.DEEPRESEARCH_API_KEY
        self._model_id = (
            settings.DEEPRESEARCH_MODEL or "qwen-deep-research-2025-12-15"
        ).strip()

    async def research(
        self,
        question: str,
        context_messages: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        执行 Deep Research 两阶段流程，向前端流式吐出：
            {"type": "step",        "step": int, "title": str, "content": str}
            {"type": "thinking",    "content": str}   # 第一阶段模型反问
            {"type": "final_chunk", "content": str}   # 第二阶段研究内容片段
            {"type": "final",       "content": str}   # 完整最终内容
            {"type": "error",       "message": str}
        """
        context = context_messages or []

        logger.info(
            f"[DeepResearch] ========== DR API 调用开始 ========== "
            f"model={self._model_id} | question='{question[:60]}' | context_len={len(context)}"
        )

        yield {
            "type": "step",
            "step": 1,
            "title": "派发研究任务",
            "content": f"已将问题交由 {self._model_id} 进行深度研究…",
        }

        if not self._api_key:
            yield {
                "type": "error",
                "message": "DeepResearch API Key 未配置，请在 .env 中设置 DEEPRESEARCH_API_KEY。",
            }
            return

        try:
            import dashscope  # noqa: F401 — 仅做可用性检查
        except ImportError:
            yield {
                "type": "error",
                "message": "未安装 dashscope SDK，请执行：pip install dashscope",
            }
            return

        try:
            # ── 第一阶段：模型反问确认 ─────────────────────────────────────────
            yield {
                "type": "step",
                "step": 2,
                "title": "研究规划中",
                "content": "模型正在分析研究方向…",
            }

            messages_s1 = [{"role": "user", "content": question}]
            messages_s1.extend(context)  # 追加历史上下文
            logger.info(f"[DeepResearch] Phase-1 请求 DashScope DR API, messages_count={len(messages_s1)}")

            step1_content = ""
            async for resp in _dashscope_stream_async(
                self._api_key, self._model_id, messages_s1
            ):
                if hasattr(resp, "output") and resp.output:
                    msg = resp.output.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        step1_content += content
                        yield {"type": "thinking", "content": content}

            # ── 第二阶段：深入研究 ────────────────────────────────────────────
            yield {
                "type": "step",
                "step": 3,
                "title": "深入研究中",
                "content": "正在展开子问题分解、证据收集与综合分析…",
            }

            messages_s2 = [{"role": "user", "content": question}]
            if step1_content:
                # 将第一阶段反问带入对话，自动确认开始研究
                messages_s2.append({"role": "assistant", "content": step1_content})
                messages_s2.append({
                    "role": "user",
                    "content": "请按照你的研究方向开始深入分析。",
                })
            logger.info(f"[DeepResearch] Phase-2 请求 DashScope DR API, messages_count={len(messages_s2)}")

            full_response = ""
            async for resp in _dashscope_stream_async(
                self._api_key, self._model_id, messages_s2
            ):
                if hasattr(resp, "output") and resp.output:
                    msg = resp.output.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        full_response += content
                        yield {"type": "final_chunk", "content": content}

            # 兜底：第二阶段无内容时，将第一阶段内容作为结果
            if not full_response and step1_content:
                full_response = step1_content
                yield {"type": "final_chunk", "content": step1_content}

        except Exception as e:
            logger.exception(f"DeepResearch 调用失败 [{self._model_id}]")
            yield {
                "type": "error",
                "message": f"Deep Research 调用失败: {type(e).__name__}: {str(e)}",
            }
            return

        yield {
            "type": "step",
            "step": 4,
            "title": "研究完成",
            "content": "报告已生成。",
        }
        yield {"type": "final", "content": full_response}


# 全局 Deep Research 服务实例
deep_research_service = DeepResearchService()
