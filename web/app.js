"use strict";

const $ = (id) => document.getElementById(id);
const WIDTH = 128, HEIGHT = 64;
const state = { sample: null, tool: "paint", drawing: false, running: false,
  loadingSample: false, ready: false, edited: false, hasResult: false, status: null,
  labs: null, labsPromise: null, history: [], result: null, selectedDigit: 0,
  previousPoint: null, keyboardPoint: { x: 32, y: 32 }, canvasFocused: false };
const formatInt = (number) => Number(number).toLocaleString("en-US");
const percent = (number, digits = 1) => `${(Number(number) * 100).toFixed(digits)}%`;
const finite = (number) => typeof number === "number" && Number.isFinite(number);
const backendNames = { reference: "Python integer reference", c: "Native C integer model", rtl: "Verilog / Icarus batch simulation" };
let context, overlay;

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 240000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || data.message || `Request failed (${response.status}).`);
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The local engine took too long. Check the server console and try again.");
    throw error;
  } finally { clearTimeout(timeout); }
}
function showError(error) { $("global-error").textContent = error.message || String(error); $("global-error").hidden = false; }
function clearError() { $("global-error").hidden = true; }
function element(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}
function locked() { return state.running || state.loadingSample || !state.ready; }
function remember() {
  state.history.push(context.getImageData(0, 0, WIDTH, HEIGHT));
  if (state.history.length > 24) state.history.shift();
  $("undo-input").disabled = locked() || !state.history.length;
}
function readPixels() {
  const rgba = context.getImageData(0, 0, WIDTH, HEIGHT).data;
  return Array.from({ length: WIDTH * HEIGHT }, (_, i) => Math.round(rgba[i * 4] * 16 / 255));
}
function writePixels(pixels) {
  if (!Array.isArray(pixels) || pixels.length !== WIDTH * HEIGHT) throw new Error("The server returned an invalid canvas image.");
  const image = context.createImageData(WIDTH, HEIGHT);
  pixels.forEach((value, i) => {
    const gray = Math.round(Math.max(0, Math.min(16, value)) * 255 / 16);
    image.data[i * 4] = image.data[i * 4 + 1] = image.data[i * 4 + 2] = gray;
    image.data[i * 4 + 3] = 255;
  });
  context.putImageData(image, 0, 0);
}
function redrawOverlay() {
  overlay.clearRect(0, 0, WIDTH, HEIGHT);
  if (state.result?.segmentation?.boxes && state.hasResult) {
    overlay.strokeStyle = "#a0f2bf"; overlay.lineWidth = .6;
    state.result.segmentation.boxes.forEach((box, i) => {
      overlay.strokeRect(box.x - 1, box.y - 1, box.width + 2, box.height + 2);
      overlay.fillStyle = "#a0f2bf"; overlay.font = "5px monospace";
      overlay.fillText(String(i + 1), Math.max(1, box.x), Math.max(5, box.y - 2));
    });
  }
  if ($("manual-split").checked && $("digit-mode").value !== "single") {
    const split = Number($("split-position").value);
    overlay.save(); overlay.setLineDash([2, 2]); overlay.lineWidth = .6; overlay.strokeStyle = "#f8a18e";
    overlay.beginPath(); overlay.moveTo(split, 0); overlay.lineTo(split, HEIGHT); overlay.stroke(); overlay.restore();
  }
  if (state.canvasFocused) {
    const point = state.keyboardPoint;
    overlay.strokeStyle = "#f8a18e"; overlay.lineWidth = .5;
    overlay.strokeRect(point.x - 2, point.y - 2, 4, 4);
  }
}
function invalidateResult() {
  state.result = null; state.hasResult = false;
  $("result-content").hidden = true; $("empty-result").hidden = false;
  $("result-status").textContent = "INPUT CHANGED"; $("result-status").classList.remove("complete");
  $("inference-status").textContent = "Input changed. Recognize again to compute a new result.";
  redrawOverlay();
}
function edited(description = "Custom drawing · 128 × 64 pixels") {
  state.edited = true; invalidateResult(); $("sample-description").textContent = description;
}
function pointFromEvent(event) {
  const bounds = $("draw-canvas").getBoundingClientRect();
  return { x: Math.max(0, Math.min(WIDTH - .01, (event.clientX - bounds.left) * WIDTH / bounds.width)),
    y: Math.max(0, Math.min(HEIGHT - .01, (event.clientY - bounds.top) * HEIGHT / bounds.height)) };
}
function stroke(from, to) {
  const width = Number($("brush-size").value);
  context.strokeStyle = context.fillStyle = state.tool === "erase" ? "#000" : "#fff";
  context.lineWidth = state.tool === "erase" ? width * 1.6 : width;
  context.lineCap = "round"; context.lineJoin = "round";
  context.beginPath(); context.moveTo(from.x, from.y); context.lineTo(to.x, to.y); context.stroke();
  context.beginPath(); context.arc(to.x, to.y, context.lineWidth / 2, 0, Math.PI * 2); context.fill();
}
function showSample(sample) {
  remember(); writePixels(sample.pixels); state.sample = sample; state.edited = false;
  invalidateResult(); $("sample-description").textContent = `MNIST example ${sample.index + 1} · expected “${sample.label}”`;
}
async function nextExample() {
  clearError(); state.loadingSample = true; setRunning(false);
  try {
    const count = state.status?.highres?.model?.metrics?.test_samples || 10000;
    const index = ((state.sample?.index ?? -1) + 1) % count;
    const digits = $("digit-mode").value === "single" ? 1 : 2;
    showSample(await request(`/api/hd/sample?index=${index}&digits=${digits}`));
  } catch (error) { showError(error); }
  finally { state.loadingSample = false; setRunning(false); }
}
async function importImage(file) {
  if (!file) return;
  if (!["image/png", "image/jpeg"].includes(file.type)) throw new Error("Choose a PNG or JPEG image.");
  if (file.size > 10 * 1024 * 1024) throw new Error("Choose an image smaller than 10 MB.");
  state.loadingSample = true; setRunning(false);
  try {
    const image = await createImageBitmap(file);
    const temporary = document.createElement("canvas"); temporary.width = WIDTH; temporary.height = HEIGHT;
    const ctx = temporary.getContext("2d", { willReadFrequently: true });
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, WIDTH, HEIGHT);
    const scale = Math.min((WIDTH - 6) / image.width, (HEIGHT - 6) / image.height);
    const width = image.width * scale, height = image.height * scale;
    ctx.drawImage(image, (WIDTH - width) / 2, (HEIGHT - height) / 2, width, height); image.close();
    const rgba = ctx.getImageData(0, 0, WIDTH, HEIGHT).data;
    const gray = Array.from({ length: WIDTH * HEIGHT }, (_, i) => .299 * rgba[i * 4] + .587 * rgba[i * 4 + 1] + .114 * rgba[i * 4 + 2]);
    let edge = 0, edgeCount = 0;
    const left = Math.floor((WIDTH - width) / 2), top = Math.floor((HEIGHT - height) / 2);
    const right = Math.ceil((WIDTH + width) / 2), bottom = Math.ceil((HEIGHT + height) / 2);
    for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) if (x < left + 2 || x >= right - 2 || y < top + 2 || y >= bottom - 2) { edge += gray[y * WIDTH + x]; edgeCount++; }
    const invert = edge / edgeCount > 127;
    remember(); writePixels(gray.map((value, i) => {
      const x = i % WIDTH, y = Math.floor(i / WIDTH);
      return x < left || x >= right || y < top || y >= bottom ? 0 : Math.round((invert ? 255 - value : value) * 16 / 255);
    }));
    edited(`Imported ${file.name} · ${invert ? "dark ink normalized" : "light ink normalized"}`);
  } finally { state.loadingSample = false; setRunning(false); }
}
function buildEditor() {
  const canvas = $("draw-canvas"); context = canvas.getContext("2d", { willReadFrequently: true });
  overlay = $("overlay-canvas").getContext("2d"); overlay.scale(4,4); context.fillStyle = "#000"; context.fillRect(0, 0, WIDTH, HEIGHT);
  canvas.addEventListener("pointerdown", (event) => {
    if (locked() || event.button !== 0) return;
    event.preventDefault(); remember(); state.drawing = true; state.previousPoint = pointFromEvent(event);
    canvas.setPointerCapture(event.pointerId); stroke(state.previousPoint, state.previousPoint); edited();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!state.drawing || locked()) return;
    const point = pointFromEvent(event); stroke(state.previousPoint, point); state.previousPoint = point;
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => canvas.addEventListener(type, () => { state.drawing = false; state.previousPoint = null; }));
  canvas.addEventListener("focus", () => { state.canvasFocused = true; redrawOverlay(); });
  canvas.addEventListener("blur", () => { state.canvasFocused = false; redrawOverlay(); });
  canvas.addEventListener("keydown", (event) => {
    if (locked()) return;
    const point = state.keyboardPoint, step = event.shiftKey ? 5 : 1;
    if (event.key === "ArrowLeft") point.x = Math.max(1, point.x - step);
    else if (event.key === "ArrowRight") point.x = Math.min(WIDTH - 1, point.x + step);
    else if (event.key === "ArrowUp") point.y = Math.max(1, point.y - step);
    else if (event.key === "ArrowDown") point.y = Math.min(HEIGHT - 1, point.y + step);
    else if (event.key === " ") { remember(); stroke(point, point); edited(); }
    else return;
    event.preventDefault(); redrawOverlay();
  });
  ["paint", "erase"].forEach((tool) => $(tool + "-tool").addEventListener("click", () => {
    state.tool = tool;
    ["paint", "erase"].forEach((name) => { $(name + "-tool").classList.toggle("selected", name === tool); $(name + "-tool").setAttribute("aria-pressed", String(name === tool)); });
  }));
  $("brush-size").addEventListener("input", () => { $("brush-value").textContent = $("brush-size").value + " px"; });
  $("clear-input").addEventListener("click", () => { remember(); context.fillStyle = "#000"; context.fillRect(0, 0, WIDTH, HEIGHT); edited("Blank canvas · draw one or two digits"); });
  $("undo-input").addEventListener("click", () => { const image = state.history.pop(); if (image) context.putImageData(image, 0, 0); edited("Previous canvas restored"); $("undo-input").disabled = !state.history.length; });
  $("next-example").addEventListener("click", nextExample);
  $("upload-image").addEventListener("click", () => $("image-upload").click());
  $("image-upload").addEventListener("change", async (event) => { clearError(); try { await importImage(event.target.files[0]); } catch (error) { showError(error); } finally { event.target.value = ""; } });
  $("digit-mode").addEventListener("change", () => { invalidateResult(); setRunning(false); });
  $("manual-split").addEventListener("change", () => { invalidateResult(); setRunning(false); });
  $("split-position").addEventListener("input", () => { $("split-value").textContent = "x = " + $("split-position").value; invalidateResult(); });
  $("backend-select").addEventListener("change", invalidateResult);
}
function setRunning(running) {
  state.running = running; const isLocked = locked();
  $("inference-output").setAttribute("aria-busy", String(running));
  ["run-inference", "backend-select", "next-example", "clear-input", "paint-tool", "erase-tool", "brush-size", "upload-image", "image-upload", "digit-mode", "manual-split"].forEach((id) => { $(id).disabled = isLocked; });
  $("undo-input").disabled = isLocked || !state.history.length;
  $("split-position").disabled = isLocked || !$("manual-split").checked || $("digit-mode").value === "single";
  $("manual-split").disabled = isLocked || $("digit-mode").value === "single";
  $("draw-canvas").setAttribute("aria-disabled", String(isLocked));
  $("run-label").textContent = state.loadingSample ? "Preparing image…" : running ? ($("backend-select").value === "rtl" ? "Simulating digit batch…" : "Recognizing…") : "Recognize number";
  if (running) { $("result-status").textContent = "COMPUTING"; $("result-status").classList.remove("complete"); $("inference-status").textContent = "Recognition started."; }
}
function addMetric(value, label) { const metric = element("div", "metric"); metric.append(element("strong", "", value), element("span", "", label)); $("inference-metrics").append(metric); }
function drawNormalized(canvas, pixels) {
  canvas.width = canvas.height = 28;
  const ctx = canvas.getContext("2d"), image = ctx.createImageData(28, 28);
  pixels.forEach((value, i) => { const gray = Math.round(value / 16 * 255); image.data[i * 4] = image.data[i * 4 + 1] = image.data[i * 4 + 2] = gray; image.data[i * 4 + 3] = 255; });
  ctx.putImageData(image, 0, 0);
}
function inspectDigit(index) {
  state.selectedDigit = index; const digit = state.result.digits[index];
  [...$("digit-crops").children].forEach((button, i) => { button.classList.toggle("selected", i === index); button.setAttribute("aria-pressed", String(i === index)); });
  $("logit-title").textContent = `Digit ${index + 1} · raw class logits`;
  const maximum = Math.max(1, ...digit.logits.map(Math.abs)); $("logits-chart").replaceChildren();
  digit.logits.forEach((value, label) => {
    const row = element("div", "logit-row" + (label === digit.prediction ? " winner" : ""));
    const track = element("div", "logit-track"), bar = element("span", "logit-bar" + (value < 0 ? " negative" : ""));
    const width = Math.abs(value) / maximum * 50; bar.style.width = `${width}%`; bar.style.left = `${value < 0 ? 50 - width : 50}%`;
    if (!value) bar.style.minWidth = "0"; track.append(bar);
    row.append(element("span", "logit-digit", label), track, element("span", "logit-value", formatInt(value)));
    row.setAttribute("aria-label", `Digit class ${label}, logit ${value}`); $("logits-chart").append(row);
  });
  $("logits-chart").setAttribute("aria-label", `Digit ${index + 1} class logits. Prediction ${digit.prediction}.`);
  const ranked = digit.logits.map((logit,label) => ({logit,label})).sort((a,b) => b.logit-a.logit || a.label-b.label).slice(0,3);
  $("class-alternatives").replaceChildren(element("span", "ranking-caption", "Top scores"), ...ranked.map(({logit,label}) => element("span", label === digit.prediction ? "ranking-winner" : "", `${label}: ${formatInt(logit)}`)));
  $("hidden-activations").replaceChildren(); digit.hidden.forEach((value, i) => {
    const neuron = element("div", "neuron"); neuron.style.backgroundColor = `rgba(160,242,191,${.07 + value / 127 * .75})`;
    neuron.setAttribute("title", `Neuron ${i + 1}: ${value}`); neuron.setAttribute("aria-label", `Neuron ${i + 1}, value ${value}`); $("hidden-activations").append(neuron);
  });
  $("hidden-caption").textContent = `${digit.hidden.length} neurons · 0–127`;
}
function renderResult(result, sampleLabel) {
  state.result = result; state.hasResult = true;
  $("empty-result").hidden = true; $("result-content").hidden = false;
  const blank = result.status === "blank" || !result.digits?.length;
  $("prediction-digit").textContent = blank ? "—" : result.text;
  $("prediction-caption").textContent = blank ? "No ink found. Draw a digit or load an example." : sampleLabel === null ? `${result.digits.length} digit${result.digits.length === 1 ? "" : "s"}, read left to right.` : result.text === String(sampleLabel) ? `Matches this example: ${sampleLabel}.` : `Example label ${sampleLabel}; recognized ${result.text}.`;
  $("verification-badge").textContent = blank ? "No classifier was forced to guess" : result.verified ? "✓ Exact integer reference check passed" : "Python reference result";
  $("verification-badge").classList.toggle("unchecked", !result.verified);
  $("result-backend").textContent = backendNames[result.backend] || result.backend || "";
  $("result-status").textContent = blank ? "BLANK INPUT" : result.verified ? "CHECKED RESULT" : "RESULT RETURNED"; $("result-status").classList.add("complete");
  $("inference-metrics").replaceChildren();
  if (finite(result.kernel_cycles)) addMetric(formatInt(result.kernel_cycles), "RTL kernel cycles");
  if (finite(result.transaction_cycles)) addMetric(formatInt(result.transaction_cycles), "MMIO bench cycles");
  if (finite(result.macs)) addMetric(formatInt(result.macs), "Useful MACs");
  if (finite(result.host_elapsed_ms)) addMetric(`${result.host_elapsed_ms.toFixed(1)} ms`, "Host elapsed time");
  const warnings = [...(result.warnings || []), ...(result.segmentation?.warnings || [])];
  $("pipeline-warning").textContent = [...new Set(warnings)].join(" "); $("pipeline-warning").hidden = !warnings.length;
  $("digit-crops").replaceChildren();
  (result.digits || []).forEach((digit, i) => {
    if (!Array.isArray(digit.logits) || digit.logits.length !== 10 || !Array.isArray(digit.normalized) || digit.normalized.length !== 784) throw new Error("The local engine returned an incomplete digit result.");
    const button = element("button", "digit-crop"); button.type = "button";
    const canvas = element("canvas", "normalized-digit"); canvas.setAttribute("aria-label", `Normalized 28 by 28 input for digit ${i + 1}`); drawNormalized(canvas, digit.normalized);
    const copy = element("span", "crop-copy"); copy.append(element("b", "", `Digit ${i + 1} → ${digit.prediction}`), element("small", "", "28 × 28 · 784 values"));
    if (finite(digit.margin)) copy.append(element("small", "crop-margin", `Relative score gap: ${formatInt(digit.margin)}`));
    button.append(canvas, copy); button.addEventListener("click", () => inspectDigit(i)); $("digit-crops").append(button);
  });
  const method = result.segmentation?.method || "Digit normalization";
  $("segmentation-caption").textContent = blank ? "The blank check happens before model inference." : `${method}. ${result.batch_size || result.digits.length} digit(s) processed. ${result.cycle_scope || "Host elapsed time includes preparation and execution; it is not hardware latency."}`;
  $("logits-chart").hidden = blank; $("hidden-activations").hidden = blank;
  $("class-alternatives").hidden = blank;
  $("logit-title").parentElement.hidden = blank; $("hidden-caption").parentElement.hidden = blank;
  if (!blank) inspectDigit(0);
  redrawOverlay(); $("inference-status").textContent = blank ? "Blank image. No prediction made." : `Recognized ${result.text}. ${result.verified ? "Integer reference matched." : "Reference inference completed."}`;
}

const policyLabels = { off: "Prefetch off", next_line: "Next-line", stride: "Stride", rule: "Fixed rule", learned: "Learned selector", scratchpad: "Scheduled scratchpad" };
function renderMemorySelection() {
  const lab = state.labs.memory;
  const selection = $("memory-workload").value;
  const values = selection === "all" ? lab.summary : lab.workloads.find((row) => row.id === selection).results;
  $("memory-table").replaceChildren();
  for (const name of ["off", "next_line", "stride", "rule", "learned", "scratchpad"]) {
    const result = values[name];
    if (!result) continue;
    const row = element("tr", name === "learned" ? "emphasized" : "");
    const label = element("td", "", policyLabels[name]);
    if (name === "learned") label.append(element("span", "table-policy-hint", "CART decision tree"));
    row.append(label, element("td", "", formatInt(result.cycles)), element("td", "", formatInt(result.memory_transactions)), element("td", "", `${(values.off.cycles / result.cycles).toFixed(3)}×`));
    $("memory-table").append(row);
  }
  const learned = values.learned.cycles, rule = values.rule.cycles;
  let verdict = learned === rule ? "The learned selector ties the fixed rule on modeled cycles in this selection." : learned < rule ? `The learned selector uses ${((1 - learned / rule) * 100).toFixed(1)}% fewer modeled cycles than the fixed rule in this selection.` : `The learned selector uses ${((learned / rule - 1) * 100).toFixed(1)}% more modeled cycles than the fixed rule in this selection.`;
  verdict += " Learning does not guarantee an improvement over a good heuristic.";
  $("memory-verdict").textContent = verdict;
}

function populateList(id, entries) {
  $(id).replaceChildren(...entries.map((text) => element("li", "", text)));
}
function modelPills(id, values) { $(id).replaceChildren(...values.map((text) => element("span", "", text))); }

function renderMemory(lab) {
  modelPills("memory-model", [lab.model.cache, `${lab.model.capacity_bytes} B capacity`, `${lab.model.memory_read_cycles}-cycle memory`, `${lab.model.selection_window}-access window`]);
  $("memory-training").textContent = `${lab.training.algorithm}, depth ≤ ${lab.training.max_depth}; ${formatInt(lab.training.rows)} training windows, ${formatInt(lab.training.test_rows)} held-out windows. Held-out policy-label accuracy: ${percent(lab.training.held_out_accuracy)}. ${lab.training.split}`;
  lab.workloads.forEach((workload) => {
    const option = element("option", "", workload.kind.charAt(0).toUpperCase() + workload.kind.slice(1));
    option.value = workload.id;
    $("memory-workload").append(option);
  });
  $("memory-workload").addEventListener("change", renderMemorySelection);
  populateList("memory-limitations", lab.limitations);
  $("memory-timing").textContent = `${lab.model.timing} Scratchpad copies are charged and do not overlap compute. Labels: ${lab.training.label}`;
  renderMemorySelection();
  $("memory-loading").hidden = true;
  $("memory-content").hidden = false;
}

function renderSecurity(lab) {
  modelPills("security-model", [`${lab.model.sets} sets × ${lab.model.ways} ways`, `${lab.model.hit_cycles}-cycle hit`, `${lab.model.miss_cycles}-cycle miss`, `${formatInt(lab.shared.trials)} trials per mode`]);
  $("security-threat").textContent = lab.model.threat_model;
  $("security-comparison").replaceChildren();
  for (const mode of ["shared", "isolated"]) {
    const result = lab[mode];
    const card = element("section", `surface security-card ${mode}-card`);
    card.append(element("p", "eyebrow", mode === "shared" ? "SHARED REPLACEMENT STATE" : "ONE WAY PER DOMAIN"), element("h2", "", mode === "shared" ? "Shared cache" : "Isolated cache"));
    const rate = element("div", "security-rate");
    rate.append(element("strong", "", percent(result.observer_accuracy)), element("span", "", "observer accuracy"));
    const track = element("div", "accuracy-track");
    track.setAttribute("role", "img");
    track.setAttribute("aria-label", `Observer accuracy ${percent(result.observer_accuracy)}; chance ${percent(result.chance_accuracy)}`);
    const fill = element("div", "accuracy-fill");
    fill.style.width = `${Math.max(0, Math.min(100, result.observer_accuracy * 100))}%`;
    track.append(fill);
    const labels = element("div", "accuracy-labels");
    labels.append(element("span", "", "0%"), element("span", "", `chance ${percent(result.chance_accuracy, 0)}`), element("span", "", "100%"));
    const examples = result.observation_examples.slice(0, 3).map((pair) => `[${pair.join(", ")}]`).join(" · ");
    card.append(rate, track, labels, element("p", "security-observation", `Actual probe pairs (cycles): ${examples}. Each pair is the observer’s own latency for the two candidate sets.`), element("p", "chart-note", mode === "shared" ? "The victim’s selected set can change the observer’s cache residency in this controlled schedule." : "The reported rate is for this experiment. A result near chance does not establish general security."));
    $("security-comparison").append(card);
  }
  $("security-cost-table").replaceChildren();
  for (const mode of ["shared", "isolated"]) {
    const row = element("tr");
    const cycles = lab.summary[`${mode}_benign_cycles`];
    row.append(element("td", "", mode === "shared" ? "Shared cache" : "Isolated cache"), element("td", "", formatInt(lab.summary.benign_accesses)), element("td", "", formatInt(cycles)), element("td", "", `${(cycles / lab.summary.shared_benign_cycles).toFixed(2)}×`));
    $("security-cost-table").append(row);
  }
  $("security-cost-caption").textContent = `On this conflicting benign trace, isolation costs ${lab.summary.isolation_slowdown_on_conflicting_benign_trace.toFixed(2)}× as many modeled cycles. Attack-trial totals use different priming sequences and are not used for this performance comparison.`;
  populateList("security-limitations", lab.limitations);
  $("security-loading").hidden = true;
  $("security-content").hidden = false;
}

async function loadLabs() {
  if (state.labs) return;
  if (!state.labsPromise) state.labsPromise = request("/api/labs").then((labs) => {
    state.labs = labs;
    renderMemory(labs.memory);
    renderSecurity(labs.security);
  }).catch((error) => {
    state.labsPromise = null;
    $("memory-loading").textContent = "The experiment could not load. Select this tab again to retry.";
    $("security-loading").textContent = "The experiment could not load. Select this tab again to retry.";
    showError(error);
  });
  await state.labsPromise;
}

function selectTab(name) {
  ["inference", "memory", "security"].forEach((tabName) => {
    const selected = name === tabName;
    $("tab-" + tabName).classList.toggle("active", selected);
    $("tab-" + tabName).setAttribute("aria-selected", String(selected));
    $("tab-" + tabName).tabIndex = selected ? 0 : -1;
    $("panel-" + tabName).hidden = !selected;
  });
  if (name !== "inference") loadLabs();
}


async function initialize() {
  buildEditor(); setRunning(false);
  const tabs = ["inference", "memory", "security"];
  tabs.forEach((name, index) => {
    $("tab-" + name).addEventListener("click", () => selectTab(name));
    $("tab-" + name).addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault(); selectTab(tabs[next]); $("tab-" + tabs[next]).focus();
    });
  });
  $("run-inference").addEventListener("click", async () => {
    clearError(); setRunning(true);
    const label = !state.edited && state.sample ? state.sample.label : null;
    const body = { pixels: readPixels(), width: WIDTH, height: HEIGHT, mode: $("digit-mode").value, backend: $("backend-select").value };
    if ($("manual-split").checked && body.mode !== "single") body.split = Number($("split-position").value);
    try { renderResult(await request("/api/recognize", { method: "POST", body: JSON.stringify(body) }), label); }
    catch (error) { showError(error); $("result-status").textContent = "RUN FAILED"; $("inference-status").textContent = "Recognition failed. See the error message."; }
    finally { setRunning(false); }
  });
  try {
    const status = await request("/api/status"); state.status = status;
    if (!status.highres?.model) throw new Error("The running server still uses NeuroTile v1. Restart tools/serve.py and refresh this page to load the high-resolution engine.");
    const model = status.highres.model, backends = status.highres.backends || status.backends;
    $("connection-status").textContent = "VISION ENGINE CONNECTED";
    $("model-topology").textContent = `${model.input_size} → ${model.hidden_size} → ${model.output_size}`;
    $("backend-select").replaceChildren();
    ["rtl", "c", "reference"].forEach((name) => { const option = element("option", "", backendNames[name] + (backends[name] ? "" : " — unavailable")); option.value = name; option.disabled = !backends[name]; $("backend-select").append(option); });
    $("backend-select").value = backends.rtl ? "rtl" : backends.c ? "c" : "reference";
    const metrics = model.metrics || {};
    $("model-footnote").textContent = finite(metrics.quantized_test_accuracy) ? `28 × 28 quantized MNIST model: ${percent(metrics.quantized_test_accuracy, 2)} on ${formatInt(metrics.test_samples)} held-out test digits. Two-digit inputs are segmented into individual model crops. Single-digit test accuracy is not a guarantee for arbitrary handwritten pairs or uploads.` : "Real 28 × 28 digit model. Two-digit recognition segments the image and classifies both crops; consult the model report for measured accuracy.";
    state.ready = true; await nextExample(); setRunning(false);
  } catch (error) { $("connection-status").textContent = "VISION ENGINE UNAVAILABLE"; showError(error); }
}
initialize();
