// Status marker shapes, matching the server-side {% status_shape %} tag and the map.
export const CODE_CLASS = { L: "lead", G: "grr", U: "unknown", N: "nonlead" };

const SHAPES = {
  L: '<circle cx="8" cy="8" r="6.5"/>',
  G: '<path d="M8 1.2 14.8 8 8 14.8 1.2 8Z"/>',
  U: '<rect x="2" y="2" width="12" height="12" rx="2.5"/>',
  N: '<circle cx="8" cy="8" r="4.75"/>',
};

export function shapeSvg(code, size = 16) {
  const cls = CODE_CLASS[code] || "unknown";
  return `<svg class="shape shape-${cls}" width="${size}" height="${size}" viewBox="0 0 16 16" aria-hidden="true" focusable="false">${SHAPES[code] || SHAPES.U}</svg>`;
}

export function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}
