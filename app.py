from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, flash
import sqlite3
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pdfplumber

app = Flask(__name__)
app.secret_key = "pdf_pro_secret_key_2024"

UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"
ALLOWED_EXTENSIONS = {"pdf", "txt"}
DB_PATH = "database.db"
FONT_PATH = "fonts/NotoSansDevanagari.ttf"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# Register Hindi font
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("NotoDevanagari", FONT_PATH))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            input_files TEXT,
            output_file TEXT,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'success',
            details TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_action(action, input_files, output_file, status="success", details=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO history (action, input_files, output_file, created_at, status, details) VALUES (?, ?, ?, ?, ?, ?)",
        (action, input_files, output_file, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, details)
    )
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


# ─── Merge PDFs ──────────────────────────────────────────────────────────────
@app.route("/merge", methods=["POST"])
def merge():
    files = request.files.getlist("pdfs")
    if len(files) < 2:
        flash("Kam se kam 2 PDF files chahiye merge karne ke liye!", "error")
        return redirect(url_for("index"))

    writer = PdfWriter()
    input_names = []
    for f in files:
        if f and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)
            input_names.append(filename)
            reader = PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)

    out_name = f"merged_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)
    with open(out_path, "wb") as out:
        writer.write(out)

    log_action("Merge PDF", ", ".join(input_names), out_name)
    flash(f"PDF merge ho gayi: {out_name}", "success")
    return redirect(url_for("preview", filename=out_name))


# ─── Split PDF ───────────────────────────────────────────────────────────────
@app.route("/split", methods=["POST"])
def split():
    f = request.files.get("pdf")
    pages_input = request.form.get("pages", "").strip()

    if not f or not allowed_file(f.filename):
        flash("Valid PDF file upload karein!", "error")
        return redirect(url_for("index"))

    filename = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)

    reader = PdfReader(path)
    total = len(reader.pages)

    # Parse page ranges like "1-3,5,7-9"
    if pages_input:
        selected = set()
        for part in pages_input.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-")
                selected.update(range(int(a) - 1, min(int(b), total)))
            else:
                idx = int(part) - 1
                if 0 <= idx < total:
                    selected.add(idx)
    else:
        selected = set(range(total))

    out_name = f"split_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)
    writer = PdfWriter()
    for i in sorted(selected):
        writer.add_page(reader.pages[i])
    with open(out_path, "wb") as out:
        writer.write(out)

    log_action("Split PDF", filename, out_name, details=f"Pages: {pages_input or 'all'}")
    flash(f"PDF split ho gayi: {out_name}", "success")
    return redirect(url_for("preview", filename=out_name))


# ─── Extract Text ─────────────────────────────────────────────────────────────
@app.route("/extract", methods=["POST"])
def extract():
    f = request.files.get("pdf")
    if not f or not allowed_file(f.filename):
        flash("Valid PDF file upload karein!", "error")
        return redirect(url_for("index"))

    filename = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)

    extracted = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            extracted.append({"page": i + 1, "text": text})

    out_name = f"extracted_{uuid.uuid4().hex[:8]}.txt"
    out_path = os.path.join(GENERATED_FOLDER, out_name)
    with open(out_path, "w", encoding="utf-8") as out:
        for item in extracted:
            out.write(f"=== Page {item['page']} ===\n{item['text']}\n\n")

    log_action("Extract Text", filename, out_name)
    flash(f"Text extract ho gaya: {out_name}", "success")
    return redirect(url_for("preview", filename=out_name))


# ─── Create PDF ──────────────────────────────────────────────────────────────
@app.route("/create", methods=["POST"])
def create():
    title = request.form.get("title", "Mera Document")
    content = request.form.get("content", "")
    template = request.form.get("template", "simple")

    out_name = f"created_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=24,
        spaceAfter=20,
        textColor=colors.HexColor("#2C3E50"),
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=12,
        leading=18,
        spaceAfter=10,
    )

    story = []

    if template == "report":
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.2 * inch))
        date_style = ParagraphStyle("Date", parent=styles["Normal"],
                                    fontSize=10, textColor=colors.grey)
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d %B %Y')}", date_style))
        story.append(Spacer(1, 0.3 * inch))

        # Divider line using Table trick
        story.append(Table([[""]], colWidths=[6.5 * inch],
                           style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#2C3E50"))])))
        story.append(Spacer(1, 0.3 * inch))

    elif template == "invoice":
        story.append(Paragraph("INVOICE", title_style))
        story.append(Paragraph(f"#{uuid.uuid4().hex[:6].upper()}", body_style))
        story.append(Spacer(1, 0.3 * inch))
        data = [["Item", "Qty", "Rate", "Amount"],
                ["Service 1", "1", "₹1000", "₹1000"],
                ["Service 2", "2", "₹500", "₹1000"],
                ["", "", "Total", "₹2000"]]
        tbl = Table(data, colWidths=[3 * inch, inch, inch, 1.5 * inch])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.whitesmoke, colors.white]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ECF0F1")),
            ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.3 * inch))
    else:
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.3 * inch))

    for para in content.split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.strip().replace("\n", "<br/>"), body_style))

    doc.build(story)
    log_action("Create PDF", "-", out_name, details=f"Template: {template}")
    flash(f"PDF ban gayi: {out_name}", "success")
    return redirect(url_for("preview", filename=out_name))


# ─── Rotate PDF ──────────────────────────────────────────────────────────────
@app.route("/rotate", methods=["POST"])
def rotate():
    f = request.files.get("pdf")
    angle = int(request.form.get("angle", 90))

    if not f or not allowed_file(f.filename):
        flash("Valid PDF file upload karein!", "error")
        return redirect(url_for("index"))

    filename = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)

    reader = PdfReader(path)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(angle)
        writer.add_page(page)

    out_name = f"rotated_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)
    with open(out_path, "wb") as out:
        writer.write(out)

    log_action("Rotate PDF", filename, out_name, details=f"Angle: {angle}°")
    flash(f"PDF rotate ho gayi: {out_name}", "success")
    return redirect(url_for("preview", filename=out_name))


# ─── Add Watermark ───────────────────────────────────────────────────────────
@app.route("/watermark", methods=["POST"])
def watermark():
    f = request.files.get("pdf")
    wm_text = request.form.get("watermark_text", "CONFIDENTIAL")

    if not f or not allowed_file(f.filename):
        flash("Valid PDF file upload karein!", "error")
        return redirect(url_for("index"))

    filename = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)

    # Create watermark PDF
    wm_path = os.path.join(GENERATED_FOLDER, f"wm_{uuid.uuid4().hex[:6]}.pdf")
    c = canvas.Canvas(wm_path, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica", 50)
    c.setFillColorRGB(0.8, 0.8, 0.8, alpha=0.4)
    c.saveState()
    c.translate(width / 2, height / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, wm_text)
    c.restoreState()
    c.save()

    wm_reader = PdfReader(wm_path)
    wm_page = wm_reader.pages[0]

    reader = PdfReader(path)
    writer = PdfWriter()
    for page in reader.pages:
        page.merge_page(wm_page)
        writer.add_page(page)

    out_name = f"watermarked_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)
    with open(out_path, "wb") as out:
        writer.write(out)

    os.remove(wm_path)
    log_action("Watermark PDF", filename, out_name, details=f"Text: {wm_text}")
    flash(f"Watermark lag gayi: {out_name}", "success")
    return redirect(url_for("preview", filename=out_name))


# ─── Password Protect ────────────────────────────────────────────────────────
@app.route("/protect", methods=["POST"])
def protect():
    f = request.files.get("pdf")
    password = request.form.get("password", "")

    if not f or not allowed_file(f.filename):
        flash("Valid PDF file upload karein!", "error")
        return redirect(url_for("index"))
    if not password:
        flash("Password dalna zaroori hai!", "error")
        return redirect(url_for("index"))

    filename = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)

    reader = PdfReader(path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)

    out_name = f"protected_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)
    with open(out_path, "wb") as out:
        writer.write(out)

    log_action("Protect PDF", filename, out_name)
    flash(f"PDF password se protect ho gayi: {out_name}", "success")
    return redirect(url_for("preview", filename=out_name))


# ─── Preview & Download ──────────────────────────────────────────────────────
@app.route("/preview/<filename>")
def preview(filename):
    path = os.path.join(GENERATED_FOLDER, filename)
    if not os.path.exists(path):
        flash("File nahi mili!", "error")
        return redirect(url_for("index"))

    info = {}
    if filename.endswith(".pdf"):
        try:
            reader = PdfReader(path)
            info["pages"] = len(reader.pages)
            info["size"] = f"{os.path.getsize(path) / 1024:.1f} KB"
        except Exception:
            info["pages"] = "?"
            info["size"] = "?"
    else:
        info["size"] = f"{os.path.getsize(path) / 1024:.1f} KB"

    return render_template("preview.html", filename=filename, info=info)


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(GENERATED_FOLDER, filename)
    if not os.path.exists(path):
        flash("File nahi mili!", "error")
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True)


# ─── History ─────────────────────────────────────────────────────────────────
@app.route("/history")
def history():
    conn = get_db()
    rows = conn.execute("SELECT * FROM history ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()
    return render_template("history.html", rows=rows)


@app.route("/history/clear", methods=["POST"])
def clear_history():
    conn = get_db()
    conn.execute("DELETE FROM history")
    conn.commit()
    conn.close()
    flash("History clear ho gayi!", "success")
    return redirect(url_for("history"))


# ─── PDF Info API ────────────────────────────────────────────────────────────
@app.route("/api/info", methods=["POST"])
def api_info():
    f = request.files.get("pdf")
    if not f:
        return jsonify({"error": "No file"}), 400
    filename = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)
    try:
        reader = PdfReader(path)
        meta = reader.metadata or {}
        return jsonify({
            "pages": len(reader.pages),
            "title": meta.get("/Title", "N/A"),
            "author": meta.get("/Author", "N/A"),
            "size_kb": round(os.path.getsize(path) / 1024, 2),
            "encrypted": reader.is_encrypted,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
