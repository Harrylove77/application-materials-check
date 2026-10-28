# 官网要求核验

## 检索与证据

以正式校名、校区、项目、年份和 supporting documents / application checklist / upload file size / applicant guide 搜索。中文“港科”区分香港科技大学香港校区与广州校区；NUS/NTU需落实校名。UK区分校方直申、UCAS及其他系统。

先读项目页，再读其引用的学院/大学规则、申请系统指南。官方外包系统需核实项目官网跳转。中介/论坛只用作发现入口。原站403、无正文或只有搜索摘要时，记入口和访问受限，继续找官方替代来源或请求截图，不标已核验。

每条要求字段：
id, document_type, obligation, applicability, channel, upload_slot, accepted_formats, max_file_size, max_total_size, count, pages, words, naming, language, certification, translation_pairing, deadline, verification, source_ids, note。

obligation = required / conditional / optional / not_requested / prohibited。
条件记录 applied / not_applicable / unknown 及依据。
channel 区分 applicant_upload、referee_direct、institution_direct、test_agency、online_text、native_format、later_stage。

来源保存 id, title, url（或截图local_path）, locator, checked_at, intake_scope, authority, verified, note。保存最短必要短引句或准确转述，不复制整页。日期用用户时区。

## 必须区分

- 单件大小、槽位合计、整个申请合计；建议值与硬性上限；上传文件数。
- 小于与小于等于；MB/MiB。无定义时保留原文，处理可保守按1MB=1,000,000字节并留余量，说明这是处理假设，不能冒充官方定义。压缩目标另记。
- 在读/已毕业、转学/交换/联合学位、多份成绩单、认证译文配原文、雇主/奖项是否逐件上传。
- 申请与录取后核验/签证/注册的阶段。直送材料没有本地PDF不自动是缺件；有本地PDF也不等于已经送达。
- 文书PDF与在线文本/单独短答；已有PS不代表回答全部问题。
- 字数计算范围、脚注/参考文献。仅PDF提取词数不一定准确，不确定写计数口径。
- 某槽位不接受PDF时，PDF只是整理副本，规定格式另保留并标注提交待办。
- 未要求不等于禁止；二者均不混入默认上传包。必要性不明记待确认。

## 冲突与未知

比较对象、阶段、年份、系统、更新日期；不同范围可能同时成立。同一范围冲突须列出双方，保守预整理，并等待当前项目/系统证据。禁止按固定来源优先级隐去冲突。未知写unknown，不编“无限制”。

## 官方发现入口（开发查阅2026-10-28，不能直接套用）

每次运行仍须打开并核对适用版本。以下仅作入口，非院校限制数据库。

- HKUST香港校区：[Documents Required](https://fytgs.hkust.edu.hk/admissions/Admission-to-Hong-Kong-Campus/submitting-an-application/documents-required)、[2026/27研究型指南](https://fytgs.hkust.edu.hk/system/files/rpgtips202627.pdf)。开发时原站403，摘要有容量线索但不作为已确认数值，不能外推授课型或广州校区。
- NUS：[GDA3 Applicant Guide, 10 Dec 2025](https://nusgs.nus.edu.sg/wp-content/uploads/2025/12/GDA3-Applicant-User-Guide-10-Dec-2025.pdf)、[研究生院FAQ](https://nusgs.nus.edu.sg/admissions/faq/)。指南明确不同项目界面要求不同，截图示例和旧FAQ可能不属同系统。正文抽取后也检查相关页面截图。
- Oxford：[Supporting documents requirements](https://www.ox.ac.uk/admissions/graduate/application-guide/supporting-documents/supporting-documents-requirements)。页面区分表单常规上传与大文件另传，材料清单由课程页确定，非英文成绩单需原文及译文，不能只留一个全校大小值。

其他港新英学校同样实时检索，不能因未列入入口而停止。学生信息及任务特定要求只写该次工作区，不回写通用技能。

