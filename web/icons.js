// Category colors + stroke-style SVG glyphs, drawn as GTA-style radar blips.
window.CATS = {
  restaurant:   { label: "Restaurants & Food",          color: "#f7a531", glyph: '<path d="M7 3v7a2 2 0 0 0 4 0V3M9 3v18M17 21V3c-2 1-3 4-3 8h3"/>' },
  cafe_bar:     { label: "Cafés & Bars",                color: "#b56cff", glyph: '<path d="M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM16 10h1.5a2.5 2.5 0 0 1 0 5H16M7 3v3M11 3v3"/>' },
  salon:        { label: "Salons & Beauty",             color: "#ff5fa2", glyph: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.2 8.2 20 20M8.2 15.8 20 4"/>' },
  fitness:      { label: "Gyms & Fitness",              color: "#22d3a6", glyph: '<path d="M6 6v12M3 9v6M18 6v12M21 9v6M6 12h12"/>' },
  dental:       { label: "Dentists",                    color: "#5ec8ff", glyph: '<path d="M7 3C4.5 3 3 5 3 7.5c0 3 2 4 2.5 7.5S7 21 8.5 21s1.5-5 3.5-5 2 5 3.5 5 2.5-2.5 3-6S21 10.5 21 7.5C21 5 19.5 3 17 3c-2 0-3 1-5 1S9 3 7 3z"/>' },
  health:       { label: "Health & Wellness",           color: "#ff4d5e", glyph: '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/>' },
  auto:         { label: "Auto Shops",                  color: "#ffd23f", glyph: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>' },
  home:         { label: "Contractors & Home Services", color: "#9be22d", glyph: '<path d="M3 11 12 3l9 8M5 9.5V21h14V9.5M10 21v-6h4v6"/>' },
  retail:       { label: "Retail",                      color: "#4d7cff", glyph: '<path d="M5 8h14l-1 13H6zM9 8V6a3 3 0 0 1 6 0v2"/>' },
  professional: { label: "Professional Services",       color: "#b8c4d6", glyph: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2M3 13h18"/>' },
};

window.blipSvg = function (cat, size) {
  const c = CATS[cat] || CATS.retail;
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${c.glyph}</svg>`;
};
