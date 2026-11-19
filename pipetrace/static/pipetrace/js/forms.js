// Resident forms: photo previews, answers carried over from the guide, and, in a
// static export, sending to SiteConfig.static_form_endpoint (or by email).
import { escapeHtml } from "./shapes.js";
import { findLine } from "./search.js";

function prefillFromQuery(form) {
  const params = new URLSearchParams(window.location.search);
  for (const name of ["scratch", "magnet"]) {
    const value = params.get(name);
    const input = value && form.querySelector(`input[name="${name}"][value="${CSS.escape(value)}"]`);
    if (input) input.checked = true;
  }
}

function photoPreviews(form) {
  const preview = form.querySelector("[data-photo-preview]");
  if (!preview) return;
  form.querySelectorAll('input[type="file"]').forEach((input) => {
    input.addEventListener("change", () => {
      preview.replaceChildren(...[...form.querySelectorAll('input[type="file"]')]
        .flatMap((el) => [...el.files])
        .filter((file) => file.type.startsWith("image/"))
        .map((file) => {
          const img = document.createElement("img");
          img.src = URL.createObjectURL(file);
          img.alt = "";
          return img;
        }));
    });
  });
}

async function staticLine(config, form) {
  const id = new URLSearchParams(window.location.search).get("line");
  if (!id) return;
  document.querySelectorAll("a[data-carry-line]").forEach((a) => {
    const url = new URL(a.href, window.location.href);
    url.searchParams.set("line", id);
    a.href = url.pathname + url.search;
  });
  if (!form) return;
  const line = await findLine(config, id).catch(() => null);
  if (!line) return;
  form.querySelector("[data-line-field]").value = line.id;
  const address = form.querySelector('[name="address"]');
  if (address && !address.value) address.value = [line.address, line.city].filter(Boolean).join(", ");
  const note = document.querySelector("[data-line-note]");
  if (note) {
    note.querySelector("[data-line-address]").textContent = line.address;
    note.hidden = false;
  }
}

function fieldLabel(form, name) {
  const input = form.querySelector(`[name="${name}"]`);
  const field = input?.closest(".field");
  const label = field?.querySelector("label, legend");
  return (label?.textContent || name).replace(/\s*\(.*\)\s*$/, "").trim();
}

function emailFallback(config, form, statusEl) {
  if (!config.email) {
    statusEl.innerHTML = `<p class="form-errors">${escapeHtml(config.labels.noEmail)} ${escapeHtml(config.phone || "")}</p>`;
    return;
  }
  const data = new FormData(form);
  const skip = new Set(["kind", "line", "website", "started", "language", "csrfmiddlewaretoken"]);
  const lines = [];
  for (const [name, value] of data.entries()) {
    if (skip.has(name) || value instanceof File || !String(value).trim()) continue;
    let text = String(value);
    const radio = form.querySelector(`input[name="${name}"][value="${CSS.escape(text)}"]`);
    if (radio && radio.type === "radio") text = radio.closest("label")?.textContent.trim() || text;
    if (radio && radio.type === "checkbox") continue;
    lines.push(`${fieldLabel(form, name)}: ${text}`);
  }
  const subject = `${form.dataset.staticForm === "photo" ? "Pipe photo" : "Inspection request"}: ${data.get("address") || ""}`;
  const href = `mailto:${config.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join("\n"))}`;
  window.location.href = href;
  statusEl.innerHTML = `<div class="callout"><p class="mb-0">${escapeHtml(config.labels.emailOpened)}</p></div>`;
}

function showErrors(form, errors) {
  form.querySelectorAll(".errorlist[data-js]").forEach((el) => el.remove());
  for (const [name, messages] of Object.entries(errors)) {
    const input = form.querySelector(`[name="${name}"]`);
    const field = input?.closest(".field");
    const list = document.createElement("ul");
    list.className = "errorlist";
    list.dataset.js = "1";
    list.innerHTML = messages.map((m) => `<li>${escapeHtml(m)}</li>`).join("");
    (field || form.querySelector("[data-form-status]")).appendChild(list);
  }
}

function staticSubmit(config, form) {
  const statusEl = form.querySelector("[data-form-status]");
  if (!form.getAttribute("action")) {
    // Email can't carry the file: the resident attaches the photo in their email app.
    form.querySelectorAll('input[type="file"]').forEach((input) => { input.required = false; });
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const endpoint = form.getAttribute("action");
    if (!endpoint) {
      emailFallback(config, form, statusEl);
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    statusEl.textContent = config.labels.sending;
    try {
      const response = await fetch(endpoint, { method: "POST", body: new FormData(form) });
      const data = await response.json().catch(() => ({}));
      if (response.status === 201 && data.reference) {
        form.innerHTML = `<div class="form-success"><p>${escapeHtml(config.labels.sent)}</p>`
          + `<p class="ref">${escapeHtml(data.reference)}</p></div>`;
        form.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      if (data.errors) showErrors(form, data.errors);
      statusEl.innerHTML = `<p class="form-errors">${escapeHtml(config.labels.sendError)}</p>`;
    } catch (error) {
      console.error(error);
      statusEl.innerHTML = `<p class="form-errors">${escapeHtml(config.labels.sendError)}</p>`;
    } finally {
      button.disabled = false;
    }
  });
}

export function initForms(config) {
  const form = document.querySelector("form.form");
  if (form) {
    prefillFromQuery(form);
    photoPreviews(form);
    if (config.static && form.dataset.staticForm) staticSubmit(config, form);
  }
  if (config.static) staticLine(config, form?.dataset.staticForm ? form : null).catch(() => {});
}
