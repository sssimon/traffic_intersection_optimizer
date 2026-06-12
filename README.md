# Traffic Intersection Optimizer

Sistema configurable para optimizar tiempos de semáforo, analizar flujo, simular
escenarios y gestionar congestión en cualquier tipo de intersección
semaforizada — incluso sin datos históricos.

- **Backend**: Python 3.11+ con FastAPI, Pydantic, NumPy.
- **Frontend**: React 18 + TypeScript + CSS puro (Vite).

## ¿Qué hace?

1. **Configuración genérica**: cualquier número de accesos, carriles, fases;
   ubicación geográfica en un mapa de la ciudad (Leaflet + OpenStreetMap).
2. **Optimización de tiempos (dos métodos)**: Webster (1958) y minimización
   directa de la demora HCM — la app calcula ambos planes y resalta el de
   menor demora. Cicl​o y verdes óptimos a partir de la demanda.
3. **Análisis HCM 2010**: demora, capacidad, cola al percentil 95 (back of
   queue, HCM 2000 ap. G), LOS A–F.
4. **Simulación de colas**: llegadas Poisson + descarga a saturación, con N
   réplicas y banda de percentiles 5–95 de la cola en el tiempo.
5. **Escenarios**: compara crecimiento global o direccional (factores por
   acceso/movimiento) — recomienda estrategia.
6. **Análisis sin semáforo**: PARE en calle secundaria (HCM cap. 19) por
   aceptación de brechas; compara semáforo vs PARE.

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

### Documentación (`docs/`)

- `INSTRUCTIVO-CARGA-DE-DATOS.md` — guía paso a paso de carga de datos.
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

Para datos reales en el futuro: cualquier conteo manual o aforo (incluso 15 min
de hora pico) puede usarse como volumen horario equivalente.

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
- **Simulación de colas de tiempo discreto** — paso fijo (1 s por defecto),
  llegadas Poisson (muestreo exacto por paso), salidas a flujo de saturación
  durante el verde; N réplicas con semillas consecutivas y percentiles
  5/50/95 (sin periodo de calentamiento: parte con colas vacías).
  Ver `backend/app/simulator.py`.
- **Aceptación de brechas** — HCM 2010 cap. 19 (PARE en la calle secundaria)
  para intersecciones no semaforizadas. Ver `backend/app/unsignalized.py`.

## API

| Método | Ruta                     | Descripción                                  |
|--------|--------------------------|----------------------------------------------|
| GET    | `/api/health`            | Health check                                 |
| GET    | `/api/sample`            | Configuración de ejemplo                     |
| POST   | `/api/optimize`          | Plan de tiempos (`?method=webster\|delay_min`) |
| POST   | `/api/analyze`           | Optimiza (`?method=`) + análisis HCM         |
| POST   | `/api/simulate`          | Simulación de colas (N réplicas, banda 5–95) |
| POST   | `/api/scenarios`         | Escenarios (global/direccional) + estrategia |
| POST   | `/api/analyze-twsc`      | Análisis no semaforizado con PARE (HCM 19)   |

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

- No modela peatones ni ciclos vehículo-bicicleta.
- No modela coordinación entre intersecciones (cada una se trata como aislada).
- No incluye control adaptativo en tiempo real — el plan es pretimed con
  posibilidad de re-optimizar al cambiar la demanda.
- Saturación de flujo base HCM (1900 veh/h/carril); para ajustes finos editar
  el campo `saturation_flow_per_lane` por grupo.

## Próximos pasos sugeridos

- Integración con SUMO para microsimulación de mayor fidelidad.
- Control actuado (vehicle-actuated) con sensores virtuales.
- Coordinación de corredor (onda verde) entre múltiples intersecciones.
- Aprendizaje por refuerzo (DQN) para control adaptativo.
