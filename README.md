# Traffic Intersection Optimizer

Sistema configurable para optimizar tiempos de semáforo, analizar flujo, simular
escenarios y gestionar congestión en cualquier tipo de intersección
semaforizada — incluso sin datos históricos.

- **Backend**: Python 3.11+ con FastAPI, Pydantic, NumPy.
- **Frontend**: React 18 + TypeScript + CSS puro (Vite).

## ¿Qué hace?

1. **Configuración genérica**: cualquier número de accesos, carriles, fases;
   ubicación en un mapa (Leaflet + OpenStreetMap) con **importación de la
   geometría del cruce desde OSM** — accesos, carriles, nombres de calles y
   sentidos con un clic en el pin.
2. **Optimización de tiempos (dos métodos)**: Webster (1958) y minimización
   directa de la demora HCM — la app calcula ambos planes y resalta el de
   menor demora. Cicl​o y verdes óptimos a partir de la demanda.
3. **Análisis HCM 2010**: demora, capacidad, cola al percentil 95 (back of
   queue, HCM 2000 ap. G), LOS A–F.
4. **Simulación de colas**: llegadas Poisson + descarga a saturación, con N
   réplicas y banda de percentiles 5–95 de la cola en el tiempo.
5. **Escenarios**: compara crecimiento global o direccional (factores por
   acceso/movimiento) — recomienda estrategia.
6. **Explorador de alternativas de control**: con la misma demanda optimiza
   y rankea semáforo (fases configuradas y fases por acceso auto-generadas)
   vs PARE en secundaria (HCM cap. 19) — responde *qué control conviene*,
   con recomendación y criterios de aplicabilidad.
7. **Incertidumbre del aforo (Monte Carlo)**: 1 000 muestras sobre los
   volúmenes según la calidad del conteo — P(cada LOS), banda de demora
   p5–p95 y tornado de sensibilidad. Un conteo corto no justifica una
   letra única.
8. **Modo auditoría**: traza de cálculo por movimiento — cada número con su
   fórmula, sustitución numérica y edición del manual citada
   (`/api/analyze?audit=true`). Un revisor verifica con calculadora, sin
   leer código.
9. **Corridas guardadas**: historial en SQLite (`data/runs/`) con la
   configuración completa y el resumen del análisis — comparable entre
   fechas y recargable con un clic.
10. **Aforo de campo (15 min)**: hoja imprimible + captura por intervalo y
    clase (auto/moto/bus/camión); la app detecta la hora pico (ventana
    móvil), calcula el PHF y el PCU por movimiento (motos < 1.0) y los
    aplica a la demanda — sin Excel.
11. **Corredor (onda verde)**: ciclo común, offsets optimizados (MAXBAND
    simplificado), banda verde bidireccional ponderada por volumen,
    diagrama tiempo-espacio y **PF de progresión real** aplicado al modelo
    de demora — coordinada vs aislada, cuantificado.
12. **Aforo por video** (paquete opcional `tools/aforo-video/`, no infla el
    backend): YOLO + ByteTrack sobre video fijo → matriz de giros (OD) por
    clase con PCU, video anotado para verificación manual y volcado directo
    a la configuración (`--config --map`).
13. **Validación con SUMO** (opcional): exporta la intersección a un modelo
    SUMO completo (red, rutas, semáforo) y, si SUMO está instalado, corre
    réplicas headless para comparar la demora analítica (HCM) con la
    microsimulada lado a lado. Degradación elegante si SUMO no está (solo
    exporta los archivos). En el caso de ejemplo no saturado ambos métodos
    coinciden en < 1 %.
14. **Informe profesional de 1 clic**: el botón «Generar informe» produce un
    informe técnico completo en español (HTML autocontenido, listo para
    imprimir a PDF) con portada, resumen ejecutivo, análisis HCM, **P(LOS)
    probabilístico** y **anexo de auditoría** (cada número con su fórmula y
    edición citada) — los dos pilares que ningún software comercial integra.
15. **Copiloto (IA)** (opcional, pestaña 08): explica los resultados en
    lenguaje natural (anclado en los números reales del motor) y **edita la
    configuración por instrucción** («sube 20 % la demanda del Este», «agrega
    una fase peatonal exclusiva»); la propuesta se valida con el esquema y el
    usuario decide si aplicarla. Requiere `ANTHROPIC_API_KEY` en el entorno del
    backend; sin ella el copiloto se desactiva y el resto funciona igual.
16. **Peatones (M10)**: cruces peatonales por fase con **demora y LOS peatonal**
    (HCM, `dp = 0.5·C·(1 − gp/C)²`) reportados junto al vehicular, y
    verificación del **verde mínimo seguro** (MUTCD: Walk + despeje L/Sp). Avisa
    cuando una fase es demasiado corta para cruzar con seguridad.

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
python run.py
```

El backend escanea puertos en `[8765, 8800]` y elige el primero libre. Lo escribe
en `.dev-port` (raíz del repo) y el proxy de Vite lo lee al arrancar. Para forzar
un puerto: `BACKEND_PORT=8770 python run.py`. Docs interactivas en `/docs`.

**Copiloto (opcional):** para activar la pestaña 08, exporta tu clave antes de
arrancar el backend: `ANTHROPIC_API_KEY=sk-... python run.py` (modelo por
defecto `claude-sonnet-4-6`, configurable con `COPILOT_MODEL`). No instala
dependencias nuevas: la API se llama por `urllib` de la librería estándar.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App en `http://localhost:5173`. El proxy de Vite reenvía `/api` al backend.

## Flujo de uso

1. Pulsa **Cargar ejemplo** para poblar una intersección 4×4 congestionada.
2. Ajusta accesos, fases y demanda en la pestaña **Configuración**.
3. Pulsa **Optimizar y analizar** — verás ciclo, verdes, demora y LOS.
4. Ve a **Simulación** para ver la evolución de colas con datos sintéticos.
5. Ve a **Escenarios** para comparar futuros y obtener una recomendación.
6. Pulsa **Generar informe** para abrir el informe técnico completo (HCM +
   P(LOS) + auditoría) y guardarlo como PDF desde el navegador.

### Documentación (`docs/`)

- `INSTRUCTIVO-CARGA-DE-DATOS.md` — guía paso a paso de carga de datos.
- `validacion.md` — validación cruzada del motor contra valores publicados
  del HCM (Ejemplo 1 TWSC: fórmulas < 1 %, motor completo < 5 %) y contra
  microsimulación SUMO (semaforizado no saturado < 1 %).
- `informe-caso-ejemplo.html` — fuente del informe técnico del caso.
- `ejemplo-aforo-cruce-av-principal.json` — caso de ejemplo importable.
- `figura-1-flujos.svg` / `figura-2-resultados.svg` / `figura-3-simulacion.svg` —
  diagramas de la intersección y de la simulación.
- `figura-4-ubicacion.png` — mapa de ubicación de la intersección.
- `*.pdf` — versiones imprimibles del instructivo y del informe del caso.

**Regenerar los PDF** — `docs/build-pdf.py` (o doble clic en `docs/build-pdf.bat`).
Requiere el paquete `markdown` (`pip install --user markdown`) y Edge o Chrome.

**Regenerar el mapa de ubicación** — `docs/build-map.py` (o `docs/build-map.bat`).
Toma las coordenadas del JSON del caso, o explícitas:
`python build-map.py 7.780639 -72.221870 [zoom]`. Requiere `websocket-client`
(`pip install --user websocket-client`), Edge o Chrome, e internet para los tiles.

## ¿Y si no tengo datos?

El sistema funciona con **estimaciones**:
- Carga el ejemplo y ajusta los volúmenes "a ojo" según observación.
- La simulación genera tráfico Poisson consistente con la demanda configurada.
- Compara varios escenarios para entender la sensibilidad al volumen.

Para datos reales: la tarjeta **Aforo de campo (15 min)** de la pestaña 01
procesa conteos manuales (incluso de un solo intervalo, con expansión y
advertencia) y aplica volúmenes, PHF y PCU sin pasar por Excel.

## Teoría aplicada

- **Webster (1958)** — fórmula clásica del ciclo óptimo. Ver `backend/app/optimizer.py`.
- **Minimización directa de demora** — búsqueda de ciclo y reparto de verdes
  que minimiza la demora media del modelo HCM (descenso coordinado); en
  congestión produce ciclos más cortos que Webster. Ver
  `backend/app/optimizer_delay.py`.
- **HCM 2010** capítulo 18 — modelo de demora `d = d1·PF + d2` con sus componentes
  uniforme e incremental. Ver `backend/app/analysis.py`.
- **Back of queue (HCM 2000 cap. 16, ap. G)** — cola media `Q1 + Q2` por carril
  y percentil 95 con factor `fB95 = 1.6 + e^(-Q/5)` (pretimed). Ver
  `backend/app/analysis.py`.
- **Factores de saturación (HCM 2010 cap. 18)** — cadena opcional por grupo:
  `fw · fg · fp · fbb · fa · fLU` + giro protegido (0.95 izq / 0.85 der en
  carril exclusivo). Pesados vía `pcu_factor` en la demanda (≡ fHV). Ver
  `SaturationFactors` en `backend/app/models.py`.
- **Monte Carlo de incertidumbre** — volúmenes ~ Normal(media, CV·media)
  truncada en 0, independientes por movimiento; el plan se diseña con el
  aforo medio y se evalúa fijo bajo demanda incierta. Ver
  `backend/app/uncertainty.py`.
- **Coordinación de corredor** — banda verde por intersección cíclica de
  verdes desplazados (offsets por descenso coordinado, paso 1 s) y
  `PF = (1−P)·fPA/(1−g/C)` (HCM 2000 cap. 16) con pelotón uniforme sin
  dispersión (declarado). Ver `backend/app/corridor.py`.
- **Simulación de colas de tiempo discreto** — paso fijo (1 s por defecto),
  llegadas Poisson (muestreo exacto por paso), salidas a flujo de saturación
  durante el verde; N réplicas con semillas consecutivas y percentiles
  5/50/95 (sin periodo de calentamiento: parte con colas vacías).
  Ver `backend/app/simulator.py`.
- **Aceptación de brechas** — HCM 2010 cap. 19 (PARE en la calle secundaria;
  cap. 20 desde la 6.ª ed., valores base idénticos entre ediciones), con
  impedancia por rangos y ajuste p′ del giro izquierda menor (ec. 17-8/19-48).
  Ver `backend/app/unsignalized.py`.

## API

| Método | Ruta                     | Descripción                                  |
|--------|--------------------------|----------------------------------------------|
| GET    | `/api/health`            | Health check                                 |
| GET    | `/api/sample`            | Configuración de ejemplo                     |
| POST   | `/api/optimize`          | Plan de tiempos (`?method=webster\|delay_min`) |
| POST   | `/api/analyze`           | Optimiza (`?method=`) + análisis HCM + LOS peatonal (`?audit=true`: traza) |
| POST   | `/api/simulate`          | Simulación de colas (N réplicas, banda 5–95) |
| POST   | `/api/scenarios`         | Escenarios (global/direccional) + estrategia |
| POST   | `/api/analyze-twsc`      | Análisis no semaforizado con PARE (HCM 19)   |
| POST   | `/api/compare-controls`  | Ranking de alternativas de control           |
| POST   | `/api/uncertainty`       | Monte Carlo: P(LOS), banda y tornado         |
| POST   | `/api/corridor`          | Corredor: offsets, banda verde y PF          |
| POST   | `/api/field-count`       | Aforo 15 min: hora pico, PHF y PCU           |
| POST   | `/api/osm-import`        | Geometría del cruce desde OSM (Overpass)     |
| POST   | `/api/sumo-export`       | Exporta a SUMO + compara analítico vs microsim |
| POST   | `/api/report`            | Informe HTML de 1 clic (HCM + P(LOS) + auditoría) |
| GET    | `/api/copilot/status`    | Disponibilidad del copiloto LLM (opcional)   |
| POST   | `/api/copilot/explain`   | Explica el análisis en lenguaje natural      |
| POST   | `/api/copilot/edit`      | Edita la configuración por instrucción       |
| POST/GET | `/api/runs`            | Guardar / listar corridas (SQLite)           |
| GET/DELETE | `/api/runs/{id}`     | Cargar / eliminar una corrida                |

## Estructura

```
Traffic-Intersection-Optimizer/
├── backend/
│   ├── app/
│   │   ├── models.py       # Pydantic
│   │   ├── optimizer.py    # Webster
│   │   ├── optimizer_delay.py # Mínima demora HCM
│   │   ├── analysis.py     # HCM 2010
│   │   ├── simulator.py    # Microsim
│   │   ├── scenarios.py    # Comparación
│   │   ├── unsignalized.py # TWSC — PARE en secundaria (HCM 19)
│   │   ├── alternatives.py # Explorador de alternativas de control
│   │   ├── uncertainty.py  # Monte Carlo de incertidumbre
│   │   ├── audit.py        # Traza de cálculo verificable
│   │   ├── storage.py      # Corridas guardadas (SQLite)
│   │   ├── osm.py          # Importación de geometría (Overpass)
│   │   ├── corridor.py     # Onda verde: offsets, banda y PF
│   │   ├── field_count.py  # Aforo de campo de 15 min
│   │   ├── data.py         # Sample
│   │   └── main.py         # FastAPI
│   ├── requirements.txt
│   └── run.py
└── frontend/
    ├── src/
    │   ├── App.tsx
    │   ├── api.ts
    │   ├── types.ts
    │   ├── styles.css
    │   └── components/
    │       ├── IntersectionForm.tsx
    │       ├── DemandTable.tsx
    │       ├── TimingResults.tsx
    │       ├── SimulationPanel.tsx
    │       ├── ScenarioComparison.tsx
    │       └── QueueChart.tsx
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── index.html
```

## Limitaciones conocidas

- Peatones: se modela la **demora y el LOS peatonal por cruce** (basado en
  demora) y el verde mínimo seguro MUTCD. No se modela el LOS peatonal
  perceptual multifactor del HCM 2010 ni los ciclistas.
- El análisis de una intersección (pestañas 01–05) la trata como aislada;
  la coordinación vive en la pestaña 06 · Corredor con supuestos
  declarados (pelotón uniforme sin dispersión, fase arterial única).
- No incluye control adaptativo en tiempo real — el plan es pretimed con
  posibilidad de re-optimizar al cambiar la demanda.
- Flujo de saturación: base 1900 veh/h/carril + cadena opcional de factores
  HCM por grupo (botón ƒ). El bloqueo de giros por peatones/ciclistas
  (fLpb/fRpb) aún no se modela.

## Próximos pasos sugeridos

- Control actuado (vehicle-actuated) con sensores virtuales.
- Dispersión de pelotón (Robertson) en el corredor.
- Aprendizaje por refuerzo (DQN) para control adaptativo.
