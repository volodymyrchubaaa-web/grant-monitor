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
  "соціальний захист": "Соц. захист",
  "євроінтеграція": "Євроінтеграція",
  "інше": "Інше",
};

function sectorLabel(sector) {
  return SECTOR_LABELS[sector] || sector || "Інше";
}

const SOURCE_LABELS = {
  eu_funding_tenders_portal: "EU Funding & Tenders Portal",
  decentralization_gov_ua_grants: "Децентралізація.gov.ua",
  prostir_ua_grants: "Громадський Простір (prostir.ua)",
  gurt_org_ua: "ГУРТ (gurt.org.ua)",
  getgrant_ua: "GetGrant.ua",
  international_donors_direct: "Прямі джерела донорів",
};

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source || "—";
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

const FAV_KEY = "grantMonitor.favorites";

function favId(g) {
  return `${g.source || ""}::${g.external_id || g.url}`;
}

function loadFavorites() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveFavorites(set) {
  localStorage.setItem(FAV_KEY, JSON.stringify([...set]));
}

let FAVORITES = loadFavorites();
let SHOW_FAVORITES_ONLY = false;

function toggleFavorite(id) {
  if (FAVORITES.has(id)) FAVORITES.delete(id);
  else FAVORITES.add(id);
  saveFavorites(FAVORITES);
  updateFavCount();
}

function updateFavCount() {
  const el = document.getElementById("fav-count");
  if (el) el.textContent = FAVORITES.size;
}

function renderPartnerOrgs(g) {
  if (!g.needs_partner_org) return "";
  const orgs = Array.isArray(g.partner_orgs) && g.partner_orgs.length ? g.partner_orgs : null;
  const isMunicipalityConsortium = orgs && orgs.every((o) => o.type === "municipality");
  const noteTitle = isMunicipalityConsortium
    ? "Умови гранту вимагають консорціуму — готові кандидати-муніципалітети для партнерства:"
    : g.is_oms_eligible
    ? "Умови гранту вимагають партнера — готові кандидати для консорціуму:"
    : "ОМС не є прямим заявником — готові кандидати на партнера для подання:";

  if (!orgs) {
    const warnText = g.is_oms_eligible
      ? "Умови гранту вимагають партнера (напр. закордонного муніципалітету для консорціуму) — конкретного кандидата ще не підібрано, зверніться до відділу економічного розвитку громади."
      : "ОМС не є прямим заявником — потрібна ГО/БФ-партнер для подання. Конкретну організацію-партнера ще не підібрано, зверніться до відділу економічного розвитку громади.";
    return `<div class="partner-note partner-note-warn">${warnText}</div>`;
  }

  const cards = orgs
    .map(
      (o) => `
        <li class="partner-org">
          <div class="partner-org-name">${o.name}</div>
          ${o.type === "municipality" ? `<div class="partner-org-type">Муніципалітет-партнер (консорціум)</div>` : ""}
          ${o.rationale ? `<div class="partner-org-rationale">${o.rationale}</div>` : ""}
          <div class="partner-org-contacts">
            ${o.url ? `<a href="${o.url}" target="_blank" rel="noopener">${o.url.replace(/^https?:\/\//, "")}</a>` : ""}
            ${o.contact ? `<span class="partner-org-contact">${o.contact}</span>` : ""}
          </div>
        </li>`
    )
    .join("");

  return `
    <div class="partner-note">
      <div class="partner-note-title">${noteTitle}</div>
      <ul class="partner-org-list">${cards}</ul>
    </div>
  `;
}

function renderProjectFit(g) {
  if (!g.community_project_fit) return "";
  const matches = Array.isArray(g.epp_project_matches) ? g.epp_project_matches : [];
  const badges = matches
    .map(
      (m) => `
        <div class="epp-match">
          <span class="epp-match-label">Проєкт ЄПП</span>
          <span class="epp-match-name">${m.title}</span>
          ${m.cost_uah ? `<span class="epp-match-cost">${m.cost_uah.toLocaleString("uk-UA")} грн</span>` : ""}
        </div>
      `
    )
    .join("");
  return `
    <div class="project-fit">
      <div class="project-fit-title">Відповідність проєктам громади</div>
      ${badges}
      <p>${g.community_project_fit}</p>
    </div>
  `;
}

function renderCard(g) {
  const sector = sectorLabel(g.sector);
  const id = favId(g);
  const isFav = FAVORITES.has(id);

  const tags = [`<span class="tag">${sector}</span>`];
  if (g.is_oms_eligible) tags.push(`<span class="tag tag-accent">ОМС прийнятний</span>`);
  if (g.needs_partner_org) tags.push(`<span class="tag tag-solid">Потрібен партнер</span>`);

  const programRow = g.program_name
    ? `<li><span class="k">Програма/донор</span><span class="v">${g.program_name}</span></li>`
    : "";

  const partnerNote = renderPartnerOrgs(g);
  const projectFit = renderProjectFit(g);
  const methodology = renderMethodology(g);

  return `
    <article class="card" data-sector="${g.sector || ""}" data-status="${g.status || ""}" data-oms="${g.is_oms_eligible ? "yes" : ""}" data-partner="${g.needs_partner_org ? "partner" : ""}" data-fav-id="${id}">
      <div class="card-top">
        <div class="card-tags">${tags.join("")}</div>
        <button type="button" class="fav-btn${isFav ? " is-active" : ""}" data-fav-toggle="${id}" aria-pressed="${isFav}" aria-label="Додати в обране" title="Додати в обране">★</button>
      </div>
      <h3>${g.title || "Без назви"}</h3>
      <p class="desc">${g.description || ""}</p>
      <ul class="meta">
        <li><span class="k">Дедлайн</span><span class="v">${fmtDate(g.deadline)}</span></li>
        <li><span class="k">Бюджет</span><span class="v">${fmtAmount(g.amount_min, g.amount_max, g.currency)}</span></li>
        <li><span class="k">Заявник</span><span class="v">${g.applicant_type_raw || (g.is_oms_eligible ? "ОМС прийнятний" : "Уточнюється")}</span></li>
        <li><span class="k">Локація</span><span class="v">${g.location_raw || "—"}</span></li>
        ${programRow}
        <li><span class="k">Джерело</span><span class="v">${sourceLabel(g.source)}</span></li>
        <li><span class="k">Ймовірність успіху</span><span class="v ${probClass(g.success_probability)}">${g.success_probability != null ? Math.round(g.success_probability * 100) + "%" : "—"}</span></li>
      </ul>
      ${projectFit}
      ${partnerNote}
      ${methodology}
      <a class="btn-source" href="${g.url}" target="_blank" rel="noopener">Перейти до джерела та подати заявку →</a>
    </article>
  `;
}

const CHECKLIST_PHASE_ORDER = ["📋 ПІДГОТОВКА", "🔬 АНАЛІЗ", "✍️ НАПИСАННЯ", "💰 БЮДЖЕТ", "✅ ФІНАЛІЗАЦІЯ"];

function renderChecklist(checklist) {
  if (!checklist || !checklist.length) return "";
  const byPhase = {};
  checklist.forEach((step) => {
    (byPhase[step.phase] = byPhase[step.phase] || []).push(step);
  });
  const phases = [...new Set([...CHECKLIST_PHASE_ORDER, ...Object.keys(byPhase)])].filter((p) => byPhase[p]);
  return phases
    .map(
      (phase) => `
        <div class="checklist-phase">
          <div class="checklist-phase-title">${phase}</div>
          <ol class="checklist-steps">
            ${byPhase[phase]
              .map((s) => `<li><span class="step-text">${s.text}</span><span class="step-detail">${s.detail || ""}</span></li>`)
              .join("")}
          </ol>
        </div>`
    )
    .join("");
}

function renderMethodology(g) {
  const hasReframing = g.reframing_bad && g.reframing_good;
  const hasTips = g.application_tips && g.application_tips.length;
  const hasChecklist = g.checklist && g.checklist.length;
  if (!hasReframing && !hasTips && !hasChecklist) return "";

  const reframingBlock = hasReframing
    ? `<div class="reframe-box">
        <div class="reframe-row reframe-bad"><span class="k">НЕ</span><span class="v">${g.reframing_bad}</span></div>
        <div class="reframe-row reframe-good"><span class="k">А</span><span class="v">${g.reframing_good}</span></div>
        ${
          g.reframing_soft_components && g.reframing_soft_components.length
            ? `<ul class="soft-components">${g.reframing_soft_components.map((s) => `<li>${s}</li>`).join("")}</ul>`
            : ""
        }
      </div>`
    : "";

  const tipsBlock = hasTips
    ? `<ul class="tips-list">${g.application_tips.map((t) => `<li>${t}</li>`).join("")}</ul>`
    : "";

  const checklistBlock = hasChecklist
    ? `<div class="checklist">${renderChecklist(g.checklist)}</div>`
    : "";

  return `
    <details class="methodology">
      <summary>Методологія заявки</summary>
      <div class="methodology-body">
        ${reframingBlock}
        ${tipsBlock}
        ${checklistBlock}
      </div>
    </details>
  `;
}

function applyFilters() {
  const sector = document.getElementById("f-sector").value;
  const oms = document.getElementById("f-oms").value;
  const source = document.getElementById("f-source").value;

  const filtered = ALL_GRANTS.filter((g) => {
    if (sector && g.sector !== sector) return false;
    if (oms === "yes" && !g.is_oms_eligible) return false;
    if (oms === "partner" && !g.needs_partner_org) return false;
    if (source && g.source !== source) return false;
    if (SHOW_FAVORITES_ONLY && !FAVORITES.has(favId(g))) return false;
    return true;
  });

  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  grid.innerHTML = filtered.map(renderCard).join("");
  empty.hidden = filtered.length > 0;
  empty.textContent = SHOW_FAVORITES_ONLY
    ? "Ви ще не додали жодного гранту в обране."
    : "Записів за цим фільтром не знайдено.";

  grid.querySelectorAll("[data-fav-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      toggleFavorite(btn.getAttribute("data-fav-toggle"));
      applyFilters();
    });
  });

  setupClampToggles(grid);
}

function setupClampToggles(grid) {
  grid.querySelectorAll(".card .desc, .project-fit p, .partner-org-rationale").forEach((el) => {
    if (el.scrollHeight - el.clientHeight <= 2) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "clamp-toggle";
    btn.textContent = "Показати повністю";
    btn.addEventListener("click", () => {
      const expanded = el.classList.toggle("is-expanded");
      btn.textContent = expanded ? "Згорнути" : "Показати повністю";
    });
    el.insertAdjacentElement("afterend", btn);
  });
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

function populateSourceFilter(grants) {
  const select = document.getElementById("f-source");
  const sources = [...new Set(grants.map((g) => g.source).filter(Boolean))];
  sources.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = sourceLabel(s);
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
    populateSourceFilter(ALL_GRANTS);
    updateFavCount();
    applyFilters();

    ["f-sector", "f-oms", "f-source"].forEach((id) =>
      document.getElementById(id).addEventListener("change", applyFilters)
    );

    const favBtn = document.getElementById("f-favorites");
    favBtn.addEventListener("click", () => {
      SHOW_FAVORITES_ONLY = !SHOW_FAVORITES_ONLY;
      favBtn.classList.toggle("is-active", SHOW_FAVORITES_ONLY);
      favBtn.setAttribute("aria-pressed", String(SHOW_FAVORITES_ONLY));
      applyFilters();
    });
  } catch (err) {
    document.getElementById("grid").innerHTML = "";
    document.getElementById("empty").hidden = false;
    document.getElementById("empty").textContent = "Не вдалося завантажити дані. Спробуйте пізніше.";
    document.getElementById("cli-status").textContent = "помилка завантаження";
    console.error(err);
  }
}

init();
