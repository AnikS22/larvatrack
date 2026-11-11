"""The 10 graphs the lab handouts ask for, plus figure legends.

  cd ~/Downloads/geotaxis_results && python3 ~/Desktop/PCB4054C-01H/fly/fly_figures.py [reviewed_climbing.csv] [reviewed_fly_paper.csv]

Climbing (5): stacked columns at 1-5 s, Q1 = bottom ... Q4 = top (handout numbering), mean % per quadrant,
  SEM error bars, Welch t-tests of each mutant vs each wild-type control (CS, w1118) on % in the top half.
Flight (1): stacked columns, Interval 1 = water ... Interval 4 = top of the fly paper, SD error bars, chi-square.
Cold shock (4): mean time to 50% / 100% paralysis (s) and 50% / 100% recovery (min), SD error bars, replicate dots.
Without arguments it uses the auto counts (data/fly_climbing_all.csv + phenotypes, data/fly_paper.csv).
"""
import collections, csv, os, sys
import numpy as np
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

OUT = "charts/assignment"
os.makedirs(OUT, exist_ok=True)
INK, MUTED, GRID = "#2b2a27", "#5f5e58", "#e3e2dc"
plt.rcParams.update({"font.family": "Arial", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True, "axes.titleweight": "bold",
                     "axes.titlesize": 13, "axes.titlecolor": INK, "figure.dpi": 200})
BLUES = ["#86b6ef", "#5598e7", "#256abf", "#104281"]          # ordinal: Q1/Interval 1 (bottom) light -> top dark
GCOL = {"Hey": "#2a78d6", "f": "#eb6834", "M1": "#1baf7a", "w1118": "#eda100", "CS": "#e87ba4"}   # validated, fixed order
GT, MUT, CTRL = ["Hey", "f", "M1", "w1118", "CS"], ["Hey", "f", "M1"], ["CS", "w1118"]
ORDER = [f"{g} {s}" for s in ("♂", "♀") for g in GT]
legends = []


def table(name, header, rows):
    """CSV of exactly what a graph plots: summary rows (row_type=mean) then the replicates behind them."""
    with open(f"{OUT}/{name}.csv", "w", newline="") as fh:
        csv.writer(fh).writerows([header] + rows)


def pfmt(p):
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def save(fig, name):
    fig.tight_layout(); fig.savefig(f"{OUT}/{name}.png", facecolor="white"); plt.close(fig); print("saved", name)


def stacked(ax, x, parts, err_each):
    """parts[k] = means for layer k (bottom first); err_each[k] = error bars for layer k (top layer skipped: stack sums to 100%)."""
    bottom = np.zeros(len(x))
    for k, m in enumerate(parts):
        ax.bar(x, m, bottom=bottom, color=BLUES[k + (4 - len(parts))], width=0.72, edgecolor="white", linewidth=1.5)
        if k < len(parts) - 1:
            ax.errorbar(x, bottom + m, yerr=err_each[k], fmt="none", ecolor=INK, elinewidth=1, capsize=3)
        bottom += m


# ---------------- climbing ----------------
TOPPED_UP = []   # (video, phenotype, second, flies added to Quadrant 4)


def load_climbing():
    """-> {(phenotype, second): [[Q1_bottom, Q2, Q3, Q4_top] fractions per vial-trial]}"""
    out = collections.defaultdict(list)
    if len(sys.argv) > 1:   # reviewed CSV from review_all.html (Q1_bottom..Q4_top, phenotype column)
        rows = list(csv.DictReader(open(sys.argv[1])))
        # a vial's fly count can't drop: N = its highest count over 0-5 s. Frames that come up short are missing
        # climbers bunched at the plug / glass edge (checked on video), so the shortfall is added to Quadrant 4.
        N = collections.defaultdict(int)
        for r in rows: N[(r["video"], r["vial"])] = max(N[(r["video"], r["vial"])], int(r["total"]))
        for r in rows:
            q = [int(r[k]) for k in ("Q1_bottom", "Q2", "Q3", "Q4_top")]
            missing = N[(r["video"], r["vial"])] - sum(q)
            if missing > 0: q[3] += missing; TOPPED_UP.append((r["video"], r["phenotype"], int(r["t_s"]), missing))
            if sum(q): out[(r["phenotype"], int(r["t_s"]))].append([v / sum(q) for v in q])
        return out
    import openpyxl
    d = openpyxl.load_workbook("data/Fly_Experiments_Final.xlsx", data_only=True)["Data"]
    h = [c.value for c in d[1]]; I = {k: h.index(k) for k in h}
    for r in d.iter_rows(min_row=2, values_only=True):
        t = r[I["Total"]]
        if t:   # workbook columns are top->bottom; flip to handout order Q1 = bottom
            out[(r[I["Phenotype"]], r[I["Second"]])].append([r[I[k]] / t for k in ("Q4 bottom", "Q3", "Q2", "Q1 top")])
    return out


clim = load_climbing()
x = np.arange(len(ORDER)) + np.array([0] * 5 + [0.6] * 5)
for sec in range(1, 6):
    fig, ax = plt.subplots(figsize=(11, 5.6))
    parts = [np.array([np.mean([t[q] for t in clim[(g, sec)]]) for g in ORDER]) for q in range(4)]
    errs = [np.array([stats.sem([t[q] for t in clim[(g, sec)]]) for g in ORDER]) for q in range(4)]
    stacked(ax, x, parts, errs)
    ax.set_xticks(x, ORDER); ax.set_ylim(0, 1.02); ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.grid(axis="x", visible=False)
    ax.set(title=f"Climbing at {sec} s", xlabel="Genotype and sex", ylabel="% of flies in each quadrant")
    hs = [plt.Rectangle((0, 0), 1, 1, color=c) for c in BLUES[::-1]]
    ax.legend(hs, ["Quadrant 4 (top)", "Quadrant 3", "Quadrant 2", "Quadrant 1 (bottom)"], loc="upper left", bbox_to_anchor=(1, 1), frameon=False, fontsize=9)
    save(fig, f"climbing_{sec}s")
    pc = lambda v: round(100 * v, 1)
    rows = [["mean", g.split()[0], g.split()[1], len(clim[(g, sec)])] + [pc(p[i]) for p in parts] + [pc(e[i]) for e in errs]
            + [pc(parts[2][i] + parts[3][i])] for i, g in enumerate(ORDER)]
    for g in ORDER:
        for j, t in enumerate(clim[(g, sec)], 1):
            rows.append(["replicate", g.split()[0], g.split()[1], j] + [pc(v) for v in t] + ["", "", "", ""] + [pc(t[2] + t[3])])
    table(f"climbing_{sec}s", ["row_type", "genotype", "sex", "n (vial-trials) / replicate #", "% Q1 bottom", "% Q2", "% Q3", "% Q4 top",
                               "SEM Q1", "SEM Q2", "SEM Q3", "SEM Q4", "% top half (Q3+Q4)"], rows)
    top = {g: [t[2] + t[3] for t in clim[(g, sec)]] for g in ORDER}
    tests = []
    for s in ("♂", "♀"):
        for m in MUT:
            for c in CTRL:
                p = stats.ttest_ind(top[f"{m} {s}"], top[f"{c} {s}"], equal_var=False).pvalue
                tests.append(f"{m} vs {c} {s} {pfmt(p)}")
    ci = []
    for g in ORDER:
        v = top[g]; lo, hi = stats.t.interval(0.95, len(v) - 1, np.mean(v), stats.sem(v))
        ci.append(f"{g} {np.mean(v):.0%} ({max(lo, 0):.0%}-{min(hi, 1):.0%})")
    legends.append(
        f"Figure {sec}. Climbing at {sec} s. Negative geotaxis assay: flies were tapped to the bottom of a vial marked into four "
        f"2-cm quadrants (Quadrant 1 = bottom, Quadrant 4 = top) and filmed; {sec} s after the last tap the flies in each quadrant were "
        "counted and expressed as % of the flies in the vial. Genotypes: mutants Hey, f and M1; wild-type controls CS and w1118. "
        "Male (♂) and female (♀) flies were tested separately (8-10 flies per vial). Flies missing from a frame (climbers hidden at the plug) "
        "were counted in Quadrant 4. Bars = mean of 6 measurements per genotype and sex "
        "(2 vials x 3 trials); error bars = SEM. Welch t-tests on % of flies in the top half (Quadrants 3 + 4), each mutant vs each "
        "control: " + "; ".join(tests) + ". 95% confidence intervals for % in the top half: " + "; ".join(ci) + ".")

# ---------------- flight ----------------
WATER = {("Oct 29", "M1"): 2}   # notebook: "M1 ♂ 2 in water"; no water flies noted for the other sheets
if len(sys.argv) > 2:   # reviewed fly paper CSV: average the photos of each sheet
    per = collections.defaultdict(list)
    for r in csv.DictReader(open(sys.argv[2])):
        g = next(k for k in GT if r["phenotype"].startswith(k))
        per[(r["date"], g)].append([float(r[k]) for k in ("interval2_bottom", "interval3", "interval4_top")])
    sheets = {k: np.mean(v, 0) for k, v in per.items()}
else:
    sheets = {}
    for r in csv.DictReader(open("data/fly_paper.csv")):
        g = next(k for k in GT if r["genotype"].startswith(k) or (k == "w1118" and r["genotype"].startswith("W")))
        sheets[(r["date"], g)] = np.array([float(r["zone3 (bottom)"]), float(r["zone2 (middle)"]), float(r["zone1 (top)"])])
fl = {}   # genotype -> list of [Int1..Int4] counts per sheet
for (date, g), paper in sheets.items():
    fl.setdefault(g, []).append(np.concatenate([[WATER.get((date, g), 0)], paper]))
fig, ax = plt.subplots(figsize=(8.5, 5.6)); xf = np.arange(len(GT))
pct = {g: [c / c.sum() for c in fl[g]] for g in GT}
parts = [np.array([np.mean([p[k] for p in pct[g]]) for g in GT]) for k in range(4)]
errs = [np.array([np.std([p[k] for p in pct[g]], ddof=1) if len(pct[g]) > 1 else 0 for g in GT]) for k in range(4)]
stacked(ax, xf, parts, errs)
ax.set_xticks(xf, GT); ax.set_ylim(0, 1.02); ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.grid(axis="x", visible=False)
ax.set(title="Flight assay (free-fall escape)", xlabel="Genotype", ylabel="% of flies in each interval")
hs = [plt.Rectangle((0, 0), 1, 1, color=c) for c in BLUES[::-1]]
ax.legend(hs, ["Interval 4 (top of paper)", "Interval 3", "Interval 2 (bottom of paper)", "Interval 1 (water)"], loc="upper left", bbox_to_anchor=(1, 1), frameon=False, fontsize=9)
save(fig, "flight_assay")
rows = [["mean", g, len(pct[g])] + [round(100 * p[i], 1) for p in parts] + [round(100 * e[i], 1) for e in errs] + [""] * 4 for i, g in enumerate(GT)]
for (date, g), paper in sorted(sheets.items()):
    c = np.concatenate([[WATER.get((date, g), 0)], paper])
    rows.append(["sheet", g, date] + [round(100 * v / c.sum(), 1) for v in c] + [""] * 4 + [round(v, 1) for v in c])
table("flight_assay", ["row_type", "genotype", "n sheets / date", "% Int1 water", "% Int2", "% Int3", "% Int4 top",
                       "SD Int1", "SD Int2", "SD Int3", "SD Int4", "count Int1", "count Int2", "count Int3", "count Int4"], rows)
tests = []
for m in MUT:
    for c in CTRL:
        tab = np.round(np.array([np.sum(fl[m], 0), np.sum(fl[c], 0)]))
        tab = tab[:, tab.sum(0) > 0]
        tests.append(f"{m} vs {c} {pfmt(stats.chi2_contingency(tab).pvalue)}")
legends.append(
    "Figure 6. Flight assay (free-fall escape). Flies were dropped through a funnel into a 250-ml cylinder lined with sticky paper; "
    "good fliers escape free fall quickly and stick high. The paper was divided by red lines into intervals (Interval 1 = water at the "
    "bottom, Interval 4 = top) and the flies in each interval were counted from photos and expressed as % of the flies tested. "
    "Genotypes: mutants Hey, f and M1; wild-type controls CS and w1118. Bars = mean of 2 sheets per genotype (Oct 22 and Oct 29); "
    "error bars = standard deviation. Sex: Oct 29 sheets were males; Oct 22 sheets were Hey ♀, f ♂, CS ♂ (M1 and w1118 not recorded). "
    "Chi-square tests of the interval distribution (pooled counts), each mutant vs each control: " + "; ".join(tests) + ".")

# ---------------- cold shock ----------------
cs = list(csv.DictReader(open("data/cold_shock.csv")))
specs = [("par50_s", "Time to 50% paralysis", "Seconds in ice water", 1, "cold_shock_1_paralysis_50pct"),
         ("par100_s", "Time to 100% paralysis", "Seconds in ice water", 1, "cold_shock_2_paralysis_100pct"),
         ("rec50_s", "Time to 50% recovery", "Minutes after leaving the ice", 60, "cold_shock_3_recovery_50pct"),
         ("rec100_s", "Time to 100% recovery", "Minutes after leaving the ice", 60, "cold_shock_4_recovery_100pct")]
for k, (col, title, ylab, div, name) in enumerate(specs, 7):
    fig, ax = plt.subplots(figsize=(10, 5.4)); notes = []
    for i, g in enumerate(ORDER):
        rows = [r for r in cs if f"{r['genotype']} {r['sex']}" == g and r[col]]
        vals = [float(r[col].lstrip(">")) / div for r in rows]
        cens = [r[col].startswith(">") for r in rows]
        if not vals:
            ax.text(x[i], 0.02 * ax.get_ylim()[1], "no data", ha="center", rotation=90, fontsize=8, color=MUTED); continue
        m = np.mean(vals)
        ax.bar(x[i], m, color=GCOL[g.split()[0]], width=0.72, edgecolor="white", linewidth=1.5, hatch="//" if any(cens) else None)
        if len(vals) > 1: ax.errorbar(x[i], m, yerr=np.std(vals, ddof=1), fmt="none", ecolor=INK, elinewidth=1, capsize=3)
        ax.scatter([x[i]] * len(vals), vals, s=18, color=INK, zorder=3)
        ax.text(x[i], m, f"{'≥' if any(cens) else ''}{m:.1f}" if div > 1 else f"{m:.0f}", ha="center", va="bottom", fontsize=8, color=INK,
                transform=ax.transData)
        if any(cens): notes.append(g)
    ax.set_xticks(x, ORDER); ax.grid(axis="x", visible=False); ax.set_ylim(bottom=0)
    ax.set(title=f"Cold shock: {title.lower()}", xlabel="Genotype and sex", ylabel=ylab)
    save(fig, name)
    rows = []
    for g in ORDER:
        rr = [r for r in cs if f"{r['genotype']} {r['sex']}" == g and r[col]]
        vals = [float(r[col].lstrip(">")) / div for r in rr]
        if vals:
            rows.append(["mean", g.split()[0], g.split()[1], len(vals), round(np.mean(vals), 2),
                         round(np.std(vals, ddof=1), 2) if len(vals) > 1 else "", "yes" if any(r[col].startswith(">") for r in rr) else "", ""])
        for r in rr:
            rows.append(["tube", r["genotype"], r["sex"], r["date"], round(float(r[col].lstrip(">")) / div, 2), "",
                         "yes" if r[col].startswith(">") else "", f"{r['sleep video']} / {r['wake video']}"])
    table(name, ["row_type", "genotype", "sex", "n tubes / date", "seconds" if div == 1 else "minutes", "SD",
                 "lower bound (not finished when video ended)", "videos"], rows)
    n = {g: len([r for r in cs if f"{r['genotype']} {r['sex']}" == g and r[col]]) for g in ORDER}
    legends.append(
        f"Figure {k}. Cold shock - {title.lower()}. Flies (10 per tube, one sex per tube) in plastic test tubes were submerged in a "
        "~4 °C ice-water bath and filmed until paralyzed, then laid on the bench and filmed while they recovered. "
        + ("Paralysis = time after the tube entered the water until about half / all flies dropped to the bottom of the tube. "
           if div == 1 else "Recovery = time after the tube left the water until about half / all flies stood up and walked off the pile. ")
        + "Genotypes: mutants Hey, f and M1; wild-type controls CS and w1118; males (♂) and females (♀) tested separately. "
        "Bars = mean of replicate tubes, dots = individual tubes, error bars = SD where there are 2 tubes. Replicates per bar: "
        + ", ".join(f"{g} n={c}" for g, c in n.items() if c) + "."
        + (f" Hatched bars (≥) include a tube that had not finished recovering when filming stopped ({', '.join(notes)}); the value is a lower bound."
           if notes else "")
        + " Times read by eye from video frames (about ±2 s for paralysis, ±30 s for recovery); too few replicates for a significance test.")

open(f"{OUT}/figure_legends.txt", "w").write("\n\n".join(legends) + "\n")
print("wrote figure_legends.txt")

# ---------------- hand-off folder: one subfolder per assay, each figure = picture + data + legend ----------------
import shutil
DEST = os.path.expanduser("~/Downloads/Fly_Lab_Graphs")
shutil.rmtree(DEST, ignore_errors=True)
figs = [(f"climbing_{s}s", "1 Climbing", f"Figure {s} - Climbing at {s}s") for s in range(1, 6)] + \
       [("flight_assay", "2 Flight", "Figure 6 - Flight assay")] + \
       [(n, "3 Cold shock", f"Figure {k} - {t}") for k, (_, t, _, _, n) in enumerate(specs, 7)]
for (src, folder, title), leg in zip(figs, legends):
    d = os.path.join(DEST, folder); os.makedirs(d, exist_ok=True)
    shutil.copy(f"{OUT}/{src}.png", f"{d}/{title}.png")
    shutil.copy(f"{OUT}/{src}.csv", f"{d}/{title} - data.csv")
    open(f"{d}/{title} - figure legend.txt", "w").write(leg + "\n")
open(os.path.join(DEST, "README.txt"), "w").write(
    "Fly lab graphs - one folder per assay. Each figure has 3 files: the graph (.png), the numbers behind it (- data.csv:\n"
    "'mean' rows = what the bars show, then each replicate) and its figure legend (- figure legend.txt).\n\n"
    "1 Climbing  - Figures 1-5: where the flies are at 1-5 s after tapping (Quadrant 1 = bottom, 4 = top).\n"
    "2 Flight    - Figure 6: where the flies stuck on the fly paper (Interval 1 = water, 4 = top).\n"
    "3 Cold shock - Figures 7-10: time to 50% / 100% paralysis (seconds) and 50% / 100% recovery (minutes).\n\n"
    "Genotypes: mutants Hey, f, M1; wild-type controls CS, w1118. Males and females tested separately (sex on every bar).\n\n"
    "DATA CHECKS\n"
    f"- Climbing: counts were hand-checked in the review page. In {len({(v, p) for v, p, _, _ in TOPPED_UP})} vials some flies "
    "were hidden at the plug in later frames; those frames were topped up to the vial's full count in Quadrant 4.\n"
    "- Flight: 2 sheets per genotype (Oct 22 + Oct 29). Low counts on paper: Hey (Oct 22) 5-7 flies; M1 (Oct 29) only 3 on the paper\n"
    "  plus 2 in the water (from the notebook) - so M1's error bars are very wide.\n"
    "- Cold shock: times read from video frames (about +/-2 s paralysis, +/-30 s recovery); 1-2 tubes per bar, so no p-values.\n"
    "  Hatched bars = a tube still not recovered when filming stopped (value is a minimum). No wake video for the 2nd ice dunk on Oct 22.\n")
print("hand-off folder:", DEST)
