# Validación cruzada del motor de cálculo

**Tarea 1.8 del plan estratégico — cierre de la Fase 1 (motor defendible).**

Fecha: 2026-06-12 · Suite de respaldo: `backend/tests/test_validation_hcm.py`
(ejecutable con `pytest`; estos números se verifican en cada corrida).

## 1. Qué se validó y contra qué

| Bloque | Módulo | Fuente publicada | Resultado |
|---|---|---|---|
| V1 | TWSC — fórmulas (capacidad potencial, impedancia, demora) | HCM 2000 cap. 17, Example Problem 1 (worksheets publicados) | **< 1 %** en los 4 valores publicados |
| V2 | TWSC — motor completo sobre el Ejemplo 1 | Ídem | **< 5 %** en capacidad y demora por movimiento |
| V3 | Cola (back of queue Q1+Q2, fB95) | Nota técnica de Akçelik sobre el modelo HCM 2000 (ap. G), ejemplo resuelto | Ecuaciones reproducidas en la transcripción (Q1 = 12.95 ✓, Q2 = 6.94 ✓) |
| V4 | Demora semaforizada (d1·PF + d2) | Derivación a mano de las ecuaciones HCM (tests de regresión) | Exacta a la fórmula; **pendiente** contraste con caso publicado del cap. 16/HCS |

## 2. V1 — Fórmulas TWSC contra valores publicados (Ejemplo 1, HCM 2000)

Intersección en T con PARE en la calle menor, izquierda exclusiva WB, 10 %
de pesados, terreno plano, sin peatones. Con las **entradas del manual**
(sus tc/tf ya ajustados por pesados), nuestras ecuaciones reproducen:

| Magnitud | Publicado | Nuestro motor | Desv. |
|---|--:|--:|--:|
| cp giro derecha menor (vc=270, tc=6.30, tf=3.39) | 750 | 749.8 | −0.03 % |
| cp izquierda mayor (vc=290, tc=4.20, tf=2.29) | 1227 | 1227.4 | +0.03 % |
| cp izquierda menor en T (vc=870, tc=6.50, tf=3.59) | 312 | 311.8 | −0.06 % |
| Demora de control (v=160, c=523) | 14.9 s (LOS B) | 14.88 s (LOS B) | −0.1 % |

## 3. V2 — Motor completo sobre el Ejemplo 1

Volúmenes del ejemplo (v2=250, v3=40, v4=150, v5=300, v7=40, v9=120),
PHF = 1, PCU = 1. Diferencias estructurales declaradas del motor: los
pesados van por PCU en la demanda (no en tc/tf) y los movimientos menores
se modelan en carriles separados (el ejemplo comparte el carril NB).

**Flujos conflictivos** — dos exactos, uno aproximado:

| Movimiento | Publicado | Nuestro | Nota |
|---|--:|--:|---|
| Izquierda mayor (W-L) | 290 | 290 | idéntico |
| Izquierda menor (N-L) | 870 | 870 | idéntico (izquierdas mayores ×2, Exhibit 17-4) |
| Derecha menor (N-R) | 270 | 285 | aproximación de ambos sentidos (declarada) |

**Capacidades y demoras por movimiento** (publicado-equivalente por carril
separado con las capacidades del manual):

| Movimiento | Capacidad pub. | Nuestra | Desv. | Demora pub. | Nuestra | Desv. |
|---|--:|--:|--:|--:|--:|--:|
| W-L | 1227 | 1283 | +4.6 % | 8.3 s | 8.2 s | −1.9 % |
| N-R | 750 | 759 | +1.2 % | 10.7 s | 10.6 s | −0.8 % |
| N-L | 274 | 287 | +4.6 % | 20.4 s | 19.6 s | −3.8 % |

**Causa dominante de la desviación (+4.6 %):** el ejemplo ajusta tc/tf por
10 % de pesados (tc +0.10 s, tf +0.09 s); nuestro motor modela los pesados
vía PCU en la demanda. Son mecanismos distintos y no acumulables; la
desviación queda dentro del criterio (< 5 %).

**Diferencia estructural no comparable:** el manual publica la demora del
carril compartido NB (cSH = 523 → 14.9 s); nuestro modelo reporta cada
movimiento en carril separado (19.6 s y 10.6 s). No es una desviación de
fórmula sino de alcance: el carril menor compartido no está modelado.

## 4. Mejoras incorporadas durante la validación

La validación contra el ejemplo publicado reveló y corrigió dos brechas
(verificadas con los propios números del manual):

1. **Ajuste t3,LT en intersecciones de 3 ramas**: la brecha crítica de la
   izquierda menor se reduce 0.7 s en una T (ec. 17-1). Antes no se
   aplicaba.
2. **Izquierdas mayores cuentan doble** en el flujo conflictivo de la
   izquierda menor (Exhibit 17-4): el 870 del ejemplo se descompone como
   2·150 + 250 + 20 + 300. Antes se contaban una vez (vc = 720, capacidad
   sobreestimada ≈ +28 %).

## 5. V3 — Cola (back of queue)

Las ecuaciones Q1/Q2/kB/fB95 se decodificaron de la nota técnica de
Akçelik (que documenta el HCM 2000 ap. G) y se verificaron contra su
ejemplo resuelto **antes** de transcribirlas (commit `2c3e24e`):
Q1 = 12.95 veh ✓ y Q2 = 6.94 veh ✓ con las ecuaciones completas (con cola
inicial). El motor implementa el caso sin cola inicial (QbL = 0), cuyo
término Q1 coincide con el publicado para los mismos insumos.

## 6. Brechas conocidas y siguiente paso de validación

- **Semaforizado end-to-end (V4):** falta reproducir un Example Problem
  del cap. 16/18 o contrastar contra HCS con licencia. Los componentes
  (d1, d2, factores de saturación, Webster) están verificados por
  derivación a mano en la suite, pero no contra un caso publicado completo
  (los ejemplos del manual usan giros permitidos y PF por coordinación,
  fuera del alcance actual del motor).
- **Derecha menor:** la aproximación de ambos sentidos introduce ±5 % en
  vc según la asimetría direccional (±1 % en capacidad en el Ejemplo 1).
- **Carril menor compartido (cSH)** y **ajustes tc/tf por pesados y
  pendiente**: no modelados; candidatos a la Fase 2 si los casos de uso lo
  piden.

## Fuentes

- Highway Capacity Manual 2000, cap. 17 (Unsignalized Intersections),
  Example Problem 1 y Exhibits 17-4/17-5. Los valores base de brechas son
  idénticos en HCM 2010 (cap. 19) y HCM 6.ª/7.ª ed. (cap. 20).
- Akçelik & Associates, *HCM 2000 Back of Queue Model for Signalised
  Intersections* (nota técnica, sidrasolutions.com).
