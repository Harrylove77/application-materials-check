#!/usr/bin/env python3
"""Local file mechanics for application-materials-check; semantic review is model-led."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps, ImageSequence
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
from xml.sax.saxutils import escape
import receipt

VERSION = 1
BUCKETS = {"upload", "review", "reference"}
OBLIGATIONS = {"required", "conditional", "optional", "not_requested", "prohibited"}
EXTERNAL_CHANNELS = {"referee_direct", "institution_direct", "test_agency",
                     "online_text", "native_format", "later_stage"}

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

def plain_error(exc):
    return f"{type(exc).__name__}: {str(exc)[:500]}"

def safe_name(value):
    if (not isinstance(value, str) or value in {"", ".", ".."}
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
        or value.endswith((" ", ".")) or len(value) > 180):
        raise ValueError(f"Unsafe filename: {value!r}")
    if value.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10))
    }:
        raise ValueError("Reserved Windows filename")
    return value

def pdf_meta(path, text=False):
    reader = PdfReader(str(path))
    result = {"encrypted": reader.is_encrypted}
    if reader.is_encrypted:
        result.update(readable=False, reason="加密文件未解锁，未移除保护")
        return result
    fields = reader.get_fields() or {}
    root = reader.trailer["/Root"]
    sig = any(str(f.get("/FT")) == "/Sig" and bool(f.get("/V"))
              for f in fields.values())
    widgets = any(str(a.get_object().get("/Subtype")) == "/Widget"
                  for p in reader.pages for a in p.get("/Annots", []))
    protected = bool(root.get("/Perms"))
    result.update(readable=True, pages=len(reader.pages), signed=sig,
                  certification=protected, form=bool(fields) or widgets,
                  text_lengths=[], low_text_pages=[])
    extracted = []
    for index, page in enumerate(reader.pages, 1):
        value = page.extract_text() or "" if text else ""
        if text:
            result["text_lengths"].append(len(value.strip()))
            if len(value.strip()) < 30:
                result["low_text_pages"].append(index)
            extracted.append(f"=== PAGE {index} ===\n{value}")
    if text:
        result["text"] = "\n\n".join(extracted)
    return result

def docx_meta(path):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs, revisions, comments = [], 0, 0
    with zipfile.ZipFile(path) as package:
        names = [n for n in package.namelist() if re.fullmatch(
            r"word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml", n)]
        for name in names:
            tree = ET.fromstring(package.read(name))
            revisions += len(tree.findall(".//w:ins", ns)) + len(tree.findall(".//w:del", ns))
            comments += len(tree.findall(".//w:comment", ns))
            for index, p in enumerate(tree.findall(".//w:p", ns), 1):
                value = "".join(node.text or "" for node in p.iter()
                                if node.tag in {f"{{{ns['w']}}}t", f"{{{ns['w']}}}delText"})
                if value.strip():
                    paragraphs.append(f"[{name} paragraph {index}] {value}")
    return {"readable": True, "tracked_changes": revisions, "comments": comments,
            "text": "\n".join(paragraphs), "layout_checked": False}

def inventory(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not root.is_dir():
        raise ValueError("Input must be a directory")
    if output == root or root in output.parents:
        raise ValueError("Inventory output must be outside the input tree")
    output.mkdir(parents=True, exist_ok=False)
    (output / "text").mkdir()
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink() or root not in path.resolve().parents:
            files.append({"path": str(path), "relative_path": str(path.relative_to(root)),
                          "readable": False, "reason": "跳过输入目录外链接"})
            continue
        item = {"path": str(path), "relative_path": str(path.relative_to(root)),
                "bytes": path.stat().st_size, "sha256": sha(path), "extension": path.suffix.lower()}
        try:
            if path.suffix.lower() == ".pdf":
                item.update(pdf_meta(path, text=True))
            elif path.suffix.lower() == ".docx":
                item.update(docx_meta(path))
            elif path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
                with Image.open(path) as pic:
                    item.update(readable=True, frames=getattr(pic, "n_frames", 1),
                                width=pic.width, height=pic.height, needs_visual_or_ocr=True)
            else:
                item.update(readable=False, reason="需相应本地转换器或人工确认格式")
            value = item.pop("text", None)
            if value is not None:
                dest = output / "text" / f"{item['sha256']}.txt"
                dest.write_text(value, encoding="utf-8")
                item["text_file"] = str(dest)
        except Exception as exc:
            item.update(readable=False, reason=plain_error(exc))
        files.append(item)
    hashes = {}
    for item in files:
        if item.get("sha256"):
            hashes.setdefault(item["sha256"], []).append(item["relative_path"])
    result = {"schema_version": VERSION, "created_at": now(), "input_root": str(root),
              "files": files, "byte_identical_groups": [g for g in hashes.values() if len(g) > 1],
              "note": "仅抽取与技术盘点，不代表内容已审读；相同哈希不自动删除。"}
    write_json(output / "inventory.json", result)
    return result

def image_pdf(path, max_px=None):
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer, pagesize=(595.28, 841.89), invariant=1)
    frames = 0
    with Image.open(path) as pic:
        for frame in ImageSequence.Iterator(pic):
            image = ImageOps.exif_transpose(frame.copy()).convert("RGBA")
            bg = Image.new("RGB", image.size, "white")
            bg.paste(image, mask=image.getchannel("A"))
            if max_px:
                bg.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
            width, height = 595.28, 841.89
            if bg.width > bg.height:
                width, height = height, width
            doc.setPageSize((width, height))
            scale = min(width / bg.width, height / bg.height)
            draw_w, draw_h = bg.width * scale, bg.height * scale
            doc.drawImage(ImageReader(bg), (width-draw_w)/2, (height-draw_h)/2,
                          draw_w, draw_h, preserveAspectRatio=True)
            doc.showPage()
            frames += 1
    doc.save()
    buffer.seek(0)
    return buffer, frames

def check_limit(actual, rule):
    if not rule or rule.get("max_bytes") is None:
        return None
    maximum = rule["max_bytes"]
    return actual < maximum if rule.get("comparator", "le") == "lt" else actual <= maximum

def validate_plan(plan):
    for key in ("target", "sources", "requirements", "outputs", "review"):
        if key not in plan:
            raise ValueError(f"Plan missing {key}")
    for key in ("university", "programme", "intake", "applicant"):
        if not plan["target"].get(key):
            raise ValueError(f"Target missing {key}")
    if plan.get("requirements_coverage", {}).get("complete") and not plan["requirements"]:
        raise ValueError("Complete coverage requires a nonempty requirements list")
    if type(plan.get("requirements_coverage", {}).get("complete", False)) is not bool:
        raise ValueError("Coverage complete must be boolean")
    for src in plan["sources"]:
        if type(src.get("verified", False)) is not bool:
            raise ValueError("Source verified must be boolean")
        if src.get("verified") and not all([
            src.get("title"), src.get("url") or src.get("local_path"),
            src.get("locator"), src.get("checked_at"), src.get("intake_scope")]):
            raise ValueError("Verified source needs title, location, locator, time and scope")
    for collection in ("sources", "requirements", "outputs"):
        ids = [entry["id"] for entry in plan[collection]]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate {collection} id")
    for finding in plan.get("findings", []):
        if finding.get("severity") not in {"blocker", "high", "medium", "low"}:
            raise ValueError("Unknown finding severity")
    output_ids = {o["id"] for o in plan["outputs"]}
    source_ids = {s["id"] for s in plan["sources"]}
    seen_names = set()
    for spec in plan["outputs"]:
        name = safe_name(spec["filename"])
        if not name.lower().endswith(".pdf") or name.casefold() in seen_names:
            raise ValueError("Output PDF names must be unique across the package")
        seen_names.add(name.casefold())
        if spec.get("bucket", "upload") not in BUCKETS or not spec.get("inputs"):
            raise ValueError("Invalid output bucket or empty inputs")
        if spec.get("image_max_px") is not None and (
            type(spec["image_max_px"]) is not int or spec["image_max_px"] < 1200):
            raise ValueError("Refusing image_max_px below 1200; retain readability")
        if spec.get("naming_regex"):
            re.compile(spec["naming_regex"])
        for inp in spec["inputs"]:
            if "path" not in inp or "pages" in inp:
                raise ValueError("Every input needs path; page dropping/selection is unsupported")
    if type(plan.get("receipt_pdf", False)) is not bool:
        raise ValueError("receipt_pdf must be boolean")
    for entry in plan["requirements"] + plan.get("findings", []) + plan.get("reminders", []):
        if receipt.stage(entry) not in receipt.STAGES:
            raise ValueError("Unknown stage")
        if "kind" in entry and entry["kind"] not in {"material", "workflow"}:
            raise ValueError("Unknown requirement kind")
        if not set(entry.get("source_ids", [])).issubset(source_ids):
            raise ValueError("Entry refers to unknown source")
    for req in plan["requirements"]:
        if req.get("applicability", "applied") not in {"applied", "not_applicable", "unknown"}:
            raise ValueError("Unknown applicability")
        if req.get("verification") not in {"verified", "unknown", "conflict"}:
            raise ValueError("Unknown requirement verification")
        if req.get("manual_status", "pending") not in {"confirmed", "pending", "unknown"}:
            raise ValueError("Unknown channel status")
        if req.get("obligation") not in OBLIGATIONS:
            raise ValueError("Unknown obligation")
        if req.get("channel") not in EXTERNAL_CHANNELS | {"applicant_upload"}:
            raise ValueError("Unknown submission channel")
        if not set(req.get("output_ids", [])).issubset(output_ids):
            raise ValueError("Requirement refers to unknown output")
        if not set(req.get("source_ids", [])).issubset(source_ids):
            raise ValueError("Requirement refers to unknown source")
    rules = [o.get("limit") for o in plan["outputs"]] + plan.get("aggregate_limits", [])
    for rule in filter(None, rules):
        if rule.get("max_bytes") is not None and (
            type(rule["max_bytes"]) is not int or rule["max_bytes"] <= 0):
            raise ValueError("max_bytes must be a positive integer or null")
        if rule.get("comparator", "le") not in {"lt", "le"}:
            raise ValueError("Invalid size comparator")
        if not set(rule.get("source_ids", [])).issubset(source_ids):
            raise ValueError("Limit refers to unknown source")

def make_output(spec, base, destination):
    result = {"id": spec["id"], "filename": spec["filename"],
              "desired_bucket": spec.get("bucket", "upload"), "slot": spec.get("slot", ""),
              "limit": spec.get("limit"), "technical_issues": [], "sources": [],
              "visual_review": None, "generated": False}
    paths, readers, resources, expected = [], [], [], 0
    for inp in spec["inputs"]:
        path = (base / inp["path"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        mapping = {"file": path.name, "path": str(path), "sha256": sha(path),
                   "origin": inp.get("origin"), "conversion_note": inp.get("conversion_note", ""),
                   "output_start_page": expected + 1}
        if path.suffix.lower() == ".pdf":
            meta = pdf_meta(path)
            if not meta["readable"]:
                raise ValueError(f"{path.name}: {meta.get('reason')}")
            resources.append(meta)
            reader = PdfReader(str(path))
        elif path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
            stream, _ = image_pdf(path, spec.get("image_max_px"))
            resources.append(stream)
            reader = PdfReader(stream)
        else:
            raise ValueError(f"{path.name}: 请先用本地引擎导出PDF，再将PDF列入计划")
        pages = len(reader.pages)
        if not pages:
            raise ValueError(f"{path.name}: zero pages")
        expected += pages
        mapping.update(source_pages=f"1-{pages}", output_end_page=expected)
        result["sources"].append(mapping)
        readers.append(reader)
        paths.append(path)
    protected = any(isinstance(m, dict) and (
        m.get("signed") or m.get("certification") or m.get("form")) for m in resources)
    if len(paths) > 1 and protected:
        raise ValueError("含数字签名/认证/交互表单，拒绝合并；请保留独立原件")
    unchanged = len(paths) == 1 and paths[0].suffix.lower() == ".pdf"
    if unchanged:
        shutil.copyfile(paths[0], destination)
        result["operation"] = "byte_copy"
    else:
        writer = PdfWriter()
        for reader in readers:
            writer.append(reader)
        with destination.open("wb") as stream:
            writer.write(stream)
        result["operation"] = "merge" if len(paths) > 1 else "image_to_pdf"
    if check_limit(destination.stat().st_size, spec.get("limit")) is False and not protected:
        writer = PdfWriter()
        writer.clone_document_from_reader(PdfReader(str(destination)))
        for page in writer.pages:
            page.compress_content_streams()
        optimized = io.BytesIO()
        writer.write(optimized)
        if len(optimized.getvalue()) < destination.stat().st_size:
            destination.write_bytes(optimized.getvalue())
            result["operation"] += "+lossless_stream_compression"
    final = pdf_meta(destination)
    result.update(generated=True, bytes=destination.stat().st_size, sha256=sha(destination),
                  pages=final.get("pages"), protected=protected)
    if result["pages"] != expected:
        result["technical_issues"].append("输出页数与源文件合计不符")
    if check_limit(result["bytes"], spec.get("limit")) is False:
        result["technical_issues"].append("单件大小超限")
    if spec.get("max_pages") is not None and result["pages"] > spec["max_pages"]:
        result["technical_issues"].append("页数超限")
    if spec.get("naming_regex") and not re.fullmatch(spec["naming_regex"], spec["filename"]):
        result["technical_issues"].append("文件名不符合指定规则")
    return result


def derive_status(manifest):
    plan = manifest["plan"]
    items = {o["id"]: o for o in manifest["outputs"]}
    sources = {s["id"]: s for s in plan["sources"]}
    errors, pending = [], []
    for limit in plan.get("aggregate_limits", []):
        slots = limit.get("slots")
        group = [o for o in items.values() if o["desired_bucket"] == "upload"
                 and (slots is None or o["slot"] in slots)]
        total = sum(o.get("bytes", 0) for o in group)
        count = sum(bool(o["generated"]) for o in group)
        label = limit.get("label", "上传组")
        if check_limit(total, limit) is False:
            errors.append(f"{label}: 合计大小超限 ({total} bytes)")
        if limit.get("max_files") is not None and count > limit["max_files"]:
            errors.append(f"{label}: 文件数量超限 ({count})")
        if (limit.get("verification") != "verified" or not limit.get("source_ids")
            or any(not sources[i].get("verified") for i in limit.get("source_ids", []))):
            pending.append(f"{label}: 合计限制待核验")
    for item in items.values():
        issues = list(item["technical_issues"])
        if not item["generated"]:
            issues.append(item.get("error", "未生成文件"))
        if item["desired_bucket"] == "upload":
            linked_rules = [r for r in plan["requirements"] if item["id"] in r.get("output_ids", [])]
            if not linked_rules:
                pending.append(f"{item['filename']}: 未关联适用材料要求")
            limit = item.get("limit") or {}
            if limit.get("verification") not in {"verified", "not_published"}:
                pending.append(f"{item['filename']}: 单件容量限制待核验")
            elif not limit.get("source_ids") or any(
                not sources[i].get("verified") for i in limit.get("source_ids", [])):
                pending.append(f"{item['filename']}: 单件容量依据待核验")
        affected = [f for f in plan.get("findings", [])
                    if receipt.stage(f) == "application" and not f.get("resolved")
                    and f.get("severity") in {"high", "blocker"}
                    and (not f.get("output_ids") or item["id"] in f["output_ids"])]
        issues.extend(f"内容风险: {f['title']}" for f in affected)
        item["issues"] = issues
        item["state"] = "待处理" if issues else (
            "已复核" if item.get("visual_review") else "待视觉复核")
        if issues:
            errors.append(f"{item['filename']}: {'; '.join(issues)}")
        elif item["desired_bucket"] != "reference" and not item.get("visual_review"):
            pending.append(f"{item['filename']}: 待视觉复核")
    rows = []
    for req in plan["requirements"]:
        if receipt.stage(req) != "application":
            rows.append({**req, "status": "已确认完成" if req.get("manual_status") == "confirmed"
                         and req.get("manual_evidence") else "后续阶段待办"})
            continue
        obligation = req["obligation"]
        application = req.get("applicability", "applied")
        required = obligation == "required" or (obligation == "conditional" and application == "applied")
        linked = [items[i] for i in req.get("output_ids", [])]
        active = (application != "not_applicable" and obligation not in {"not_requested", "prohibited"}
                  and (required or bool(linked)))
        bad_checks = [c for c in req.get("checks", []) if c.get("status") == "fail"] if active else []
        unknown_checks = [c for c in req.get("checks", []) if c.get("status") not in {"pass", "fail"}] if active else []
        verified = (req.get("verification") == "verified"
                    and bool(req.get("source_ids"))
                    and all(sources[i].get("verified") for i in req["source_ids"]))
        if obligation in {"not_requested", "prohibited"} or application == "not_applicable":
            status = "不需上传" if obligation != "prohibited" else "不接受上传"
            if any(o["desired_bucket"] == "upload" for o in linked):
                errors.append(f"{req['label']}: 不应放入上传包")
        elif obligation == "conditional" and application == "unknown":
            status = "适用条件待确认"
            pending.append(f"{req['label']}: {status}")
        elif req["channel"] in EXTERNAL_CHANNELS:
            status = ("渠道已核对完成" if req.get("manual_status") == "confirmed"
                      and req.get("manual_evidence") else "渠道待办")
            if required and status == "渠道待办":
                errors.append(f"{req['label']}: {LABELS.get(req['channel'], req['channel'])} 待办，非本地PDF缺件")
        elif not linked:
            status = "缺件" if required else "未提供（可选）"
            if required:
                errors.append(f"{req['label']}: 缺件")
        elif any(not o["generated"] or o["issues"] for o in linked):
            status = "已收到，待处理"
            if required:
                errors.append(f"{req['label']}: {status}")
        elif any(o["desired_bucket"] != "upload" for o in linked):
            status = "仅整理副本，待确认提交文件"
            if required:
                errors.append(f"{req['label']}: {status}")
        elif any(not o.get("visual_review") for o in linked):
            status = "已收到，待复核"
        else:
            status = "本地文件已核对"
        if (required or any(o["desired_bucket"] == "upload" for o in linked)) and not verified:
            pending.append(f"{req['label']}: 要求证据待核验")
        formats = req.get("details", {}).get("accepted_formats")
        if (formats and req["channel"] == "applicant_upload"
            and "pdf" not in {str(f).lower().lstrip(".") for f in formats}
            and any(o["desired_bucket"] == "upload" for o in linked)):
            errors.append(f"{req['label']}: 该槽位不接受PDF，须保留规定格式")
            status += " / 提交格式不符"
        if bad_checks:
            errors.extend(f"{req['label']}: {c['label']} 不通过 - {c.get('note', '')}"
                          for c in bad_checks)
            status += " / 要求检查未通过"
        if unknown_checks:
            pending.extend(f"{req['label']}: {c['label']} 待核验" for c in unknown_checks)
            status += " / 部分要求待核验"
        rows.append({**req, "status": status})
    for finding in plan.get("findings", []):
        if (receipt.stage(finding) == "application" and not finding.get("resolved")
            and finding.get("severity") in {"high", "blocker"}):
            errors.append(f"{finding['id']}: {finding['title']}")
    if not plan.get("requirements_coverage", {}).get("complete"):
        pending.append("官网要求覆盖尚未完成")
    if plan["review"].get("status") != "complete":
        pending.append("跨文件内容审读尚未完成")
    pending.extend(plan.get("unresolved_requirements", []))
    manifest.update(checklist=rows, blockers=list(dict.fromkeys(errors)),
                    pending=list(dict.fromkeys(pending)), updated_at=now())
    manifest["status"] = ("待补件或处理" if errors else
                          "尚未完成核验" if pending else "本地材料核对就绪")

def sync_locations(root, manifest):
    moves = []
    for item in manifest["outputs"]:
        if not item["generated"]:
            continue
        wanted = item["desired_bucket"]
        if wanted == "upload" and (item["issues"] or not item.get("visual_review")):
            wanted = "review"
        # A package-wide limit/requirement failure must not leave apparently ready PDFs.
        if wanted == "upload" and manifest["status"] != "本地材料核对就绪":
            wanted = "review"
        old = root / item["path"]
        new = root / wanted / item["filename"]
        if old != new:
            if new.exists():
                raise FileExistsError(f"Refusing overwrite: {new}")
            moves.append((old, new))
        item["path"] = str(new.relative_to(root))
    # All conflicts are checked before the first move.
    for old, new in moves:
        shutil.move(str(old), str(new))

def text_value(value):
    if value is None:
        return "未公开/待核实"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

LABELS = {
    "applicant": "申请人", "university": "院校", "campus": "校区", "programme": "项目",
    "level": "层级", "intake": "入学季", "round": "批次", "notice": "说明",
    "required": "必交", "conditional": "条件性材料", "optional": "可选", "not_requested": "未要求",
    "prohibited": "不接受", "applied": "适用", "not_applicable": "不适用", "unknown": "待核实",
    "applicant_upload": "申请人上传", "referee_direct": "推荐人直传",
    "institution_direct": "学校直送", "test_agency": "考试机构送分", "online_text": "在线填写",
    "native_format": "指定原生格式", "later_stage": "后续阶段", "verified": "已核验",
    "conflict": "要求存在冲突", "condition_note": "条件说明", "deadline": "截止时点", "note": "说明",
    "accepted_formats": "接受格式", "upload_slot": "上传栏位", "language": "语言要求",
    "certification": "认证要求", "translation_pairing": "原文译文配对", "count": "份数",
    "merge_rule": "合并规则", "pass": "通过", "fail": "未通过", "words": "字数", "pages": "页数",
    "naming": "命名要求", "byte_copy": "原PDF完整复制", "merge": "按顺序合并",
    "image_to_pdf": "图片整页转PDF", "lossless_stream_compression": "无损压缩", "le": "小于等于", "lt": "严格小于",
    "blocker": "提交阻碍", "high": "高风险", "medium": "待解释风险", "low": "轻微问题",
    "confirmed_conflict": "已确认冲突", "needs_confirmation": "需学生确认", "unverified": "尚未核验",
    "complete": "已完成所述范围", "partial": "部分完成"
}

def receipt_font():
    # Use a locally installed TrueType CJK face when available; otherwise standard PDF CID font.
    candidates = [Path("C:/Windows/Fonts/simsun.ttc"),
                  Path("/usr/share/fonts/truetype/arphic/uming.ttc")]
    for path in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("ReceiptCJK", str(path), subfontIndex=0))
                return "ReceiptCJK"
            except Exception:
                pass
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"

def write_receipt_pdf(path, manifest):
    """Optional export only; the Markdown receipt remains the conversation source."""
    font = receipt_font()
    style = ParagraphStyle("Receipt", fontName=font, fontSize=8.5, leading=13, wordWrap="CJK")
    heading = ParagraphStyle("ReceiptHeading", parent=style, fontSize=13, leading=20,
                             spaceBefore=12, spaceAfter=8, keepWithNext=True)
    def para(value):
        value = escape(str(value))
        value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                       lambda m: '<link href="' + m.group(2) + '">' + m.group(1) + '</link>', value)
        return Paragraph(value.replace("\n", "<br/>"), style)
    story = [Paragraph("申请材料终检回执", heading), para(manifest["status"]),
             para(" / ".join(str(manifest["plan"]["target"].get(k, ""))
                             for k in ("university", "programme", "intake"))),
             Paragraph("一、材料检查", heading)]
    data = [[para(s) for s in ("材料", "要求 / 状态", "点评与处理", "对应文件")]]
    for row in receipt.material_rows(manifest):
        data.append([para(row[k]) for k in ("material", "status", "comment", "files")])
    table = LongTable(data, colWidths=[65, 80, 260, 106], repeatRows=1, splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9F0F4")),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#B7C5CF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.extend([table, Paragraph("二、提醒", heading)])
    for value in receipt.reminder_lines(manifest):
        story.extend([para("- " + value), Spacer(1, 5)])
    SimpleDocTemplate(str(path), pagesize=(595.28, 841.89), leftMargin=42, rightMargin=42,
                      topMargin=40, bottomMargin=40, title="申请材料终检回执").build(story)

def write_reports(root, manifest):
    report = root / "report"
    report.mkdir(exist_ok=True)
    (report / "receipt.md").write_text(receipt.markdown(manifest), encoding="utf-8")
    if manifest["plan"].get("receipt_pdf", False):
        write_receipt_pdf(report / "receipt.pdf", manifest)
    write_json(report / "manifest.json", manifest)
    write_json(report / "requirements.json", {
        "target": manifest["plan"]["target"], "sources": manifest["plan"]["sources"],
        "requirements": manifest["plan"]["requirements"],
        "reminders": manifest["plan"].get("reminders", []),
        "coverage": manifest["plan"].get("requirements_coverage")})

def build(plan_path, output):
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = read_json(plan_path)
    validate_plan(plan)
    if output.exists():
        raise FileExistsError("Package directory exists; choose a new batch directory")
    # A package must not contain or overwrite any input file.
    for spec in plan["outputs"]:
        for inp in spec["inputs"]:
            original = (plan_path.parent / inp["path"]).resolve()
            if output == original or output in original.parents:
                raise ValueError("Package directory would contain its input file")
    output.mkdir(parents=True)
    for name in BUCKETS:
        (output / name).mkdir()
    manifest = {"schema_version": VERSION, "created_at": now(),
                "plan": plan, "outputs": []}
    for spec in plan["outputs"]:
        bucket = "reference" if spec.get("bucket") == "reference" else "review"
        dest = output / bucket / spec["filename"]
        try:
            result = make_output(spec, plan_path.parent, dest)
            result["path"] = str(dest.relative_to(output))
        except Exception as exc:
            if dest.exists():
                dest.unlink()
            result = {"id": spec["id"], "filename": spec["filename"],
                      "desired_bucket": spec.get("bucket", "upload"), "slot": spec.get("slot", ""),
                      "generated": False, "sources": [], "technical_issues": [],
                      "error": plain_error(exc), "visual_review": None}
        manifest["outputs"].append(result)
    derive_status(manifest)
    sync_locations(output, manifest)
    write_reports(output, manifest)
    return manifest

def finalize(root, qa_path):
    root = Path(root).resolve()
    manifest = read_json(root / "report" / "manifest.json")
    validate_plan(manifest["plan"])
    qa = read_json(qa_path)
    entries = qa["outputs"]
    if len({e["id"] for e in entries}) != len(entries):
        raise ValueError("Duplicate QA id")
    known_ids = {o["id"] for o in manifest["outputs"] if o["generated"]}
    if not {e["id"] for e in entries}.issubset(known_ids):
        raise ValueError("QA refers to unknown or ungenerated output")
    records = {e["id"]: e for e in entries}
    # Verify every generated file before any movement/report mutation.
    for item in manifest["outputs"]:
        if not item["generated"]:
            continue
        path = (root / item["path"]).resolve()
        if root not in path.parents:
            raise ValueError("Manifest path escapes package")
        if sha(path) != item["sha256"]:
            raise ValueError(f"{item['id']}: output changed since build; rebuild package")
        record = records.get(item["id"])
        if record:
            if record.get("sha256") != item["sha256"]:
                raise ValueError(f"{item['id']}: QA hash does not match")
            expected = set(range(1, item["pages"]+1))
            if (record.get("status") != "pass" or
                set(record.get("pages_checked", [])) != expected or
                not record.get("checked_at") or not record.get("method")):
                raise ValueError(f"{item['id']}: require passing QA for all pages with method/time")
            item["visual_review"] = record
    derive_status(manifest)
    sync_locations(root, manifest)
    write_reports(root, manifest)
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("inventory")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p = subs.add_parser("build")
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    p = subs.add_parser("finalize")
    p.add_argument("--package", required=True)
    p.add_argument("--qa", required=True)
    args = parser.parse_args()
    if args.command == "inventory":
        result = inventory(args.input, args.out)
        print(json.dumps({"files": len(result["files"]), "inventory": str(Path(args.out).resolve() / "inventory.json")},
                         ensure_ascii=False))
    else:
        result = build(args.plan, args.out) if args.command == "build" else finalize(args.package, args.qa)
        print(json.dumps({"status": result["status"], "outputs": len(result["outputs"]),
                          "blockers": len(result["blockers"]), "pending": len(result["pending"])},
                         ensure_ascii=False))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(plain_error(exc), file=sys.stderr)
        sys.exit(2)

