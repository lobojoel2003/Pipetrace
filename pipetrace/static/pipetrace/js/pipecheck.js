// The "what did you find?" helper on the coin-and-magnet guide.
// Same rules as residents.models.guess_material on the server.
export function guess(scratch, magnet) {
  if (scratch === "plastic") return "plastic";
  if (scratch === "copper" && magnet !== "sticks") return "copper";
  if (magnet === "sticks") return "galvanized";
  if (scratch === "silver") return "lead";
  if (scratch === "gray" && magnet === "no_stick") return "lead";
  return "unknown";
}

export function initPipeHelper() {
  const helper = document.querySelector("[data-pipe-helper]");
  if (!helper) return;
  const result = helper.querySelector("[data-result]");
  const body = helper.querySelector("[data-result-body]");
  const link = helper.querySelector("[data-result-link]");
  const baseHref = link.getAttribute("href");

  const update = () => {
    const scratch = helper.querySelector('input[name="scratch"]:checked')?.value;
    const magnet = helper.querySelector('input[name="magnet"]:checked')?.value;
    if (!scratch || !magnet) return;
    const outcome = guess(scratch, magnet);
    const template = helper.querySelector(`template[data-outcome="${outcome}"]`);
    body.replaceChildren(template.content.cloneNode(true));
    const url = new URL(baseHref, window.location.href);
    url.searchParams.set("scratch", scratch);
    url.searchParams.set("magnet", magnet);
    const line = new URLSearchParams(window.location.search).get("line");
    if (line) url.searchParams.set("line", line);
    link.href = url.pathname + url.search;
    result.hidden = false;
  };
  helper.addEventListener("change", update);
}
