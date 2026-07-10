const DATA_URL = "https://volodymyrchubaaa-web.github.io/grant-monitor/grants.json";

const SECTOR_LABELS = {
  "інфраструктура (дороги, водопостачання, енергетика)": "Інфраструктура",
  "агропромисловий розвиток": "Агро",
  "підприємництво/МСП": "МСП",
  "підтримка підприємництва та МСП": "МСП",
  "освіта": "Освіта",
  "освіта та інклюзія": "Освіта",
  "довкілля": "Довкілля",
  "охорона довкілля": "Довкілля",
  "цифровізація": "Цифровізація",
  "цифровізація адмінпослуг": "Цифровізація",
  "туризм": "Туризм",
  "туризм та збереження культурної спадщини": "Туризм",
  "інше": "Інше",
};

function sectorLabel(sector) {
  return SECTOR_LABELS[sector] || sector || "Інше";
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("uk-UA", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function fmtAmount(min, max, currency) {
  if (!min && !max) return "—";
  const cur = currency || "";
  if (min && max) return `${min.toLocaleString("uk-UA")}–${max.toLocaleString("uk-UA")} ${cur}`;
  return `${(min || max).toLocaleString("uk-UA")} ${cur}`;
}

function probClass(p) {
  if (p == null) return "";
  if (p >= 0.6) return "prob-high";
  if (p < 0.35) return "prob-low";
  return "";
}

let ALL_GRANTS = [];

function renderCard(g) {
  const sector = sectorLabel(g.sector);
  const closed = g.status === "closed";
  const review = g.status === "needs_review";

  const tags = [`<span class="tag">${sector}</span>`];
  if (g.is_oms_eligible) tags.push(`<span class="tag tag-accent">ОМС прийнятний</span>`);
  if (closed) tags.push(`<span class="tag tag-muted">Дедлайн минув</span>`);
  if (review) tags.push(`<span class="tag tag-muted">Потребує перевірки</span>`);
  if (g.needs_partner_org) tags.push(`<span class="tag tag-solid">Потрібен партнер</span>`);

  const partnerNote = g.needs_partner_org
    ? `<div class="partner-note">ОМС не є прямим заявником — шукайте ГО/БФ-партнера для подання.${
        g.partner_org_name ? ` Пропозиція: <strong>${g.partner_org_name}</strong>` +
          (g.partner_org_url ? ` — <a href="${g.partner_org_url}" target="_blank" rel="noopener">сайт</a>` : "") +
          (g.partner_org_contact ? ` — <a href="${g.partner_org_contact}" target="_blank" rel="noopener">контакти</a>` : "")
          : ""
      }</div>`
    : "";

  return `
    <article class="card" data-sector="${g.sector || ""}" data-status="${g.status || ""}" data-oms="${g.is_oms_eligible ? "yes" : ""}" data-partner="${g.needs_partner_org ? "partner" : ""}">
      <div class="card-top">${tags.join("")}</div>
      <h3><a href="${g.url}" target="_blank" rel="noopener">${g.title || "Без назви"}</a></h3>
      <p class="desc">${g.description || ""}</p>
      <ul class="meta">
        <li><span class="k">Дедлайн</span><span class="v">${fmtDate(g.deadline)}</span></li>
        <li><span class="k">Бюджет</span><span class="v">${fmtAmount(g.amount_min, g.amount_max, g.currency)}</span></li>
        <li><span class="k">Заявник</span><span class="v">${g.applicant_type_raw || (g.is_oms_eligible ? "ОМС прийнятний" : "Уточнюється")}</span></li>
        <li><span class="k">Локація</span><span class="v">${g.location_raw || "—"}</span></li>
        <li><span class="k">Ймовірність успіху</span><span class="v ${probClass(g.success_probability)}">${g.success_probability != null ? Math.round(g.success_probability * 100) + "%" : "—"}</span></li>
      </ul>
      ${partnerNote}
    </article>
  `;
}

function applyFilters() {
  const sector = document.getElementById("f-sector").value;
  const status = document.getElementById("f-status").value;
  const oms = document.getElementById("f-oms").value;

  const filtered = ALL_GRANTS.filter((g) => {
    if (sector && g.sector !== sector) return false;
    if (status && g.status !== status) return false;
    if (oms === "yes" && !g.is_oms_eligible) return false;
    if (oms === "partner" && !g.needs_partner_org) return false;
    return true;
  });

  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  grid.innerHTML = filtered.map(renderCard).join("");
  empty.hidden = filtered.length > 0;
}

function renderStats(grants) {
  const active = grants.filter((g) => g.status !== "closed").length;
  const omsEligible = grants.filter((g) => g.is_oms_eligible).length;
  const needsPartner = grants.filter((g) => g.needs_partner_org).length;

  const stats = [
    { num: grants.length, label: "Всього знайдено" },
    { num: active, label: "Актуальні" },
    { num: omsEligible, label: "ОМС прийнятний" },
    { num: needsPartner, label: "Потрібен партнер" },
  ];

  document.getElementById("stats").innerHTML = stats
    .map((s) => `<div class="stat-cell"><div class="stat-num">${s.num}</div><div class="stat-label">${s.label}</div></div>`)
    .join("");
}

function populateSectorFilter(grants) {
  const select = document.getElementById("f-sector");
  const sectors = [...new Set(grants.map((g) => g.sector).filter(Boolean))];
  sectors.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = sectorLabel(s);
    select.appendChild(opt);
  });
}

async function init() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    const data = await res.json();
    ALL_GRANTS = data.grants || [];

    const badge = document.getElementById("generated-at");
    badge.textContent = data.generated_at
      ? "Оновлено: " + new Date(data.generated_at).toLocaleString("uk-UA")
      : "Ще не оновлювалось";

    const cliStatus = document.getElementById("cli-status");
    cliStatus.textContent = `знайдено ${ALL_GRANTS.length} записів · оновлено ${
      data.generated_at ? new Date(data.generated_at).toLocaleString("uk-UA") : "—"
    }`;

    renderStats(ALL_GRANTS);
    populateSectorFilter(ALL_GRANTS);
    applyFilters();

    ["f-sector", "f-status", "f-oms"].forEach((id) =>
      document.getElementById(id).addEventListener("change", applyFilters)
    );
  } catch (err) {
    document.getElementById("grid").innerHTML = "";
    document.getElementById("empty").hidden = false;
    document.getElementById("empty").textContent = "Не вдалося завантажити дані. Спробуйте пізніше.";
    document.getElementById("cli-status").textContent = "помилка завантаження";
    console.error(err);
  }
}

init();
