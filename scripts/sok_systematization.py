#!/usr/bin/env python3
"""Validate source links and render the manually synthesized SoK literature table.

This checks traceability, not the truth of interpretations, and never assigns
taxonomy labels, changes author answers, or computes E0 agreement statistics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/sok/e0-current/analysis/systematization.json"
OUTPUT = SOURCE.with_suffix(".md")
LATEX_OUTPUT = SOURCE.parent / "systematization-table.tex"
PAPER = ROOT / "paper-sok-csur"
COMPACT_SOURCE = PAPER / "supplement/systematization.csv"
COMPACT_OUTPUT = PAPER / "tables/systematization-table.tex"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text())


def validate(data: dict) -> dict:
    inputs = data["inputs"]
    for name in ("unit_inventory", "citation_map"):
        path = ROOT / inputs[name]
        assert digest(path) == inputs[name + "_sha256"], f"Input changed: {path}"
    units = read(ROOT / inputs["unit_inventory"])["unit_inventory"]
    citations = read(ROOT / inputs["citation_map"])["records"]
    cm = {x["record_id"]: x for x in citations}
    groups = defaultdict(list)
    for unit in units:
        groups[unit["group"]].append(unit)
    rows = data["rows"]
    assert len(rows) == len({r["family"] for r in rows})
    assert set(groups) == {r["family"] for r in rows}, "Family coverage differs"
    assert len(rows) == data["required_family_count"] == data["prepared_family_count"] == 132
    assert "RG126" not in groups
    source_cache = {}
    evidence_count = 0
    for row in rows:
        group = row["family"]
        us = groups[group]
        assert row["title"] == us[0]["title"], group
        assert row["unit_ids"] == [u["id"] for u in us], group
        record_ids = sorted({r for u in us for r in u["records"]})
        assert row["record_ids"] == record_ids, group
        assert row["citation_keys"] == sorted({cm[r]["bibkey"] for r in record_ids}), group
        assert row["interfaces"] and len(row["interfaces"]) == len(set(row["interfaces"]))
        assert set(row["interfaces"]) <= {"selection", "generation", "computation", "unspecified"}, group
        assert set(row["check_ownership"]) == {"observation_state", "joint_feasibility", "candidate_coverage"}
        for evidence in row["evidence"]:
            assert evidence["record_id"] in record_ids, (group, evidence)
            allowed = {e["path"] for e in cm[evidence["record_id"]]["inspected_evidence"]}
            assert evidence["path"] in allowed, (group, evidence)
            path = ROOT / evidence["path"]
            if path not in source_cache:
                source_cache[path] = (digest(path), len(path.read_text()))
            sha, length = source_cache[path]
            assert sha == evidence["sha256"], (group, path)
            assert 0 <= evidence["start"] < evidence["end"] <= length, (group, evidence)
            assert evidence["coordinate_system"] == "Unicode characters in saved text"
            evidence_count += 1
    return {
        "status": "traceability_checks_passed",
        "family_count": len(rows),
        "source_record_count": len({r for row in rows for r in row["record_ids"]}),
        "citation_key_count": len({r for row in rows for r in row["citation_keys"]}),
        "unit_scope_count": len(units),
        "additional_text_spans": evidence_count,
        "additional_source_files": len(source_cache),
        "interpretive_scope": "Assistant synthesis; not newly independently dual-coded or a full re-audit of all paper facts.",
        "source_sha256": digest(SOURCE),
    }


def cell(value: str | None) -> str:
    return (value or "—").replace("|", "\\|").replace("\n", " ")


def render(data: dict, check: dict) -> None:
    code = {"selection": "S", "generation": "G", "computation": "C", "unspecified": "?"}
    lines = [
        "# SoK 三轴文献总表：证据整理稿",
        "",
        "本表覆盖最终纳入的 **132 个论文家族、138 条来源/版本记录、137 条引用**，"
        "关联原有 **405 条证据范围**。它为导师提纲第4节准备文献体系化材料；"
        "仍待全文整合时按 Edge Orchestration 风格排版。",
        "",
        "这是助手对作者已核定任务/步骤和已保存原文的综合整理，**不是新增的双人编码字段**，"
        "不沿用 E0 的一致性系数，也不据此生成新的报告比例。原作者答案和 E0 统计未改。",
        "",
        "接口：S＝从给定备选中选择；G＝构造参数、描述、程序或其他内容；C＝规则、求解器或验证计算；"
        "?＝该范围的实现/接口尚无法确定。同一家族可以含多类接口；构造连续数值也不等于逐 token 文本生成。",
        "",
        "检查列分别对应观测状态、联合可行性与候选覆盖；每格的限定语是含义的一部分。"
        "“—”仅表示本次综合未建立明确归属，不能读成论文没有相应检查。结构/语法检查、"
        "模型判断、有限测试、正式证明及候选集内覆盖互不替代。功能位是分析映射，不代表标准合规认证。",
        "",
        "每行原始任务、步骤及章节范围可用 RG 编号在 [E0完整结果](results.json) 中查找；"
        "[引用映射](citation-map.json)保留来源网址。[机器可读整理稿](systematization.json)"
        "还保存针对性的原文字符位置和哈希。",
        "",
        f"追溯核对：132组无缺漏/重复，405范围对应一致；{check['additional_text_spans']}处补充原文片段、"
        f"{check['additional_source_files']}份原文的边界与哈希匹配。此项检查验证链接和身份，不自动验证解释的科学正确性。",
        "",
        "| 家族 / 文献 | 接口 | 功能位与控制/执行路径 | 观测状态检查 | 联合可行性或相关检查的范围 | 候选覆盖 | 证据边界 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in data["rows"]:
        ck = row["check_ownership"]
        title = row["family"] + ": " + row["title"]
        refs = "; ".join(row["citation_keys"])
        values = [
            title + "<br>" + refs,
            "/".join(code[i] for i in row["interfaces"]),
            row["functional_placement"] + ". " + row["control_and_execution"],
            ck["observation_state"], ck["joint_feasibility"], ck["candidate_coverage"],
            row["scope_notes"],
        ]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", "复现：`python3 scripts/sok_systematization.py --render`。只核对与渲染当前综合，不联网、不重新筛选、不修改编码。", ""]
    OUTPUT.write_text("\n".join(lines))


def tex(text: str) -> str:
    escapes = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
               "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
               "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(escapes.get(c, c) for c in text)


def render_latex(data: dict, check: dict) -> dict:
    """Preserve the complete synthesis, including scoped checks and row qualifiers."""
    import bibtexparser
    from bibtexparser.customization import splitname

    bib_path = ROOT / "paper-sok-csur/references.bib"
    entries = bibtexparser.loads(bib_path.read_text()).entries_dict
    codes = {"selection": "S", "generation": "G", "computation": "C", "unspecified": "U"}
    lines = [
        "% Generated by scripts/sok_systematization.py --latex; edit the evidence JSON, not this file.",
        "% Requires booktabs, array, longtable, xcolor[table], and the Edge palette.",
        "% Include in a full-width appendix (one-column flow) at the normal IEEE text width.",
        r"\begingroup\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\setlength{\aboverulesep}{0pt}\setlength{\belowrulesep}{0pt}",
        r"\renewcommand{\arraystretch}{1.08}",
        r"\setlength{\LTcapwidth}{\textwidth}",
        r"\newlength{\soklitwidth}\setlength{\soklitwidth}{\dimexpr\textwidth-8\tabcolsep\relax}",
        r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{.12\soklitwidth}"
        r">{\raggedright\arraybackslash}p{.31\soklitwidth}"
        r">{\raggedright\arraybackslash}p{.17\soklitwidth}"
        r">{\raggedright\arraybackslash}p{.23\soklitwidth}"
        r">{\raggedright\arraybackslash}p{.17\soklitwidth}@{}}",
        r"\caption{Three-axis systematization of 132 paper families. "
        r"S: selection from supplied alternatives; G: construction of values or artifacts; "
        r"C: deterministic computation; U: interface unspecified in the retained scope. "
        r"A family can contain several interfaces. Functional roles locate the reported control or execution path. "
        r"NE means that this synthesis did not establish explicit ownership of the check; it does not assert absence. "
        r"Scope statements distinguish proposed mechanisms, model judgments, finite tests, and formal verification.}"
        r"\label{tab:e0-systematization}\\",
        r"\toprule",
        r"\rowcolor{ebBlue} Work / interface & Functional role and control or execution path & "
        r"Observation state & Joint feasibility or related check & Candidate coverage \\",
        r"\midrule\endfirsthead",
        r"\caption[]{Three-axis systematization (continued). S: selection; G: construction; "
        r"C: computation; U: unspecified; NE: ownership not established.}\\",
        r"\toprule",
        r"\rowcolor{ebBlue} Work / interface & Functional role and control or execution path & "
        r"Observation state & Joint feasibility or related check & Candidate coverage \\",
        r"\midrule\endhead",
        r"\bottomrule\endfoot",
    ]
    row_map = []
    presentation_edits = []
    for row in data["rows"]:
        keys = row["citation_keys"]
        assert all(k in entries for k in keys), row["family"]
        authors = entries[keys[0]]["author"].split(" and ")
        name = splitname(authors[0])
        surname = " ".join(name["von"] + name["last"])
        assert surname, row["family"]
        # Author names come from the existing BibTeX and may contain TeX accent macros.
        author = surname + (r" et al." if len(authors) > 1 else "")
        label = author + r"~\cite{" + ",".join(keys) + r"}\newline " + row["family"]
        label += r"\newline " + "/".join(codes[i] for i in row["interfaces"])
        path = tex(row["functional_placement"].rstrip(". ")) + ". " + tex(row["control_and_execution"])
        ownership = row["check_ownership"]
        checks = [tex(ownership[k]) if ownership[k] else r"\textit{NE}"
                  for k in ["observation_state", "joint_feasibility", "candidate_coverage"]]
        line_number = len(lines) + 1
        scope = row["scope_notes"].strip()
        if row["family"] == "RG012":
            assert scope == ("Contradiction-classifier ownership follows RG012-U4, section 10.1; "
                             "it is not silently assigned to every deployed Lumi request.")
            scope = ("The contradiction classifier is evaluated in Sec. 10.1; the source does not establish "
                     "its execution on every deployed Lumi request.")
            presentation_edits.append(dict(family=row["family"], source=row["scope_notes"], rendered=scope,
                                           purpose="Replace internal scope locator with a reader-facing section reference"))
        lines.append(" & ".join([label, path] + checks) + (r" \\*" if scope else r" \\"))
        if scope:
            lines.append(r"\multicolumn{5}{@{}>{\raggedright\arraybackslash}p{\textwidth}@{}}{"
                         r"\emph{Scope.} " + tex(scope) + r"} \\")
        lines.append(r"\addlinespace[3pt]")
        row_map.append(dict(family=row["family"], citation_keys=keys, latex_line=line_number))
    lines += [r"\end{longtable}", r"\endgroup", ""]
    LATEX_OUTPUT.write_text("\n".join(lines))
    metadata = dict(status="LATEX_PREPARED_PENDING_LAYOUT_CHECK", source_check=check,
        source_sha256={str(SOURCE.relative_to(ROOT)):digest(SOURCE),
                       str(bib_path.relative_to(ROOT)):digest(bib_path)},
        generated_sha256=digest(LATEX_OUTPUT), generator_sha256=digest(Path(__file__)),
        source_to_latex=row_map, presentation_edits=presentation_edits,
        template="IEEEtran conference/compsoc at normal full text width",
        style_source="artifacts/paper/overleaf-sync/checkout/palette.tex",
        style_commit="86102e952ca5b77b0e310778394ce554ec871bf7",
        content_scope="All 132 rows, supplied role/path/check text, every scope qualifier and 137 citation keys. "
                      "Names label the families; no new taxonomy values or reporting proportions are inferred.",
        placement="Multipage full-width appendix, kept separate from the current manuscript until integration")
    (SOURCE.parent / "systematization-table-source.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2)+"\n")
    return dict(latex=str(LATEX_OUTPUT.relative_to(ROOT)), families=len(row_map),
                status=metadata["status"])


def compact_rows(data: dict) -> list[dict]:
    """Check presentation summaries against the unchanged three-axis inventory."""
    with COMPACT_SOURCE.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (PAPER / "supplement/coding-scopes.csv").open(newline="") as handle:
        scopes = {row["id"]: row for row in csv.DictReader(handle)}
    with (PAPER / "supplement/coding-sources.csv").open(newline="") as handle:
        sources = {row["record_id"]: row for row in csv.DictReader(handle)}
    used_scopes, used_sources = set(), set()
    assert [r["family_id"] for r in rows] == [r["family"] for r in data["rows"]]
    codes = {"selection": "S", "generation": "G", "computation": "C", "unspecified": "U"}
    fields = [("observation", "observation_state"),
              ("feasibility", "joint_feasibility"),
              ("coverage", "candidate_coverage")]
    for row, original in zip(rows, data["rows"]):
        assert row["title"] == original["title"], row["family_id"]
        for compact, source in [("bibliography_keys", "citation_keys"),
                                ("source_record_ids", "record_ids"), ("scope_ids", "unit_ids")]:
            assert json.loads(row[compact]) == original[source], row["family_id"]
        assert row["interfaces"] == "/".join(codes[i] for i in original["interfaces"])
        assert row["workflow"] and row["workflow_detail"]
        for scope_id in json.loads(row["scope_ids"]):
            assert scopes[scope_id]["group"] == row["family_id"], scope_id
            used_scopes.add(scope_id)
        for record_id in json.loads(row["source_record_ids"]):
            source = sources[record_id]
            assert row["family_id"] in json.loads(source["family_ids"]), record_id
            assert source["source_url"] or source["inspected_source_url"], record_id
            assert source["bibliography_key"] in original["citation_keys"], record_id
            used_sources.add(record_id)
        for name, key in fields:
            unresolved = original["check_ownership"][key] is None
            assert (row[name + "_check"] == "NE") == unresolved, row["family_id"]
            assert (row[name + "_detail"] == "NE") == unresolved, row["family_id"]
    assert used_scopes == set(scopes) and used_sources == set(sources)
    return rows


def citation_ordered_rows(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Use the manuscript's compiled reference numbers for display order."""
    aux = PAPER / "build/main.aux"
    if not aux.exists():
        raise FileNotFoundError("Compile paper-sok-csur/main.tex into build/ before rendering the compact table.")
    numbers = {key: int(number) for key, number in
               re.findall(r"\\bibcite\{([^}]+)\}\{(\d+)\}", aux.read_text())}
    used_keys = {key for row in rows for key in json.loads(row["bibliography_keys"])}
    missing = used_keys - numbers.keys()
    if missing:
        raise ValueError(f"Recompile the manuscript to resolve reference numbers: {sorted(missing)}")
    ordered = sorted(rows, key=lambda row: (
        min(numbers[key] for key in json.loads(row["bibliography_keys"])), row["family_id"]))
    return ordered, numbers


def reader_terms(text: str) -> str:
    """Expand one-off technical shorthand in the displayed literature map.

    These are display-only edits. The source CSV, identities and check assignments
    stay unchanged; cited system names remain their published names.
    """
    replacements = {
        'Registered workflow/model to slice/NFV action':
            'Registered workflow/model to slice or network function virtualization (NFV) action',
        'ILP:': 'Integer linear program:',
        'ACL verification': 'Access-control-list verification',
        'MIP experts:': 'Mixed-integer programs:',
        'L-PCE/RSA:': 'Lightpath computation and routing/spectrum assignment:',
        'PAI/LAM heuristics:': 'Priority-aware installation/location-aware mapping heuristics:',
        'IP-optical': 'Internet Protocol (IP)/optical',
        'Device-intent symbols to QoS slices':
            'Device-intent symbols to quality-of-service (QoS) slices',
        'Entity/KG completion': 'Entity/knowledge-graph completion',
        'SHACL/SPARQL rejects stale entities':
            'Shape constraints and graph queries reject stale entities',
        'certified LEO routing': 'certified low-Earth-orbit routing',
        'RDF intent representation': 'Resource Description Framework intent representation',
        'UPF/user reassignment': 'user-plane-function/user reassignment',
        'gNB configuration': '5G base-station configuration',
        'RL placement': 'reinforcement-learning placement',
        'CSP:': 'Constraint-satisfaction solver:',
        'ONOS installation': 'Open Network Operating System installation',
        'Workflow/DSL generation': 'Workflow/domain-specific-language generation',
        'Similarity/KNN classifier': 'Similarity/k-nearest-neighbour classifier',
        'multivendor CLI': 'multivendor command-line output',
        'Multivendor CLI generation': 'Multivendor command-line generation',
        'CLI hierarchy': 'command-line hierarchy',
        'Interactive CLI changes': 'Interactive command-line changes',
        'target CLI trees': 'target command-line trees',
    }
    for short, expanded in replacements.items():
        text = text.replace(short, expanded)
    return text


def compact_latex(rows: list[dict]) -> str:
    """Render short, manually edited labels; full descriptions stay in the CSV."""
    rows, numbers = citation_ordered_rows(rows)
    header = (r"\rowcolor{ebBlue} Work & Interface & Task and execution path & "
              r"Check responsibility \\")
    lines = [
        "% Generated by scripts/sok_systematization.py --compact from supplement/systematization.csv.",
        "% Short labels are presentation edits; original family/interface/ownership assignments are unchanged.",
        r"\begingroup\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\setlength{\aboverulesep}{0pt}\setlength{\belowrulesep}{0pt}",
        r"\renewcommand{\arraystretch}{1.10}",
        r"\setlength{\LTcapwidth}{\textwidth}",
        r"\newlength{\soklitwidth}\setlength{\soklitwidth}{\dimexpr\textwidth-1pt-8\tabcolsep\relax}",
        r"\begin{longtable}{>{\raggedright\arraybackslash}p{.09\soklitwidth}"
        r">{\centering\arraybackslash}p{.07\soklitwidth}"
        r">{\raggedright\arraybackslash}p{.36\soklitwidth}"
        r">{\raggedright\arraybackslash}p{.48\soklitwidth}}",
        r"\caption{Three-axis literature map of 132 paper families, ordered by the lowest reference number in each row. S: selection; G: construction; "
        r"C: deterministic computation; U: interface unspecified. Multiple letters retain multiple interfaces. "
        r"Check labels distinguish observation state, feasibility or related checks, and candidate coverage. "
        r"Unlisted check types have unresolved ownership; NE marks rows with all three unresolved.}"
        r"\label{tab:e0-systematization}\\",
        r"\toprule", header, r"\midrule\endfirsthead",
        r"\caption[]{Three-axis literature map (continued). S: selection; G: construction; C: computation; "
        r"U: unspecified. Unlisted checks and NE denote unresolved ownership.}\\",
        r"\toprule", header, r"\midrule\endhead", r"\bottomrule\endfoot",
    ]
    for row in rows:
        keys = sorted(json.loads(row["bibliography_keys"]), key=numbers.__getitem__)
        family = r"\cite{" + ",".join(keys) + "}"
        responsibilities = []
        for key, label in [("observation_check", "State"), ("feasibility_check", "Feasibility"),
                           ("coverage_check", "Coverage")]:
            if row[key] != "NE":
                responsibilities.append(r"\emph{" + label + ":} " + tex(reader_terms(row[key])))
        checks = "; ".join(responsibilities) if responsibilities else r"\textit{NE}"
        lines.append(" & ".join([family, row["interfaces"], tex(reader_terms(row["workflow"])), checks]) + r" \\")
        lines.append(r"\addlinespace[1pt]")
    lines += [r"\end{longtable}", r"\endgroup", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--latex", action="store_true")
    parser.add_argument("--compact", action="store_true",
                        help="Render from the companion CSV using build/main.aux reference numbers; compile before and after")
    args = parser.parse_args()
    data = read(SOURCE)
    check = validate(data)
    if args.render:
        render(data, check)
    if args.latex:
        check["latex"] = render_latex(data, check)
    if args.compact:
        rows = compact_rows(data)
        COMPACT_OUTPUT.write_text(compact_latex(rows))
        check["compact"] = dict(families=len(rows), unresolved_checks=sum(
            row[k] == "NE" for row in rows
            for k in ["observation_check", "feasibility_check", "coverage_check"]),
            companion_csv=str(COMPACT_SOURCE.relative_to(ROOT)),
            ordering="Ascending lowest compiled reference number per family",
            latex=str(COMPACT_OUTPUT.relative_to(ROOT)))
    print(json.dumps(check, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
