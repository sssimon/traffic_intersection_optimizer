# Aforo por video (tarea 3.2)

Convierte un **video fijo** de una intersección (celular en trípode, dron
estático o CCTV) en una **matriz de giros (OD) por clase vehicular**, con
expansión a veh/h y PCU por movimiento — importable a la app.

Es un **paquete opcional**: sus dependencias (PyTorch/YOLO) no tocan el
backend. Detección con YOLOv8 (clases COCO: car→auto, motorcycle→moto,
bus→bus, truck→camión) y seguimiento ByteTrack; el conteo OD es lógica
pura (`counting.py`) con pruebas propias.

## Instalación

```bash
pip install -r requirements.txt   # ultralytics + supervision + opencv
```

## Uso

1. **Zonas**: define un polígono por boca de acceso en un JSON (usa un
   cuadro del video para leer coordenadas en píxeles):

```json
{ "zonas": [
  { "nombre": "W", "poligono": [[0, 340], [300, 380], [300, 640], [0, 670]] },
  { "nombre": "E", "poligono": [[980, 50], [1280, 30], [1280, 300], [1000, 290]] }
]}
```

2. **Contar**:

```bash
python aforo.py video.mp4 zonas.json --out tmc.json \
    --anotado verificacion.mp4 \
    --config interseccion.json --map "W>E=W-T,E>W=E-T,N>S=N-T,S>N=S-T"
```

- `--anotado`: video con cajas, IDs y zonas para la **verificación manual**
  (el criterio de aceptación es error < 10 % contra un conteo humano).
- `--config` + `--map`: vuelca los veh/h y PCU en una copia del
  IntersectionConfig (`*-aforado.json`) lista para **Importar JSON**.
- `--stride N`: procesa 1 de cada N cuadros (3 ≈ 20 fps efectivos, buen
  equilibrio CPU/continuidad del tracking). `--conf`, `--imgsz`,
  `--modelo` ajustan la detección (nocturnas: conf 0.15, imgsz 1280).

## Cómo decide el origen-destino

Cada track aporta su trayectoria de centros; el **origen** es la primera
zona tocada y el **destino** la última. Se descartan (y se reportan) los
tracks cortos (< 8 puntos), casi inmóviles (< 40 px — estacionados) o que
no tocan dos zonas distintas (trayectorias truncadas por los bordes del
clip o por oclusión).

## Límites declarados

- Un clip corto es una **muestra**, no un aforo: la expansión ×(3600/dur)
  se reporta con advertencia. El criterio formal pide ≥ 15 min de video.
- Noche, lluvia u oclusiones degradan la detección: revisa siempre el
  video anotado y ajusta `--conf`.
- Los giros se infieren por zonas OD, no por carril; los movimientos sin
  mapeo a grupo se listan como aviso.

## Cómo decide el origen-destino, en detalle

El tracking pierde el ID a mitad del cruce (sobre todo de noche), así que un
viaje completo llega partido en fragmentos. `stitch_tracks` los cose:
fragmento B continúa a A si empieza dentro de `max_gap_s` y su primer punto
cae cerca de la posición de A **extrapolada por su velocidad final** (el
vehículo sigue avanzando durante el hueco). Solo después de coser se asignan
las zonas OD. Sin esta costura, casi ningún viaje toca dos zonas.

## Protocolo de validación (< 10 %)

1. Corre con `--anotado`.
2. Cuenta a mano (en el reproductor, a 0.5×) los vehículos por movimiento.
3. Compara contra `tmc.json`: |auto − manual| / manual < 0.10 por
   movimiento principal. Documenta el resultado.

## Smoke test incluido (clip nocturno de 31 s)

`ejemplo-zonas-180386.json` son las zonas para un clip aéreo nocturno de
**31 s** (un caso difícil: oscuro, vehículos pequeños, IDs efímeros). Con
`--stride 2 --conf 0.10`, el pipeline detecta 175 tracks, los cose a ~115 y
cuenta el flujo **direccionalmente correcto** (W→E y E→S dominantes, que es
lo que se ve). No es una validación formal: un clip tan corto y oscuro está
cerca del peor caso y la propia salida lo advierte. La validación < 10 %
exige el video de campo del usuario (≥ 15 min, de día, cámara fija).
