#!/usr/bin/env python3
"""Typeset advisor-retained old table cells and separated billing; no reanalysis."""
import collections
import json
import re
from pathlib import Path
from sok_systematization import tex, digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/sok/cross-study"
SOURCE = OUT / "retained-table-evidence.json"

SPECS = {
    "4A": ("policy-scale", "RQ-A: policy input structure. Changed/Preserved each contain 60 cases, distinguished by whether all 64 requirements change the minimum-cost feasible choice. Conditions retain a feasible candidate and pair the same cases and candidates. Long irrelevant context and repetition retain four distinct requirements. Tokens gives observed ranges at matched character budgets."),
    "5B": ("policy-online", "RQ-A: online policy execution on 24 preselected cases, six per demand family, in each condition. Correct requires the minimum-cost choice; Direct counts successful execution before fallback; Final includes fallback; Fallback counts fallback trajectories. Time spans observation, selection, installation, verification, and fallback."),
    "6A": ("observation", "RQ-B: observation conditions. Each node-count group has 40 cases across four demand families, balanced by shared-quota binding. Inputs contain four candidates and 9,000 characters. Correct requires minimum-cost feasible selection or justified refresh. The complete/shared condition is the same measurement reused in Table~\\ref{tab:retained-quota}. Response time ends at decision return."),
    "7A": ("repair-observation", "RQ-B: descriptive repair-selection evidence. Each of the six observation conditions has six cases; Valid and median response summarize all 36 fixed records. Req./Opt. missing denote required/optional observations; Resolved is fresh evidence resolving an older contradiction; Conflict is current disagreement. A correct first decision may request refresh and is not a completed service result. Full rule checks observations and repairs; Ungated omits observation validity."),
    "7B": ("repair-faults", "Supplementary repair selection. Each fault condition has six cases; independent/dependent pairs contain two faults. Valid and median response summarize all 24 fixed records. Correct decisions can request refresh. These six-case panels are descriptive."),
    "7C": ("repair-online", "Supplementary online repair, six trajectories per condition. Direct is completion before fallback, allowing observation refresh; all trajectories finally complete, so fallback count is six minus Direct. Time includes model waiting, execution, and fallback. Complete/Stale and Single/Triple are separate matrices. The six-case summaries are descriptive."),
    "8A": ("quota", "RQ-E: observation gates and coupled quotas. Each node-count group has 40 cases across four demand families, balanced by shared-quota binding. Correct requires minimum-cost feasible selection or justified refresh. Per-stage rule checks capacities separately, omitting combined demand on a shared worker. Complete/shared reuses Table~\\ref{tab:retained-observation}. Public gating preserves state bytes and candidates while changing instructions and removing refresh; quota conditions are paired within case. Response time ends at decision return."),
    "9A": ("service-online", "RQ-E: online execution, 24 preselected cases per condition, two per worker-count/demand stratum. Correct evaluates the initial decision; Direct counts feasible execution before fallback and permits one observation refresh and reselection; Final includes fallback. Fallback counts fallback trajectories. Time spans observation through verification, including all model and fallback waiting."),
    "10A": ("contract-catalogue", "RQ-C: contract interpretation on 48 configurations per condition. Replacement introduces two incoming candidates; Absent requires new candidates. Valid and median response refer only to Stable. Rule is a lexical contract matcher; MiniLM re-ranks descriptions. These contract cases are distinct from the six-case network-catalogue population in the supplement."),
    "10B": ("network-catalogue", "Supplementary network selection, six cases per catalogue condition. Distractor/Effective denote distractor/effective replacement. Valid and median response refer only to Stable with four candidates, not to the complete nine-condition matrix. Rule is the complete network checker; MiniLM re-ranks descriptions. Six-case results are descriptive."),
    "10C": ("catalogue-online", "Supplementary online network execution, six trajectories per condition with sixteen candidates. Direct precedes fallback; all trajectories finally complete. Times include model waiting, execution, and fallback. Original failed responses remain in the batch. The six-case summaries are descriptive."),
    "11A/B": ("route-catalogue", "RQ-C: held-out route catalogues, 20 new graphs per contract and 120 per condition, with eight candidates. Link-only chooses the cheapest connected listed path without the other contract checks. Correct requires minimum-cost feasible selection or justified catalogue rebuilding, which loads a preconstructed certified catalogue. All fixed responses are valid. Response time ends at decision return."),
    "11C": ("route-online", "RQ-C: online route execution, 24 trajectories per condition. Correct is the first decision; Direct is feasible execution before fallback, including a justified catalogue rebuild that loads a preconstructed certified catalogue. All trajectories finally complete. Time includes observation, all model waiting, execution, checking, and fallback. The two execution conditions remain separate."),
}


def latex_header(s):
    # The upper headers contain only the saved up/down math arrows.
    parts = re.split(r"(\$\\(?:up|down)arrow\$)", s)
    return "".join(p if re.fullmatch(r"\$\\(?:up|down)arrow\$", p) else tex(p) for p in parts)


def header(row):
    columns, groups = row["source_columns"], row["column_groups"]
    lines = []
    if groups:
        spans = []
        for group, items in __import__("itertools").groupby(groups):
            n = len(list(items))
            spans.append(r"\multicolumn{" + str(n) + "}{c}{" + latex_header(group or "") + "}")
        lines.append(r"\rowcolor{ebBlue} " + " & ".join(spans) + r" \\")
    short = {"Independent pair": r"\shortstack{Independent\\pair}",
             "Dependent pair": r"\shortstack{Dependent\\pair}",
             "Req. missing": r"\shortstack{Req.\\missing}",
             "Opt. missing": r"\shortstack{Opt.\\missing}"}
    lines.append(r"\rowcolor{ebBlue} " + " & ".join(short.get(c, latex_header(c)) for c in columns) + r" \\")
    return lines


def number_cell(value):
    assert re.fullmatch(r"[0-9./$<\-NA]+", value), value
    return value


def count_ratio(value):
    if re.fullmatch(r"\d+/\d+", value):
        a, b = map(int, value.split("/"))
        return a / b
    return None


def render_panel(panel, source_index):
    key = str(panel["old_table"]) + panel["old_panel"]
    slug, caption = SPECS[key]
    ncols = len(panel["rows"][0]["cells"])
    assert all(len(r["cells"]) == ncols for r in panel["rows"])
    correct = [i for i, c in enumerate(panel["rows"][0]["columns"]) if "Correct" in c]
    if correct:
        caption += " Bold marks the largest displayed correct fraction within a condition and column, including ties; it does not imply statistical significance."
    if key not in {"7C", "10C", "11C"}:
        caption += " Fees are reported separately in Table~\\ref{tab:retained-billing}."
    lines = ["% Cell-preserving rendering of old table " + key + "; generated by scripts/sok_retained_tables.py.",
             r"\begingroup\begin{table*}[t]\centering\scriptsize",
             r"\caption{" + caption + "}", r"\label{tab:retained-" + slug + "}",
             r"\setlength{\tabcolsep}{3pt}",
             r"\setlength{\aboverulesep}{0pt}\setlength{\belowrulesep}{0pt}",
             r"\renewcommand{\arraystretch}{1.02}",
             r"\def\retainedtab{\begin{tabular}{l" + "r" * (ncols - 1) + "}", r"\toprule"]
    lines += header(panel["rows"][0]) + [r"\midrule"]
    groups = collections.OrderedDict()
    for row in panel["rows"]:
        groups.setdefault(row["group"], []).append(row)
    for name, rows in groups.items():
        lines.append(r"\rowcolor{ebAmber!45}\multicolumn{" + str(ncols) + r"}{l}{\textbf{" + tex(name) + r"}} \\")
        maxima = {}
        for i in correct:
            values = [count_ratio(r["cells"][i]) for r in rows]
            assert all(v is not None for v in values)
            maxima[i] = max(values)
        for row in rows:
            cells = [tex(row["method"])]
            assert row["method"] == row["cells"][0]
            for i, v in enumerate(row["cells"][1:], 1):
                cell = number_cell(v)
                if i in maxima and count_ratio(v) == maxima[i]:
                    cell = r"\cellcolor{ebCoral!25}\textbf{" + cell + "}"
                cells.append(cell)
            lines.append((r"\rowcolor{ebCoral!10}" if row["method"] == "Jev" else "") +
                         " & ".join(cells) + r" \\")
    lines += [r"\bottomrule\end{tabular}}",
              r"\sbox0{\retainedtab}",
              r"\setlength{\tabcolsep}{\dimexpr\tabcolsep+(\linewidth-\wd0-1pt)/" + str(2 * ncols) + r"\relax}",
              r"\ifdim\tabcolsep<1.5pt\setlength{\tabcolsep}{1.5pt}\fi",
              r"\sbox0{\retainedtab}",
              r"\typeout{RETAINED " + slug + r" width=\the\wd0\space limit=\the\linewidth}",
              r"\retainedtab\end{table*}\endgroup", ""]
    filename = "retained-" + slug + ".tex"
    (OUT / filename).write_text("\n".join(lines))
    return {"old_table": panel["old_table"], "old_panel": panel["old_panel"], "role": panel["role"],
            "file": filename, "label": "tab:retained-" + slug, "caption": caption,
            "rows": len(panel["rows"]), "columns": ncols,
            "source_pointer": "/panels/" + str(source_index)}


def render_billing(data):
    lines = [r"\begingroup\footnotesize\setlength{\tabcolsep}{3pt}",
             r"\renewcommand{\arraystretch}{1.14}\setlength{\LTcapwidth}{\textwidth}",
             r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{.29\textwidth}rrrrr>{\raggedright\arraybackslash}p{.25\textwidth}@{}}",
             r"\caption{Reported API fees (USD) for the displayed application-control batches. Each row gives its original batch denominator; these are rounded returned charges, not per-call costs or total project spending. N/A preserves an unavailable reported charge and does not mean free computation. Other methods lists every other displayed method whose charge was N/A. F denotes fixed decision records and O denotes online trajectories. The complete/shared measurement reused by two main tables is counted once.}\label{tab:retained-billing}\\",
             r"\toprule\rowcolor{ebBlue} Task / condition & $n$ & Jev & DeepSeek & Gemini & GLM & Other methods (N/A) \\",
             r"\midrule\endfirsthead\caption[]{Reported batch API fees (continued).}\\",
             r"\toprule\rowcolor{ebBlue} Task / condition & $n$ & Jev & DeepSeek & Gemini & GLM & Other methods (N/A) \\",
             r"\midrule\endhead\bottomrule\endfoot"]
    names = {"table-4-A": "Policy structure (F)", "table-5-B": "Online policy (O)",
             "service-fixed": "Service selection (F)", "table-7-A": "Repair observations (F)",
             "table-7-B": "Repair faults (F)", "table-9-A": "Online service (O)",
             "table-10-A": "Contract catalogue (F)", "table-10-B": "Network catalogue (F)",
             "table-11-fixed": "Held-out route catalogue (F)"}
    last = None
    core = ["Jev", "DeepSeek", "Gemini", "GLM"]
    for g in data["billing_groups"]:
        if last != g["task"]:
            lines.append(r"\rowcolor{ebAmber!35}\multicolumn{7}{@{}l}{\textbf{" + tex(names[g["task"]]) + r"}} \\*")
            last = g["task"]
        other = {m: v for m, v in g["reported_usd"].items() if m not in core}
        assert all(v == "N/A" for v in other.values())
        lines.append(" & ".join([tex(g["condition"]), str(g["batch_n"])] +
                                [g["reported_usd"].get(m, "--") for m in core] +
                                [tex(", ".join(other))]) + r" \\ \addlinespace[3pt]")
    lines += [r"\end{longtable}\endgroup", ""]
    (OUT / "retained-billing.tex").write_text("\n".join(lines))


def main():
    data = json.loads(SOURCE.read_text())
    for relative, sha in data["source_sha256"].items():
        assert digest(ROOT / relative) == sha, relative
    assert {str(p["old_table"]) + p["old_panel"] for p in data["panels"]} == set(SPECS)
    panels = [render_panel(p, i) for i, p in enumerate(data["panels"])]
    render_billing(data)
    files = [p["file"] for p in panels] + ["retained-billing.tex"]
    output = {"status": "CELL_PRESERVING_LATEX_GENERATED_PENDING_LAYOUT_REVIEW",
              "source": str(SOURCE.relative_to(ROOT)), "source_sha256": digest(SOURCE),
              "generator_sha256": digest(Path(__file__)),
              "style_reference_commit": "86102e952ca5b77b0e310778394ce554ec871bf7",
              "panels": panels, "billing_source_pointer": "/billing_groups",
              "counts": {"panels": len(panels), "rows": sum(p["rows"] for p in panels),
                         "billing_groups": len(data["billing_groups"]),
                         "billing_cells": sum(len(g["reported_usd"]) for g in data["billing_groups"])},
              "output_sha256": {f: digest(OUT / f) for f in files},
              "boundaries": ["No new measurements or inferential statistics.",
                             "Old cells retain precision, endpoint, denominator, and condition identity.",
                             "Six-case panels remain descriptive; failed responses and fallback remain represented.",
                             "Latency extrema are not ranked across censored or unequal semantic outcomes.",
                             "Retained point tables complement the new raw-record analyses and their intervals."]}
    (OUT / "retained-table-layout.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output["counts"]))


if __name__ == "__main__":
    main()
