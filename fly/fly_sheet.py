"""fly_climbing.csv (from review.html) -> fly_climbing.xlsx with normalized data, trials and a gene column.

  python fly_sheet.py ~/Downloads/fly_climbing.csv

Sheets: Genes (type the gene per vial), Videos (which set/trial each video is), Data, Summary.
Percents are per frame (Q / flies counted that second), so jars with different fly numbers compare.
Climbing score = (3*Q1 + 2*Q2 + 1*Q3) / (3*total): 0 = all at bottom, 1 = all at top.
"""
import csv, os, sys
from collections import OrderedDict
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill, Alignment

src = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Downloads/fly_climbing.csv")
out = os.path.splitext(src)[0] + ".xlsx"
rows = list(csv.DictReader(open(src)))

# videos in order, with their vial count
vids = OrderedDict()
for r in rows:
    vids.setdefault((r["group"], r["video"]), set()).add(int(r["vial"]))

# set = the folder a video was sorted into ("Folder 3" -> set "3"); trial = order within the folder by file number
sets, seen = {}, {}
for (g, v) in sorted(vids, key=lambda k: (k[0], k[1])):
    seen[g] = seen.get(g, 0) + 1
    sets[(g, v)] = (g.split()[1] if g.startswith("Folder ") else g, seen[g])  # "Folder 3 - Oct 29 - ..." -> "3"

F = "Arial"
B = Font(name=F, bold=True)
N = Font(name=F)
BLUE = Font(name=F, color="0000FF")
GREEN = Font(name=F, color="008000")
YELLOW = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="DDE3EA")
PCT = "0.0%"


def header(ws, cols, row=1):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row, i, c)
        cell.font, cell.fill = B, HEAD
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = max(9, len(c) + 2)


wb = Workbook()

# ---- Genes: one row per physical vial (set + position) ----
gs = wb.active
gs.title = "Genes"
gs["A1"] = "Type the gene / genotype for each vial in the yellow column. Everything else updates from it."
gs["A1"].font = B
gs["A2"] = "Vial ID = folder number + position from the left (3-1 = Folder 3, leftmost vial). Example entry: w1118"
gs["A2"].font = N
header(gs, ["Vial ID", "Set", "Position", "Gene", "Trials found"], row=4)
vial_ids = sorted({(s, p) for k, (s, _) in sets.items() for p in vids[k]}, key=lambda t: (int(t[0]) if t[0].isdigit() else 99, t[0], t[1]))
for i, (s, p) in enumerate(vial_ids, 5):
    gs.cell(i, 1, f"{s}-{p}").font = N
    gs.cell(i, 2, s).font = N
    gs.cell(i, 3, p).font = N
    gs.cell(i, 4).fill = YELLOW
    gs.cell(i, 5, f'=COUNTIFS(Videos!$C:$C,B{i})').font = N
gs.column_dimensions["D"].width = 24
GL = 4 + len(vial_ids)   # last row of gene table

# ---- Videos: set + trial per video (editable) ----
vs = wb.create_sheet("Videos")
header(vs, ["Group", "Video", "Set", "Trial", "Vials"])
for i, ((g, v), (s, t)) in enumerate(sets.items(), 2):
    vs.cell(i, 1, g).font = N
    vs.cell(i, 2, v).font = N
    vs.cell(i, 3, s).font = BLUE
    vs.cell(i, 4, t).font = BLUE
    vs.cell(i, 5, len(vids[(g, v)])).font = N
vs.cell(2, 3).comment = Comment("Set = the folder the video was sorted into (matched by timestamp, vial markers "
                                "and fly counts). Trial = order within the folder. Edit if wrong.", "fly_sheet")
VL = 1 + len(sets)

# ---- Data: one row per video, vial, second ----
ds = wb.create_sheet("Data")
cols = ["Group", "Video", "Vial pos", "Second", "Q1 top", "Q2", "Q3", "Q4 bottom", "Total",
        "% Q1", "% Q2", "% Q3", "% Q4", "Climbing score", "Set", "Trial", "Vial ID", "Gene"]
header(ds, cols)
for i, r in enumerate(rows, 2):
    for c, val in enumerate([r["group"], r["video"], int(r["vial"]), int(r["t_s"]),
                             int(r["Q1_top"]), int(r["Q2"]), int(r["Q3"]), int(r["Q4_bottom"])], 1):
        ds.cell(i, c, val).font = BLUE if c >= 5 else N
    ds.cell(i, 9, f"=SUM(E{i}:H{i})").font = N
    for c, q in zip(range(10, 14), "EFGH"):
        ds.cell(i, c, f"=IF($I{i}=0,0,{q}{i}/$I{i})").font = N
        ds.cell(i, c).number_format = PCT
    ds.cell(i, 14, f"=IF(I{i}=0,0,(3*E{i}+2*F{i}+G{i})/(3*I{i}))").font = N
    ds.cell(i, 14).number_format = "0.00"
    ds.cell(i, 15, f"=INDEX(Videos!$C$2:$C${VL},MATCH(B{i},Videos!$B$2:$B${VL},0))").font = GREEN
    ds.cell(i, 16, f"=INDEX(Videos!$D$2:$D${VL},MATCH(B{i},Videos!$B$2:$B${VL},0))").font = GREEN
    ds.cell(i, 17, f'=O{i}&"-"&C{i}').font = N
    ds.cell(i, 18, f'=IF(INDEX(Genes!$D$5:$D${GL},MATCH(Q{i},Genes!$A$5:$A${GL},0))="","",'
                   f'INDEX(Genes!$D$5:$D${GL},MATCH(Q{i},Genes!$A$5:$A${GL},0)))').font = GREEN
ds.freeze_panes = "A2"
DL = len(rows) + 1

# ---- Summary: per vial x second, averaged over its trials ----
ss = wb.create_sheet("Summary")
header(ss, ["Vial ID", "Gene", "Second", "Trials", "Mean % Q1", "Mean % Q2", "Mean % Q3", "Mean % Q4",
            "Mean climbing score"])
seconds = sorted({int(r["t_s"]) for r in rows})
i = 2
for s, p in vial_ids:
    for t in seconds:
        ss.cell(i, 1, f"{s}-{p}").font = N
        ss.cell(i, 2, f'=IF(INDEX(Genes!$D$5:$D${GL},MATCH(A{i},Genes!$A$5:$A${GL},0))="","",'
                      f'INDEX(Genes!$D$5:$D${GL},MATCH(A{i},Genes!$A$5:$A${GL},0)))').font = GREEN
        ss.cell(i, 3, t).font = N
        crit = f"Data!$Q$2:$Q${DL},$A{i},Data!$D$2:$D${DL},$C{i}"
        ss.cell(i, 4, f"=COUNTIFS({crit})").font = N
        for c, col in zip(range(5, 9), "JKLM"):
            ss.cell(i, c, f"=IFERROR(AVERAGEIFS(Data!${col}$2:${col}${DL},{crit}),0)").font = N
            ss.cell(i, c).number_format = PCT
        ss.cell(i, 9, f"=IFERROR(AVERAGEIFS(Data!$N$2:$N${DL},{crit}),0)").font = N
        ss.cell(i, 9).number_format = "0.00"
        i += 1
ss.freeze_panes = "A2"

wb.save(out)
print(out)
for (g, v), (s, t) in sets.items():
    print(f"  {v}: set {s}, trial {t}, {len(vids[(g, v)])} vials")
