import time
import json
import logging
from collections import Counter

from config import setup_logging, AI_MODEL, OLLAMA_URL
from reporter import generate_summary_text

logger = setup_logging("ai_analyzer")


def analyze_results(results, model=None, ollama_url=None):
    if model is None:
        model = AI_MODEL
    if ollama_url is None:
        ollama_url = OLLAMA_URL

    if not results:
        return "No results to analyze."

    try:
        from ollama import Client
    except ImportError:
        logger.warning("ollama Python client not installed. Install with: pip install ollama")
        return _fallback_analysis(results)

    summary_text = generate_summary_text(results)
    error_files = [r for r in results if r["status"] == "error"]
    warning_files = [r for r in results if r["status"] == "warning"]

    detail_sample = []
    for r in (error_files + warning_files)[:50]:
        detail_sample.append({
            "path": r["path"],
            "status": r["status"],
            "issues": [{"type": i["type"], "message": i["message"], "severity": i["severity"]} for i in r.get("issues", [])],
            "size": r["size"],
            "category": r["category"],
        })

    prompt = f"""You are a document health analysis expert. Analyze the following document health check results and provide:

1. OVERALL HEALTH ASSESSMENT - A brief summary of the overall document health
2. MOST COMMON ISSUES - What are the most frequent problems found
3. RECOMMENDED ACTIONS - What should be done to fix the issues
4. PRIORITY FILES - Which files need immediate attention

SUMMARY STATISTICS:
{summary_text}

DETAILED ISSUES (up to 50 worst files):
{json.dumps(detail_sample, indent=2, default=str)}

Provide a concise but thorough analysis focused on actionable insights."""

    try:
        client = Client(host=ollama_url)
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 4096},
        )
        analysis = response.get("message", {}).get("content", "")
        if not analysis:
            raise ValueError("Empty response from Ollama")
        logger.info("AI analysis completed successfully")
        time.sleep(1)
        return analysis
    except Exception as e:
        logger.warning("Ollama AI analysis failed: %s. Using fallback analysis.", e)
        return _fallback_analysis(results)


def _fallback_analysis(results):
    total = len(results)
    status_counts = Counter(r["status"] for r in results)
    all_issues = [i for r in results for i in r.get("issues", [])]
    issue_type_counts = Counter(i["type"] for i in all_issues)
    error_files = [r for r in results if r["status"] == "error"]

    lines = []
    lines.append("FALLBACK ANALYSIS (Ollama unavailable)")
    lines.append("=" * 60)
    lines.append("")
    ok_rate = status_counts.get("ok", 0) / total * 100 if total > 0 else 0
    if ok_rate >= 95:
        health = "Excellent"
    elif ok_rate >= 80:
        health = "Good"
    elif ok_rate >= 60:
        health = "Fair"
    else:
        health = "Poor"

    lines.append(f"Overall Health Assessment: {health}")
    lines.append(f"Health rate: {ok_rate:.1f}% ({status_counts.get('ok', 0)}/{total} files OK)")
    lines.append("")
    lines.append("Most Common Issues:")
    for issue_type, cnt in issue_type_counts.most_common(10):
        lines.append(f"  - {issue_type}: {cnt} occurrences")
    lines.append("")
    lines.append("Recommended Actions:")
    if status_counts.get("error", 0) > 0:
        lines.append(f"  - Investigate and fix {status_counts['error']} error files (highest priority)")
    if status_counts.get("warning", 0) > 0:
        lines.append(f"  - Review {status_counts['warning']} warning files")
    if ok_rate < 80:
        lines.append("  - Consider bulk re-encoding or file recovery for problematic files")
    if any(i["type"] == "corrupt_pdf" for i in all_issues):
        lines.append("  - Repair or regenerate corrupt PDF files")
    if any(i["type"] == "encoding_detection_failed" for i in all_issues):
        lines.append("  - Fix file encoding issues in text files")
    lines.append("")
    lines.append("Priority Files:")
    for r in error_files[:20]:
        issues_str = "; ".join(i["type"] for i in r.get("issues", [])[:3])
        lines.append(f"  - {r['path']} ({issues_str})")

    return "\n".join(lines)


def generate_report_html(results, ai_analysis):
    total = len(results)
    status_counts = Counter(r["status"] for r in results)
    category_counts = Counter(r["category"] for r in results)
    all_issues = [i for r in results for i in r.get("issues", [])]
    issue_type_counts = Counter(i["type"] for i in all_issues)

    error_count = status_counts.get("error", 0)
    warning_count = status_counts.get("warning", 0)
    ok_count = status_counts.get("ok", 0)

    status_rows = ""
    for r in results[:500]:
        issue_msgs = "<br>".join(i.get("message", "") for i in r.get("issues", [])[:5])
        status_class = r["status"]
        status_rows += f"""
        <tr class="{status_class}">
            <td title="{r['path']}">{r['name']}</td>
            <td>{r['ext']}</td>
            <td>{r['category']}</td>
            <td><span class="badge badge-{status_class}">{r['status']}</span></td>
            <td>{issue_msgs}</td>
        </tr>"""

    cat_rows = ""
    for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100 if total > 0 else 0
        cat_rows += f"""
        <tr>
            <td>{cat}</td>
            <td>{cnt}</td>
            <td><div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div></td>
        </tr>"""

    issue_rows = ""
    for itype, cnt in issue_type_counts.most_common(20):
        issue_rows += f"""
        <tr>
            <td>{itype}</td>
            <td>{cnt}</td>
        </tr>"""

    ai_safe = ai_analysis.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>") if ai_analysis else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Document Health Check Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ color: #1a1a2e; margin-bottom: 5px; }}
h2 {{ color: #16213e; margin: 20px 0 10px; padding-bottom: 5px; border-bottom: 2px solid #e0e0e0; }}
.subtitle {{ color: #666; margin-bottom: 20px; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px; }}
.stat-card {{ background: white; border-radius: 8px; padding: 15px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.stat-card .number {{ font-size: 2em; font-weight: bold; }}
.stat-card .label {{ color: #666; font-size: 0.9em; margin-top: 5px; }}
.stat-card.ok .number {{ color: #28a745; }}
.stat-card.warning .number {{ color: #ffc107; }}
.stat-card.error .number {{ color: #dc3545; }}
table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 0.9em; }}
th {{ background: #1a1a2e; color: white; font-weight: 600; }}
tr:hover {{ background: #f8f9fa; }}
tr.error td {{ background: #fff5f5; }}
tr.warning td {{ background: #fffef5; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; }}
.badge-ok {{ background: #d4edda; color: #155724; }}
.badge-warning {{ background: #fff3cd; color: #856404; }}
.badge-error {{ background: #f8d7da; color: #721c24; }}
.bar {{ background: #e9ecef; border-radius: 4px; height: 16px; overflow: hidden; }}
.bar-fill {{ background: #007bff; height: 100%; border-radius: 4px; }}
.ai-section {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
.ai-section h3 {{ color: #1a1a2e; margin-bottom: 10px; }}
.ai-section pre {{ white-space: pre-wrap; font-family: inherit; line-height: 1.6; color: #333; }}
.section {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
</style>
</head>
<body>
<div class="container">
    <h1>Document Health Check Report</h1>
    <p class="subtitle">Generated on {time.strftime("%Y-%m-%d %H:%M:%S")} | {total} files scanned</p>

    <div class="stats">
        <div class="stat-card ok">
            <div class="number">{ok_count}</div>
            <div class="label">OK</div>
        </div>
        <div class="stat-card warning">
            <div class="number">{warning_count}</div>
            <div class="label">Warnings</div>
        </div>
        <div class="stat-card error">
            <div class="number">{error_count}</div>
            <div class="label">Errors</div>
        </div>
        <div class="stat-card">
            <div class="number">{total}</div>
            <div class="label">Total Files</div>
        </div>
    </div>

    <div class="ai-section">
        <h3>AI Analysis</h3>
        <pre>{ai_safe}</pre>
    </div>

    <h2>Files by Category</h2>
    <div class="section">
        <table>
            <tr><th>Category</th><th>Count</th><th>Distribution</th></tr>
            {cat_rows}
        </table>
    </div>

    <h2>Most Common Issues</h2>
    <div class="section">
        <table>
            <tr><th>Issue Type</th><th>Count</th></tr>
            {issue_rows}
        </table>
    </div>

    <h2>All Files (up to 500 shown)</h2>
    <div class="section">
        <table>
            <tr><th>Name</th><th>Ext</th><th>Category</th><th>Status</th><th>Issues</th></tr>
            {status_rows}
        </table>
    </div>
</div>
</body>
</html>"""

    return html
