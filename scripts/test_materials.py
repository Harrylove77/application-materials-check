"""Synthetic regression tests; no real student files or school rules."""
import copy
import io
import os
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

import materials as m

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("MATERIALS_TEST_TMPDIR"))
        self.root = Path(self.temp.name)
        self.a = self.root / "a.pdf"
        self.b = self.root / "b.pdf"
        self.pdf(self.a, ["AWARD FIRST", "AWARD SECOND"])
        self.pdf(self.b, ["INTERNSHIP THIRD"])

    def tearDown(self):
        self.temp.cleanup()

    def pdf(self, path, texts, form=False):
        doc = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
        for text in texts:
            doc.drawString(50, 770, text)
            if form:
                doc.acroForm.textfield(name="student", x=50, y=700, width=200, height=20)
            doc.showPage()
        doc.save()

    def plan(self):
        return {
            "target": {"applicant": "Lin Example", "university": "FICTIONAL University",
                       "programme": "MSc Fictional", "intake": "2027 / TEST ONLY"},
            "sources": [{"id": "S1", "title": "Synthetic test rule, not a school",
                         "local_path": "fixture", "locator": "fixture section",
                         "checked_at": m.now(), "intake_scope": "TEST ONLY",
                         "authority": "synthetic", "verified": True}],
            "requirements_coverage": {"complete": True, "note": "TEST ONLY"},
            "requirements": [{"id": "R1", "label": "获奖证明", "obligation": "required",
                              "channel": "applicant_upload", "verification": "verified",
                              "source_ids": ["S1"], "output_ids": ["O1"],
                              "details": {"accepted_formats": ["pdf"]}, "checks": []}],
            "outputs": [{"id": "O1", "filename": "LinExample_FictionalU_Awards.pdf",
                         "bucket": "upload", "slot": "Awards", "inputs": [{"path": str(self.a)}],
                         "limit": {"max_bytes": 1_000_000, "comparator": "lt",
                                   "verification": "verified", "source_ids": ["S1"],
                                   "original": "TEST <1,000,000 bytes"}}],
            "aggregate_limits": [],
            "review": {"status": "complete", "coverage": ["fixture PDF all pages"],
                       "limitations": ["synthetic test; not a real application"]},
            "findings": []
        }

    def build(self, plan, folder="package"):
        path = self.root / (folder + ".json")
        m.write_json(path, plan)
        return m.build(path, self.root / folder)

    def qa(self, manifest):
        return {"outputs": [{"id": item["id"], "sha256": item["sha256"],
                             "status": "pass", "pages_checked": list(range(1, item["pages"]+1)),
                             "method": "synthetic fixture QA", "checked_at": m.now()}
                            for item in manifest["outputs"] if item["generated"]]}

    def test_unchanged_copy_and_final_move(self):
        plan = self.plan()
        result = self.build(plan)
        item = result["outputs"][0]
        self.assertEqual(item["sha256"], m.sha(self.a))
        self.assertEqual(item["operation"], "byte_copy")
        self.assertEqual(result["status"], "尚未完成核验")
        self.assertTrue((self.root / "package" / "review" / item["filename"]).exists())
        qa = self.root / "qa.json"
        m.write_json(qa, self.qa(result))
        final = m.finalize(self.root / "package", qa)
        self.assertEqual(final["status"], "本地材料核对就绪")
        self.assertEqual(final["outputs"][0]["path"], str(Path("upload") / item["filename"]))
        self.assertEqual(m.sha(self.root / "package" / final["outputs"][0]["path"]), m.sha(self.a))
        receipt = self.root / "package" / "report" / "receipt.md"
        self.assertTrue(receipt.exists())
        self.assertFalse(receipt.with_suffix(".pdf").exists())

    def test_merge_order_page_map_and_source_immutability(self):
        plan = self.plan()
        plan["outputs"][0]["inputs"] = [{"path": str(self.b)}, {"path": str(self.a)}]
        before = {p: m.sha(p) for p in [self.a, self.b]}
        result = self.build(plan)
        item = result["outputs"][0]
        reader = PdfReader(str(self.root / "package" / item["path"]))
        self.assertEqual(item["pages"], 3)
        self.assertEqual([p.extract_text().strip() for p in reader.pages],
                         ["INTERNSHIP THIRD", "AWARD FIRST", "AWARD SECOND"])
        self.assertEqual([(s["output_start_page"], s["output_end_page"]) for s in item["sources"]],
                         [(1, 1), (2, 3)])
        self.assertEqual(before, {p: m.sha(p) for p in [self.a, self.b]})

    def test_missing_optional_external_and_unknown_condition(self):
        plan = self.plan()
        for rid, label, obligation, channel in [
            ("R2", "成绩单", "required", "applicant_upload"),
            ("R3", "可选论文", "optional", "applicant_upload"),
            ("R4", "推荐信", "required", "referee_direct"),
            ("R5", "条件材料", "conditional", "applicant_upload")]:
            plan["requirements"].append({"id": rid, "label": label, "obligation": obligation,
                                         "channel": channel, "applicability": "unknown" if rid == "R5" else "applied",
                                         "verification": "verified", "source_ids": ["S1"],
                                         "output_ids": [], "manual_status": "pending"})
        result = self.build(plan)
        statuses = {r["id"]: r["status"] for r in result["checklist"]}
        self.assertEqual(statuses["R2"], "缺件")
        self.assertEqual(statuses["R3"], "未提供（可选）")
        self.assertEqual(statuses["R4"], "渠道待办")
        self.assertEqual(statuses["R5"], "适用条件待确认")
        self.assertFalse(any("可选论文" in x for x in result["blockers"]))
        self.assertTrue(any("非本地PDF缺件" in x for x in result["blockers"]))

    def test_high_risk_never_becomes_ready(self):
        plan = self.plan()
        plan["findings"] = [{"id": "F1", "severity": "high", "certainty": "confirmed_conflict",
                             "title": "文书错校名", "evidence": [], "output_ids": ["O1"],
                             "action": "Check target", "resolved": False}]
        result = self.build(plan)
        qa = self.root / "qa.json"
        m.write_json(qa, self.qa(result))
        final = m.finalize(self.root / "package", qa)
        self.assertEqual(final["status"], "待补件或处理")
        self.assertIn("review", final["outputs"][0]["path"])

    def test_stale_or_partial_qa_is_rejected_before_mutation(self):
        result = self.build(self.plan())
        qa = self.root / "qa.json"
        record = self.qa(result)
        record["outputs"][0]["pages_checked"] = [1]
        m.write_json(qa, record)
        report = self.root / "package" / "report" / "manifest.json"
        before = report.read_bytes()
        with self.assertRaises(ValueError):
            m.finalize(self.root / "package", qa)
        self.assertEqual(before, report.read_bytes())
        record = self.qa(result)
        record["outputs"][0]["sha256"] = "0" * 64
        m.write_json(qa, record)
        with self.assertRaises(ValueError):
            m.finalize(self.root / "package", qa)
        m.write_json(qa, self.qa(result))
        path = self.root / "package" / result["outputs"][0]["path"]
        path.write_bytes(path.read_bytes() + b"\n% changed")
        with self.assertRaises(ValueError):
            m.finalize(self.root / "package", qa)
        self.assertEqual(before, report.read_bytes())

    def test_size_boundaries_aggregate_and_file_count(self):
        self.assertFalse(m.check_limit(1000, {"max_bytes": 1000, "comparator": "lt"}))
        self.assertTrue(m.check_limit(1000, {"max_bytes": 1000, "comparator": "le"}))
        plan = self.plan()
        plan["aggregate_limits"] = [{"label": "TOTAL TEST", "max_bytes": 100, "comparator": "lt",
                                     "slots": ["Awards"], "max_files": 0, "verification": "verified",
                                     "source_ids": ["S1"]}]
        result = self.build(plan)
        self.assertTrue(any("合计大小超限" in x for x in result["blockers"]))
        self.assertTrue(any("文件数量超限" in x for x in result["blockers"]))
        plan["outputs"][0]["limit"]["max_bytes"] = 100
        result = self.build(plan, "single-limit")
        self.assertIn("单件大小超限", result["outputs"][0]["technical_issues"])

    def test_protected_forms_refuse_merge_but_copy_identically(self):
        form = self.root / "form.pdf"
        self.pdf(form, ["FORM DOCUMENT"], form=True)
        plan = self.plan()
        plan["outputs"][0]["inputs"] = [{"path": str(form)}]
        result = self.build(plan)
        self.assertEqual(result["outputs"][0]["sha256"], m.sha(form))
        self.assertTrue(result["outputs"][0]["protected"])
        plan["outputs"][0]["inputs"].append({"path": str(self.a)})
        result = self.build(plan, "merge-form")
        self.assertFalse(result["outputs"][0]["generated"])
        self.assertIn("拒绝合并", result["outputs"][0]["error"])

    def test_failure_is_partial_and_encryption_not_removed(self):
        encrypted = self.root / "encrypted.pdf"
        writer = PdfWriter()
        writer.add_page(PdfReader(str(self.b)).pages[0])
        writer.encrypt("test-password")
        with encrypted.open("wb") as stream:
            writer.write(stream)
        corrupt = self.root / "corrupt.pdf"
        corrupt.write_bytes(b"not a PDF")
        plan = self.plan()
        for i, path in enumerate([encrypted, corrupt], 2):
            spec = copy.deepcopy(plan["outputs"][0])
            spec.update(id=f"O{i}", filename=f"Failure_{i}.pdf", inputs=[{"path": str(path)}])
            plan["outputs"].append(spec)
        before = m.sha(encrypted)
        result = self.build(plan)
        self.assertEqual([o["generated"] for o in result["outputs"]], [True, False, False])
        self.assertTrue(PdfReader(str(encrypted)).is_encrypted)
        self.assertEqual(m.sha(encrypted), before)
        self.assertEqual(result["status"], "待补件或处理")

    def test_images_multiframe_and_orientation(self):
        image = self.root / "证书.tiff"
        Image.new("RGB", (300, 500), "white").save(
            image, save_all=True, append_images=[Image.new("RGB", (600, 400), "white")])
        plan = self.plan()
        plan["outputs"][0]["inputs"] = [{"path": str(image)}]
        result = self.build(plan)
        item = result["outputs"][0]
        reader = PdfReader(str(self.root / "package" / item["path"]))
        self.assertEqual(len(reader.pages), 2)
        self.assertLess(float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height))
        self.assertGreater(float(reader.pages[1].mediabox.width), float(reader.pages[1].mediabox.height))

    def test_traversal_reserved_names_and_overwrite(self):
        for name in ["../escape.pdf", "CON.pdf", "a/b.pdf", "a.pdf ", "a:stream.pdf"]:
            plan = self.plan()
            plan["outputs"][0]["filename"] = name
            with self.assertRaises(ValueError):
                m.validate_plan(plan)
        self.build(self.plan())
        with self.assertRaises(FileExistsError):
            self.build(self.plan())
        self.assertFalse((self.root.parent / "escape.pdf").exists())

    def test_unknown_rules_manual_checks_and_native_formats(self):
        plan = self.plan()
        plan["outputs"][0]["limit"]["verification"] = "unknown"
        plan["requirements"][0]["checks"] = [{"label": "语言", "status": "unknown"}]
        result = self.build(plan)
        self.assertTrue(any("单件容量" in x for x in result["pending"]))
        self.assertTrue(any("语言" in x for x in result["pending"]))
        plan["requirements"][0]["details"]["accepted_formats"] = ["jpg"]
        result = self.build(plan, "wrong-format")
        self.assertTrue(any("不接受PDF" in x for x in result["blockers"]))
        plan["requirements"][0]["checks"] = [{"label": "字数", "status": "fail", "note": "test"}]
        result = self.build(plan, "word-check")
        self.assertTrue(any("字数" in x for x in result["blockers"]))

    def test_inventory_tracks_low_text_duplicate_and_docx_revisions(self):
        inputs = self.root / "student"
        inputs.mkdir()
        self.pdf(inputs / "scan.pdf", [""])
        (inputs / "same.pdf").write_bytes((inputs / "scan.pdf").read_bytes())
        docx = inputs / "statement.docx"
        with zipfile.ZipFile(docx, "w") as package:
            package.writestr("word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>Test Name</w:t></w:r></w:p>'
                '<w:p><w:ins><w:r><w:t>EDIT</w:t></w:r></w:ins></w:p></w:body></w:document>')
        result = m.inventory(inputs, self.root / "inv")
        self.assertEqual(len(result["byte_identical_groups"]), 1)
        docs = {f["relative_path"]: f for f in result["files"]}
        self.assertEqual(docs["scan.pdf"]["low_text_pages"], [1])
        self.assertEqual(docs["statement.docx"]["tracked_changes"], 1)
        with self.assertRaises(ValueError):
            m.inventory(inputs, inputs / "bad")
        self.assertTrue((inputs / "statement.docx").exists())


    def test_invalid_statuses_and_source_booleans_rejected(self):
        plan = self.plan()
        plan["sources"][0]["verified"] = "false"
        with self.assertRaises(ValueError):
            m.validate_plan(plan)
        plan = self.plan()
        plan["requirements"][0]["applicability"] = "maybe"
        with self.assertRaises(ValueError):
            m.validate_plan(plan)

    def test_optional_unprovided_unknown_checks_do_not_block(self):
        plan = self.plan()
        plan["requirements"].append({
            "id": "OPTIONAL", "label": "可选材料", "obligation": "optional",
            "channel": "applicant_upload", "verification": "unknown",
            "source_ids": [], "output_ids": [],
            "checks": [{"label": "尚未提供材料的字数", "status": "unknown"}]})
        result = self.build(plan)
        qa = self.root / "qa.json"
        m.write_json(qa, self.qa(result))
        final = m.finalize(self.root / "package", qa)
        self.assertEqual(final["status"], "本地材料核对就绪")

    def test_confirmed_direct_channel_needs_evidence(self):
        plan = self.plan()
        plan["requirements"].append({
            "id": "DIRECT", "label": "直送报告", "obligation": "required",
            "channel": "referee_direct", "verification": "verified",
            "source_ids": ["S1"], "output_ids": [], "manual_status": "confirmed"})
        result = self.build(plan)
        self.assertEqual(result["checklist"][-1]["status"], "渠道待办")
        plan["requirements"][-1]["manual_evidence"] = ["Synthetic portal fixture: 2 received of 2"]
        result = self.build(plan, "with-evidence")
        self.assertEqual(result["checklist"][-1]["status"], "渠道已核对完成")

    def test_move_conflict_does_not_move_any_files(self):
        result = self.build(self.plan())
        item = result["outputs"][0]
        destination = self.root / "package" / "upload" / item["filename"]
        destination.write_bytes(b"User file must not be overwritten")
        qa = self.root / "qa.json"
        m.write_json(qa, self.qa(result))
        with self.assertRaises(FileExistsError):
            m.finalize(self.root / "package", qa)
        self.assertTrue((self.root / "package" / item["path"]).exists())
        self.assertEqual(destination.read_bytes(), b"User file must not be overwritten")


    def test_receipt_covers_present_and_missing_materials_in_table(self):
        plan = self.plan()
        plan["requirements"].append({
            "id": "TRANSCRIPT", "label": "正式成绩单", "obligation": "required",
            "channel": "applicant_upload", "verification": "verified",
            "source_ids": ["S1"], "output_ids": []})
        result = self.build(plan)
        text = (self.root / "package/report/receipt.md").read_text(encoding="utf-8")
        self.assertEqual([line for line in text.splitlines() if line.startswith("## ")],
                         ["## 一、材料检查", "## 二、提醒"])
        table = text.split("## 二、提醒")[0]
        self.assertIn("| 获奖证明 |", table)
        self.assertIn("| 正式成绩单 | 必交 / 缺件 |", table)
        self.assertFalse((self.root / "package/report/receipt.pdf").exists())

    def test_english_proof_stays_material_and_esending_stays_current_workflow(self):
        plan = self.plan()
        plan["requirements"].extend([
            {"id":"SCORE", "label":"英语正式报告", "obligation":"required",
             "channel":"applicant_upload", "verification":"verified",
             "source_ids":["S1"], "output_ids":[]},
            {"id":"SEND", "label":"电子送分", "obligation":"required", "stage":"application",
             "channel":"test_agency", "verification":"verified",
             "source_ids":["S1"], "output_ids":[], "manual_status":"pending"}])
        result = self.build(plan)
        text = (self.root / "package/report/receipt.md").read_text(encoding="utf-8")
        table, reminders = text.split("## 二、提醒")
        self.assertIn("| 英语正式报告 | 必交 / 缺件 |", table)
        self.assertNotIn("| 电子送分 |", table)
        self.assertIn("【申请阶段】电子送分", reminders)
        self.assertTrue(any("电子送分" in e for e in result["blockers"]))

    def test_after_offer_material_and_risk_do_not_block_current_readiness(self):
        plan = self.plan()
        plan["requirements"].append({
            "id":"FINAL", "label":"最终毕业证", "obligation":"required", "stage":"after_offer",
            "channel":"applicant_upload", "verification":"unknown", "source_ids":[], "output_ids":[]})
        plan["findings"].append({
            "id":"FUTURE", "title":"入学前需更新证件", "severity":"high", "stage":"registration",
            "output_ids":["O1"], "action":"入学前按学校要求更新", "resolved":False})
        result = self.build(plan)
        qa = self.root / "qa.json"
        m.write_json(qa, self.qa(result))
        final = m.finalize(self.root / "package", qa)
        self.assertEqual(final["status"], "本地材料核对就绪")
        text = (self.root / "package/report/receipt.md").read_text(encoding="utf-8")
        table, reminders = text.split("## 二、提醒")
        self.assertNotIn("| 最终毕业证 |", table)
        self.assertNotIn("入学前需更新证件", table)
        self.assertIn("【获录取后】最终毕业证", reminders)
        self.assertIn("【注册/入学前】入学前需更新证件", reminders)

    def test_round_reminders_preserve_verified_time_and_condition(self):
        plan = self.plan()
        plan["reminders"] = [{
            "title":"示例第一轮", "stage":"application", "due_at":"2099-01-01 12:00",
            "time_zone":"Asia/Hong_Kong", "condition":"FICTIONAL programme only",
            "action":"完成本轮要求", "source_ids":["S1"]}]
        self.build(plan)
        text = (self.root / "package/report/receipt.md").read_text(encoding="utf-8")
        reminders = text.split("## 二、提醒")[1]
        self.assertIn("2099-01-01 12:00（Asia/Hong_Kong）", reminders)
        self.assertIn("FICTIONAL programme only", reminders)
        self.assertTrue(all(not line.startswith("|") for line in reminders.splitlines()))

    def test_table_escapes_content_and_preserves_actionable_evidence(self):
        plan = self.plan()
        plan["requirements"][0]["comment"] = "需确认 A | B <script>"
        plan["findings"] = [{
            "id":"F1", "title":"日期需确认", "severity":"medium", "certainty":"needs_confirmation",
            "output_ids":["O1"], "evidence":[{"file":"cv.pdf", "locator":"第2页", "excerpt":"June 2025"}],
            "action":"请核对实际开始月份", "resolved":False}]
        self.build(plan)
        text = (self.root / "package/report/receipt.md").read_text(encoding="utf-8")
        self.assertIn("A &#124; B &lt;script&gt;", text)
        self.assertIn("cv.pdf 第2页 June 2025", text)
        self.assertIn("请核对实际开始月份", text)

    def test_pdf_receipt_requires_explicit_opt_in(self):
        plan = self.plan()
        plan["receipt_pdf"] = True
        self.build(plan)
        path = self.root / "package/report/receipt.pdf"
        self.assertTrue(path.is_file())
        content = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
        self.assertIn("材料检查", content)
        self.assertIn("提醒", content)
        self.assertIn("获奖证明", content)

if __name__ == "__main__":
    unittest.main()

