from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, flash
import sqlite3
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
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

# 🔥 FIXED FONT PATH (root में रखा है इसलिए)
FONT_PATH = "NotoSansDevanagari.ttf"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# Register font safely
try:
    if os.path.exists(FONT_PATH):
        pdfmetrics.registerFont(TTFont("NotoDevanagari", FONT_PATH))
except:
    print("Font load failed, using default font")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            input_files TEXT,
            output_file TEXT,
            created_at TEXT,
            status TEXT,
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


# ─── MERGE PDF ─────────────────────────────
@app.route("/merge", methods=["POST"])
def merge():
    files = request.files.getlist("pdfs")
    if len(files) < 2:
        flash("At least 2 PDFs required!", "error")
        return redirect(url_for("index"))

    writer = PdfWriter()
    names = []

    for f in files:
        if f and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)

            names.append(filename)
            reader = PdfReader(path)

            for page in reader.pages:
                writer.add_page(page)

    out_name = f"merged_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)

    with open(out_path, "wb") as out:
        writer.write(out)

    log_action("Merge", ", ".join(names), out_name)
    return redirect(url_for("preview", filename=out_name))


# ─── SPLIT PDF ─────────────────────────────
@app.route("/split", methods=["POST"])
def split():
    f = request.files.get("pdf")
    if not f:
        flash("Upload PDF!", "error")
        return redirect(url_for("index"))

    path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
    f.save(path)

    reader = PdfReader(path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    out_name = f"split_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)

    with open(out_path, "wb") as out:
        writer.write(out)

    log_action("Split", f.filename, out_name)
    return redirect(url_for("preview", filename=out_name))


# ─── CREATE PDF ─────────────────────────────
@app.route("/create", methods=["POST"])
def create():
    title = request.form.get("title", "Document")
    content = request.form.get("content", "")

    out_name = f"created_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)

    doc = SimpleDocTemplate(out_path, pagesize=A4)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))

    for para in content.split("\n\n"):
        story.append(Paragraph(para, styles["Normal"]))
        story.append(Spacer(1, 10))

    doc.build(story)

    log_action("Create", "-", out_name)
    return redirect(url_for("preview", filename=out_name))


# ─── WATERMARK (FIXED) ─────────────────────────────
@app.route("/watermark", methods=["POST"])
def watermark():
    f = request.files.get("pdf")
    text = request.form.get("watermark_text", "CONFIDENTIAL")

    path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
    f.save(path)

    wm_path = os.path.join(GENERATED_FOLDER, "wm.pdf")
    c = canvas.Canvas(wm_path, pagesize=A4)

    width, height = A4
    c.setFont("Helvetica", 40)

    # FIXED (NO alpha crash)
    c.setFillGray(0.5)

    c.saveState()
    c.translate(width/2, height/2)
    c.rotate(45)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.save()

    wm_reader = PdfReader(wm_path)
    wm_page = wm_reader.pages[0]

    reader = PdfReader(path)
    writer = PdfWriter()

    for page in reader.pages:
        page.merge_page(wm_page)
        writer.add_page(page)

    out_name = f"wm_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)

    with open(out_path, "wb") as out:
        writer.write(out)

    os.remove(wm_path)

    log_action("Watermark", f.filename, out_name)
    return redirect(url_for("preview", filename=out_name))


# ─── HISTORY ─────────────────────────────
@app.route("/history")
def history():
    conn = get_db()
    rows = conn.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("history.html", rows=rows)


# ─── PREVIEW ─────────────────────────────
@app.route("/preview/<filename>")
def preview(filename):
    path = os.path.join(GENERATED_FOLDER, filename)

    if not os.path.exists(path):
        flash("File not found!", "error")
        return redirect(url_for("index"))

    return render_template("preview.html", filename=filename)


# ─── DOWNLOAD ─────────────────────────────
@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(GENERATED_FOLDER, filename), as_attachment=True)


if __name__ == "__main__":
    init_db()
    app.run()