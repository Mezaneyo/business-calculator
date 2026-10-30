"""
Business Calculator - profit / loss per item and overall
COM 412: E-Business Applications
Setup: pip install flask      Run: python app.py      Open: http://127.0.0.1:5000
Exports (Excel, PDF, Word, CSV) use only the Python standard library - nothing else to install.
"""
import csv, io, logging, os, sqlite3, sys, zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape as esc
from flask import Flask, Response, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

NAME = "Business Calculator"
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))  # _MEIPASS = inside the .exe


def data_dir():
    """Where the database and log live: next to the code, in the app folder on Android, in %APPDATA% for the .exe."""
    d = (os.environ.get("CALC_DATA") or os.environ.get("ANDROID_PRIVATE")
         or (os.path.join(os.environ.get("APPDATA", ""), "BusinessCalculator") if getattr(sys, "frozen", False)
             else os.path.dirname(os.path.abspath(__file__))))
    os.makedirs(d, exist_ok=True)
    return d


DB = os.path.join(data_dir(), "calculator.db")
logging.basicConfig(filename=os.path.join(data_dir(), "calculator.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
app = Flask(__name__, template_folder=os.path.join(HERE, "templates"))
app.secret_key = os.environ.get("SECRET_KEY", "change-me")


@app.errorhandler(Exception)
def crash(e):
    """Any unexpected error is written to calculator.log (with the full traceback) instead of killing the app."""
    if isinstance(e, HTTPException):
        return e
    logging.exception("Unhandled error on %s %s", request.method, request.path)
    return render_template("error.html", name=NAME), 500


# ---------- database ----------
def q(sql, args=(), one=False):
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    rows = g.db.execute(sql, args).fetchall()
    g.db.commit()
    return (rows[0] if rows else None) if one else rows


@app.teardown_appcontext
def close_db(_):
    c = g.pop("db", None)
    if c:
        c.close()


def init_db():
    """products = the items you sell (name + buying/selling price); records = what you bought and sold of them."""
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, buy REAL, sell REAL);
    CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER,
        bought REAL, sold REAL, extra REAL, created TEXT);
    CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, amount REAL);""")
    con.commit()
    con.close()


@app.template_filter("mk")
def mk(n):
    s = f"{abs(n):,.2f}"
    s = s[:-3] if s.endswith(".00") else s
    return ("-" if n < 0 else "") + "MK" + s


@app.template_filter("pct")
def pct(n):
    return f"{n:.1f}%"


@app.template_filter("num")
def num(n):
    return f"{n:g}"


# ---------- calculations ----------
def result(bought, sold, extra, buy, sell):
    """revenue = sold x selling price; cost = BOUGHT x buying price + extra costs; profit = revenue - cost."""
    revenue = sold * sell
    cost = bought * buy + extra
    profit = revenue - cost
    status, color = ("Profit", "success") if profit > 0 else ("Loss", "danger") if profit < 0 else ("Break-even", "secondary")
    unsold = bought - sold
    return dict(bought=bought, sold=sold, unsold=unsold, extra=extra, revenue=revenue, cost=cost, profit=profit,
                status=status, color=color, stock_value=unsold * sell, potential=profit + unsold * sell,
                margin=profit / revenue * 100 if revenue else 0)


def summary():
    products = q("SELECT * FROM products ORDER BY id")
    recs = q("SELECT r.*, p.name, p.buy, p.sell FROM records r JOIN products p ON p.id = r.product_id ORDER BY r.id DESC")
    records = [dict(r, **result(r["bought"], r["sold"], r["extra"], r["buy"], r["sell"])) for r in recs]
    items = []
    for p in products:
        mine = [r for r in recs if r["product_id"] == p["id"]]
        res = result(sum(r["bought"] for r in mine), sum(r["sold"] for r in mine), sum(r["extra"] for r in mine), p["buy"], p["sell"])
        items.append(dict(p, has_records=bool(mine), unit_profit=p["sell"] - p["buy"], **res))
    expenses = q("SELECT * FROM expenses ORDER BY id")
    revenue, cost = sum(i["revenue"] for i in items), sum(i["cost"] for i in items)
    exp_total = sum(e["amount"] for e in expenses)
    net, stock_value = revenue - cost - exp_total, sum(i["stock_value"] for i in items)
    active = [i for i in items if i["has_records"]]
    return items, records, expenses, products, dict(
        revenue=revenue, cost=cost, gross=revenue - cost, expenses=exp_total, net=net,
        stock_value=stock_value, potential=net + stock_value, margin=net / revenue * 100 if revenue else 0,
        profits=sum(i["profit"] > 0 for i in active), losses=sum(i["profit"] < 0 for i in active),
        best=max(active, key=lambda i: i["profit"]) if active else None,
        worst=min(active, key=lambda i: i["profit"]) if active else None)


def fnum(f, key, default=None):
    v = (f.get(key) or "").strip()
    return float(v) if v else default  # raises ValueError for text


def parse_product(f):
    try:
        name, buy, sell = f["name"].strip(), fnum(f, "buy"), fnum(f, "sell")
    except (KeyError, ValueError):
        return None
    return (name, buy, sell) if name and buy is not None and sell is not None and min(buy, sell) >= 0 else None


def parse_record(f):
    """Quantity sold left blank = everything bought was sold."""
    try:
        pid, bought = int(f["product_id"]), fnum(f, "bought")
        sold, extra = fnum(f, "sold", bought), fnum(f, "extra", 0.0)
    except (KeyError, ValueError):
        return None
    ok = bought and bought > 0 and 0 <= sold <= bought and extra >= 0 and q("SELECT 1 FROM products WHERE id=?", (pid,), one=True)
    return (pid, bought, sold, extra) if ok else None


# ---------- routes ----------
@app.route("/")
def index():
    items, records, expenses, products, s = summary()
    return render_template("index.html", name=NAME, items=items, records=records, expenses=expenses,
                           products=products, s=s)


@app.post("/product/add")
def add_product():
    row = parse_product(request.form)
    if row:
        q("INSERT INTO products(name,buy,sell) VALUES(?,?,?)", row)
        flash("Item added. Now record what you bought and sold in step 2.", "success")
    else:
        flash("Enter the item name and both prices (0 or more).", "danger")
    return redirect(url_for("index"))


@app.route("/product/<int:pid>/edit", methods=["GET", "POST"])
def edit_product(pid):
    item = q("SELECT * FROM products WHERE id=?", (pid,), one=True)
    if not item:
        abort(404)
    if request.method == "POST":
        row = parse_product(request.form)
        if row:
            q("UPDATE products SET name=?, buy=?, sell=? WHERE id=?", row + (pid,))
            flash("Item updated.", "success")
            return redirect(url_for("index"))
        flash("Invalid values.", "danger")
    return render_template("edit_product.html", name=NAME, item=item)


@app.post("/product/<int:pid>/delete")
def delete_product(pid):
    q("DELETE FROM records WHERE product_id=?", (pid,))
    q("DELETE FROM products WHERE id=?", (pid,))
    flash("Item and its records deleted.", "success")
    return redirect(url_for("index"))


@app.post("/record/add")
def add_record():
    row = parse_record(request.form)
    if row:
        q("INSERT INTO records(product_id,bought,sold,extra,created) VALUES(?,?,?,?,?)",
          row + (datetime.now().strftime("%Y-%m-%d %H:%M"),))
        flash("Record added.", "success")
    else:
        flash("Choose an item, enter quantity bought above 0, and quantity sold not more than bought.", "danger")
    return redirect(url_for("index") + "#results")


@app.route("/record/<int:rid>/edit", methods=["GET", "POST"])
def edit_record(rid):
    rec = q("SELECT * FROM records WHERE id=?", (rid,), one=True)
    if not rec:
        abort(404)
    if request.method == "POST":
        row = parse_record(request.form)
        if row:
            q("UPDATE records SET product_id=?, bought=?, sold=?, extra=? WHERE id=?", row + (rid,))
            flash("Record updated.", "success")
            return redirect(url_for("index") + "#results")
        flash("Invalid values. Quantity sold cannot be more than quantity bought.", "danger")
    return render_template("edit_record.html", name=NAME, rec=rec, products=q("SELECT * FROM products ORDER BY id"))


@app.post("/record/<int:rid>/delete")
def delete_record(rid):
    q("DELETE FROM records WHERE id=?", (rid,))
    flash("Record deleted.", "success")
    return redirect(url_for("index") + "#results")


@app.post("/expense/add")
def add_expense():
    try:
        name, amount = request.form["name"].strip(), float(request.form["amount"])
        assert name and amount >= 0
        q("INSERT INTO expenses(name,amount) VALUES(?,?)", (name, amount))
        flash("Expense added.", "success")
    except (KeyError, ValueError, AssertionError):
        flash("Enter an expense name and an amount of 0 or more.", "danger")
    return redirect(url_for("index"))


@app.post("/expense/<int:eid>/delete")
def delete_expense(eid):
    q("DELETE FROM expenses WHERE id=?", (eid,))
    return redirect(url_for("index"))


@app.post("/reset")
def reset():
    for t in ("records", "products", "expenses"):
        q(f"DELETE FROM {t}")
    flash("All data cleared.", "warning")
    return redirect(url_for("index"))


# ---------- export: Excel, PDF, Word, CSV (standard library only) ----------
HEAD = ["Item", "Bought", "Sold", "Unsold", "Buy price", "Sell price", "Extra costs", "Revenue", "Total cost", "Profit/Loss"]


def report():
    items, records, expenses, products, s = summary()
    rows = [[i["name"], i["bought"], i["sold"], i["unsold"], i["buy"], i["sell"], i["extra"],
             i["revenue"], i["cost"], i["profit"]] for i in items if i["has_records"]]
    totals = [("Total revenue (sales)", s["revenue"]), ("Total cost of all stock bought", s["cost"]),
              ("Gross profit / loss", s["gross"])]
    totals += [("Expense: " + e["name"], e["amount"]) for e in expenses]
    totals += [("Total business expenses", s["expenses"]), ("NET PROFIT / LOSS", s["net"]),
               ("Unsold stock value (at selling price)", s["stock_value"]),
               ("Potential net profit if all stock is sold", s["potential"])]
    sub = "Generated " + date.today().strftime("%d %B %Y") + " | Amounts in MK"
    return "Business Calculator - Profit and Loss Report", sub, rows, totals


def cell_text(j, v):
    return str(v) if j == 0 else f"{v:g}" if j < 4 else f"{v:,.2f}"


def zip_bytes(parts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


def make_xlsx(title, sub, rows, totals):
    grid = [[(title, 1)], [(sub, 0)], [], [(h, 1) for h in HEAD]]
    grid += [[(v, 0 if j < 4 else 2) for j, v in enumerate(r)] for r in rows] + [[]]
    grid += [[(l, 1), (v, 2)] for l, v in totals]
    xml = []
    for n, row in enumerate(grid, 1):
        cells = ""
        for j, (v, st) in enumerate(row):
            ref = f"{chr(65 + j)}{n}"
            cells += (f'<c r="{ref}" s="{st}"><v>{v}</v></c>' if isinstance(v, (int, float))
                      else f'<c r="{ref}" s="{st}" t="inlineStr"><is><t>{esc(str(v))}</t></is></c>')
        xml.append(f'<row r="{n}">{cells}</row>')
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    head = '<?xml version="1.0" encoding="UTF-8"?>'
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    return zip_bytes({
        "[Content_Types].xml": head + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": head + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": head + f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="Profit and Loss" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": head + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{rel}/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": head + f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        "xl/worksheets/sheet1.xml": head + f'<worksheet xmlns="{ns}"><cols><col min="1" max="1" width="40" customWidth="1"/><col min="2" max="10" width="14" customWidth="1"/></cols><sheetData>{"".join(xml)}</sheetData></worksheet>'})


def make_docx(title, sub, rows, totals):
    def p(text, bold=False, size=22):
        return (f'<w:p><w:r><w:rPr>{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/></w:rPr>'
                f'<w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>')
    tr = lambda cells, bold=False: "<w:tr>" + "".join(
        f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>{p(c, bold, 16)}</w:tc>' for c in cells) + "</w:tr>"
    borders = "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="888888"/>'
                      for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    table = (f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{borders}</w:tblBorders></w:tblPr>'
             + tr(HEAD, True) + "".join(tr([cell_text(j, v) for j, v in enumerate(r)]) for r in rows) + "</w:tbl>")
    body = (p(title, True, 32) + p(sub) + table + p("") + p("Summary", True, 26)
            + "".join(p(f"{l}: MK{v:,.2f}", l.startswith("NET")) for l, v in totals)
            + '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/><w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    return zip_bytes({
        "[Content_Types].xml": head + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": head + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": head + f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'})


def make_pdf(title, sub, rows, totals):
    W = [24, 8, 8, 8, 12, 12, 12, 14, 14, 14]
    line = lambda cells: " ".join(str(c)[:W[j]].ljust(W[j]) if j == 0 else str(c).rjust(W[j]) for j, c in enumerate(cells))
    lines = ["#" + title, sub, "", line(HEAD), "-" * 135]
    lines += [line([cell_text(j, v) for j, v in enumerate(r)]) for r in rows] + ["", "#Summary"]
    lines += [f"{l:<46}{v:>16,.2f}" for l, v in totals]
    pages = [lines[i:i + 40] for i in range(0, len(lines), 40)]
    pe = lambda t: t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>"]
    kids = []
    for pg in pages:
        n = len(objs) + 1
        kids.append(f"{n} 0 R")
        ops = ["BT", "40 555 Td", "12 TL"] + [
            f"/F2 11 Tf ({pe(l[1:])}) Tj T* /F1 8 Tf" if l.startswith("#") else f"/F1 8 Tf ({pe(l)}) Tj T*"
            for l in pg] + ["ET"]
        stream = "\n".join(ops).encode("latin-1", "replace")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {n + 1} 0 R >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()


def make_csv(title, sub, rows, totals):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerows([[title], [sub], [], HEAD] + rows + [[]] + [list(t) for t in totals])
    return out.getvalue().encode("utf-8-sig")  # BOM so Excel shows it correctly


EXPORTS = {"xlsx": (make_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
           "docx": (make_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
           "pdf": (make_pdf, "application/pdf"), "csv": (make_csv, "text/csv")}


@app.route("/export/<fmt>")
def export(fmt):
    if fmt not in EXPORTS:
        abort(404)
    maker, mime = EXPORTS[fmt]
    return Response(maker(*report()), mimetype=mime,
                    headers={"Content-Disposition": f"attachment; filename=profit_loss_report.{fmt}"})


init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
