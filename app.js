/* ── PDF Info API ──────────────────────────────────── */
function getPdfInfo() {
  const fileInput = document.getElementById("info-file");
  const resultDiv = document.getElementById("info-result");

  if (!fileInput.files.length) {
    alert("Pehle ek PDF file chunen!");
    return;
  }

  const formData = new FormData();
  formData.append("pdf", fileInput.files[0]);

  resultDiv.classList.remove("hidden");
  resultDiv.textContent = "⏳ Loading...";

  fetch("/api/info", { method: "POST", body: formData })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        resultDiv.textContent = "❌ Error: " + data.error;
        return;
      }
      resultDiv.innerHTML = `
        <strong>📑 Pages:</strong> ${data.pages}<br/>
        <strong>📝 Title:</strong> ${data.title}<br/>
        <strong>👤 Author:</strong> ${data.author}<br/>
        <strong>💾 Size:</strong> ${data.size_kb} KB<br/>
        <strong>🔒 Encrypted:</strong> ${data.encrypted ? "Haan" : "Nahi"}
      `;
    })
    .catch(() => {
      resultDiv.textContent = "❌ Server se connect nahi ho saka.";
    });
}

/* ── File name display for merge input ────────────── */
document.addEventListener("DOMContentLoaded", () => {
  // Show selected file names for merge
  const mergeInput = document.querySelector("#merge-card input[type='file']");
  const mergePreview = document.getElementById("merge-preview");
  if (mergeInput && mergePreview) {
    mergeInput.addEventListener("change", () => {
      const files = Array.from(mergeInput.files);
      if (files.length) {
        mergePreview.innerHTML = files
          .map((f, i) => `<span>${i + 1}. ${f.name}</span>`)
          .join("<br/>");
      } else {
        mergePreview.innerHTML = "";
      }
    });
  }

  // Generic: update file-label span text on file selection
  document.querySelectorAll(".file-label").forEach(label => {
    const input = label.querySelector("input[type='file']");
    const span  = label.querySelector("span");
    if (!input || !span) return;
    input.addEventListener("change", () => {
      if (input.files.length === 1) {
        span.textContent = "✅ " + input.files[0].name;
      } else if (input.files.length > 1) {
        span.textContent = `✅ ${input.files.length} files chunen`;
      } else {
        span.textContent = "📂 File Chunen";
      }
    });
  });

  // Auto-dismiss flash messages after 4s
  document.querySelectorAll(".flash").forEach(el => {
    setTimeout(() => {
      el.style.transition = "opacity .5s";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 500);
    }, 4000);
  });
});
