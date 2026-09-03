#!/usr/bin/env python3
"""fable-skills benchmark harness.

Runs solver models with and without skills through headless Claude Code
(`claude -p`), blind-grades every run against a fixed answer key, and compiles
the results. Standard library only. Needs the `claude` CLI installed and logged
in; no API key.

  python benchmark/harness.py init-legacy --suite b3     # task.json for the four Benchmark 1/2 areas
  python benchmark/harness.py tasks  --suite b3
  python benchmark/harness.py run    --suite b3 --areas debugging --models haiku,sonnet,opus --conditions bare,skills --n 5
  python benchmark/harness.py grade  --suite b3 --judge opus
  python benchmark/harness.py report --suite b3
  python benchmark/harness.py status --suite b3

Design choices that keep the measurement honest:
- Every solver runs with `--disable-slash-commands`, so the model has no skills
  available except the ones the harness puts in front of it. Without that flag a
  logged-in Claude Code session may already have this library installed.
- Solvers get no tools. Both conditions see the same prompt; the with-skills
  condition additionally gets the task's skill files appended to the system
  prompt (or prefixed to the prompt when the bundle is too long for argv).
- The judge sees one candidate at a time with model names redacted, never the
  condition, and returns one true/false per answer-key item with a citation.
- Every run and grade writes a JSON sidecar with the canonical model id, cost,
  tokens and timing so a result can be audited.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean, pstdev

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
CLAUDE = os.environ.get("CLAUDE_CODE_EXECPATH") or shutil.which("claude") or "claude"
NO_TOOLS = ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "Read", "Glob", "Grep", "LS", "WebFetch",
            "WebSearch", "Agent", "Task", "Skill", "ToolSearch", "TodoWrite", "Artifact"]
REDACT = re.compile(r"\b(claude|sonnet|opus|haiku|fable|anthropic|openai|gpt-?[0-9.]*|gemini|codex)\b", re.I)
RATE_WORDS = ("rate limit", "usage limit", "session limit", "429", "overloaded", "try again later", "capacity",
              "limit reached", "hit your")
MODEL_ORDER = ["haiku", "sonnet", "opus", "fable"]
COND_ORDER = ["bare", "skills"]
LEGACY = {
    "debugging": ("Stale config cache: root cause", "root-cause-debugging"),
    "concurrency": ("Racy rate limiter review", "concurrency-reasoning"),
    "edge-numerical": ("CSV revenue aggregator edge cases", "edge-case-sweep"),
    "security": ("Orders module security review", "security-reflexes"),
}
_lock = threading.Lock()
for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252, which cannot print the report
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def say(msg):
    with _lock:
        print(msg, flush=True)


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def strip_provenance(text):
    """Drop a leading <!-- provenance --> comment and the --- separator the recovered files carry."""
    text = text.lstrip()
    if text.startswith("<!--"):
        end = text.find("-->")
        if end != -1:
            text = text[end + 3:].lstrip()
        if text.startswith("---"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
    return text.strip() + "\n"


def load_tasks(suite_dir, areas=None):
    tasks = {}
    for tj in sorted((suite_dir / "tasks").glob("*/task.json")):
        t = json.loads(tj.read_text(encoding="utf-8"))
        area = t.get("area") or tj.parent.name
        if areas and area not in areas:
            continue
        base = tj.parent
        t["area"] = area
        t["_dir"] = base
        t["prompt"] = strip_provenance((base / t["prompt_file"]).read_text(encoding="utf-8"))
        t["key"] = strip_provenance((base / t["answer_key_file"]).read_text(encoding="utf-8"))
        t["item_ids"] = [i["id"] for i in t["items"]]
        t["max_score"] = t.get("max_score") or len(t["item_ids"])
        tasks[area] = t
    if areas:
        missing = [a for a in areas if a not in tasks]
        if missing:
            sys.exit(f"unknown areas (no tasks/<area>/task.json): {missing}")
    return tasks


def skills_bundle(skill_names, skills_dir):
    # Mirrors what happens when Claude Code activates a skill: the whole file lands in context as
    # instructions to follow for the task at hand, not as optional reference material.
    parts = ["# Activated engineering-discipline skills", "",
             "The following skills have been activated for this task. Follow their instructions as you work; "
             "where they ask for a step, an order of operations, or a reporting requirement, do it.", ""]
    for name in skill_names:
        p = skills_dir / name / "SKILL.md"
        if not p.exists():
            sys.exit(f"skill not found: {p}")
        parts += ["---", f"## Skill: {name}", "", p.read_text(encoding="utf-8").strip(), ""]
    return "\n".join(parts)


def child_env():
    env = dict(os.environ)
    for k in ("CLAUDECODE", "CLAUDE_EFFORT", "CLAUDE_PID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
              "CLAUDE_CODE_BRIDGE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN"):
        env.pop(k, None)
    return env


def claude_call(prompt, model, system_append=None, max_turns=4, effort=None, timeout=900, attempts=4, label=""):
    # --strict-mcp-config with an empty config keeps the profile's MCP servers (and their tool
    # definitions, which can run to 200K+ tokens) out of the solver's context entirely.
    cmd = [CLAUDE, "-p", "--model", model, "--disable-slash-commands", "--output-format", "json",
           "--max-turns", str(max_turns), "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--disallowedTools", *NO_TOOLS]
    if system_append:
        cmd += ["--append-system-prompt", system_append]
    if effort:
        cmd += ["--effort", effort]
    last = None
    for i in range(attempts):
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, env=child_env(), cwd=str(BENCH))
        except subprocess.TimeoutExpired:
            last = {"error": f"timeout after {timeout}s"}
            say(f"    {label} retry {i + 1}/{attempts}: timeout")
            time.sleep(15)
            continue
        raw = proc.stdout.strip()
        data = None
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                s, e = raw.find("{"), raw.rfind("}")
                if s != -1 and e > s:
                    try:
                        data = json.loads(raw[s:e + 1])
                    except json.JSONDecodeError:
                        data = None
        if data is None:
            last = {"error": f"exit {proc.returncode}, no JSON", "stderr": proc.stderr[-1500:], "stdout": raw[-1500:]}
        else:
            result = data.get("result") or ""
            if data.get("is_error") or not result.strip():
                last = {"error": "empty or error result",
                        "data": {k: data.get(k) for k in ("result", "stop_reason", "terminal_reason", "is_error")}}
            else:
                data["_wall_ms"] = int((time.time() - t0) * 1000)
                data["_attempts"] = i + 1
                return data
        blob = json.dumps(last).lower()
        limited = any(w in blob for w in RATE_WORDS)
        wait = 300 * (i + 1) if limited else 20 * (2 ** i)
        say(f"    {label} retry {i + 1}/{attempts} in {wait}s: {last.get('error')}{' (limit)' if limited else ''}")
        time.sleep(wait)
    raise RuntimeError(f"{label}: claude call failed after {attempts} attempts: {json.dumps(last)[:1200]}")


# ---------------------------------------------------------------- run

def run_job(task, model, cond, idx, suite_dir, skills_dir, args):
    out_dir = suite_dir / "runs" / task["area"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{model}-{cond}-run{idx}"
    md, js = out_dir / f"{stem}.md", out_dir / f"{stem}.json"
    if md.exists() and js.exists() and not args.force:
        return "skip"
    prompt, sys_append, mode, skills = task["prompt"], None, "none", []
    if cond == "skills":
        skills = task["skills"]
        bundle = skills_bundle(skills, skills_dir)
        if len(bundle) <= 28000:
            sys_append, mode = bundle, "system-prompt"
        else:
            prompt, mode = bundle + "\n---\n# Task\n\n" + prompt, "prompt-prefix"
    label = f"{task['area']}/{stem}"
    say(f"  run   {label}")
    data = claude_call(prompt, model, sys_append, args.max_turns, args.effort, args.timeout, label=label)
    md.write_text(data["result"], encoding="utf-8")
    meta = {
        "area": task["area"], "model_alias": model, "canonical_models": sorted((data.get("modelUsage") or {}).keys()),
        "condition": cond, "run": idx, "skills": skills, "skills_mode": mode, "tools": "none",
        "max_turns": args.max_turns, "effort": args.effort or "default",
        "cost_usd": data.get("total_cost_usd"), "duration_api_ms": data.get("duration_api_ms"), "wall_ms": data["_wall_ms"],
        "num_turns": data.get("num_turns"), "permission_denials": data.get("permission_denials"),
        "usage": data.get("usage"), "session_id": data.get("session_id"),
        "stop_reason": data.get("stop_reason"), "attempts": data["_attempts"], "finished_at": stamp(),
    }
    js.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    cost = meta["cost_usd"] if meta["cost_usd"] is not None else 0.0
    say(f"  done  {label}  ${cost:.3f}  {meta['wall_ms'] // 1000}s")
    return "ok"


def cmd_run(args):
    suite_dir = BENCH / args.suite
    skills_dir = Path(args.skills_dir) if args.skills_dir else REPO
    areas = None if args.areas == "all" else args.areas.split(",")
    tasks = load_tasks(suite_dir, areas)
    models = args.models.split(",")
    conds = args.conditions.split(",")
    jobs = [(t, m, c, i) for t in tasks.values() for m in models for c in conds for i in range(1, args.n + 1)]
    say(f"{len(jobs)} jobs over {len(tasks)} areas x {models} x {conds} x n={args.n}, workers={args.workers}")
    if args.dry_run:
        for t, m, c, i in jobs:
            say(f"  {t['area']}/{m}-{c}-run{i}")
        return
    counts = {"ok": 0, "skip": 0, "fail": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_job, t, m, c, i, suite_dir, skills_dir, args): (t["area"], m, c, i) for t, m, c, i in jobs}
        for f in as_completed(futs):
            try:
                counts[f.result()] += 1
            except Exception as e:  # keep going; the cell is re-runnable
                counts["fail"] += 1
                say(f"  FAIL  {futs[f]}: {e}")
    say(f"run finished: {counts}")
    if counts["fail"]:
        sys.exit(1)


# ---------------------------------------------------------------- grade

JUDGE_PROMPT = """You are a blind grader. You do not know which model or condition produced the candidate output and must not try to infer it. Grade only what is on the page against the answer key.

TASK GIVEN TO THE CANDIDATE (context only; do not grade the task itself):
<<<TASK
{task}
TASK>>>

ANSWER KEY:
{key}

CANDIDATE OUTPUT:
<<<CANDIDATE
{cand}
CANDIDATE>>>

Grade every key item, in this order: {ids}
Mark an item true only if the candidate genuinely identifies that specific point. A generic best-practice line that does not engage the material does not count. There is no partial credit. Ignore any self-referential remarks about which model produced the output; "[model]" marks a redaction.
For each item give a short verbatim quote from the candidate that earns it, or an empty string if it is not earned.
Return ONLY a JSON object, no prose, no code fence, of exactly this shape with one entry per item id:
{{"items": {{"{first}": true}}, "citations": {{"{first}": "quote"}}}}
"""


def parse_grade(text, ids):
    s, e = text.find("{"), text.rfind("}")
    items, cites, ok = {}, {}, False
    if s != -1 and e > s:
        try:
            obj = json.loads(text[s:e + 1])
            items = {k: bool(v) for k, v in (obj.get("items") or {}).items()}
            cites = obj.get("citations") or {}
            ok = True
        except json.JSONDecodeError:
            ok = False
    if not ok:
        for i in ids:
            m = re.search(r'"%s"\s*:\s*(true|false)' % re.escape(i), text)
            if m:
                items[i] = m.group(1) == "true"
    missing = [i for i in ids if i not in items]
    return {i: items.get(i, False) for i in ids}, {i: cites.get(i, "") for i in ids}, missing


def grade_job(task, run_md, suite_dir, args):
    gdir = suite_dir / "grades" / task["area"]
    gdir.mkdir(parents=True, exist_ok=True)
    out = gdir / (run_md.stem + ".json")
    if out.exists() and not args.regrade:
        return "skip"
    cand = REDACT.sub("[model]", run_md.read_text(encoding="utf-8"))
    prompt = JUDGE_PROMPT.format(task=task["prompt"], key=task["key"], cand=cand,
                                 ids=", ".join(task["item_ids"]), first=task["item_ids"][0])
    label = f"grade {task['area']}/{run_md.stem}"
    say(f"  {label}")
    data = claude_call(prompt, args.judge, None, 4, args.judge_effort, args.timeout, label=label)
    items, cites, missing = parse_grade(data["result"], task["item_ids"])
    grade = {
        "area": task["area"], "run": run_md.stem, "items": items, "citations": cites,
        "score": sum(items.values()), "max": task["max_score"], "incomplete": missing,
        "judge_alias": args.judge, "judge_models": sorted((data.get("modelUsage") or {}).keys()),
        "judge_cost_usd": data.get("total_cost_usd"), "judge_wall_ms": data["_wall_ms"], "graded_at": stamp(),
    }
    out.write_text(json.dumps(grade, indent=1), encoding="utf-8")
    say(f"  {label}: {grade['score']}/{grade['max']}" + (f"  (unparsed: {missing})" if missing else ""))
    return "ok"


def cmd_grade(args):
    suite_dir = BENCH / args.suite
    areas = None if args.areas == "all" else args.areas.split(",")
    tasks = load_tasks(suite_dir, areas)
    jobs = []
    for t in tasks.values():
        rdir = suite_dir / "runs" / t["area"]
        if rdir.exists():
            for md in sorted(rdir.glob("*.md")):
                if args.match and not re.search(args.match, md.stem):
                    continue
                jobs.append((t, md))
    say(f"{len(jobs)} candidates to grade with judge={args.judge}, workers={args.workers}")
    counts = {"ok": 0, "skip": 0, "fail": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(grade_job, t, md, suite_dir, args): md for t, md in jobs}
        for f in as_completed(futs):
            try:
                counts[f.result()] += 1
            except Exception as e:
                counts["fail"] += 1
                say(f"  FAIL grade {futs[f]}: {e}")
    say(f"grade finished: {counts}")
    if counts["fail"]:
        sys.exit(1)


# ---------------------------------------------------------------- report

def parse_stem(stem):
    m = re.match(r"^(?P<model>[a-z0-9.-]+?)-(?P<cond>bare|skills)-run(?P<run>\d+)$", stem)
    return (m.group("model"), m.group("cond"), int(m.group("run"))) if m else (None, None, None)


def collect(suite_dir, tasks):
    rows = []
    for area, t in tasks.items():
        gdir = suite_dir / "grades" / area
        if not gdir.exists():
            continue
        for gj in sorted(gdir.glob("*.json")):
            g = json.loads(gj.read_text(encoding="utf-8"))
            model, cond, run = parse_stem(gj.stem)
            if not model:
                continue
            rj = suite_dir / "runs" / area / gj.name
            meta = json.loads(rj.read_text(encoding="utf-8")) if rj.exists() else {}
            rows.append({"area": area, "model": model, "cond": cond, "run": run, "score": g["score"], "max": g["max"],
                         "items": g["items"], "incomplete": g.get("incomplete", []),
                         "cost": meta.get("cost_usd"), "wall_ms": meta.get("wall_ms"),
                         "canonical": meta.get("canonical_models", []), "judge": g.get("judge_models", [])})
    return rows


def pct(x):
    return f"{100 * x:.0f}%"


def cmd_report(args):
    suite_dir = BENCH / args.suite
    tasks = load_tasks(suite_dir)
    rows = collect(suite_dir, tasks)
    if not rows:
        sys.exit("no grades found")
    models = [m for m in MODEL_ORDER if any(r["model"] == m for r in rows)] + sorted({r["model"] for r in rows} - set(MODEL_ORDER))
    areas = [a for a in tasks if any(r["area"] == a for r in rows)]
    cells = {}
    for r in rows:
        cells.setdefault((r["area"], r["model"], r["cond"]), []).append(r)

    def cell(area, model, cond):
        rs = cells.get((area, model, cond), [])
        if not rs:
            return None
        scores = [r["score"] for r in rs]
        mx = rs[0]["max"]
        costs = [r["cost"] for r in rs if r["cost"] is not None]
        return {"n": len(rs), "mean": mean(scores), "max": mx, "pct": mean(scores) / mx,
                "sd": pstdev(scores) if len(scores) > 1 else 0.0, "min": min(scores), "maxs": max(scores),
                "cost": mean(costs) if costs else None,
                "items": {i: mean([1.0 if r["items"].get(i) else 0.0 for r in rs]) for i in tasks[area]["item_ids"]}}

    canon = {}
    for r in rows:
        for c in r["canonical"]:
            canon.setdefault(r["model"], set()).add(c)
    judges = sorted({j for r in rows for j in r["judge"]})

    L = []
    L.append(f"# Benchmark results: suite `{args.suite}`")
    L.append("")
    L.append(f"Generated {stamp()} by `benchmark/harness.py report`. Blind-graded per run against fixed answer keys; "
             f"judge model(s): {', '.join(judges) or 'unknown'}. Solvers ran headless with no tools and no skills installed; "
             f"the with-skills condition had the task's skill files in its system prompt.")
    L.append("")
    L.append("Model aliases resolved to: " + "; ".join(f"`{m}` = {', '.join(sorted(canon.get(m, [])))}" for m in models))
    L.append("")
    L.append("## Headline: mean score per cell (n runs)")
    L.append("")
    L.append("| Area | " + " | ".join(f"{m} bare | {m} +skills | Δ" for m in models) + " |")
    L.append("|---|" + "|".join(":---:" for _ in range(3 * len(models))) + "|")
    for a in areas:
        mx = tasks[a]["max_score"]
        parts = [f"**{a}** (/{mx})"]
        for m in models:
            b, s = cell(a, m, "bare"), cell(a, m, "skills")
            parts.append(f"{b['mean']:.1f} · {pct(b['pct'])} (n={b['n']})" if b else "–")
            parts.append(f"**{s['mean']:.1f} · {pct(s['pct'])}** (n={s['n']})" if s else "–")
            parts.append(f"{s['mean'] - b['mean']:+.1f}" if b and s else "–")
        L.append("| " + " | ".join(parts) + " |")
    L.append("")
    L.append("## Per model, averaged over areas (mean of cell percentages)")
    L.append("")
    L.append("| Model | bare | +skills | Δ points | areas |")
    L.append("|---|:---:|:---:|:---:|:---:|")
    for m in models:
        bs = [cell(a, m, "bare") for a in areas]
        ss = [cell(a, m, "skills") for a in areas]
        both = [(b, s) for b, s in zip(bs, ss) if b and s]
        if both:
            mb, ms = mean([b["pct"] for b, _ in both]), mean([s["pct"] for _, s in both])
            L.append(f"| {m} | {pct(mb)} | **{pct(ms)}** | {100 * (ms - mb):+.0f} | {len(both)} |")
        elif any(bs):
            mb = mean([b["pct"] for b in bs if b])
            L.append(f"| {m} | {pct(mb)} | – | – | {sum(1 for b in bs if b)} |")
    L.append("")
    if len(models) > 1:
        L.append("## Parity: cheaper model with skills vs the next model up running bare")
        L.append("")
        L.append("| Area | " + " | ".join(f"{models[i]} +skills vs {models[i + 1]} bare" for i in range(len(models) - 1)) + " |")
        L.append("|---|" + "|".join(":---:" for _ in range(len(models) - 1)) + "|")
        for a in areas:
            parts = [a]
            for i in range(len(models) - 1):
                s, b = cell(a, models[i], "skills"), cell(a, models[i + 1], "bare")
                parts.append(f"{s['mean']:.1f} vs {b['mean']:.1f} ({s['mean'] - b['mean']:+.1f})" if s and b else "–")
            L.append("| " + " | ".join(parts) + " |")
        L.append("")
    L.append("## Consistency: score range (min–max) and spread per cell")
    L.append("")
    L.append("| Area | " + " | ".join(f"{m} bare | {m} +skills" for m in models) + " |")
    L.append("|---|" + "|".join(":---:" for _ in range(2 * len(models))) + "|")
    for a in areas:
        parts = [a]
        for m in models:
            for c in COND_ORDER:
                x = cell(a, m, c)
                parts.append(f"{x['min']}–{x['maxs']} (sd {x['sd']:.1f})" if x else "–")
        L.append("| " + " | ".join(parts) + " |")
    L.append("")
    L.append("## Cost per run (mean USD at list price, from the CLI's own accounting)")
    L.append("")
    L.append("| Area | " + " | ".join(f"{m} bare | {m} +skills" for m in models) + " |")
    L.append("|---|" + "|".join(":---:" for _ in range(2 * len(models))) + "|")
    for a in areas:
        parts = [a]
        for m in models:
            for c in COND_ORDER:
                x = cell(a, m, c)
                parts.append(f"${x['cost']:.3f}" if x and x["cost"] is not None else "–")
        L.append("| " + " | ".join(parts) + " |")
    L.append("")
    L.append("## Per-item hit rate by cell")
    L.append("")
    for a in areas:
        ids = tasks[a]["item_ids"]
        shorts = {i["id"]: i.get("short", "") for i in tasks[a]["items"]}
        L.append(f"### {a}")
        L.append("")
        L.append("| Cell | " + " | ".join(ids) + " |")
        L.append("|---|" + "|".join(":---:" for _ in ids) + "|")
        for m in models:
            for c in COND_ORDER:
                x = cell(a, m, c)
                if x:
                    L.append(f"| {m} {c} (n={x['n']}) | " + " | ".join(pct(x["items"][i]) for i in ids) + " |")
        L.append("")
        L.append("Items: " + "; ".join(f"{i} = {shorts[i]}" for i in ids if shorts[i]))
        L.append("")
    incomplete = [r for r in rows if r["incomplete"]]
    if incomplete:
        L.append(f"Grader output could not be fully parsed for {len(incomplete)} run(s); unparsed items were scored false: "
                 + ", ".join(f"{r['area']}/{r['model']}-{r['cond']}-run{r['run']}" for r in incomplete))
        L.append("")
    (suite_dir / "results.md").write_text("\n".join(L), encoding="utf-8")
    summary = {"suite": args.suite, "generated": stamp(), "judges": judges, "canonical": {m: sorted(v) for m, v in canon.items()},
               "cells": [{"area": a, "model": m, "cond": c, **cell(a, m, c)}
                         for a in areas for m in models for c in COND_ORDER if cell(a, m, c)],
               "runs": rows}
    (suite_dir / "results.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    say("\n".join(L) if args.print else f"wrote {suite_dir / 'results.md'} and results.json ({len(rows)} graded runs)")


def cmd_status(args):
    suite_dir = BENCH / args.suite
    tasks = load_tasks(suite_dir)
    for a in tasks:
        runs = sorted((suite_dir / "runs" / a).glob("*.md")) if (suite_dir / "runs" / a).exists() else []
        grades = {p.stem for p in (suite_dir / "grades" / a).glob("*.json")} if (suite_dir / "grades" / a).exists() else set()
        cells = {}
        for r in runs:
            m, c, _ = parse_stem(r.stem)
            cells.setdefault(f"{m}-{c}", [0, 0])
            cells[f"{m}-{c}"][0] += 1
            cells[f"{m}-{c}"][1] += 1 if r.stem in grades else 0
        say(f"{a:18s} " + "  ".join(f"{k}:{v[0]}r/{v[1]}g" for k, v in sorted(cells.items())))


def cmd_tasks(args):
    for a, t in load_tasks(BENCH / args.suite).items():
        say(f"{a:18s} items={len(t['item_ids']):2d} skills={t['skills']} prompt={len(t['prompt'])} chars")


def cmd_init_legacy(args):
    """Write task.json for the four recovered Benchmark 1/2 areas, pointing at the verbatim recovered files."""
    suite_dir = BENCH / args.suite
    for area, (title, discipline) in LEGACY.items():
        src = BENCH / "tasks" / area
        key = strip_provenance((src / "answer-key.md").read_text(encoding="utf-8"))
        ids = re.findall(r"^- ([A-Z]+\d+)\b(.*)$", key, re.M)
        numbered = [] if ids else re.findall(r"^(\d+)\.\s+(.*)$", key, re.M)
        apply_block = (src / "prompt-skills.md").read_text(encoding="utf-8")
        skills = (re.findall(r"^- ([a-z-]+):", apply_block, re.M)
                  or re.findall(r"^=+ SKILL: ([a-z-]+) =+", apply_block, re.M))
        if not skills:
            skills = [discipline, "workmanship"]
            say(f"  {area}: no skill list found in prompt-skills.md, using {skills}")
        out = suite_dir / "tasks" / area
        out.mkdir(parents=True, exist_ok=True)
        rel = os.path.relpath(src, out).replace(os.sep, "/")
        note = "Legacy area from Benchmark 1/2 (2026-07-07), reused unchanged so current models can be compared on the same task."
        key_file = f"{rel}/answer-key.md"
        if numbered:
            # Benchmark 1's key is a plain numbered list; give each line a stable id without changing its wording.
            prefix = area[0].upper()
            items = [{"id": f"{prefix}{n}", "short": re.sub(r"\s+", " ", d).strip()[:60]} for n, d in numbered]
            lines = [f"ANSWER KEY - {len(items)} items. Mark an item Y only if the output genuinely identifies that specific point."]
            lines += [f"- {prefix}{n} {d.strip()}" for n, d in numbered]
            (out / "answer-key.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            key_file = "answer-key.md"
            note += f" Answer key normalised from the recovered numbered list into id'd bullets ({prefix}1..{prefix}{len(items)}); wording verbatim."
        else:
            items = [{"id": i, "short": re.sub(r"\s+", " ", d).strip(" :-")[:60]} for i, d in ids]
        (out / "task.json").write_text(json.dumps({
            "area": area, "title": title, "discipline": discipline, "skills": skills,
            "prompt_file": f"{rel}/prompt-bare.md", "answer_key_file": key_file,
            "output_format": "numbered-findings", "items": items, "max_score": len(items),
            "design_notes": note,
        }, indent=1) + "\n", encoding="utf-8")
        say(f"  {area}: {len(items)} items, skills={skills}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("tasks", "run", "grade", "report", "status", "init-legacy"):
        p = sub.add_parser(name)
        p.add_argument("--suite", default="b3")
        if name in ("run", "grade"):
            p.add_argument("--areas", default="all")
            p.add_argument("--workers", type=int, default=6)
            p.add_argument("--timeout", type=int, default=900)
        if name == "run":
            p.add_argument("--models", default="sonnet")
            p.add_argument("--conditions", default="bare,skills")
            p.add_argument("--n", type=int, default=5)
            p.add_argument("--max-turns", type=int, default=4)
            p.add_argument("--effort", default=None)
            p.add_argument("--skills-dir", default=None, help="directory holding <skill>/SKILL.md (default: repo root)")
            p.add_argument("--force", action="store_true")
            p.add_argument("--dry-run", action="store_true")
        if name == "grade":
            p.add_argument("--judge", default="opus")
            p.add_argument("--judge-effort", default=None)
            p.add_argument("--match", default=None, help="regex on run stem, e.g. 'sonnet-.*'")
            p.add_argument("--regrade", action="store_true")
        if name == "report":
            p.add_argument("--print", action="store_true")
    args = ap.parse_args()
    {"tasks": cmd_tasks, "run": cmd_run, "grade": cmd_grade, "report": cmd_report, "status": cmd_status,
     "init-legacy": cmd_init_legacy}[args.cmd](args)


if __name__ == "__main__":
    main()
