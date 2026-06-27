from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, flash
import sqlite3
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "pdf_pro_secret_key_2024"

UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"
ALLOWED_EXTENSIONS = {"pdf", "txt"}
DB_PATH = "database.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)


# ─── DB ─────────────────────────────
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
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_action(action, input_files, output_file):
    conn = get_db()
    conn.execute(
        "INSERT INTO history VALUES (NULL,?,?,?,?)",
        (action, input_files, output_file, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── HOME ─────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ─── MERGE ─────────────────────────────
@app.route("/merge", methods=["POST"])
def merge():
    files = request.files.getlist("pdfs")

    if not files or len(files) < 2:
        flash("कम से कम 2 PDF upload करो", "error")
        return redirect(url_for("index"))

    writer = PdfWriter()
    names = []

    for f in files:
        if f and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)

            reader = PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)

            names.append(filename)

    out_name = f"merged_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(GENERATED_FOLDER, out_name)

    with open(out_path, "wb") as out:
        writer.write(out)

    log_action("merge", ", ".join(names), out_name)
    return redirect(url_for("preview", filename=out_name))


# ─── SPLIT (FIXED) ─────────────────────────────
@app.route("/split", methods=["POST"])
def split():
    f = request.files.get("pdf")

    if not f or not allowed_file(f.filename):
        flash("Valid PDF upload करो", "error")
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

    log_action("split", f.filename, out_name)
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

    story = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 12)
    ]

    for para in content.split("\n\n"):
        story.append(Paragraph(para, styles["Normal"]))
        story.append(Spacer(1, 10))

    doc.build(story)

    log_action("create", "-", out_name)
    return redirect(url_for("preview", filename=out_name))


# ─── WATERMARK (FIXED 100%) ─────────────────────────────
@app.route("/watermark", methods=["POST"])
def watermark():
    f = request.files.get("pdf")
    text = request.form.get("watermark_text", "CONFIDENTIAL")

    if not f or not allowed_file(f.filename):
        flash("Valid PDF upload करो", "error")
        return redirect(url_for("index"))

    path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
    f.save(path)

    wm_path = os.path.join(GENERATED_FOLDER, f"wm_{uuid.uuid4().hex[:6]}.pdf")

    c = canvas.Canvas(wm_path, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica", 40)
    c.setFillGray(0.5)

    c.saveState()
    c.translate(width / 2, height / 2)
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

    log_action("watermark", f.filename, out_name)
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
        flash("File not found", "error")
        return redirect(url_for("index"))

    return render_template("preview.html", filename=filename)


# ─── DOWNLOAD ─────────────────────────────
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(GENERATED_FOLDER, filename)
    return send_file(path, as_attachment=True)


# ─── START ─────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run()