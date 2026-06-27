from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import os
import uuid
from werkzeug.utils import secure_filename
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)
app.secret_key = "pdf_tool_secret"

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ALLOWED = {"pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


@app.route("/")
def index():
    return render_template("index.html")


# ───────── MERGE PDF ─────────
@app.route("/merge", methods=["POST"])
def merge():
    files = request.files.getlist("pdfs")
    if len(files) < 2:
        flash("At least 2 PDFs required")
        return redirect(url_for("index"))

    writer = PdfWriter()

    for f in files:
        if f and allowed_file(f.filename):
            path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
            f.save(path)

            reader = PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)

    out_name = f"merged_{uuid.uuid4().hex[:8]}.pdf"
    out_path = os.path.join(OUTPUT_FOLDER, out_name)

    with open(out_path, "wb") as f:
        writer.write(f)

    return redirect(url_for("preview", filename=out_name))


# ───────── EXTRACT TEXT (FIXED) ─────────
@app.route("/extract", methods=["POST"])
def extract():
    f = request.files.get("pdf")

    if not f or not allowed_file(f.filename):
        flash("Upload valid PDF")
        return redirect(url_for("index"))

    path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
    f.save(path)

    reader = PdfReader(path)

    text = ""
    for page in reader.pages:
        text += (page.extract_text() or "") + "\n"

    out_name = f"extract_{uuid.uuid4().hex[:8]}.txt"
    out_path = os.path.join(OUTPUT_FOLDER, out_name)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    return redirect(url_for("download", filename=out_name))


# ───────── DOWNLOAD ─────────
@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)


# ───────── PREVIEW ─────────
@app.route("/preview/<filename>")
def preview(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)

    if not os.path.exists(path):
        flash("File not found")
        return redirect(url_for("index"))

    return render_template("preview.html", filename=filename)


# ───────── RUN ─────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)