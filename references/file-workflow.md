# 文件处理协议

## 环境和调用

Python 3.10+及 scripts/requirements.txt 的依赖；优先用宿主现成解释器。缺依赖时按环境许可安装，不能承诺没有的转换/OCR能力。只有调用模型及其搜索工具才能执行官网研究/逻辑审读，materials.py不是独立的招生规则爬虫。

在本技能根目录调用（python替换为可用解释器；所有路径按真实路径替换）：

```text
python scripts/materials.py inventory --input STUDENT_INPUT_DIR --out WORK_DIR/inventory-run1
python scripts/materials.py build --plan WORK_DIR/plan.json --out USER_OUTPUT_DIR/School_Programme_Intake_Run1
python scripts/materials.py finalize --package USER_OUTPUT_DIR/School_Programme_Intake_Run1 --qa WORK_DIR/qa.json
python -m unittest discover -s scripts -p test_materials.py
```

inventory输出目录必须在输入树之外且不存在。build只写新目录，不覆盖旧包。输入相对路径以plan.json所在文件夹为基准，不以终端目录为基准。build生成后仍需真实审读与渲染；finalize只确认QA声明与已生成文件匹配，不会自动看页面或检查逻辑。修正文书/要求/计划后新建一批，不直接改manifest骗过核验。

包结构：
- upload/：只有整包检查就绪后才放入的待上传PDF。
- review/：未复核、有风险、超限、其他整体待办存在时的PDF；即使已通过单件检查也须看回执。
- reference/：学校未要求/不接受的整理副本。
- report/：默认receipt.md、requirements.json、manifest.json；用户明确要求时另存receipt.pdf。最终对话直接展示完整两模块回执，不能只给文件链接。回执不混入待上传目录。

## 计划示例（全部为虚构演示，大小不是任何学校规则）

仅展示数据结构；真实任务必须替换目标、来源、要求、文件及审读结论。manifest同时保留完整plan及每件输出来源哈希，对话/Markdown回执仅写必要文件名和页码，避免披露完整个人信息。

```json
{
  "receipt_pdf": false,
  "target": {
    "applicant": "Lin Example",
    "university": "Example University",
    "campus": "Example Campus",
    "programme": "MSc Example",
    "level": "taught-master",
    "intake": "2027 September",
    "round": "Round 1"
  },
  "sources": [{
    "id": "S1",
    "title": "当前项目申请材料页面",
    "url": "https://example.edu/programme/application",
    "locator": "Supporting documents / Upload",
    "checked_at": "2026-10-28T15:00:00+08:00",
    "intake_scope": "MSc Example / 2027 / initial application",
    "authority": "official",
    "verified": false,
    "note": "虚构结构示例，真实使用需打开目标官方页面"
  }],
  "requirements_coverage": {
    "complete": false,
    "note": "尚未取得实际项目要求；不能将示例标成已核验"
  },
  "unresolved_requirements": ["等待当前项目的上传容量说明"],
  "requirements": [{
    "id": "R1",
    "label": "实习证明",
    "obligation": "conditional",
    "applicability": "applied",
    "condition_note": "学生申报实习经历",
    "channel": "applicant_upload",
    "verification": "unknown",
    "source_ids": ["S1"],
    "output_ids": ["O1"],
    "deadline": "待核实",
    "details": {
      "accepted_formats": ["pdf"],
      "upload_slot": "Employment evidence",
      "language": "待核实",
      "certification": "待核实",
      "merge_rule": "本示例按同类合并，真实任务须核实槽位"
    },
    "checks": [
      {"label": "每段经历证明对应", "status": "unknown", "note": "待阅读"},
      {"label": "语言及认证要求", "status": "unknown", "note": "待官网核验"}
    ]
  }, {
    "id": "R2",
    "label": "推荐人报告",
    "obligation": "required",
    "applicability": "applied",
    "channel": "referee_direct",
    "manual_status": "pending",
    "verification": "unknown",
    "source_ids": ["S1"],
    "output_ids": [],
    "note": "无本地PDF不等于缺件；需核对该渠道状态和要求数量"
  }],
  "outputs": [{
    "id": "O1",
    "filename": "LinExample_ExampleU_MScExample_Internships.pdf",
    "bucket": "upload",
    "slot": "Employment evidence",
    "inputs": [
      {"path": "converted/internship_a.pdf", "origin": "original/internship_a.docx",
       "conversion_note": "本地Word保留版式导出，原件未修改"},
      {"path": "original/internship_b.png"}
    ],
    "limit": {
      "max_bytes": null,
      "comparator": "le",
      "original": "单件限制未公开/待核实",
      "verification": "unknown",
      "source_ids": ["S1"],
      "note": "未知不是无限制"
    },
    "max_pages": null
  }],
  "aggregate_limits": [],
  "review": {
    "status": "partial",
    "coverage": ["待逐件审读"],
    "limitations": ["未提供申请表，无法与网申所填内容对照"]
  },
  "findings": [{
    "id": "F1",
    "severity": "medium",
    "certainty": "needs_confirmation",
    "title": "需确认实习起止差异",
    "evidence": [
      {"file": "cv.pdf", "locator": "第1页 实习A", "excerpt": "2025.06-2025.08"},
      {"file": "internship_a.pdf", "locator": "第1页", "excerpt": "2025.07-2025.08"}
    ],
    "impact": "同一经历出现不同起始月份",
    "action": "学生确认实际起始时间及证明覆盖范围后再决定是否修CV",
    "output_ids": ["O1"],
    "resolved": false
  }]
}
```

## 字段约束

- sources的verified只在真实打开适用原文/截图后置true；需要当前年份及项目适用性。requirements.verification为verified / unknown / conflict。
- requirements_coverage.complete指已核查材料种类和适用范围。公开未规定的条款可以记“官网未公开”，有关键登录后限制未查清则complete=false，列入unresolved_requirements。
- required及conditional/applied才算必交。conditional/unknown是条件待确认。optional未提供不判缺件。not_requested/prohibited不放upload。
- 对推荐人/学校/考试机构直送、在线文本及原生格式，用对应channel及manual_status=confirmed/pending/unknown。confirmed必须附manual_evidence（可追溯页面/截图或学生明确确认的状态），并核对数量，不能仅凭本地文件代替。details注明非PDF格式与所需份数。
- requirements.checks保存脚本无法验证的题目、字数口径、页数例外、语言、认证等逐项判断，status=pass/fail/unknown及证据说明；未公开写unknown及解释，不能用空列表掩盖已知要求。
- upload输出必须关联适用的材料要求。accepted_formats用扩展名列表，如pdf/jpg；只接收原生格式的要求使用native_format渠道，PDF副本放reference。
- outputs.inputs按输出页序排列，脚本不支持挑页/删页。不允许重复哈希自动丢文件；盘点提示后由实际内容决定。origin为转换前文件，可为路径或文件名；保留转换前文件哈希到工作记录。
- bucket=upload/review/reference。filename须合法且全包唯一，以.pdf结尾；学校命名规则可用naming_regex全匹配，max_pages可作已核验页数上限。限制证据也应写到要求details/checks。
- limit.max_bytes是硬性容量的字节值，不填建议容量；comparator=lt/le，original存官方原文/准确转述。verification=verified/unknown/not_published；source_ids列证据。官方没定义MB时note说明保守换算，压缩目标可另写note，不篡改硬性值。
- aggregate_limits项格式与limit类似，另有label、slots（字符串数组；省略为全部upload输出）、max_files（可选）。可用多个项检查单槽位数量、跨槽位合计及总申请大小。例如经核验后设slots=["Employment evidence"]、max_files=1。建议值只记note。
- 普通单份PDF若未超限逐字节复制；超限可尝试内容流无损压缩，不保证显著缩小。图像转PDF默认不降采样，可设置image_max_px（长边像素，下限1200），但每页必须比较小字、二维码及印章。脚本不栅格化PDF，不做有损PDF图像压缩；需要时用可用工具处理普通扫描副本并重新验证。
- 签名/认证/交互表单拒绝多文件合并。单件默认复制但可能超限，报告障碍。加密文件不移除保护，无法读取则输出失败记录；允许用户解锁副本后重跑。
- review.status=complete仅在实际读完可用材料且完成跨文件核对时设置；coverage记录文件/页段，limitations列仍缺的输入。高风险未解决不因status=complete而变就绪。
- findings按consistency-review协议保存，确认冲突有两处证据，resolved需resolution依据。未指定output_ids的高风险视为全包风险。

## QA协议

先实际渲染检查最终文件，读取manifest中的真实sha256、页数及路径。用如下结构逐个记录，不凭空填“通过”：

```json
{
  "outputs": [{
    "id": "O1",
    "sha256": "填写实际输出哈希",
    "status": "pass",
    "pages_checked": [1, 2],
    "method": "最终PDF逐页渲染，与来源比对方向、顺序、清晰度和完整性",
    "checked_at": "2026-10-28T16:00:00+08:00"
  }]
}
```

未检查的输出不填QA，不强行finalize为就绪。脚本会拒绝哈希变动或页码未覆盖；所有PDF在有缺件/高风险/关键未核验时仍保留review，直到一批新包真正完成核验。仅用户要求导出回执PDF时才对它渲染审查，不循环要求其哈希写入自身；默认Markdown底稿须在最终对话直接展示。

## DOCX转换

Windows有Microsoft Word时：

```text
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/convert_word.ps1 -InputFile INPUT.docx -OutputFile WORK_DIR/converted.pdf
```

脚本禁用宏、只读打开，不保存源文件，发现批注/修订拒绝导出，避免静默选定版本；使用Word真实版式。没有Word或COM访问被拒，则尝试可用的LibreOffice或已获准的本地界面导出工具；仍不可用时如实记录未转换。导出后必须检查字体、页数、分页、页眉页脚和表格，不能只看命令退出码。PDF含复杂保护时，检测是保守拦截，不等于验证其数字签名有效性。

## 失败与交付

部分文件失败不会阻止其余输出，回执记录失败原因。缺依赖、无法解锁、缺转换器、需要人工辨认均记录具体缺口，不伪造可提交文件。修订plan后新建批次；禁止覆盖原件、上一批或已导出文件。


## 回执与阶段字段

按[回执格式](receipt-format.md)生成材料表格和非表格提醒。

- requirements.stage / findings.stage：application（默认）、after_offer、registration、post_arrival；后续条目不作当前缺件或当前风险阻碍。
- requirements.kind：material / workflow；省略时test_agency、online_text、later_stage默认workflow，其余默认material。
- requirements.comment：简洁点评；详细依据留note、checks、findings。
- plan.reminders：时间/流程提醒数组，例如：

```json
{
  "reminders": [{
    "title": "本轮申请截止",
    "stage": "application",
    "due_at": "填经官网核验的日期及时间；未知写待核实",
    "time_zone": "填官网时区；未公开不猜测",
    "condition": "具体项目和轮次",
    "action": "在适用截止时点前完成所需材料和流程",
    "source_ids": ["S1"],
    "status": "待核实"
  }],
  "receipt_pdf": false
}
```

报告默认仅存Markdown和JSON。用户明确要求PDF时设receipt_pdf=true，导出同样表格与提醒并渲染检查。后续提醒不阻止当前就绪，但申请阶段的必要送分/在线事项仍须核对，不能因放入提醒而豁免。

最终对话展示核对后的完整receipt.md；状态在表格前简写，输出链接放两模块后。不要把哈希、解析日志或长篇摘录打印成第三个附录。
