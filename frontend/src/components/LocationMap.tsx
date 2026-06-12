import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Button, Card, Input } from "neobrutalistcomponents";
import { importOsm } from "../api";
import type { IntersectionConfig } from "../types";

interface Props {
  config: IntersectionConfig;
  onChange: (c: IntersectionConfig) => void;
}

function isValid(lat: number | null, lng: number | null): boolean {
  return (
    lat != null &&
    lng != null &&
    !isNaN(lat) &&
    !isNaN(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
}

export function LocationMap({ config, onChange }: Props) {
  const lat = config.latitude ?? null;
  const lng = config.longitude ?? null;
  const valid = isValid(lat, lng);

  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.CircleMarker | null>(null);
  const [paste, setPaste] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importWarnings, setImportWarnings] = useState<string[]>([]);

  // Referencia viva para el handler de clic del mapa (evita closures viejos).
  const liveRef = useRef({ config, onChange });
  liveRef.current = { config, onChange };

  // Crea / actualiza el mapa Leaflet cuando hay coordenadas válidas.
  useEffect(() => {
    if (!valid) {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        markerRef.current = null;
      }
      return;
    }
    if (!divRef.current) return;

    let map = mapRef.current;
    if (!map) {
      map = L.map(divRef.current, { scrollWheelZoom: false });
      L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        {
          subdomains: "abcd",
          maxZoom: 19,
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
        },
      ).addTo(map);
      map.setView([lat as number, lng as number], 16);
      map.on("click", (e: L.LeafletMouseEvent) => {
        const live = liveRef.current;
        live.onChange({
          ...live.config,
          latitude: e.latlng.lat,
          longitude: e.latlng.lng,
        });
      });
      mapRef.current = map;
    } else {
      map.setView([lat as number, lng as number], map.getZoom() || 16);
    }

    if (markerRef.current) markerRef.current.remove();
    markerRef.current = L.circleMarker([lat as number, lng as number], {
      radius: 9,
      color: "#8a0f1c",
      weight: 3,
      fillColor: "#8a0f1c",
      fillOpacity: 0.35,
    })
      .addTo(map)
      .bindPopup(config.name || "Intersección");
  }, [valid, lat, lng, config.name]);

  // Destruye el mapa al desmontar el componente.
  useEffect(
    () => () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    },
    [],
  );

  const setCoords = (la: number | null, ln: number | null) => {
    onChange({ ...config, latitude: la, longitude: ln });
  };

  const parseField = (raw: string): number | null => {
    if (raw.trim() === "") return null;
    const n = parseFloat(raw);
    return isNaN(n) ? null : n;
  };

  const applyPaste = (text: string) => {
    setPaste(text);
    const nums = text
      .split(/[,;\s]+/)
      .map((s) => parseFloat(s.trim()))
      .filter((n) => !isNaN(n));
    if (nums.length >= 2) setCoords(nums[0], nums[1]);
  };

  const latStr = lat != null && !isNaN(lat) ? lat : "";
  const lngStr = lng != null && !isNaN(lng) ? lng : "";

  const runImport = async () => {
    if (!valid) return;
    if (
      config.approaches.length > 0 &&
      !window.confirm(
        "Importar desde OSM reemplaza la configuración actual (accesos, " +
          "fases y demanda). ¿Continuar?",
      )
    ) {
      return;
    }
    setImporting(true);
    setImportError(null);
    setImportWarnings([]);
    try {
      const res = await importOsm(lat as number, lng as number);
      onChange(res.config);
      setImportWarnings(res.warnings);
    } catch (e) {
      setImportError(String(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <Card>
      <Card.Header>
        <Card.Title>Ubicación</Card.Title>
        <Card.Description>
          Posición de la intersección en el plano de la ciudad
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <div className="row" style={{ marginBottom: 12, alignItems: "flex-end" }}>
          <Input
            label="Latitud"
            size="sm"
            type="number"
            step={0.000001}
            value={latStr}
            onChange={(e) => setCoords(parseField(e.target.value), lng)}
            style={{ width: 150 }}
          />
          <Input
            label="Longitud"
            size="sm"
            type="number"
            step={0.000001}
            value={lngStr}
            onChange={(e) => setCoords(lat, parseField(e.target.value))}
            style={{ width: 150 }}
          />
          <Input
            label="Pegar «latitud, longitud»"
            size="sm"
            type="text"
            placeholder="latitud, longitud"
            value={paste}
            onChange={(e) => applyPaste(e.target.value)}
            style={{ width: 220 }}
          />
        </div>

        {valid ? (
          <>
            <div ref={divRef} className="map-container" />
            <div
              className="row"
              style={{ marginTop: 8, justifyContent: "space-between" }}
            >
              <span style={{ fontSize: 12, color: "var(--muted)" }}>
                Coordenadas: {(lat as number).toFixed(5)},{" "}
                {(lng as number).toFixed(5)} · clic en el mapa mueve el pin
              </span>
              <a
                href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}`}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: 12 }}
              >
                Abrir en OpenStreetMap →
              </a>
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <Button
                variant="secondary"
                size="sm"
                loading={importing}
                onClick={runImport}
              >
                Importar geometría desde OSM
              </Button>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>
                Detecta el cruce más cercano al pin: accesos, carriles y
                nombres de calles. Luego agrega giros y demanda.
              </span>
            </div>
            {importError && (
              <div className="error" style={{ marginTop: 8 }}>
                {importError}
              </div>
            )}
            {importWarnings.map((w, i) => (
              <div key={i} className="note" style={{ marginTop: 6 }}>
                {w}
              </div>
            ))}
          </>
        ) : (
          <div className="map-placeholder">
            Ingresa la latitud y la longitud para ubicar la intersección en el
            plano.
          </div>
        )}
      </Card.Content>
    </Card>
  );
}
