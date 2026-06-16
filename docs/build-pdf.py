#!/usr/bin/env python3
"""build-pdf.py — Regenera los PDF de la carpeta docs/.

Produce:
  INSTRUCTIVO-CARGA-DE-DATOS.pdf  <-  INSTRUCTIVO-CARGA-DE-DATOS.md
  INFORME-CRUCE-AV-PRINCIPAL.pdf  <-  informe-caso-ejemplo.html (narrativo)
  INFORME-GENERADO-EJEMPLO.pdf    <-  informe-generado-ejemplo.html (1 clic, tarea 5.1)
  INVESTIGACION-COMPARATIVA.pdf   <-  investigacion-comparativa.md

El informe «generado» se produce con `python regen-informe-generado.py` (que
llama al motor); aquí solo se imprime a PDF el HTML resultante.

Requisitos:
  - Python 3
  - Paquete 'markdown'  ->  pip install --user markdown
  - Microsoft Edge o Google Chrome instalado

Uso:
  python build-pdf.py              (genera todos)
  python build-pdf.py informe      (solo el informe)
  python build-pdf.py instructivo
  python build-pdf.py investigacion
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DOCS = Path(__file__).resolve().parent

# Estilo swiss compartido para el HTML del instructivo.
CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family:'Inter Tight','Helvetica Neue','Segoe UI',Arial,sans-serif;
       font-size:10.5pt; line-height:1.5; color:#0a0a0a; margin:0; }
h1 { font-size:21pt; font-weight:700; letter-spacing:-0.5px; margin:0 0 6px;
     border-bottom:3px solid #8a0f1c; padding-bottom:8px; }
h2 { font-size:13.5pt; font-weight:700; margin:20px 0 8px;
     border-bottom:1px solid #0a0a0a; padding-bottom:3px; page-break-after:avoid; }
h3 { font-size:11pt; font-weight:600; color:#8a0f1c; margin:14px 0 6px;
     page-break-after:avoid; }
p { margin:6px 0; }
a { color:#8a0f1c; text-decoration:none; }
strong { font-weight:700; }
table { border-collapse:collapse; width:100%; margin:8px 0; font-size:9pt;
        page-break-inside:avoid; }
th { background:#0a0a0a; color:#fff; text-align:left; padding:5px 7px;
     font-size:8pt; text-transform:uppercase; letter-spacing:0.4px; }
td { border:1px solid #d0d0d0; padding:4px 7px; }
tbody tr:nth-child(even) td { background:#f6f6f6; }
code { font-family:'JetBrains Mono',Consolas,monospace; font-size:9pt;
       background:#f0f0f0; padding:1px 4px; border:1px solid #e2e2e2; }
pre { background:#f4f4f4; border-left:3px solid #8a0f1c; padding:9px 12px;
      font-size:9pt; page-break-inside:avoid; }
pre code { background:none; border:none; padding:0; }
blockquote { border-left:3px solid #8a0f1c; background:#faf2f2; margin:10px 0;
             padding:6px 12px; font-size:10pt; page-break-inside:avoid; }
blockquote p { margin:3px 0; }
ul,ol { margin:6px 0; padding-left:22px; }
li { margin:3px 0; }
img { max-width:100%; height:auto; display:block; margin:14px auto;
      page-break-inside:avoid; }
hr { border:none; border-top:1px solid #d0d0d0; margin:16px 0; }
"""

TARGETS = {
    "instructivo": ("INSTRUCTIVO-CARGA-DE-DATOS.md", "INSTRUCTIVO-CARGA-DE-DATOS.pdf"),
    "investigacion": ("investigacion-comparativa.md", "INVESTIGACION-COMPARATIVA.pdf"),
    "informe": ("informe-caso-ejemplo.html", "INFORME-CRUCE-AV-PRINCIPAL.pdf"),
    "informe-generado": ("informe-generado-ejemplo.html", "INFORME-GENERADO-EJEMPLO.pdf"),
}

# Claves cuya fuente es Markdown (se convierte a HTML antes de imprimir).
# El resto de TARGETS ya son HTML y se imprimen directamente.
MARKDOWN_KEYS = ("instructivo", "investigacion")


def find_browser() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    for name in ("msedge", "chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def html_to_pdf(browser: str, html_path: Path, pdf_path: Path) -> bool:
    """Imprime un HTML local a PDF usando el navegador en modo headless."""
    if pdf_path.exists():
        pdf_path.unlink()
    url = html_path.resolve().as_uri()
    subprocess.run(
        [
            browser, "--headless", "--disable-gpu",
            "--print-to-pdf-no-header", "--no-margins",
            "--virtual-time-budget=8000",
            f"--print-to-pdf={pdf_path}", url,
        ],
        check=False,
        capture_output=True,
    )
    # El proceso headless puede tardar un instante en cerrar el archivo.
    for _ in range(20):
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True
        time.sleep(0.5)
    return pdf_path.exists()


def build_markdown(browser: str, key: str) -> bool:
    """Convierte un documento Markdown a PDF (MD -> HTML con estilo swiss -> PDF)."""
    try:
        import markdown
    except ImportError:
        print("  ERROR: falta el paquete 'markdown'.")
        print("         Instálalo con:  pip install --user markdown")
        return False

    src = DOCS / TARGETS[key][0]
    if not src.exists():
        print(f"  ERROR: no se encuentra {src.name}")
        return False

    body = markdown.markdown(
        src.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    doc = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>{src.stem}</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>"
    )
    tmp = DOCS / "_build_tmp.html"
    tmp.write_text(doc, encoding="utf-8")
    try:
        return html_to_pdf(browser, tmp, DOCS / TARGETS[key][1])
    finally:
        tmp.unlink(missing_ok=True)


def build_html_target(browser: str, key: str) -> bool:
    """Imprime a PDF un target cuya fuente ya es HTML."""
    src = DOCS / TARGETS[key][0]
    if not src.exists():
        print(f"  ERROR: no se encuentra {src.name}")
        return False
    return html_to_pdf(browser, src, DOCS / TARGETS[key][1])


def main() -> int:
    valid = ("all",) + tuple(TARGETS)
    which = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if which not in valid:
        print(f"Argumento no reconocido: {which}")
        print(f"Uso: python build-pdf.py [{'|'.join(valid)}]")
        return 2

    browser = find_browser()
    if not browser:
        print("ERROR: no se encontró Microsoft Edge ni Google Chrome.")
        return 1
    print(f"Navegador: {browser}\n")

    ok = True
    for key in TARGETS:
        if which not in ("all", key):
            continue
        pdf = DOCS / TARGETS[key][1]
        print(f"Generando {pdf.name} ...")
        res = build_markdown(browser, key) if key in MARKDOWN_KEYS else build_html_target(browser, key)
        if res:
            print(f"  OK  ({pdf.stat().st_size / 1024:.0f} KB)")
        else:
            print("  FALLO")
        ok = ok and res

    print()
    if ok:
        print(f"Listo. PDFs en: {DOCS}")
        return 0
    print("Hubo errores. Revisa los mensajes anteriores.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
