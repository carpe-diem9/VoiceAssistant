"""
\u5355\u72ec\u91cd\u8dd1 gemini-2.5-flash-preview-tts \uff08\u4fee\u590d voice \u6620\u5c04\u540e\uff09\u3002

\u8c03\u7528\u91cf\uff1a3 \u6b21 gemini-tts + 3 \u6b21 qwen3-asr-flash \u56de\u8bc6\u522b = 6 \u6b21\u3002
\u7ed3\u679c\u4f1a\u8986\u76d6 tts_results.csv \u4e2d\u539f\u6709\u7684 gemini \u884c\u3002
"""
from __future__ import annotations

import sys
import csv
import asyncio
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# \u5f3a\u5236 stdout/stderr UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from benchmark.run_benchmark import (  # noqa: E402
    _synthesize_one, _recognize_one, _capture, RESULTS_DIR,
    _write_csv,
)
from benchmark.datasets import REFERENCE_SENTENCES  # noqa: E402
from benchmark.scoring import char_error_rate  # noqa: E402

GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
ASR_JUDGE = "qwen3-asr-flash"
LIMIT = 3


async def main():
    sents = REFERENCE_SENTENCES[:LIMIT]
    new_rows: list[dict] = []

    print(f"=== \u91cd\u6d4b {GEMINI_MODEL}\uff083 \u53e5\uff09===")
    for i, ref in enumerate(sents, 1):
        row = {
            "tts_model": GEMINI_MODEL,
            "idx": i, "reference": ref,
            "audio_bytes": 0,
            "tts_latency_s": None, "asr_latency_s": None,
            "hypothesis": "",
            "cer": None, "fallback": False, "error": "",
        }
        try:
            _capture.reset()
            audio, tts_dt = await _synthesize_one(GEMINI_MODEL, ref)
            row["audio_bytes"] = len(audio)
            row["tts_latency_s"] = round(tts_dt, 3)

            if _capture.has_fallback():
                row["error"] = "fallback to dashscope"
                row["fallback"] = True
                print(f"  #{i}  \u9759\u9ed8\u56de\u9000 dashscope\uff08\u4ecd\u672a\u4fee\u590d\uff09")
            elif not audio:
                row["error"] = "empty audio"
                print(f"  #{i}  \u7a7a\u97f3\u9891")
            else:
                hyp, asr_dt = await _recognize_one(ASR_JUDGE, audio)
                row["hypothesis"] = hyp
                row["asr_latency_s"] = round(asr_dt, 3)
                row["cer"] = round(char_error_rate(ref, hyp), 4)
                print(f"  #{i}  TTS={tts_dt:.2f}s  ASR={asr_dt:.2f}s  "
                      f"CER={row['cer']}  hyp={hyp[:40]}")
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"  #{i}  \u5931\u8d25\uff1a{row['error']}")
        new_rows.append(row)

    # \u8bfb\u53d6\u539f csv\uff0c\u5254\u9664 gemini \u884c\uff0c\u62fc\u4e0a\u65b0 rows
    csv_path = RESULTS_DIR / "tts_results.csv"
    keep: list[dict] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("tts_model") != GEMINI_MODEL:
                    keep.append(r)
    keep.extend(new_rows)
    _write_csv(csv_path, keep)
    print(f"\n[saved] {csv_path}  (\u5408\u5e76\u540e {len(keep)} \u884c)")


if __name__ == "__main__":
    asyncio.run(main())
