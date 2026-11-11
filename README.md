# FlyBench

A *Drosophila* data analysis tool suite, made by **Anik Sahai** (Harriet L. Wilkes Honors College, Florida Atlantic University).

Tools for measuring *Drosophila* behavior, built for **PCB 4054C, Drosophila Genes &
Behavior** at Florida Atlantic University.

**Website: https://aniks22.github.io/larvatrack/**: nine in-browser tools (larval foraging, sleep & activity from DAM files, CAFE feeding, climbing, flight, cold shock, genetic crosses, T-maze learning & memory, heat-shock/drowning/starvation stress). Each explains the biology, how to use it, how to read the results and the statistics; every count can be corrected by hand; output is graphs, tests and CSV. Automatic tracking and fly detection: AI analysis by request, asahai2024@fau.edu.

| Folder | What it does |
|---|---|
| [`larva/`](larva/) | **Larval foraging (rover/sitter).** Path length per larva from a plate video. Automatic tracker (`app.py`, `tptrack.py`) and hand tracer (`web/`). See [larva/README.md](larva/README.md). |
| [`fly/`](fly/) | **Adult fly assays.** Climbing counter (`geotaxis.py`), fly paper counter (`fly_paper.py`), one review page for both (`review_all.py`), spreadsheet (`fly_sheet.py`) and handout graphs (`fly_figures.py`). |
| [`treadmill/`](treadmill/) | **Fly treadmill hardware.** OpenSCAD sources, printable STLs, build notes (`fly/MINI_BUILD.md`, `parts/README.md`, `print_kit/README.md`), and a Fusion 360 script (`fusion/FlyTreadmill/`). |
| [`docs/`](docs/) | The FlyBench website. `docs/tools/` holds the in-browser tools (`suite.js` = shared stats; run `node docs/tools/suite.js` to self-check), `docs/trace/` the larva hand tracer. |

## Fly assays, in order

Run these from the folder that holds the data (videos in `geotaxis/Folder N/`, photos in `photos/`):

```bash
python3 fly/geotaxis.py geotaxis/*/*.MOV     # detect flies per vial, cached in cache/
python3 fly/fly_paper.py photos/*/*.jpg      # count flies per fly-paper zone
python3 fly/review_all.py                    # check and fix every count -> reviewed CSVs
python3 fly/fly_figures.py fly_climbing_reviewed.csv fly_paper_reviewed.csv
python3 fly/fly_sheet.py fly_climbing.csv    # optional: Excel workbook
```

Needs `opencv-python numpy scipy matplotlib openpyxl`.

## Larva tracker

```bash
python3 -m venv .venv-track && .venv-track/bin/pip install trackpy opencv-python numpy pandas
cd larva && ../.venv-track/bin/python app.py     # http://localhost:8020
```

Raw videos, uploads and results stay local (see `.gitignore`).
