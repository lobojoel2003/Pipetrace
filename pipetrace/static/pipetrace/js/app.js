// Pipetrace front end. Plain ES modules, no build step.
import { initSearch } from "./search.js";
import { initPipeHelper } from "./pipecheck.js";
import { initForms } from "./forms.js";

const configEl = document.getElementById("pipetrace-config");
const config = configEl ? JSON.parse(configEl.textContent) : { labels: {} };

initSearch(config);
initPipeHelper();
initForms(config);

document.querySelectorAll("[data-print]").forEach((button) => {
  button.addEventListener("click", () => window.print());
});

// The map library is large: only load it on pages that show a map.
if (document.querySelector("[data-map]")) {
  import("./map.js")
    .then((module) => module.initMaps(config))
    .catch((error) => {
      console.error(error);
      document.querySelectorAll("[data-map-fallback]").forEach((el) => {
        el.hidden = false;
        el.querySelector("p").textContent = config.labels.mapError || "";
      });
    });
}
