# Business Calculator (COM 412: E-Business Applications)
Calculates profit / loss per item and overall. Python 3 + Flask + SQLite + Bootstrap.

## Project map (where to look when something breaks)
| File | What it does |
|---|---|
| `app.py` | Everything important: database (`q`, `init_db`), maths (`calc`, `summary`), input checks (`parse_item`), pages (routes), exports (`make_xlsx/pdf/docx/csv`) |
| `templates/` | Pages. `base.html` = layout, `index.html` = main page, `_product_form.html` / `_record_form.html` = the two forms with live preview |
| `templates/settings.html`, `about.html`, `privacy.html`, `terms.html` | Settings (business name, currency, shop link, export, clear data) and information pages |
| `desktop.py` | Launcher used by the Windows .exe |
| `main.py`, `buildozer.spec` | Android (APK) entry point and build settings |
| `calculator.db` / `calculator.log` | Saved data / error details (the log shows the full traceback of any crash) |

Formulas: revenue = sold x selling price; cost = bought x buying price + extra costs; profit = revenue - cost; unsold = bought - sold.

## Run from source (any laptop)
    pip install flask
    python app.py          # open http://127.0.0.1:5000
(Android/Termux: same commands.)

## Build the Windows .exe
On a Windows laptop with Python: double-click `build_exe.bat`. Result: `dist\BusinessCalculator.exe`
(double-click it: the browser opens automatically; data is stored in %APPDATA%\BusinessCalculator).

## Build the .exe and the APK in the cloud (no laptop needed)
1. Put this folder in a GitHub repository (see the commands from your assistant).
2. Open the repository's **Actions** tab, wait for "Build exe and apk" to finish (APK takes about 20-30 minutes the first time).
3. Download `BusinessCalculator-exe` and `BusinessCalculator-apk` from **Artifacts**. Install the APK on the phone (allow "install unknown apps").

## Debugging
- Crashes never close the app: they are logged to `calculator.log` with the exact file and line.
- To see errors live while developing, change `debug=False` to `debug=True` in the last lines of `app.py`.
