"""
性能基准测试数据集。
包含 TTS/ASR 测试用中文参考句，以及 LLM 评测题目及其判分规则。
"""

# ----- ASR / TTS 参考句（中文，含数字、专名、多音字、长短混合） -----
# 用于 ASR：先用稳定 TTS 合成 -> 各 ASR 模型识别 -> 对照 reference 计算 CER
# 用于 TTS：各 TTS 模型合成 -> 用最强 ASR 回识别 -> 对照 reference 计算 CER
REFERENCE_SENTENCES = [
    "你好，请帮我查一下今天北京的天气预报。",
    "人工智能正在深刻地改变我们的工作和生活方式。",
    "今年第三季度的销售额同比增长了百分之二十三点五。",
    "请在下午三点半之前把会议纪要发送到我的邮箱。",
    "这部电影的导演是张艺谋，主演是巩俐和葛优。",
    "长江是中国第一长河，全长约六千三百公里。",
    "明天早上七点四十五分从上海虹桥站出发去杭州。",
    "中华人民共和国成立于一九四九年十月一日。",
    "请帮我把这段文字翻译成英文并校对一下语法。",
    "微信支付和支付宝已经成为中国最主要的移动支付方式。",
]


# ----- LLM 评测题目 -----
# 每题包含：id, category, prompt, 以及判分规则
#   expect_keywords: 命中任一即判定答对（用于常识/事实题）
#   expect_all:      必须全部出现（用于指令遵循，严格）
#   expect_regex:    正则命中（用于数学/代码格式）
LLM_TEST_CASES = [
    {
        "id": "qa_capital",
        "category": "常识问答",
        "prompt": "中国的首都是哪里？请直接给出城市名。",
        "expect_keywords": ["北京"],
    },
    {
        "id": "qa_science",
        "category": "常识问答",
        "prompt": "水的化学分子式是什么？只回答分子式。",
        "expect_keywords": ["H2O", "H₂O", "H2o"],
    },
    {
        "id": "math_arith",
        "category": "数学计算",
        "prompt": "计算 128 × 37 等于多少？只输出数字结果。",
        # 128*37 = 4736
        "expect_regex": r"\b4736\b",
    },
    # 数学应用题（math_word）已从测试集中移除：
    # qwen3.5-plus 在该题上会触发深度思考模式，单题耗时过长（>1000s）且占用较多 token。
    {
        "id": "reason_logic",
        "category": "逻辑推理",
        "prompt": (
            "如果所有的 A 都是 B，所有的 B 都是 C，那么所有的 A 是不是都是 C？"
            "请回答“是”或“否”，并一句话说明理由。"
        ),
        "expect_keywords": ["是", "正确", "成立", "传递"],
    },
    {
        "id": "instr_format",
        "category": "指令遵循",
        "prompt": "请用严格的 JSON 格式输出一个联系人对象，字段为 name、age、city，示例值自拟，不要输出任何额外文字。",
        # 要求含 JSON 大括号与三个字段名
        "expect_all": ["{", "}", "name", "age", "city"],
    },
    {
        "id": "code_python",
        "category": "代码生成",
        "prompt": "用 Python 写一个函数 is_prime(n) 判断整数是否为质数，只输出代码，不要解释。",
        "expect_all": ["def", "is_prime", "return"],
    },
    {
        "id": "cn_knowledge",
        "category": "中文知识",
        "prompt": "《红楼梦》的作者是谁？只回答人名。",
        "expect_keywords": ["曹雪芹"],
    },
]
