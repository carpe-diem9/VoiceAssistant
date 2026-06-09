"""
真实性能基准测试入口。
直接调用 services.* 实例，对以下三项进行端到端测量：

  1. TTS 朗读错词率：各 TTS 合成中文参考句，再用 qwen3-asr-flash 回识别，算 CER。
  2. ASR 识别准确率：用 qwen3-tts-instruct-flash 合成标准音频，各 ASR 识别，算 CER。
  3. LLM 回复质量：八题多维度评测，按关键词/正则自动判分。

结果输出：
  benchmark/results/tts_results.csv
  benchmark/results/asr_results.csv
  benchmark/results/llm_results.csv
  benchmark/results/summary.md   （Markdown 表格对比）

用法：
  cd backend
  python -m benchmark.run_benchmark              # 跑全部
  python -m benchmark.run_benchmark --only tts   # 只跑某项
  python -m benchmark.run_benchmark --only asr
  python -m benchmark.run_benchmark --only llm
  python -m benchmark.run_benchmark --limit 3    # 每个模型只跑前 3 条（冒烟测试）
"""
from __future__ import annotations

import os
import sys
import csv
import time
import asyncio
import argparse
import logging
import traceback
from statistics import mean
from pathlib import Path
from typing import Callable

# Windows GBK 控制台遇到 Unicode 字符（如 H₂O）会报 UnicodeEncodeError 并阻塞。
# 在入口强制使用 utf-8 + errors='replace'，避免后续 print/logger 卡住。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

# 允许 `python -m benchmark.run_benchmark` 和 `python benchmark/run_benchmark.py` 两种启动
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from benchmark.datasets import REFERENCE_SENTENCES, LLM_TEST_CASES  # noqa: E402
from benchmark.scoring import char_error_rate, evaluate_llm_answer  # noqa: E402
from config import settings  # noqa: E402
from services.tts_service import tts_service  # noqa: E402
from services.asr_service import asr_service  # noqa: E402
from services.llm_service import llm_service  # noqa: E402


# 降低子模块日志噪声，只保留 WARNING 及以上（保留我们自己的 print 输出清爽）
logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")


RESULTS_DIR = CURRENT_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 全局预算保护（防止失控调用，账户余额仅 ~$5）
#   - GLOBAL_CALL_BUDGET：进程内所有 services.* 调用总次数上限
#   - PER_MODEL_BUDGET：每个具体模型的最大调用次数
# 超出后后续的 bench_* 会直接跳过。
# ---------------------------------------------------------------------------
GLOBAL_CALL_BUDGET = int(os.getenv("BENCH_GLOBAL_BUDGET", "80"))
PER_MODEL_BUDGET = int(os.getenv("BENCH_PER_MODEL_BUDGET", "20"))

_call_counter = {"total": 0, "per_model": {}}


def _budget_check(model: str) -> str | None:
    """调用前检查：返回原因字符串表示被拒绝，None 表示可以进行。"""
    if _call_counter["total"] >= GLOBAL_CALL_BUDGET:
        return f"global budget exhausted ({_call_counter['total']}/{GLOBAL_CALL_BUDGET})"
    used = _call_counter["per_model"].get(model, 0)
    if used >= PER_MODEL_BUDGET:
        return f"per-model budget exhausted for {model} ({used}/{PER_MODEL_BUDGET})"
    return None


def _budget_inc(model: str) -> None:
    _call_counter["total"] += 1
    _call_counter["per_model"][model] = _call_counter["per_model"].get(model, 0) + 1


def _budget_summary() -> str:
    parts = [f"total={_call_counter['total']}/{GLOBAL_CALL_BUDGET}"]
    for k, v in _call_counter["per_model"].items():
        parts.append(f"{k}={v}")
    return "  ".join(parts)


# ---------------------------------------------------------------------------
# 日志拦截：捕获 services.* 模块里出现的"失败 / 回退"事件。
# 很多 gpt.ge 路由的模型（CosyVoice2 / gemini-tts / SenseVoiceSmall / whisper / gpt / gemini-LLM）
# 在配额不足或音色不匹配时会静默回退到 dashscope。
# benchmark 必须如实地把这些事件标记出来，避免把回退结果算作该模型的真实成绩。
# ---------------------------------------------------------------------------
class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(self.format(record))
        except Exception:
            pass

    def reset(self) -> None:
        self.records.clear()

    def has_fallback(self) -> bool:
        joined = "\n".join(self.records)
        return ("回退" in joined) or ("falling back" in joined.lower()) or ("fallback" in joined.lower())

    def collect_error(self) -> str:
        # 优先返回最后一条带 ERROR 的消息，便于定位
        errs = [r for r in self.records if " ERROR " in r]
        if errs:
            return errs[-1]
        return self.records[-1] if self.records else ""


_capture = _CaptureHandler()
_capture.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
for _name in ("services.tts_service", "services.asr_service", "services.llm_service"):
    _lg = logging.getLogger(_name)
    _lg.addHandler(_capture)
    _lg.setLevel(logging.INFO)


# =============================================================================
#  TTS 基准
# =============================================================================
async def _synthesize_one(model: str, text: str) -> tuple[bytes, float]:
    """单条 TTS 合成，返回 (audio_bytes, elapsed_seconds)。"""
    t0 = time.perf_counter()
    result = await tts_service.synthesize(text, voice="Cherry", model=model)
    dt = time.perf_counter() - t0
    return result.get("audio_data") or b"", dt


async def _recognize_one(model: str, audio: bytes) -> tuple[str, float]:
    t0 = time.perf_counter()
    text = await asr_service.recognize(audio, is_wav=True, language="zh", model=model)
    dt = time.perf_counter() - t0
    return text, dt


async def bench_tts(limit: int | None) -> list[dict]:
    """每个 TTS 模型 × 每条参考句：合成 -> 用最强 ASR 回识别 -> 计算 CER。"""
    rows: list[dict] = []
    asr_judge = "qwen3-asr-flash"
    sents = REFERENCE_SENTENCES if not limit else REFERENCE_SENTENCES[:limit]

    print(f"\n=== [TTS 基准] 共 {len(settings.AVAILABLE_TTS_MODELS)} 个模型 × {len(sents)} 句 ===")
    print(f"    判定 ASR = {asr_judge}\n")

    for tts_model in settings.AVAILABLE_TTS_MODELS:
        consec_fail = 0
        for i, ref in enumerate(sents, 1):
            if consec_fail >= 2:
                print(f"  [{tts_model}] 已连续失败，跳过剩下 {len(sents)-i+1} 条样本。")
                break
            # 预算拦截：TTS 一条样本 = 1 次 TTS + 1 次 ASR
            blk = _budget_check(tts_model) or _budget_check(asr_judge)
            if blk:
                print(f"  [{tts_model}] 预算耗尽，跳过：{blk}")
                break
            row = {
                "tts_model": tts_model,
                "idx": i,
                "reference": ref,
                "audio_bytes": 0,
                "tts_latency_s": None,
                "asr_latency_s": None,
                "hypothesis": "",
                "cer": None,
                "fallback": False,
                "error": "",
            }
            try:
                _capture.reset()
                _budget_inc(tts_model)
                audio, tts_dt = await _synthesize_one(tts_model, ref)
                row["audio_bytes"] = len(audio)
                row["tts_latency_s"] = round(tts_dt, 3)
                # 检测静默回退：gpt.ge 路由的模型失败后会回退到 dashscope
                is_gptge = tts_service._is_gptge_model(tts_model)
                if is_gptge and _capture.has_fallback():
                    row["error"] = "fallback to dashscope: " + _capture.collect_error()[-200:]
                    row["fallback"] = True
                    print(f"  [{tts_model}] #{i}  回退 dashscope（不计入该模型成绩）")
                elif not audio:
                    row["error"] = "empty audio"
                    print(f"  [{tts_model}] #{i}  合成失败（空音频）")
                else:
                    _budget_inc(asr_judge)
                    hyp, asr_dt = await _recognize_one(asr_judge, audio)
                    row["hypothesis"] = hyp
                    row["asr_latency_s"] = round(asr_dt, 3)
                    row["cer"] = round(char_error_rate(ref, hyp), 4)
                    print(f"  [{tts_model}] #{i}  TTS={tts_dt:.2f}s  ASR={asr_dt:.2f}s  "
                          f"CER={row['cer']:.3f}  hyp={hyp[:30]}")
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
                print(f"  [{tts_model}] #{i}  ERROR: {row['error']}")
            # 累计连续失败 / 回退
            if row["error"] or row["cer"] is None:
                consec_fail += 1
            else:
                consec_fail = 0
            rows.append(row)
    return rows


# =============================================================================
#  ASR 基准
# =============================================================================
async def bench_asr(limit: int | None) -> list[dict]:
    """用稳定 TTS 预生成标准音频，再让各 ASR 识别。"""
    rows: list[dict] = []
    tts_ref = "qwen3-tts-instruct-flash"
    sents = REFERENCE_SENTENCES if not limit else REFERENCE_SENTENCES[:limit]

    print(f"\n=== [ASR 基准] 共 {len(settings.AVAILABLE_ASR_MODELS)} 个模型 × {len(sents)} 句 ===")
    print(f"    参考 TTS = {tts_ref}\n")

    # 先一次性把所有参考句合成好，缓存音频避免重复生成
    print("  [prep] 预生成参考音频...")
    ref_audios: list[tuple[str, bytes]] = []
    for i, ref in enumerate(sents, 1):
        if _budget_check(tts_ref):
            print(f"    #{i}  skip: budget")
            break
        try:
            _budget_inc(tts_ref)
            audio, dt = await _synthesize_one(tts_ref, ref)
            if audio:
                ref_audios.append((ref, audio))
                print(f"    #{i}  ok ({len(audio)} bytes, {dt:.2f}s)")
            else:
                print(f"    #{i}  skip: empty audio")
        except Exception as e:
            print(f"    #{i}  skip: {e}")

    for asr_model in settings.AVAILABLE_ASR_MODELS:
        consec_fail = 0
        for i, (ref, audio) in enumerate(ref_audios, 1):
            if consec_fail >= 2:
                print(f"  [{asr_model}] 已连续失败，跳过剩下 {len(ref_audios)-i+1} 条样本。")
                break
            blk = _budget_check(asr_model)
            if blk:
                print(f"  [{asr_model}] 预算耗尽，跳过：{blk}")
                break
            row = {
                "asr_model": asr_model,
                "idx": i,
                "reference": ref,
                "hypothesis": "",
                "latency_s": None,
                "cer": None,
                "error": "",
            }
            try:
                _budget_inc(asr_model)
                hyp, dt = await _recognize_one(asr_model, audio)
                row["hypothesis"] = hyp
                row["latency_s"] = round(dt, 3)
                row["cer"] = round(char_error_rate(ref, hyp), 4)
                print(f"  [{asr_model}] #{i}  {dt:.2f}s  CER={row['cer']:.3f}  hyp={hyp[:30]}")
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
                print(f"  [{asr_model}] #{i}  ERROR: {row['error']}")
            if row["error"]:
                consec_fail += 1
            else:
                consec_fail = 0
            rows.append(row)
    return rows


# =============================================================================
#  LLM 基准
# =============================================================================
async def bench_llm(limit: int | None) -> list[dict]:
    rows: list[dict] = []
    cases = LLM_TEST_CASES if not limit else LLM_TEST_CASES[:limit]
    print(f"\n=== [LLM 基准] 共 {len(settings.AVAILABLE_LLM_MODELS)} 个模型 × {len(cases)} 题 ===\n")

    for llm_model in settings.AVAILABLE_LLM_MODELS:
        consec_fail = 0
        for c in cases:
            if consec_fail >= 2:
                print(f"  [{llm_model}] 已连续失败，跳过剩下题目。")
                break
            blk = _budget_check(llm_model)
            if blk:
                print(f"  [{llm_model}] 预算耗尽，跳过：{blk}")
                break
            row = {
                "llm_model": llm_model,
                "case_id": c["id"],
                "category": c["category"],
                "prompt": c["prompt"],
                "answer": "",
                "answer_len": 0,
                "latency_s": None,
                "correct": False,
                "error": "",
            }
            try:
                _budget_inc(llm_model)
                t0 = time.perf_counter()
                ans = await llm_service.chat(
                    [{"role": "user", "content": c["prompt"]}],
                    model=llm_model,
                )
                dt = time.perf_counter() - t0
                ans = (ans or "").strip()
                row["answer"] = ans
                row["answer_len"] = len(ans)
                row["latency_s"] = round(dt, 3)
                row["correct"] = evaluate_llm_answer(c, ans)
                mark = "√" if row["correct"] else "×"
                print(f"  [{llm_model}] {c['id']:<14}{dt:6.2f}s  {mark}  {ans[:50].replace(chr(10),' ')}")
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
                print(f"  [{llm_model}] {c['id']:<14}ERROR: {row['error']}")
            if row["error"]:
                consec_fail += 1
            else:
                consec_fail = 0
            rows.append(row)
    return rows


# =============================================================================
#  汇总与导出
# =============================================================================
def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"[saved] {path}  ({len(rows)} rows)")


def _agg_by(rows: list[dict], key: str, metric_fn: Callable[[list[dict]], dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    out = []
    for k, items in groups.items():
        d = {key: k, "n": len(items)}
        d.update(metric_fn(items))
        out.append(d)
    return out


def _avg(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(mean(vals), 4) if vals else None


def summarize_tts(rows: list[dict]) -> list[dict]:
    def metric(items):
        ok = [r for r in items if r["cer"] is not None]
        return {
            "成功条数": len(ok),
            "平均CER(字错率)": _avg([r["cer"] for r in ok]),
            "平均TTS延迟(s)": _avg([r["tts_latency_s"] for r in items]),
            "平均音频大小(KB)": _avg([r["audio_bytes"] / 1024 for r in items if r["audio_bytes"]]),
            "失败数": sum(1 for r in items if r["error"]),
        }
    return _agg_by(rows, "tts_model", metric)


def summarize_asr(rows: list[dict]) -> list[dict]:
    def metric(items):
        ok = [r for r in items if r["cer"] is not None]
        return {
            "成功条数": len(ok),
            "平均CER(字错率)": _avg([r["cer"] for r in ok]),
            "识别准确率": round(1 - _avg([r["cer"] for r in ok]), 4) if ok else None,
            "平均延迟(s)": _avg([r["latency_s"] for r in items]),
            "失败数": sum(1 for r in items if r["error"]),
        }
    return _agg_by(rows, "asr_model", metric)


def summarize_llm(rows: list[dict]) -> list[dict]:
    def metric(items):
        ok = [r for r in items if not r["error"]]
        correct = sum(1 for r in ok if r["correct"])
        return {
            "作答数": len(ok),
            "正确数": correct,
            "正确率": round(correct / len(ok), 4) if ok else None,
            "平均字数": _avg([r["answer_len"] for r in ok]),
            "平均延迟(s)": _avg([r["latency_s"] for r in ok]),
            "失败数": sum(1 for r in items if r["error"]),
        }
    return _agg_by(rows, "llm_model", metric)


def _md_table(rows: list[dict], title: str) -> str:
    if not rows:
        return f"### {title}\n\n(无数据)\n"
    cols = list(rows[0].keys())
    lines = [f"### {title}", "", "| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(
            ("" if r[c] is None else str(r[c])) for c in cols
        ) + " |")
    return "\n".join(lines) + "\n"


def write_summary(tts_rows, asr_rows, llm_rows) -> Path:
    md_path = RESULTS_DIR / "summary.md"
    parts = ["# 语音助理系统 · 模型性能对比报告",
             "",
             f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             "",
             "> **指标说明**",
             "> - CER（Character Error Rate，字错率）= Levenshtein 编辑距离 / 参考文本长度，越低越好。",
             "> - 识别准确率 = 1 - CER。",
             "> - TTS 朗读错词率 = 各 TTS 合成 → 最强 ASR 回识别 → 与原文对照的 CER。",
             "> - LLM 正确率 = 自动判分规则（关键词/正则）命中题数 / 作答题数。",
             ""]

    if tts_rows:
        parts.append(_md_table(summarize_tts(tts_rows), "一、TTS 朗读错词率对比"))
    if asr_rows:
        parts.append(_md_table(summarize_asr(asr_rows), "二、ASR 识别准确率对比"))
    if llm_rows:
        parts.append(_md_table(summarize_llm(llm_rows), "三、LLM 回复质量对比"))

    md_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"[saved] {md_path}")
    return md_path


# =============================================================================
#  入口
# =============================================================================
async def main():
    parser = argparse.ArgumentParser(description="语音助理真实性能基准")
    parser.add_argument("--only", choices=["tts", "asr", "llm"], default=None)
    parser.add_argument("--limit", type=int, default=3,
                        help="每个模型只跑前 N 条（默认 3，控制预算）")
    args = parser.parse_args()

    print(f"[budget] 全局上限 {GLOBAL_CALL_BUDGET} 次调用，单模型上限 {PER_MODEL_BUDGET} 次")
    print(f"[budget] limit={args.limit}, only={args.only or 'all'}")

    tts_rows: list[dict] = []
    asr_rows: list[dict] = []
    llm_rows: list[dict] = []

    try:
        if args.only in (None, "tts"):
            tts_rows = await bench_tts(args.limit)
            _write_csv(RESULTS_DIR / "tts_results.csv", tts_rows)

        if args.only in (None, "asr"):
            asr_rows = await bench_asr(args.limit)
            _write_csv(RESULTS_DIR / "asr_results.csv", asr_rows)

        if args.only in (None, "llm"):
            llm_rows = await bench_llm(args.limit)
            _write_csv(RESULTS_DIR / "llm_results.csv", llm_rows)
    except Exception:
        traceback.print_exc()

    # 汇总报告
    write_summary(tts_rows, asr_rows, llm_rows)

    # 控制台打印汇总
    print("\n" + "=" * 70)
    print(" 汇总")
    print("=" * 70)
    if tts_rows:
        print("\n[TTS] 朗读错词率：")
        for r in summarize_tts(tts_rows):
            print(f"  {r['tts_model']:<40}  CER={r['平均CER(字错率)']}  "
                  f"延迟={r['平均TTS延迟(s)']}s  失败={r['失败数']}")
    if asr_rows:
        print("\n[ASR] 识别准确率：")
        for r in summarize_asr(asr_rows):
            print(f"  {r['asr_model']:<40}  CER={r['平均CER(字错率)']}  "
                  f"准确率={r['识别准确率']}  延迟={r['平均延迟(s)']}s  失败={r['失败数']}")
    if llm_rows:
        print("\n[LLM] 回复质量：")
        for r in summarize_llm(llm_rows):
            print(f"  {r['llm_model']:<40}  正确率={r['正确率']}  "
                  f"均字数={r['平均字数']}  延迟={r['平均延迟(s)']}s  失败={r['失败数']}")
    print("")
    print("=" * 70)
    print(f" 预算使用情况: {_budget_summary()}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
