// Bakkie family admin: the shared layout for SiteBakkie and QuoteBakkie.
// This file is identical in both apps (with family-admin.css). Each admin.html
// fetches its own data and passes it here, so both home pages have the same
// sections in the same order. Change it in one app, copy it to the other.
const FA = (() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (n) => (n === null || n === undefined || n === "") ? "–" : String(n);

  // The page frame: title, add button, tiles, needs, customers, sign-ups, visitors.
  function frame(el, { title, sub, addLabel }) {
    el.innerHTML = `<div class="fa-title"><div><h1>${esc(title)}</h1><p class="muted">${esc(sub)}</p></div>
        ${addLabel ? `<button class="primary" id="fa-add-btn">+ ${esc(addLabel)}</button>` : ""}</div>
      <div id="fa-add" class="card hidden"></div>
      <div id="fa-tiles" class="fa-tiles"></div>
      <div id="fa-needs"></div>
      <h2>Customers</h2><div id="fa-customers"></div>
      <h2>Sign-ups</h2><div id="fa-signups" class="card"></div>
      <h2>Website visitors</h2><div id="fa-visitors" class="card"><p class="muted small">Loading…</p></div>`;
    const btn = el.querySelector("#fa-add-btn");
    if (btn) btn.onclick = () => { const box = el.querySelector("#fa-add"); box.classList.toggle("hidden");
      const f = box.querySelector("input"); if (f && !box.classList.contains("hidden")) f.focus(); };
    return { add: el.querySelector("#fa-add"), tiles: el.querySelector("#fa-tiles"), needs: el.querySelector("#fa-needs"),
      customers: el.querySelector("#fa-customers"), signups: el.querySelector("#fa-signups"), visitors: el.querySelector("#fa-visitors") };
  }

  // Six numbers: [{label, value, hint, tone: ok|warn|bad}]
  function tiles(el, items) {
    el.innerHTML = items.map((t) => `<div class="fa-tile ${t.tone || ""}"><b>${esc(num(t.value))}</b><span>${esc(t.label)}</span>
      ${t.hint ? `<small>${esc(t.hint)}</small>` : ""}</div>`).join("");
  }

  // Things that need the admin now: [{tone, html}]. Hidden when empty.
  function needs(el, items) {
    el.innerHTML = items.length ? `<h2>Needs you</h2><div class="card fa-needs">${items.map((n) =>
      `<div class="fa-need ${n.tone || "warn"}">${n.html}</div>`).join("")}</div>` : "";
  }

  const badge = (text, tone) => `<span class="badge ${tone || ""}">${esc(text)}</span>`;

  // One customer card. c: {id, name, badge:{text,tone}, off, meta:[..], usage, actions (html), extra (html)}
  const card = (c) => `<li class="fa-cust ${c.off ? "off" : ""}" data-cust="${esc(c.id)}">
      <div class="row between wrap"><b class="fa-name">${esc(c.name)}</b>${c.badge ? badge(c.badge.text, c.badge.tone) : ""}</div>
      ${c.meta && c.meta.length ? `<div class="muted small">${c.meta.filter(Boolean).map(esc).join(" · ")}</div>` : ""}
      ${c.usage ? `<div class="small">${esc(c.usage)}</div>` : ""}
      ${c.actions ? `<div class="actions-row" style="margin-top:8px">${c.actions}</div>` : ""}
      ${c.extra || ""}</li>`;

  // Search box, status filters and the cards. filters: [{key, label, test(c)}]; text(c) for search.
  function customers(el, list, { filters, text, toCard, empty }) {
    let q = "", f = filters[0].key;
    el.innerHTML = `<div class="fa-tools"><input id="fa-q" type="search" placeholder="Search name, email, phone…" autocomplete="off">
        <div class="fa-chips">${filters.map((x) => `<button type="button" data-fa-filter="${x.key}">${esc(x.label)} <span class="muted"></span></button>`).join("")}</div></div>
      <ul class="hist" id="fa-list"></ul>`;
    const draw = () => {
      const match = (c) => !q || text(c).toLowerCase().includes(q);
      el.querySelectorAll("[data-fa-filter]").forEach((b) => {
        const x = filters.find((y) => y.key === b.dataset.faFilter);
        b.classList.toggle("on", x.key === f);
        b.querySelector("span").textContent = list.filter((c) => x.test(c) && match(c)).length;
      });
      const test = filters.find((x) => x.key === f).test;
      const shown = list.filter((c) => test(c) && match(c));
      el.querySelector("#fa-list").innerHTML = shown.map((c) => card(toCard(c))).join("") ||
        `<li class="muted">${esc(q || f !== filters[0].key ? "Nobody matches." : (empty || "No customers yet."))}</li>`;
    };
    el.querySelector("#fa-q").oninput = (e) => { q = e.target.value.trim().toLowerCase(); draw(); };
    el.querySelectorAll("[data-fa-filter]").forEach((b) => b.onclick = () => { f = b.dataset.faFilter; draw(); });
    draw();
  }

  // Anonymous website visitors (the same analytics module in both apps).
  function visitors(el, s, { site, onDays }) {
    const bars = (rows) => { const m = Math.max(1, ...rows.map((r) => r[1]));
      return rows.map(([k, v]) => `<li style="--w:${Math.round(100 * v / m)}%"><span>${esc(k)}</span><b>${v}</b></li>`).join("") || "<li class='muted'>No data yet</li>"; };
    const max = Math.max(1, ...s.days.map((d) => d.visitors));
    el.innerHTML = `<div class="row between"><span class="muted small">Different people per day, from the public website and the app</span>
        <select id="fa-days" style="width:auto;margin:0">${[7, 30, 90].map((d) => `<option value="${d}" ${d === s.days.length ? "selected" : ""}>${d} days</option>`).join("")}</select></div>
      <div class="sgrid"><div><span>${s.today}</span>today</div><div><span>${s.week}</span>last 7 days</div>
        <div><span>${s.month}</span>in period</div><div><span>${s.signups}</span>sign-ups (${s.conversion}%)</div></div>
      <div class="chart">${s.days.map((d) => `<i class="${d.signups ? "s" : ""}" style="height:${Math.round(100 * d.visitors / max)}%"
        title="${esc(d.day)}: ${d.visitors} visitors, ${d.views} views${d.signups ? ", " + d.signups + " sign-ups" : ""}"></i>`).join("")}</div>
      <div class="two"><div><b class="small">Where they came from</b><ul class="bars">${bars(s.sources)}</ul></div>
        <div><b class="small">Pages</b><ul class="bars">${bars(s.pages)}</ul><b class="small">Device</b><ul class="bars">${bars(s.devices)}</ul></div></div>
      <details><summary class="small">Recent visits</summary><ul class="plain small">${s.recent.map((r) =>
        `<li>${esc(r.t.slice(5, 16).replace("T", " "))} · ${r.e === "signup" ? "<b>SIGN-UP</b>" : esc(r.p)} · ${esc(r.s)} · ${esc(r.d)}</li>`).join("") || "<li class='muted'>No visits yet</li>"}</ul></details>
      <p class="muted small">Anonymous: no cookies, no IP addresses stored. Tag your links to see campaigns, e.g. <code>${esc(site)}/?utm_source=facebook</code>.</p>`;
    el.querySelector("#fa-days").onchange = (e) => onDays(+e.target.value);
  }

  const daysAgo = (iso) => iso ? (Date.now() - new Date(iso.replace(" ", "T")).getTime()) / 86400000 : Infinity;
  return { esc, badge, frame, tiles, needs, customers, visitors, daysAgo };
})();
