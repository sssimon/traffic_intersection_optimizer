# Plan estratégico — Traffic Intersection Optimizer

**Objetivo: una herramienta de análisis de intersecciones state-of-the-art,
diferenciada de VISSIM, SUMO, Synchro y Sidra.**

Fecha: 2026-06-11 · Parte del estado auditado en `investigacion-comparativa.md`
(2026-05-21) y del código actual (25 tests pasando).

---

## 1. Qué tenemos hoy (diagnóstico honesto)

**Activos:**

| Activo | Estado |
|--------|--------|
| Motor analítico: Webster + demora HCM (d1/d2) + LOS | Correcto, testeado (25 tests, 0.05 s) |
| TWSC (PARE) + glorieta por aceptación de brechas | Funcional, supuestos declarados |
| Simulador de colas estocástico | Funcional, etiquetas ya sinceradas |
| Comparación de escenarios + recomendación | Funcional pero básica (multiplicador uniforme) |
| Frontend React 19, 5 pestañas, mapa Leaflet, import/export JSON | Funcional |
| Pipeline de informes (HTML→PDF) y mapa | Funcional, semi-manual |
| Auditoría técnica completa (F1–F25, M1–M13) | Hecha — hoja de ruta de rigor ya priorizada |
| Documentación en español | Muy por encima del estándar |

**Deudas vigentes (de la auditoría, aún abiertas):** HCM 2010 en vez de 7ª ed.
(M3), un solo optimizador y es Webster que flaquea en congestión (M4), llegadas
Bernoulli no Poisson (M2b), cola ≈ 2×promedio no percentil HCM (M2c), una sola
semilla sin réplicas (M6), escenarios solo uniformes (M8), saturación casi sin
factores de ajuste (M9), sin peatones/ciclistas (M10), sin corredor (M5), sin
persistencia (M13).

**El dato estratégico que cambia todo:** el motor evalúa una intersección
completa en **milisegundos**. VISSIM/SUMO tardan minutos u horas por corrida y
semanas de modelado. Esa diferencia de 4–6 órdenes de magnitud es la base de
toda la diferenciación: permite **optimización global, Monte Carlo y "qué pasa
si" interactivo en tiempo real**, cosas que un microsimulador no puede ofrecer
de forma interactiva por diseño.

---

## 2. La tesis de diferenciación

No se compite con VISSIM/SUMO en su terreno (fidelidad microscópica,
car-following, 3D). Se compite en un eje que ellos estructuralmente no cubren:

> **VISSIM y SUMO responden "¿qué pasa si hago X?" después de semanas de
> modelado. Nosotros respondemos "¿qué debo hacer, y con qué confianza?"
> en una hora, a partir de un aforo o un video.**

| Eje | VISSIM | SUMO | Synchro/HCS/Sidra | **Nosotros (meta)** |
|-----|--------|------|--------------------|---------------------|
| Naturaleza | Descriptivo | Descriptivo | Normativo determinista | **Prescriptivo + probabilístico** |
| Pregunta que responde | ¿Qué pasa si…? | ¿Qué pasa si…? | ¿Cumple la norma? | **¿Qué hacer y con qué riesgo?** |
| Tiempo de estudio | Semanas | Semanas | Días | **< 1 hora** |
| Incertidumbre de entrada | No | No | No | **Nativa (Monte Carlo)** |
| Costo | ~USD 10–20k/licencia | Gratis (UX hostil) | Pago | **Gratis / web** |
| Idioma y contexto LatAm | No | No | No | **Sí (motos, español, sin aforos caros)** |
| Trazabilidad del cálculo | Caja negra | Código abierto críptico | Parcial | **Cada número con su fórmula y edición** |

### Los 5 pilares diferenciadores

1. **Prescriptivo, no solo descriptivo.** Dado un aforo, el sistema explora y
   rankea *alternativas de diseño*: semáforo (2/3/4 fases, izquierda protegida
   o permitida), PARE, glorieta de 1 o 2 carriles — todas con la misma demanda,
   en segundos. Ningún software del mercado responde "¿qué tipo de control
   merece esta intersección?" de forma integrada; el usuario de Synchro tiene
   que modelar cada alternativa a mano.

2. **Incertidumbre nativa.** Un aforo de 15 minutos no justifica un LOS de
   letra única. Las entradas llevan incertidumbre declarada (±%), se propagan
   por Monte Carlo (miles de evaluaciones en <2 s gracias al motor analítico)
   y la salida es **"P(LOS ≥ E) = 78 %"** con bandas de confianza y tornado de
   sensibilidad. Ninguna herramienta comercial propaga incertidumbre de
   entrada. Es defendible académicamente y barato de computar — solo para
   nosotros.

3. **Del dato crudo al informe sin fricción.** Importar geometría desde
   OpenStreetMap con un clic en el mapa; obtener volúmenes de giro desde un
   video de celular o dron (visión por computador); generar el informe técnico
   en español con un botón. El costo real de un estudio en LatAm es el aforo
   manual y el reporte — atacamos eso, no la microsimulación.

4. **Transparencia auditable.** Modo auditoría: cada demora muestra su d1, d2,
   factores aplicados y la edición del HCM citada. Convierte la honestidad
   (que la auditoría ya impuso) en *feature* visible para revisores, academia
   y entes públicos.

5. **Rigor vigente como boleto de entrada.** HCM 7.ª ed. (2022) + 7.1 (2025),
   segundo optimizador por minimización directa de demora, réplicas con
   intervalos. Sin esto los pilares 1–4 no tienen credibilidad; es condición
   necesaria, no diferenciador.

### Qué NO vamos a hacer (igual de importante)

- **No** escribir un microsimulador car-following propio ni 3D — es regalar
  años a un terreno donde VISSIM ya ganó. Para alta fidelidad: puente a SUMO
  (Fase 4), que convierte esa debilidad en validación gratuita.
- **No** asignación dinámica de tráfico en red grande (terreno Aimsun).
- **No** SaaS multiusuario/autenticación todavía — primero el producto técnico.

---

## 3. Plan ejecutable

Dependencias: F0 → F1 → F2; F3 y F5 paralelizables desde F2; F4 al final.
Esfuerzos en semanas-persona aproximadas.

### Fase 0 — Higiene (1 día)

| # | Tarea | Archivos | Criterio de aceptación |
|---|-------|----------|------------------------|
| 0.1 | Commitear el trabajo de sinceramiento de etiquetas que está sin commitear en el working tree | (todo lo modificado) | `git status` limpio |
| 0.2 | Corregir README §"¿Y si no tengo datos?" que aún dice "Poisson"; alinear mención de NumPy con `requirements.txt` | `README.md`, `backend/requirements.txt` | README consistente con el código |
| 0.3 | Añadir `numpy` a requirements (lo usarán F1.1 y F2.3) | `requirements.txt` | `pip install` ok |

### Fase 1 — Motor defendible (1–2 semanas) · cierra la Fase 1 de la auditoría

| # | Tarea (ref. auditoría) | Archivos | Criterio de aceptación |
|---|------------------------|----------|------------------------|
| 1.1 | Llegadas Poisson reales (M2b): `numpy.random.poisson(λ·dt)` por paso | `simulator.py` | Test: varianza/media de llegadas ≈ 1 (índice de dispersión) |
| 1.2 | Cola percentil-95 del HCM (M2c): término uniforme + incremental con factor de percentil; renombrar el campo y la UI | `analysis.py`, `models.py`, `TimingResults.tsx` | Test contra valor calculado a mano del HCM |
| 1.3 | HCM 7.ª ed. (M3): glorieta A=1380 y ecuación **por carril** (no multiplicar); revisar coeficientes TWSC | `unsignalized.py` | Tests actualizados; nota de edición en docstring y UI |
| 1.4 | Cadena de factores de saturación HCM (M9): ancho de carril, pendiente, pesados, estacionamiento, buses, tipo de área, utilización, giros, peatones — campos opcionales con default 1.0 | `models.py`, `analysis.py`, `IntersectionForm.tsx` | Caso del manual reproducido; defaults no cambian resultados actuales |
| 1.5 | Segundo optimizador (M4): minimización directa de la demora HCM agregada — búsqueda sobre ciclo × reparto de verdes (grid + refinamiento local; el motor lo permite por fuerza bruta) | nuevo `optimizer_delay.py`, `main.py` (`/api/optimize?method=`) | En el caso de ejemplo congestionado produce ciclo ≤ Webster y demora ≤ Webster; UI compara ambos |
| 1.6 | Réplicas estocásticas (M6): N semillas, percentiles 5/50/95, banda en la gráfica de colas | `simulator.py`, `models.py`, `QueueChart.tsx` | Banda visible; punto único eliminado |
| 1.7 | Escenarios direccionales (M8): multiplicador por acceso y por movimiento | `scenarios.py`, `models.py`, `ScenarioComparison.tsx` | Escenario "desarrollo nuevo en acceso E" modelable |
| 1.8 | **Validación cruzada**: reproducir 2–3 ejemplos resueltos publicados del HCM/HCS y documentar desviación | nuevo `tests/test_validation_hcm.py`, `docs/validacion.md` | Desviación < 5 % en demora documentada |

### Fase 2 — Diferenciación core: prescripción + incertidumbre (2–3 semanas)

| # | Tarea | Archivos | Criterio de aceptación |
|---|-------|----------|------------------------|
| 2.1 | **Explorador de alternativas**: `/api/compare-controls` corre con la misma demanda semáforo (esquemas de fase alternativos), TWSC y glorieta 1×/2×; tabla ranking por demora/LOS/cola con advertencias de aplicabilidad (volúmenes mínimos tipo warrant) | nuevo `alternatives.py`, `main.py`, nueva pestaña UI | Para el caso de ejemplo: ranking completo en < 2 s |
| 2.2 | Generador de esquemas de fases: enumerar esquemas válidos (NEMA-like: 2 fases, izquierdas protegidas, lead/lag) a partir de los lane groups y optimizar cada uno | `alternatives.py` | ≥ 4 esquemas evaluados automáticamente para una 4×4 |
| 2.3 | **Incertidumbre Monte Carlo**: ±CV% por volumen (defaults según duración del aforo), 1 000+ muestras vectorizadas, salida: distribución de demora, P(cada LOS), tornado de sensibilidad | nuevo `uncertainty.py`, `models.py`, UI | 1 000 muestras < 2 s; UI muestra P(LOS) y banda |
| 2.4 | **Modo auditoría**: traza de cálculo por movimiento (d1, d2, cada factor, fórmula y edición citada) en la respuesta y como tabla colapsable + anexo del informe | `analysis.py`, `TimingResults.tsx` | Un revisor puede verificar cualquier número contra el manual sin leer código |
| 2.5 | Persistencia mínima (M13): proyectos y corridas en SQLite; comparar corridas | nuevo `storage.py`, `data/runs/` | Guardar/cargar/comparar funciona |

### Fase 3 — Datos sin fricción (3–4 semanas, paralelizable con F2)

| # | Tarea | Archivos | Criterio de aceptación |
|---|-------|----------|------------------------|
| 3.1 | Import OSM: desde el pin del mapa, Overpass API → accesos, nº de carriles aproximado, nombres de calles; pre-llenar el formulario | `LocationMap.tsx`, nuevo endpoint | Intersección real de la ciudad pre-cargada con 1 clic |
| 3.2 | **Aforo por video** (paquete opcional `tools/aforo-video/`, no infla el core): YOLO + ByteTrack (ultralytics + supervision), el usuario dibuja zonas de movimiento sobre un frame, salida = matriz de giros (TMC) en el JSON importable, con clasificación auto/moto/bus/camión → `pcu_factor` automático | nuevo paquete | Video fijo de 15 min → TMC importable; error < 10 % vs conteo manual en un video de prueba |
| 3.3 | Plantilla de aforo manual: hoja imprimible + entrada rápida de conteos de 15 min con expansión a hora pico y PHF calculado | UI | Flujo completo sin Excel |

### Fase 4 — Corredor y alta fidelidad (3–4 semanas)

| # | Tarea | Archivos | Criterio de aceptación |
|---|-------|----------|------------------------|
| 4.1 | Corredor (M5): múltiples intersecciones, offsets, PF real por llegadas en pelotón, **diagrama tiempo-espacio interactivo** (onda verde), optimización de offsets (maximización de banda tipo MAXBAND simplificado) | nuevo `corridor.py`, nueva vista | Corredor de 3–5 intersecciones con banda verde visible y optimizable |
| 4.2 | Puente SUMO opcional: exportar config → `.net.xml` + `.rou.xml`; si SUMO está instalado, correr N réplicas headless y mostrar "analítico vs microsimulado" lado a lado | nuevo `sumo_bridge.py` | Comparación automática en el caso de ejemplo; degradación elegante sin SUMO |

### Fase 5 — Informes inteligentes y copiloto (2 semanas, transversal)

| # | Tarea | Archivos | Criterio de aceptación |
|---|-------|----------|------------------------|
| 5.1 | Informe profesional de 1 clic: productizar el pipeline HTML→PDF existente (plantilla, figuras, anexo de auditoría, P(LOS)) | `reports.py` + plantilla | Botón "Generar informe" → PDF completo en español |
| 5.2 | Copiloto LLM opcional (API de Claude, feature-flag): explicar resultados, redactar conclusiones, editar config por lenguaje natural ("agrega fase peatonal exclusiva") | nuevo `copilot.py` | Funciona con API key; el core no la requiere |
| 5.3 | Peatones y ciclistas (M10): fase peatonal, verde mínimo peatonal por ancho de cruce, demora peatonal HCM 7 | `models.py`, `analysis.py` | LOS peatonal reportado junto al vehicular |

---

## 4. Métricas de éxito (North Star)

1. **Tiempo de estudio**: de video/aforo a informe PDF < 1 hora (vs semanas).
2. **Rigor**: desviación < 5 % vs casos resueltos del HCM, documentada.
3. **Interactividad**: ranking de alternativas < 2 s; 1 000 muestras MC < 2 s.
4. **Único en mercado**: P(LOS) probabilístico + explorador de alternativas —
   ninguna herramienta comercial los ofrece integrados.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Precisión del CV de video en condiciones reales (lluvia, noche, oclusión) | UI de revisión/corrección manual de conteos; declarar error estimado |
| La cadena completa de factores HCM 7 es extensa | Priorizar los 4 de mayor impacto (pesados, ancho, pendiente, utilización); el resto incremental |
| SUMO en Windows como dependencia | Siempre opcional con degradación elegante |
| Scope creep hacia microsimulación propia | Prohibido por este plan (§2, "Qué NO") |

## 6. Stack (cambios mínimos)

- Backend: + `numpy` (F1/F2), `scipy` opcional (optimización), `sqlite3`
  (stdlib). CV solo en el paquete opcional: `ultralytics`, `supervision`,
  `opencv-python`.
- Frontend: se mantiene React 19 + Vite; gráficas siguen en SVG propio
  mientras alcance.
