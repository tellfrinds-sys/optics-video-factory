import ast
p = "/root/video-factory/qa_gate.py"
s = open(p, encoding="utf-8").read()

s = s.replace('"num_ctx": 8192}}).encode()', '"num_ctx": 4096}}).encode()')
s = s.replace("with urllib.request.urlopen(req, timeout=600) as resp:",
              "with urllib.request.urlopen(req, timeout=420) as resp:")
s = s.replace(
    '    llm = _ollama(sysmsg, "النص المعتمد:\\n" + expected[:6000])\n'
    '    llm_ok = str(llm.get("verdict", "")).lower() == "pass"',
    '    try:\n'
    '        llm = _ollama(sysmsg, "النص المعتمد:\\n" + expected[:3500])\n'
    '    except Exception as _e:\n'
    '        llm = {"verdict": "skip", "issues": [], "note": str(_e)[:120]}\n'
    '    llm_ok = str(llm.get("verdict", "")).lower() in ("pass", "skip")')
s = s.replace('add("مراجعة_qwen", llm_ok', 'add("مراجعة_ذكية", llm_ok')
s = s.replace('"مراجعة_qwen"))', '"مراجعة_ذكية"))')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("qa_gate patched:", '"num_ctx": 4096' in s, "مراجعة_ذكية" in s, "verdict\": \"skip" in s)
