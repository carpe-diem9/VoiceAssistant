"""
\u5c06 results/ \u4e0b\u7684\u4e09\u4efd csv \u6c47\u603b\u4e3a\u4e00\u4efd\u5b8c\u6574\u7684 summary.md\uff0c\u907f\u514d\u5355\u8dd1\u67d0\u4e2a\u5b50\u9879\u540e\u8986\u76d6\u3002
"""
import csv
import time
import argparse
from pathlib import Path
from benchmark.run_benchmark import (
    summarize_tts, summarize_asr, summarize_llm, _md_table,
    RESULTS_DIR,
)


def _read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            # \u6570\u503c\u5b57\u6bb5\u8f6c\u56de float/int/bool
            for k, v in list(r.items()):
                if v == "":
                    r[k] = None if k in ("cer", "tts_latency_s", "asr_latency_s", "latency_s", "audio_bytes", "answer_len") else ""
                elif k in ("cer", "tts_latency_s", "asr_latency_s", "latency_s"):
                    try:
                        r[k] = float(v)
                    except ValueError:
                        r[k] = None
                elif k in ("audio_bytes", "idx", "answer_len"):
                    try:
                        r[k] = int(v)
                    except ValueError:
                        r[k] = 0
                elif k in ("fallback", "correct"):
                    r[k] = (v.lower() == "true")
            rows.append(r)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asr-skip-idx", type=str, default="",
                        help="剔除的 ASR idx列表，逗号分隔。例：--asr-skip-idx 1")
    args = parser.parse_args()

    skip_idx: set[int] = set()
    if args.asr_skip_idx:
        for s in args.asr_skip_idx.split(","):
            s = s.strip()
            if s.isdigit():
                skip_idx.add(int(s))

    tts_rows = _read_csv(RESULTS_DIR / "tts_results.csv")
    asr_rows_all = _read_csv(RESULTS_DIR / "asr_results.csv")
    llm_rows = _read_csv(RESULTS_DIR / "llm_results.csv")

    asr_rows = [r for r in asr_rows_all if r.get("idx") not in skip_idx]
    skipped_n = len(asr_rows_all) - len(asr_rows)

    parts = [
        "# 语音助理系统 · 模型性能对比报告",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "> **指标说明**",
        "> - CER（Character Error Rate，字错率）= Levenshtein 编辑距离 / 参考文本长度，越低越好。",
        "> - 识别准确率 = 1 - CER。",
        "> - TTS 朗读错词率 = 各 TTS 合成 → 最强 ASR 回识别 → 与原文对照的 CER。",
        "> - LLM 正确率 = 自动判分规则（关键词/正则）命中题数 / 作答题数。",
        "",
    ]
    if skip_idx:
        parts.append(
            f"> **ASR 过滤**：已剔除 idx 为 {sorted(skip_idx)} 的异常样本"
            f"（共 {skipped_n} 行）。原因：该样本 TTS 合成音频开头带静默/呼吸帧，被三个 ASR 模型一致漏识。"
        )
        parts.append("")

    if tts_rows:
        parts.append(_md_table(summarize_tts(tts_rows), "\u4e00\u3001TTS \u6717\u8bfb\u9519\u8bcd\u7387\u5bf9\u6bd4"))
    if asr_rows:
        parts.append(_md_table(summarize_asr(asr_rows), "\u4e8c\u3001ASR \u8bc6\u522b\u51c6\u786e\u7387\u5bf9\u6bd4"))
    if llm_rows:
        parts.append(_md_table(summarize_llm(llm_rows), "\u4e09\u3001LLM \u56de\u590d\u8d28\u91cf\u5bf9\u6bd4"))

    (RESULTS_DIR / "summary.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"[saved] {RESULTS_DIR / 'summary.md'}")


if __name__ == "__main__":
    main()
