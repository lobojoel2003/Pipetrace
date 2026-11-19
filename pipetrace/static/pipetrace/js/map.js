// Service line map: MapLibre GL + an optional Protomaps (PMTiles) basemap.
// No tile service, API key or map fees: the basemap is a single .pmtiles file the
// utility hosts itself, read with HTTP range requests.
import * as maplibregl from "../vendor/maplibre-gl/maplibre-gl.mjs";
import * as basemaps from "../vendor/protomaps-basemaps/basemaps.mjs";
import { CODE_CLASS, escapeHtml, shapeSvg } from "./shapes.js";

const CODES = ["N", "U", "G", "L"]; // drawing order: lead on top
const SHAPE = { L: "circle", G: "diamond", U: "square", N: "dot" };

const absolute = (url) => new URL(url, window.location.href).href;
const isDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`could not load ${src}`));
    document.head.appendChild(script);
  });
}

let pmtilesReady = null;
async function enablePmtiles() {
  if (!pmtilesReady) {
    pmtilesReady = (async () => {
      if (!window.pmtiles) await loadScript(new URL("../vendor/pmtiles/pmtiles.js", import.meta.url).href);
      const protocol = new window.pmtiles.Protocol();
      maplibregl.addProtocol("pmtiles", protocol.tile);
    })();
  }
  return pmtilesReady;
}

// Draw a status marker to a canvas: coloured shape, surface ring, thin dark edge.
function markerImage(code, ratio = 2) {
  const size = code === "N" ? 16 : 22;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size * ratio;
  const g = canvas.getContext("2d");
  g.scale(ratio, ratio);
  const c = size / 2;
  const r = code === "N" ? 5 : 7.5;
  const path = new Path2D();
  switch (SHAPE[code]) {
    case "diamond":
      path.moveTo(c, c - r - 1.5); path.lineTo(c + r + 1.5, c); path.lineTo(c, c + r + 1.5);
      path.lineTo(c - r - 1.5, c); path.closePath();
      break;
    case "square": {
      const s = r * 1.75, x = c - s / 2, rad = 2.5;
      path.moveTo(x + rad, x); path.arcTo(x + s, x, x + s, x + s, rad);
      path.arcTo(x + s, x + s, x, x + s, rad); path.arcTo(x, x + s, x, x, rad);
      path.arcTo(x, x, x + s, x, rad); path.closePath();
      break;
    }
    default:
      path.arc(c, c, r, 0, Math.PI * 2);
  }
  g.lineJoin = "round";
  g.lineWidth = 4;
  g.strokeStyle = isDark() ? "rgba(10,14,18,0.95)" : "rgba(255,255,255,0.95)";
  g.stroke(path);
  g.fillStyle = cssVar(`--${CODE_CLASS[code]}`) || "#888";
  g.fill(path);
  g.lineWidth = 1;
  g.strokeStyle = isDark() ? "rgba(255,255,255,0.35)" : "rgba(15,31,41,0.45)";
  g.stroke(path);
  return { width: size * ratio, height: size * ratio, data: g.getImageData(0, 0, size * ratio, size * ratio).data };
}

function demoLayers(dark) {
  const c = dark
    ? { land: "#1b2024", park: "#1f3326", school: "#2a2721", water: "#16324a", building: "#2a3036",
        buildingLine: "#353c43", casing: "#0f1316", road: "#3a424a", major: "#5a5236", text: "#c9d2d8",
        halo: "#1b2024", waterText: "#7fb3d9" }
    : { land: "#f3f1ec", park: "#d5e8c6", school: "#efe4d4", water: "#b8d7ec", building: "#e1dbd0",
        buildingLine: "#d0c8ba", casing: "#d6cfc2", road: "#ffffff", major: "#fde7a6", text: "#3d4a52",
        halo: "#ffffff", waterText: "#3b6f99" };
  const width = (minor, major) => ["interpolate", ["exponential", 1.6], ["zoom"], 13, ["case", ["==", ["get", "cls"], "major"], major[0], minor[0]], 18, ["case", ["==", ["get", "cls"], "major"], major[1], minor[1]]];
  return [
    { id: "land", type: "background", paint: { "background-color": c.land } },
    { id: "park", type: "fill", source: "demo", filter: ["==", ["get", "kind"], "park"], paint: { "fill-color": c.park } },
    { id: "school", type: "fill", source: "demo", filter: ["==", ["get", "kind"], "school"], paint: { "fill-color": c.school } },
    { id: "water", type: "fill", source: "demo", filter: ["==", ["get", "kind"], "water"], paint: { "fill-color": c.water } },
    { id: "building", type: "fill", source: "demo", minzoom: 14.5, filter: ["==", ["get", "kind"], "building"], paint: { "fill-color": c.building, "fill-outline-color": c.buildingLine } },
    { id: "road-casing", type: "line", source: "demo", filter: ["==", ["get", "kind"], "road"], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": c.casing, "line-width": width([4, 26], [6, 36]) } },
    { id: "road", type: "line", source: "demo", filter: ["==", ["get", "kind"], "road"], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["case", ["==", ["get", "cls"], "major"], c.major, c.road], "line-width": width([2.5, 22], [4, 31]) } },
    { id: "water-label", type: "symbol", source: "demo", filter: ["==", ["get", "kind"], "waterway"], layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-font": ["Noto Sans Italic"], "text-size": 13, "text-letter-spacing": 0.1 }, paint: { "text-color": c.waterText, "text-halo-color": c.halo, "text-halo-width": 1.2 } },
    { id: "road-label", type: "symbol", source: "demo", minzoom: 14.5, filter: ["==", ["get", "kind"], "road"], layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": ["interpolate", ["linear"], ["zoom"], 14.5, 11, 18, 15], "symbol-spacing": 280 }, paint: { "text-color": c.text, "text-halo-color": c.halo, "text-halo-width": 1.5 } },
    { id: "park-label", type: "symbol", source: "demo", minzoom: 14, filter: ["in", ["get", "kind"], ["literal", ["park", "school"]]], layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Italic"], "text-size": 12, "text-max-width": 7 }, paint: { "text-color": dark ? "#8fbf98" : "#4f7a45", "text-halo-color": c.halo, "text-halo-width": 1.2 } },
    { id: "place-label", type: "symbol", source: "demo", maxzoom: 16, filter: ["==", ["get", "kind"], "place"], layout: { "text-field": ["upcase", ["get", "name"]], "text-font": ["Noto Sans Medium"], "text-size": 13, "text-letter-spacing": 0.25 }, paint: { "text-color": dark ? "#9aa7af" : "#6c7880", "text-halo-color": c.halo, "text-halo-width": 1.5 } },
  ];
}

async function buildStyle(cfg) {
  const dark = isDark();
  const assets = absolute(`${cfg.assets}/`);
  const style = {
    version: 8,
    glyphs: `${assets}fonts/{fontstack}/{range}.pbf`,
    sources: {},
    layers: [],
  };
  if (cfg.pmtiles) {
    await enablePmtiles();
    style.sprite = `${assets}sprites/v4/${dark ? "dark" : "light"}`;
    style.sources.protomaps = {
      type: "vector",
      url: `pmtiles://${absolute(cfg.pmtiles)}`,
      attribution: '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
    };
    style.layers = basemaps.layers("protomaps", basemaps.namedFlavor(dark ? "dark" : "light"), { lang: cfg.lang });
  } else if (cfg.demo) {
    style.sources.demo = { type: "geojson", data: absolute(cfg.demo), attribution: cfg.demoLabel || "" };
    style.layers = demoLayers(dark);
  } else {
    style.layers = [{ id: "land", type: "background", paint: { "background-color": cssVar("--map-surface") || "#f3f1ec" } }];
  }
  return style;
}

function popupHtml(config, props) {
  const label = config.labels.status[props.s] || "";
  const replaced = props.r ? ` · ${escapeHtml(config.labels.replaced)}` : "";
  const url = config.lineUrl.replace("__ID__", props.i);
  return `<p class="popup-addr">${escapeHtml(props.a)}</p>`
    + `<p class="popup-status">${shapeSvg(props.s, 16)}<span>${escapeHtml(label)}${replaced}</span></p>`
    + `<a href="${escapeHtml(url)}">${escapeHtml(config.labels.details)} →</a>`;
}

async function createMap(container, config, cfg) {
  const mode = container.dataset.mapMode || "overview";
  const focus = cfg.focus;
  const options = {
    container,
    style: await buildStyle({ ...cfg, demoLabel: config.labels.demoMap }),
    attributionControl: { compact: true },
    cooperativeGestures: true,
    maxZoom: 19,
    dragRotate: false,
    pitchWithRotate: false,
  };
  if (focus && mode === "line") {
    options.center = [focus.lon, focus.lat];
    options.zoom = 17;
  } else if (cfg.center && cfg.zoom) {
    options.center = cfg.center;
    options.zoom = cfg.zoom;
  } else if (cfg.bounds) {
    options.bounds = cfg.bounds;
    options.fitBoundsOptions = { padding: 40, maxZoom: 16 };
  } else {
    options.center = [-96, 38.5];
    options.zoom = 3.5;
  }
  const map = new maplibregl.Map(options);
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
  map.touchZoomRotate.disableRotation();

  map.on("load", () => {
    CODES.forEach((code) => map.addImage(`pt-${code}`, markerImage(code), { pixelRatio: 2 }));
    map.addSource("lines", { type: "geojson", data: absolute(cfg.data) });
    if (focus) {
      map.addLayer({
        id: "focus-halo",
        type: "circle",
        source: "lines",
        filter: ["==", ["get", "i"], focus.id],
        paint: {
          "circle-radius": 18,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-width": 3,
          "circle-stroke-color": cssVar("--ink") || "#0f1f29",
        },
      });
    }
    map.addLayer({
      id: "lines",
      type: "symbol",
      source: "lines",
      layout: {
        "icon-image": ["concat", "pt-", ["get", "s"]],
        "icon-size": ["interpolate", ["linear"], ["zoom"], 12, 0.5, 15, 0.85, 18, 1.25],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "symbol-sort-key": ["match", ["get", "s"], "L", 3, "G", 2, "U", 1, 0],
      },
    });

    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "280px", offset: 12 });
    map.on("click", "lines", (event) => {
      const feature = event.features[0];
      popup.setLngLat(feature.geometry.coordinates).setHTML(popupHtml(config, feature.properties)).addTo(map);
    });
    map.on("mouseenter", "lines", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "lines", () => { map.getCanvas().style.cursor = ""; });

    // Legend buttons show and hide each status.
    const legend = document.querySelector("[data-legend]");
    if (legend && mode === "overview") {
      const buttons = [...legend.querySelectorAll("button[data-status]")];
      const apply = () => {
        const shown = buttons.filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.status);
        map.setFilter("lines", ["in", ["get", "s"], ["literal", shown]]);
      };
      buttons.forEach((button) => button.addEventListener("click", () => {
        button.setAttribute("aria-pressed", button.getAttribute("aria-pressed") === "true" ? "false" : "true");
        apply();
      }));
    }
  });
  map.on("error", (event) => console.warn("map:", event.error?.message || event));
  return map;
}

export function initMaps(config) {
  const cfgEl = document.getElementById("map-config");
  if (!cfgEl) return;
  const cfg = JSON.parse(cfgEl.textContent);
  document.querySelectorAll("[data-map]").forEach((container) => {
    createMap(container, config, cfg).catch((error) => {
      console.error(error);
      const fallback = container.parentElement.querySelector("[data-map-fallback]");
      if (fallback) {
        fallback.hidden = false;
        fallback.querySelector("p").textContent = config.labels.mapError;
      }
    });
  });
}
