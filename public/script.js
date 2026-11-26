(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("form"), card = $("card"), result = $("result");
  const steps = [...form.querySelectorAll(".step")];
  const navItems = [...document.querySelectorAll("#navSteps li")];
  const backBtn = $("backBtn"), nextBtn = $("nextBtn"), errBox = $("error"), bar = $("bar");
  const TOTAL = steps.length;
  const CIRC = 2 * Math.PI * 74; // ring circumference (r = 74)
  let current = 1;

  /* ---------- example customers ---------- */
  const PRESETS = {
    high: { Age: 45, Education: "PhD", Marital_Status: "Single", Income: 85000, Kidhome: 0, Teenhome: 0, Customer_Since: "2013-06-15", Recency: 8,
      MntWines: 900, MntFruits: 60, MntMeatProducts: 600, MntFishProducts: 90, MntSweetProducts: 70, MntGoldProds: 80,
      NumDealsPurchases: 1, NumWebPurchases: 6, NumCatalogPurchases: 8, NumStorePurchases: 7, NumWebVisitsMonth: 3,
      AcceptedCmp1: true, AcceptedCmp2: false, AcceptedCmp3: false, AcceptedCmp4: true, AcceptedCmp5: true, Complain: false },
    low: { Age: 52, Education: "Graduation", Marital_Status: "Married", Income: 32000, Kidhome: 1, Teenhome: 1, Customer_Since: "2014-03-10", Recency: 70,
      MntWines: 30, MntFruits: 5, MntMeatProducts: 20, MntFishProducts: 4, MntSweetProducts: 3, MntGoldProds: 10,
      NumDealsPurchases: 4, NumWebPurchases: 2, NumCatalogPurchases: 0, NumStorePurchases: 3, NumWebVisitsMonth: 8,
      AcceptedCmp1: false, AcceptedCmp2: false, AcceptedCmp3: false, AcceptedCmp4: false, AcceptedCmp5: false, Complain: false },
  };

  /* ---------- helpers ---------- */
  function setValues(values) {
    Object.entries(values).forEach(([name, val]) => {
      const el = form.elements[name];
      if (!el) return;
      if (el.type === "checkbox") el.checked = !!val; else el.value = val;
    });
    updateTotal(true);
    clearErrors();
  }

  function collect() {
    const data = {};
    [...form.elements].forEach((el) => {
      if (!el.name) return;
      data[el.name] = el.type === "checkbox" ? (el.checked ? 1 : 0) : el.value;
    });
    return data;
  }

  function showError(msg) { errBox.textContent = msg; errBox.hidden = false; }
  function clearErrors() {
    errBox.hidden = true;
    form.querySelectorAll(".invalid").forEach((e) => e.classList.remove("invalid"));
  }

  function countUp(el, to, fmt, ms = 900) {
    const t0 = performance.now();
    (function frame(now) {
      const t = Math.min((now - t0) / ms, 1);
      el.textContent = fmt(to * (1 - Math.pow(1 - t, 3)));
      if (t < 1) requestAnimationFrame(frame);
    })(t0);
  }

  /* ---------- live total of spending ---------- */
  const spendNames = ["MntWines", "MntMeatProducts", "MntFishProducts", "MntFruits", "MntSweetProducts", "MntGoldProds"];
  let shownTotal = 0;
  function updateTotal(instant) {
    const sum = spendNames.reduce((s, n) => s + (parseFloat(form.elements[n].value) || 0), 0);
    const el = $("spendTotal"), from = shownTotal;
    shownTotal = sum;
    if (instant) { el.textContent = "$" + sum.toLocaleString(); return; }
    const t0 = performance.now();
    (function frame(now) {
      const t = Math.min((now - t0) / 350, 1);
      el.textContent = "$" + Math.round(from + (sum - from) * t).toLocaleString();
      if (t < 1) requestAnimationFrame(frame);
    })(t0);
  }

  /* ---------- steppers (+ / −) ---------- */
  form.addEventListener("click", (e) => {
    const btn = e.target.closest(".st");
    if (!btn) return;
    const input = btn.parentElement.querySelector("input");
    const step = parseFloat(input.dataset.step) || 1;
    const min = input.min !== "" ? parseFloat(input.min) : -Infinity;
    const max = input.max !== "" ? parseFloat(input.max) : Infinity;
    let v = parseFloat(input.value) || 0;
    v += step * parseInt(btn.dataset.dir, 10);
    input.value = Math.min(max, Math.max(min, v));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  form.addEventListener("input", (e) => {
    e.target.closest(".stepper, .control")?.classList.remove("invalid");
    if (spendNames.includes(e.target.name)) updateTotal();
  });

  /* ---------- step navigation ---------- */
  function showStep(n, backwards = false) {
    current = n;
    steps.forEach((s, i) => {
      const on = i + 1 === n;
      s.classList.toggle("active", on);
      s.classList.toggle("back", on && backwards);
      if (on) s.querySelectorAll(".field, .cmp, .switch, .total").forEach((f, k) => f.style.setProperty("--i", k));
    });
    navItems.forEach((li, i) => {
      li.classList.toggle("active", i + 1 === n);
      li.classList.toggle("done", i + 1 < n);
    });
    bar.style.width = (n / TOTAL) * 100 + "%";
    backBtn.style.visibility = n === 1 ? "hidden" : "visible";
    nextBtn.querySelector("span").textContent = n === TOTAL ? "Predict response ✦" : "Continue →";
    clearErrors();
  }

  function validateStep(n) {
    clearErrors();
    let first = null;
    steps[n - 1].querySelectorAll("input[type=number], input[type=date], select").forEach((el) => {
      const v = String(el.value).trim();
      let bad = v === "";
      if (!bad && el.type === "number") bad = Number(v) < Number(el.min || -Infinity) || Number(v) > Number(el.max || Infinity);
      if (bad) {
        el.closest(".stepper, .control")?.classList.add("invalid") || el.classList.add("invalid");
        first = first || el;
      }
    });
    if (first) {
      const lo = first.min, hi = first.max;
      showError(first.type === "number" && lo !== "" && hi !== ""
        ? `Please enter a number between ${Number(lo).toLocaleString()} and ${Number(hi).toLocaleString()}.`
        : "Please fill in the highlighted field.");
      first.focus();
      return false;
    }
    return true;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!validateStep(current)) return;
    if (current < TOTAL) showStep(current + 1); else predict();
  });
  backBtn.addEventListener("click", () => current > 1 && showStep(current - 1, true));
  navItems.forEach((li, i) => li.addEventListener("click", () => {
    if (li.classList.contains("done") && result.hidden) showStep(i + 1, true);
  }));

  /* ---------- prediction ---------- */
  async function predict() {
    nextBtn.disabled = true; nextBtn.classList.add("loading");
    try {
      const res = await fetch("/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(collect()) });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Something went wrong.");
      showResult(json);
    } catch (err) {
      showError(err.message || "Couldn't reach the server. Is it still running?");
    } finally {
      nextBtn.disabled = false; nextBtn.classList.remove("loading");
    }
  }

  const COPY = {
    "Very high": ["Definitely contact them", "Excellent potential. This customer is very likely to respond, so make them a priority in your next campaign."],
    "High": ["Worth contacting", "Strong potential. Include this customer in your next campaign."],
    "Moderate": ["Worth a try", "A fair chance of responding. Include them if your budget allows."],
    "Low": ["Probably skip", "Low chance of responding. Save your budget for customers with a better chance."],
  };

  function fillReasons(listEl, items, max) {
    listEl.innerHTML = "";
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "none"; li.style.setProperty("--i", 0);
      li.textContent = "Nothing significant";
      listEl.appendChild(li);
      return;
    }
    items.forEach((f, i) => {
      const li = document.createElement("li");
      li.style.setProperty("--i", i);
      const name = document.createElement("span"); name.textContent = f.label;
      const track = document.createElement("span"); track.className = "bar";
      const fill = document.createElement("i"); track.appendChild(fill);
      li.append(name, track); listEl.appendChild(li);
      requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.width = Math.max(10, (Math.abs(f.impact) / max) * 100) + "%")));
    });
  }

  function showResult(r) {
    form.hidden = true; result.hidden = false;
    navItems.forEach((li) => { li.classList.remove("active"); li.classList.add("done"); });

    const ring = document.querySelector(".ring");
    ring.className = "ring " + (r.responder ? "yes" : "no");
    const fill = $("rFill");
    fill.style.strokeDashoffset = CIRC;
    requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.strokeDashoffset = CIRC * (1 - Math.min(r.probability, 1)))));

    const a = r.threshold * 2 * Math.PI - Math.PI / 2, pt = (rad) => [90 + rad * Math.cos(a), 90 + rad * Math.sin(a)];
    const [x1, y1] = pt(63), [x2, y2] = pt(85), tick = $("rTick");
    tick.setAttribute("x1", x1); tick.setAttribute("y1", y1); tick.setAttribute("x2", x2); tick.setAttribute("y2", y2);

    countUp($("pct"), r.probability * 100, (v) => v.toFixed(1) + "%", 1200);
    $("thr").textContent = Math.round(r.threshold * 100) + "%";

    const tag = $("tag");
    tag.className = "tag " + (r.responder ? "yes" : "no");
    tag.textContent = r.responder ? "Likely responder" : "Unlikely responder";
    const [head, sub] = COPY[r.tier] || COPY.Low;
    $("headline").textContent = head;
    $("sub").textContent = sub;

    const pros = r.positive_factors.slice(0, 3), cons = r.negative_factors.slice(0, 3);
    const max = Math.max(...[...pros, ...cons].map((f) => Math.abs(f.impact)), 0.001);
    fillReasons($("pros"), pros, max);
    fillReasons($("cons"), cons, max);

    const dl = $("derived"); dl.innerHTML = "";
    Object.entries(r.derived).forEach(([k, v]) => {
      const box = document.createElement("div");
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = v;
      box.append(dt, dd); dl.appendChild(box);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function backToForm(step) {
    result.hidden = true; form.hidden = false;
    form.style.animation = "none"; void form.offsetWidth; form.style.animation = "";
    showStep(step, true);
  }
  $("editBtn").addEventListener("click", () => backToForm(1));
  $("againBtn").addEventListener("click", () => {
    form.reset(); setValues(defaults); backToForm(1);
  });

  /* ---------- examples ---------- */
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    setValues(PRESETS[b.dataset.preset]);
    predict();
  }));

  /* ---------- mouse spotlight ---------- */
  card.addEventListener("pointermove", (e) => {
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", e.clientX - r.left + "px");
    card.style.setProperty("--my", e.clientY - r.top + "px");
  });

  /* ---------- init ---------- */
  const defaults = {};
  [...form.elements].forEach((el) => { if (el.name) defaults[el.name] = el.type === "checkbox" ? el.checked : el.value; });
  updateTotal(true);
  showStep(1);
})();