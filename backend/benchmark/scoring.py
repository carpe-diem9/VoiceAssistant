"""
评分/相似度工具函数：CER、文本规范化、关键词判分。
"""
import re
import unicodedata


# 去掉所有空白与常见中英文标点
_PUNCT_RE = re.compile(
    r"[\s，。！？：；、,.!?:;'\"“”‘’（）()《》<>\-—~`·…【】\[\]{}|/\\*%$#@]+"
)


def normalize_text(text: str) -> str:
    """文本规范化：NFKC + 小写 + 去标点与空白"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    t = _PUNCT_RE.sub("", t)
    return t


def levenshtein(a: str, b: str) -> int:
    """经典 Levenshtein 编辑距离（O(len(a)*len(b))）"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(
                cur[j - 1] + 1,         # insertion
                prev[j] + 1,            # deletion
                prev[j - 1] + cost,     # substitution
            )
        prev = cur
    return prev[-1]


def char_error_rate(reference: str, hypothesis: str) -> float:
    """
    Character Error Rate (CER) = 编辑距离 / 参考串长度
    中文场景下直接按字符计算更直观。
    """
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    d = levenshtein(ref, hyp)
    return d / max(1, len(ref))


def evaluate_llm_answer(case: dict, answer: str) -> bool:
    """根据数据集中的判分规则评估 LLM 回答是否正确。"""
    if not answer:
        return False
    text = answer.strip()
    lower = text.lower()

    if "expect_regex" in case:
        if re.search(case["expect_regex"], text, flags=re.IGNORECASE):
            return True

    if "expect_all" in case:
        if all(kw.lower() in lower for kw in case["expect_all"]):
            return True
        # 若有 regex 已命中则直接通过；否则未全部命中就 False
        if "expect_regex" not in case:
            return False

    if "expect_keywords" in case:
        if any(kw.lower() in lower for kw in case["expect_keywords"]):
            return True

    # 规则都存在但都没命中
    if "expect_regex" in case or "expect_keywords" in case or "expect_all" in case:
        return False

    # 没有规则时默认算通过
    return True
