// Staff tools: column-mapping previews and browser-driven geocoding batches.
document.querySelectorAll("select[data-autosubmit]").forEach((select) => {
  select.addEventListener("change", () => select.form.submit());
});

document.querySelectorAll("select[data-column-select]").forEach((select) => {
  const cell = document.querySelector(`[data-samples-for="${select.name}"]`);
  const show = () => {
    const option = select.selectedOptions[0];
    if (cell) cell.textContent = option?.dataset.samples || "";
  };
  select.addEventListener("change", show);
  show();
});

const geocoder = document.querySelector("[data-geocoder]");
if (geocoder) {
  const start = geocoder.querySelector("[data-geocode-start]");
  const stop = geocoder.querySelector("[data-geocode-stop]");
  const bar = geocoder.querySelector("[data-progress]");
  const status = geocoder.querySelector("[data-geocode-status]");
  const token = geocoder.querySelector("input[name=csrfmiddlewaretoken]").value;
  const total = Number(start.dataset.total) || 1;
  let running = false;
  let done = { matched: 0, approximate: 0, failed: 0 };

  const step = async () => {
    const response = await fetch(geocoder.dataset.stepUrl, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  };

  start.addEventListener("click", async () => {
    running = true;
    start.hidden = true;
    stop.hidden = false;
    try {
      while (running) {
        const data = await step();
        done.matched += data.matched;
        done.approximate += data.approximate;
        done.failed += data.failed;
        const finished = total - data.remaining;
        bar.style.width = `${Math.min(100, (100 * finished) / total)}%`;
        status.textContent = `${finished} / ${total} · ${done.matched} matched, ${done.approximate} approximate, ${done.failed} not found`;
        if (!data.remaining || !data.processed) {
          status.textContent += " ✓";
          setTimeout(() => window.location.reload(), 800);
          break;
        }
      }
    } catch (error) {
      status.textContent = error.message;
    } finally {
      running = false;
      start.hidden = false;
      stop.hidden = true;
    }
  });
  stop.addEventListener("click", () => { running = false; });
}
