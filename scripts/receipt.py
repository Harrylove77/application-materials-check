"""Two-part, conversation-first receipt. No personal data or school rules are bundled."""
STAGES = {"application": "申请阶段", "after_offer": "获录取后",
          "registration": "注册/入学前", "post_arrival": "抵港/到校后"}
OBLIGATIONS = {"required": "必交", "conditional": "条件性", "optional": "可选",
               "not_requested": "未要求", "prohibited": "不接受"}
WORKFLOW_CHANNELS = {"test_agency", "online_text", "later_stage"}

def stage(entry):
    return entry.get("stage", "application")

def is_material(entry):
    return (stage(entry) == "application" and
            entry.get("kind", "workflow" if entry.get("channel") in WORKFLOW_CHANNELS else "material") == "material")

def evidence_text(finding):
    details = []
    for e in finding.get("evidence", []):
        detail = " ".join(str(e.get(k, "")).strip() for k in ("file", "locator", "excerpt")).strip()
        if detail:
            details.append(detail)
    return "；".join(details)

def refs(entry, sources):
    links = []
    for sid in entry.get("source_ids", []):
        src = sources.get(sid, {})
        url = src.get("url")
        links.append(f"[{sid}]({url})" if url and url.startswith(("https://", "http://")) else str(sid))
    return " ".join(links)

def material_rows(manifest):
    plan = manifest["plan"]
    items = {o["id"]: o for o in manifest["outputs"]}
    sources = {s["id"]: s for s in plan["sources"]}
    findings = [f for f in plan.get("findings", []) if stage(f) == "application"]
    rows = []
    used = set()
    for req in manifest["checklist"]:
        if not is_material(req):
            continue
        ids = req.get("output_ids", [])
        comments = [req["comment"]] if req.get("comment") else ([req["note"]] if req.get("note") else [])
        for check in req.get("checks", []):
            if check.get("status") != "pass":
                comments.append(f"{check['label']}：{check.get('note') or '待核对'}")
        for finding in findings:
            if ((set(ids) & set(finding.get("output_ids", []))) or
                req["id"] in finding.get("requirement_ids", [])):
                state = "已解决" if finding.get("resolved") else "待确认" if finding.get("certainty") != "confirmed_conflict" else "已发现"
                value = f"{state}：{finding['title']}"
                proof = evidence_text(finding)
                if proof:
                    value += f"（{proof}）"
                if finding.get("action"):
                    value += "；处理：" + finding["action"]
                comments.append(value)
                used.add(finding["id"])
        files = []
        for oid in ids:
            item = items[oid]
            if item["generated"]:
                files.append(f"{item['filename']}（{item['pages']}页，{item['bytes']/1_000_000:.3f}MB）")
            else:
                files.append(item["filename"] + "（未生成）")
                comments.append(item.get("error", "处理失败，需补可读文件"))
            comments.extend(item.get("technical_issues", []))
        citation = refs(req, sources)
        comment = "；".join(dict.fromkeys(c for c in comments if c)) or "本次核对未记录明显问题。"
        if citation:
            comment += " " + citation
        rows.append({"material": req["label"],
                     "status": OBLIGATIONS[req["obligation"]] + " / " + req["status"],
                     "comment": comment, "files": "；".join(files) or "未提供本地文件"})
    for finding in findings:
        if finding["id"] in used:
            continue
        proof = evidence_text(finding)
        rows.append({"material": "跨材料核对：" + finding["title"],
                     "status": "已解决" if finding.get("resolved") else "待确认",
                     "comment": "；".join(x for x in [proof, finding.get("impact"), finding.get("action")] if x),
                     "files": "；".join(items[i]["filename"] for i in finding.get("output_ids", []) if i in items) or "见证据位置"})
    return rows

def reminder_lines(manifest):
    plan = manifest["plan"]
    sources = {s["id"]: s for s in plan["sources"]}
    lines = []
    for reminder in plan.get("reminders", []):
        label = STAGES[stage(reminder)]
        text = f"【{label}】{reminder['title']}"
        if reminder.get("due_at"):
            text += "；时间：" + reminder["due_at"]
            if reminder.get("time_zone"):
                text += "（" + reminder["time_zone"] + "）"
        if reminder.get("condition"):
            text += "；适用条件：" + reminder["condition"]
        if reminder.get("action"):
            text += "；" + reminder["action"]
        if reminder.get("status"):
            text += "；状态：" + reminder["status"]
        citation = refs(reminder, sources)
        lines.append(text + (" " + citation if citation else ""))
    deadlines = {}
    for req in manifest["checklist"]:
        if req.get("deadline"):
            key = (stage(req), req["deadline"])
            deadlines.setdefault(key, req)
        if not is_material(req):
            text = f"【{STAGES[stage(req)]}】{req['label']}：{req['status']}"
            if req.get("note"):
                text += "；" + req["note"]
            if req.get("manual_evidence"):
                evidence = req["manual_evidence"]
                text += "；状态依据：" + ("；".join(evidence) if isinstance(evidence, list) else str(evidence))
            citation = refs(req, sources)
            lines.append(text + (" " + citation if citation else ""))
    for (when, deadline), req in deadlines.items():
        citation = refs(req, sources)
        lines.append(f"【{STAGES[when]}】提交时间：{deadline}" + (" " + citation if citation else ""))
    for finding in plan.get("findings", []):
        if stage(finding) != "application":
            lines.append(f"【{STAGES[stage(finding)]}】{finding['title']}；"
                         + (finding.get("action") or finding.get("impact", "")))
    for limitation in plan.get("review", {}).get("limitations", []):
        lines.append("核对范围：" + str(limitation))
    for unknown in plan.get("unresolved_requirements", []):
        lines.append("待核实：" + str(unknown))
    if not lines:
        lines.append("本次未记录额外时间或流程提醒；未公开事项不能推定为无要求。")
    return list(dict.fromkeys(lines))

def cell(value):
    # Escape pipe characters and raw HTML; preserve deliberate Markdown source links.
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\r", "").replace("\n", "<br>")

def markdown(manifest):
    target = manifest["plan"]["target"]
    context = " / ".join(str(target.get(key, "")) for key in ("university", "programme", "intake") if target.get(key))
    lines = ["**申请材料终检回执**", "", context,
             "", f"总体状态：{manifest['status']}。本次仅核对与整理材料，未代为递交；既往网申状态仅按已取得的证据记录。",
             "", "## 一、材料检查", "",
             "| 材料 | 要求 / 状态 | 点评与处理 | 对应文件 |",
             "| --- | --- | --- | --- |"]
    for row in material_rows(manifest):
        lines.append("| " + " | ".join(cell(row[k]) for k in ("material", "status", "comment", "files")) + " |")
    if not material_rows(manifest):
        lines.append("| 本阶段材料 | 待核验 | 尚未取得可用的申请阶段材料清单。 | — |")
    lines.extend(["", "## 二、提醒", ""])
    lines.extend("- " + line.replace("\n", " ") for line in reminder_lines(manifest))
    return "\n".join(lines) + "\n"

