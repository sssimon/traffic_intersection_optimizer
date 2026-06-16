"""Pruebas — informe profesional de 1 clic (tarea 5.1, F5)."""
import pytest

from app.data import sample_intersection
from app.reports import _es, build_report_html


def test_es_spanish_number_format():
    # Millares con espacio (duro), decimal con coma. Se comprueba la estructura
    # sin escribir el carácter U+00A0 como literal.
    s = _es(1234.5, 1)
    assert s[1].isspace()                 # separador de millares es un espacio
    assert s.replace(s[1], "") == "1234,5"
    assert _es(0.94, 2) == "0,94"
    assert _es(120, 0) == "120"


def test_report_has_all_core_sections():
    html = build_report_html(sample_intersection(), samples=300)
    for marker in [
        "<!doctype html>",
        "Resumen ejecutivo",
        "Descripción de la intersección",
        "Metodología",
        "Plan semafórico",
        "Flujos de demanda",
        "Análisis de capacidad",
        "Incertidumbre",
        "Conclusiones",
        "Anexo A",
    ]:
        assert marker in html, f"falta la sección: {marker}"
    # Autocontenido: CSS embebido y figuras SVG inline (sin archivos externos).
    assert "<style>" in html
    assert "<svg" in html
    assert "<img" not in html
    # Barra de impresión solo-pantalla y badges de LOS.
    assert "window.print()" in html
    assert 'class="badge' in html


def test_report_includes_audit_trace():
    html = build_report_html(sample_intersection(), samples=300)
    # El anexo trae fórmulas y la fuente HCM citada.
    assert "d1" in html
    assert "HCM" in html


def test_report_includes_plos_distribution():
    html = build_report_html(sample_intersection(), samples=300, volume_cv=0.10)
    assert "probabilidad de cada los" in html.lower()
    # La figura P(LOS) etiqueta las seis letras.
    assert ">A<" in html and ">F<" in html


def test_sections_can_be_omitted():
    html = build_report_html(
        sample_intersection(), include_uncertainty=False, include_audit=False,
    )
    assert "Anexo A" not in html
    assert "7. Incertidumbre" not in html
    # El núcleo sigue presente.
    assert "Análisis de capacidad" in html


def test_no_phases_raises():
    cfg = sample_intersection()
    cfg.phases = []
    with pytest.raises(ValueError):
        build_report_html(cfg)


def test_report_reflects_actual_numbers():
    cfg = sample_intersection()
    html = build_report_html(cfg, samples=300)
    # El nombre de la intersección y al menos un grupo aparecen.
    assert cfg.name in html
    assert "N-T" in html


def test_report_includes_pedestrian_section_when_crossings():
    # El ejemplo trae cruces (M10): el informe debe traer la sección peatonal.
    html = build_report_html(sample_intersection(), samples=300)
    assert "Análisis peatonal (M10)" in html
    assert "X-N" in html and "X-E" in html
