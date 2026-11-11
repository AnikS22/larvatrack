# Fly lab tools — PCB 4054C

Tools for measuring *Drosophila* behavior, built for **PCB 4054C, Drosophila Genes &
Behavior** at Florida Atlantic University.

**Website: https://aniks22.github.io/larvatrack/**: all six PCB 4054C projects (larval foraging, caffeine & sleep, CAFE feeding, negative geotaxis, flight, cold shock) with demos, figures, reports and the in-browser larva tracer.

| Folder | What it does |
|---|---|
| [`larva/`](larva/) | **Larval foraging (rover/sitter).** Path length per larva from a plate video. Automatic tracker (`app.py`, `tptrack.py`) and hand tracer (`web/`). See [larva/README.md](larva/README.md). |
| [`fly/`](fly/) | **Adult fly assays.** Climbing counter (`geotaxis.py`), fly paper counter (`fly_paper.py`), one review page for both (`review_all.py`), spreadsheet (`fly_sheet.py`) and handout graphs (`fly_figures.py`). |
| [`treadmill/`](treadmill/) | **Fly treadmill hardware.** OpenSCAD sources, printable STLs, build notes (`fly/MINI_BUILD.md`, `parts/README.md`, `print_kit/README.md`), and a Fusion 360 script (`fusion/FlyTreadmill/`). |
| [`docs/`](docs/) | The GitHub Pages site and the README figures. |

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
