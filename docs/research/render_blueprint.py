from pathlib import Path
import re, json
import markdown
base = Path(__file__).resolve().parent
md = (base / "momentum-blueprint.md").read_text(encoding="utf-8")
refs = set(re.findall(r"\[\^(\d+)\](?!:)", md))
defs = re.findall(r"^\[\^(\d+)\]:", md, re.M)
assert refs == set(defs), f"Citation mismatch: unused={set(defs)-refs}, missing={refs-set(defs)}"
assert len(defs) == len(set(defs))
converter = markdown.Markdown(extensions=["tables", "footnotes", "toc", "fenced_code"], extension_configs={"toc": {"toc_depth": "2"}})
body = converter.convert(md)
style = """
:root{color-scheme:light;--ink:#1d232a;--muted:#555d66;--line:#d7dce1}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#fff;color:var(--ink);font:17px/1.65 Georgia,"Times New Roman",serif}
main{max-width:1060px;margin:0 auto;padding:54px 38px 90px}h1,h2,h3,nav,table{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
h1{font-size:38px;line-height:1.16;font-weight:650;letter-spacing:-1px;margin:0 0 34px}
h2{font-size:24px;line-height:1.3;font-weight:650;margin:52px 0 18px;padding-top:18px;border-top:1px solid var(--line);scroll-margin-top:16px}
h3{font-size:19px;line-height:1.35;margin:30px 0 12px}p{margin:0 0 18px}a{color:#245274;text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}
li{margin:8px 0}table{width:100%;border-collapse:collapse;margin:24px 0 28px;font-size:13px;line-height:1.5}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:12px 10px}th{background:#f0f2f4;font-weight:650}
td:first-child{font-weight:600}code{font-family:Consolas,monospace;font-size:.87em}pre{overflow:auto;white-space:pre-wrap;border:1px solid var(--line);padding:15px}
nav{font-size:14px;color:var(--muted);margin:0 0 32px;padding:20px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
nav ul{list-style:none;padding:0;margin:0;columns:2;column-gap:35px}nav li{margin:0 0 7px;break-inside:avoid}nav a{color:var(--ink);text-decoration:none}nav a:hover{text-decoration:underline}
.footnote{font-size:13px;line-height:1.6}.footnote li{margin-bottom:14px}.footnote-ref{font:11px system-ui;text-decoration:none}.footnote-backref{padding-left:6px}
@media(max-width:700px){main{padding:30px 18px 60px}h1{font-size:30px}h2{font-size:22px}nav ul{columns:1}table{display:block;overflow-x:auto;font-size:12px}th,td{min-width:145px}body{font-size:16px}}
@page{size:A4;margin:17mm 15mm}
@media print{main{padding:0;max-width:none}body{font-size:10.5pt;line-height:1.5}h1{font-size:25pt}h2{font-size:15pt;margin-top:25px;break-after:avoid}h3{font-size:12pt;break-after:avoid}table{font-size:8.2pt;display:table}tr{break-inside:avoid}th{background:#eee!important;print-color-adjust:exact}nav{display:none}a{color:inherit}.footnote{font-size:8pt}.footnote-backref{display:none}}
"""
h1 = re.search(r"<h1[^>]*>.*?</h1>", body, re.S)
assert h1
body = body[:h1.end()] + '<nav aria-label="Report contents">' + converter.toc + "</nav>" + body[h1.end():]
output = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Momentum investing and trading blueprint</title><style>' + style + "</style></head><body><main>" + body + "</main></body></html>"
dest = base / "momentum-blueprint.html"
dest.write_text(output, encoding="utf-8")
check = {"markdown_words":len(md.split()),"footnote_count":len(defs),"headings":len(re.findall(r"^## ",md,re.M)),"html_bytes":dest.stat().st_size,"external_scripts":len(re.findall(r"<script",output)),"missing_html_footnotes":[i for i in refs if f'id="fn:{i}"' not in output]}
assert not check["missing_html_footnotes"]
assert abs((40 * 1.18)/2000 * 100 - 2.36) < 1e-12
assert abs(3*(8000*.075/1e6+1000*.30/1e6)+(8000*.15/1e6+1000*.60/1e6)-.0045)<1e-12
print(json.dumps(check))
