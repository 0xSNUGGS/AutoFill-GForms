const COLORS = ["#11b8c4", "#7367f0", "#ff9f43", "#28c76f", "#ea5455", "#00a8cc", "#9c6ade", "#f368e0", "#607d8b", "#8bc34a"];

export default function(component) {
  const { data: args, setStateValue, parentElement } = component;
  const root = parentElement.querySelector(".distribution-root");
  let counts = Object.fromEntries(args.options.map(option => [option.key, Math.max(0, Math.min(args.total, Math.round(Number(args.counts[option.key] || 0))))]));
  let inputMode = args.inputMode || "percentage";
  const total = Math.max(1, Number(args.total));
  const pct = value => 100 * Number(value || 0) / total;
  const pctText = value => `${pct(value).toLocaleString("es-PY", {minimumFractionDigits: 2, maximumFractionDigits: 2})}%`;
  const notify = () => setStateValue("value", {counts: {...counts}, inputMode});

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function toolbar(exclusive) {
    const bar = make("div", "toolbar");
    const toggle = make("div", "toggle");
    [["percentage", "%"], ["count", "Cantidad"]].forEach(([mode, label]) => {
      const button = make("button", inputMode === mode ? "active" : "", label);
      button.type = "button";
      button.onclick = () => { inputMode = mode; render(); notify(); };
      toggle.appendChild(button);
    });
    bar.appendChild(toggle);
    if (exclusive) {
      const equal = make("button", "equal-button", "Distribuir igualmente");
      equal.type = "button";
      equal.onclick = () => {
        const base = Math.floor(total / args.options.length);
        let remainder = total - base * args.options.length;
        args.options.forEach(option => { counts[option.key] = base + (remainder-- > 0 ? 1 : 0); });
        render(); notify();
      };
      bar.appendChild(equal);
    }
    return bar;
  }

  function gradient() {
    let cursor = 0;
    const stops = [];
    args.options.forEach((option, index) => {
      const start = 100 * cursor / total;
      cursor += counts[option.key] || 0;
      const end = 100 * cursor / total;
      stops.push(`${COLORS[index % COLORS.length]} ${start}%`, `${COLORS[index % COLORS.length]} ${end}%`);
    });
    return `linear-gradient(90deg, ${stops.join(",")})`;
  }

  function setExclusiveCount(index, desired) {
    const key = args.options[index].key;
    const current = counts[key] || 0;
    const delta = desired - current;
    if (delta > 0) {
      const donors = [...args.options.slice(index + 1), ...args.options.slice(0, index).reverse()];
      let acquired = 0;
      for (const donor of donors) {
        const take = Math.min(delta - acquired, counts[donor.key] || 0);
        counts[donor.key] -= take;
        acquired += take;
        if (acquired === delta) break;
      }
      counts[key] = current + acquired;
    } else if (delta < 0) {
      const receiver = args.options[index + 1] || args.options[index - 1];
      if (receiver) counts[receiver.key] -= delta;
      counts[key] = desired;
    }
  }

  function numericEditor(option, index, exclusive) {
    const wrap = make("div", "number-wrap");
    const input = document.createElement("input");
    input.type = "number";
    input.min = 0;
    input.max = inputMode === "count" ? total : 100;
    input.step = inputMode === "count" ? 1 : Math.max(0.01, 100 / total);
    input.value = inputMode === "count" ? counts[option.key] : pct(counts[option.key]).toFixed(2);
    input.setAttribute("aria-label", `${option.label}, ${inputMode === "count" ? "cantidad" : "porcentaje"}`);
    input.onchange = () => {
      let desired = inputMode === "count" ? Math.round(Number(input.value)) : Math.round(total * Number(input.value) / 100);
      desired = Math.max(0, Math.min(total, desired || 0));
      if (exclusive) setExclusiveCount(index, desired); else counts[option.key] = desired;
      render(); notify();
    };
    wrap.appendChild(input);
    if (inputMode === "percentage") wrap.appendChild(make("span", "unit", "%"));
    return wrap;
  }

  function optionName(option, index) {
    const name = make("div", "option-name");
    const swatch = make("span", "swatch");
    swatch.style.background = COLORS[index % COLORS.length];
    const label = make("span", "label", option.label);
    label.title = option.label;
    name.append(swatch, label);
    return name;
  }

  function exclusiveView() {
    root.appendChild(toolbar(true));
    const wrap = make("div", "segmented-wrap");
    const track = make("div", "segmented-track");
    track.style.background = gradient();
    wrap.appendChild(track);
    let cumulative = 0;
    args.options.slice(0, -1).forEach((option, index) => {
      cumulative += counts[option.key] || 0;
      const handle = make("input", "boundary");
      handle.type = "range";
      handle.min = 0;
      handle.max = total;
      handle.step = 1;
      handle.value = cumulative;
      handle.style.zIndex = String(20 + index);
      handle.setAttribute("aria-label", `Límite después de ${option.label}`);
      handle.oninput = () => {
        const previous = args.options.slice(0, index).reduce((sum, item) => sum + (counts[item.key] || 0), 0);
        const combined = (counts[option.key] || 0) + (counts[args.options[index + 1].key] || 0);
        const boundary = Math.max(previous, Math.min(previous + combined, Math.round(Number(handle.value))));
        counts[option.key] = boundary - previous;
        counts[args.options[index + 1].key] = combined - counts[option.key];
        updateExclusiveVisuals(track, wrap);
      };
      handle.onchange = notify;
      wrap.appendChild(handle);
    });
    root.appendChild(wrap);
    const rows = make("div", "rows");
    args.options.forEach((option, index) => {
      const row = make("div", "option-row");
      row.append(optionName(option, index), make("div", "value", `${pctText(counts[option.key])} · ${counts[option.key]}`), numericEditor(option, index, true));
      rows.appendChild(row);
    });
    root.appendChild(rows);
  }

  function updateExclusiveVisuals(track, wrap) {
    track.style.background = gradient();
    wrap.querySelectorAll(".boundary").forEach((handle, index) => {
      handle.value = args.options.slice(0, index + 1).reduce((sum, item) => sum + (counts[item.key] || 0), 0);
    });
    root.querySelectorAll(".option-row").forEach((row, index) => {
      const current = counts[args.options[index].key] || 0;
      row.querySelector(".value").textContent = `${pctText(current)} · ${current}`;
      row.querySelector("input[type=number]").value = inputMode === "count" ? current : pct(current).toFixed(2);
    });
  }

  function multipleView() {
    root.appendChild(toolbar(false));
    const rows = make("div", "rows");
    args.options.forEach((option, index) => {
      const row = make("div", "multi-row");
      const bar = make("div", "bar-wrap");
      const track = make("div", "bar-track");
      const fill = make("div", "bar-fill");
      fill.style.background = COLORS[index % COLORS.length];
      fill.style.width = `${pct(counts[option.key])}%`;
      const slider = make("input", "multi-range");
      slider.type = "range";
      slider.min = 0;
      slider.max = total;
      slider.step = 1;
      slider.value = counts[option.key];
      slider.setAttribute("aria-label", option.label);
      const value = make("div", "value", `${pctText(counts[option.key])} · ${counts[option.key]}`);
      slider.oninput = () => {
        counts[option.key] = Math.round(Number(slider.value));
        fill.style.width = `${pct(counts[option.key])}%`;
        value.textContent = `${pctText(counts[option.key])} · ${counts[option.key]}`;
        row.querySelector("input[type=number]").value = inputMode === "count" ? counts[option.key] : pct(counts[option.key]).toFixed(2);
        updateMultipleSummary();
      };
      slider.onchange = notify;
      bar.append(track, fill, slider);
      row.append(optionName(option, index), bar, value, numericEditor(option, index, false));
      rows.appendChild(row);
    });
    root.appendChild(rows);
    root.appendChild(make("div", "summary"));
    updateMultipleSummary();
  }

  function updateMultipleSummary() {
    const selected = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
    root.querySelector(".summary").textContent = `Promedio planificado: ${(selected / total).toLocaleString("es-PY", {minimumFractionDigits: 2, maximumFractionDigits: 2})} opciones por persona · ${selected} selecciones totales.`;
    const old = root.querySelector(".warning");
    if (old) old.remove();
    if (selected < total * args.minimum || selected > total * args.maximum) {
      root.appendChild(make("div", "warning", `Esta distribución no puede respetar entre ${args.minimum} y ${args.maximum} opciones por persona. Se necesitan entre ${total * args.minimum} y ${total * args.maximum} selecciones totales.`));
    }
  }

  function render() {
    root.replaceChildren();
    if (!args.options.length) return;
    args.kind === "multiple" ? multipleView() : exclusiveView();
  }

  render();
}
