#!/usr/bin/env python3
"""
Adhesive Industry Crisis Dashboard
===================================
Мониторинг цен на сырьё и оценка риска кризиса в отрасли производства клеёв.
Данные обновляются автоматически каждые 24 часа через APScheduler.

Запуск:  python adhesive_dashboard.py
Адрес:   http://localhost:8001
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template_string

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "adhesive_cache.json"
REFRESH_HOURS = 24
PORT = 8001

# ═══════════════════════════════════════════════════════════════════════════
# DATA DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

# Ключевое сырьё для производства клеёв с весовыми коэффициентами в кризис-индексе
COMMODITIES: Dict[str, Dict] = {
    "crude_oil": dict(
        ticker="CL=F",
        name="Нефть WTI",
        desc="Базовое нефтехимическое сырьё: этилен, пропилен, стирол → ПВА, EVA, SBS-клеи",
        unit="$/барр.",
        weight=0.25,
        cat="Нефтехимия",
        color="#f97316",
    ),
    "natural_gas": dict(
        ticker="NG=F",
        name="Природный газ",
        desc="Энергетика + метанол → формальдегид → карбамидные и фенол-формальдегидные смолы",
        unit="$/MMBtu",
        weight=0.10,
        cat="Нефтехимия",
        color="#60a5fa",
    ),
    "gasoline": dict(
        ticker="RB=F",
        name="Бензин RBOB",
        desc="Прокси-индикатор стоимости растворителей: толуол, ксилол, ацетон, этилацетат",
        unit="$/гал.",
        weight=0.08,
        cat="Нефтехимия",
        color="#a78bfa",
    ),
    "corn": dict(
        ticker="ZC=F",
        name="Кукуруза",
        desc="Крахмал и декстрин — основа клеёв для гофрокартона, бумаги и упаковки",
        unit="¢/бушель",
        weight=0.07,
        cat="Биосырьё",
        color="#84cc16",
    ),
    "lyondell": dict(
        ticker="LYB",
        name="LyondellBasell",
        desc="Мировой лидер по полиэтилену и ПВА-мономерам — ключевой поставщик для клеевой отрасли",
        unit="$",
        weight=0.13,
        cat="Химия",
        color="#22d3ee",
    ),
    "eastman": dict(
        ticker="EMN",
        name="Eastman Chemical",
        desc="Виниловый ацетат (VAM) и акрилаты — мономеры для ПВА и акриловых клеёв",
        unit="$",
        weight=0.12,
        cat="Химия",
        color="#f472b6",
    ),
    "dow": dict(
        ticker="DOW",
        name="Dow Inc.",
        desc="Полиуретановые, эпоксидные и силиконовые системы — конструкционные и монтажные клеи",
        unit="$",
        weight=0.10,
        cat="Химия",
        color="#34d399",
    ),
    "hb_fuller": dict(
        ticker="FUL",
        name="H.B. Fuller",
        desc="Крупнейший в мире специализированный производитель клеёв — барометр отрасли",
        unit="$",
        weight=0.15,
        cat="Отрасль",
        color="#fb923c",
    ),
}

FOREX: Dict[str, Dict] = {
    "usd_rub": dict(
        ticker="USDRUB=X",
        name="USD / RUB",
        desc="Большинство сырья торгуется в USD; ослабление рубля напрямую поднимает себестоимость",
    ),
    "eur_usd": dict(
        ticker="EURUSD=X",
        name="EUR / USD",
        desc="Европейские поставщики химии (BASF, Evonik, Arkema) выставляют счета в EUR",
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════════


def _fetch(ticker: str, period: str = "1y") -> Optional[Dict]:
    """Загружает историю цен через yfinance и возвращает ключевые метрики."""
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty:
            return None
        c = hist["Close"].dropna()
        if len(c) < 5:
            return None

        cur = float(c.iloc[-1])
        prev = float(c.iloc[-2])
        a30 = float(c.iloc[-30:].mean()) if len(c) >= 30 else float(c.mean())
        a90 = float(c.iloc[-90:].mean()) if len(c) >= 90 else float(c.mean())
        a1y = float(c.mean())
        lo = float(c.min())
        hi = float(c.max())

        tail = c.iloc[-90:]
        history = [
            {"d": str(i.date()), "p": round(float(v), 4)}
            for i, v in zip(tail.index, tail.values)
        ]

        pct1y = round((cur - lo) / (hi - lo) * 100, 1) if hi != lo else 50.0
        return dict(
            cur=round(cur, 4),
            prev=round(prev, 4),
            ch1d=round((cur - prev) / prev * 100, 2),
            a30=round(a30, 4),
            a90=round(a90, 4),
            a1y=round(a1y, 4),
            ch30=round((cur - a30) / a30 * 100, 2),
            ch1y=round((cur - a1y) / a1y * 100, 2),
            lo=round(lo, 4),
            hi=round(hi, 4),
            pct1y=pct1y,
            history=history,
        )
    except Exception as exc:
        log.warning("fetch %s: %s", ticker, exc)
        return None


def fetch_all() -> Dict[str, Any]:
    """Загружает все рыночные данные, вычисляет кризис-индекс и сохраняет кэш."""
    log.info("Fetching market data …")
    comms: Dict[str, Any] = {}
    for k, m in COMMODITIES.items():
        d = _fetch(m["ticker"])
        if d:
            comms[k] = {**m, **d}
            log.info("  %-16s  %s %s  (ch1y %+.1f%%)", k, d["cur"], m["unit"], d["ch1y"])
        else:
            log.warning("  %-16s  NO DATA", k)

    forex: Dict[str, Any] = {}
    for k, m in FOREX.items():
        d = _fetch(m["ticker"])
        if d:
            forex[k] = {**m, **d}

    result: Dict[str, Any] = dict(
        last_updated=datetime.now().strftime("%d.%m.%Y %H:%M"),
        commodities=comms,
        forex=forex,
    )
    result["crisis"] = _compute_crisis(result)
    save_cache(result)
    log.info("Done. Crisis score = %.1f (%s)", result["crisis"]["score"], result["crisis"]["level"])
    return result


# ═══════════════════════════════════════════════════════════════════════════
# CRISIS SCORE
# ═══════════════════════════════════════════════════════════════════════════


def _compute_crisis(data: Dict) -> Dict:
    """
    Составной кризис-индекс 0–100.

    Стресс компонента = 50% × (позиция в 52-нед. диапазоне)
                      + 50% × (превышение годовой средней, макс. +50% → 100 баллов)

    Поправка на валюту: ослабление рубля к USD > 0% добавляет до +15 баллов.
    """
    comms = data.get("commodities", {})
    forex = data.get("forex", {})

    weighted, total_w = 0.0, 0.0
    comps: List[Dict] = []

    for k, m in COMMODITIES.items():
        if k not in comms:
            continue
        d = comms[k]
        w = m["weight"]

        pct = d.get("pct1y", 50)
        elev = min(max(d.get("ch1y", 0), 0), 50) * 2  # 0–100
        stress = min(pct * 0.5 + elev * 0.5, 100)

        weighted += stress * w
        total_w += w

        lev = "low" if stress < 33 else ("medium" if stress < 66 else "high")
        comps.append(
            dict(
                k=k,
                name=m["name"],
                score=round(stress, 1),
                level=lev,
                pct1y=pct,
                ch1y=d.get("ch1y", 0),
                cur=d.get("cur"),
                unit=m["unit"],
            )
        )

    base = (weighted / total_w) if total_w > 0 else 50.0

    # Forex uplift: ослабление рубля усиливает шок импортных цен
    fx_adj = 0.0
    if "usd_rub" in forex:
        fx_adj = min(max(forex["usd_rub"].get("ch1y", 0), 0), 30) * 0.5
    score = round(min(base + fx_adj, 100), 1)

    if score < 30:
        level, level_ru, color = "low", "НИЗКИЙ", "#22c55e"
        interpretation = (
            "Рынок сырья стабилен. Значительного давления на себестоимость клеёв не ожидается."
        )
    elif score < 60:
        level, level_ru, color = "medium", "СРЕДНИЙ", "#f59e0b"
        interpretation = (
            "Умеренное ценовое давление на рынке сырья. "
            "Возможен рост цен на клеи в горизонте 1–3 месяцев."
        )
    else:
        level, level_ru, color = "high", "ВЫСОКИЙ", "#ef4444"
        interpretation = (
            "Острый ценовой шок сырья. "
            "Высокая вероятность существенного роста себестоимости и цен на клеи."
        )

    return dict(
        score=score,
        level=level,
        level_ru=level_ru,
        color=color,
        interpretation=interpretation,
        components=comps,
        fx_adj=round(fx_adj, 1),
    )


# ═══════════════════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════════════════


def load_cache() -> Optional[Dict]:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        ts = datetime.strptime(data["last_updated"], "%d.%m.%Y %H:%M")
        if datetime.now() - ts < timedelta(hours=REFRESH_HOURS):
            log.info("Cache hit (%s)", data["last_updated"])
            return data
        log.info("Cache expired, will refresh.")
    except Exception as exc:
        log.warning("Cache read error: %s", exc)
    return None


def save_cache(data: Dict) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("Cache write error: %s", exc)


def get_data() -> Dict:
    return load_cache() or fetch_all()


# ═══════════════════════════════════════════════════════════════════════════
# FLASK APP
# ═══════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
_sched_started = False


def _start_scheduler() -> None:
    global _sched_started
    if _sched_started:
        return
    _sched_started = True
    s = BackgroundScheduler(daemon=True)
    s.add_job(fetch_all, "interval", hours=REFRESH_HOURS, id="adhesive_refresh")
    s.start()
    log.info("Scheduler started — refresh every %d h.", REFRESH_HOURS)


# ═══════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Кризис в отрасли клеёв — Дашборд</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f172a;--card:#1e293b;--card2:#162032;--border:#334155;
  --text:#f1f5f9;--muted:#94a3b8;--accent:#3b82f6;
  --green:#22c55e;--yellow:#f59e0b;--red:#ef4444;
}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}

/* ── Header ── */
header{
  background:linear-gradient(135deg,#0f172a 0%,#1a2744 100%);
  border-bottom:1px solid var(--border);
  padding:1rem 2rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem
}
header h1{font-size:1.2rem;font-weight:800;display:flex;align-items:center;gap:.5rem}
header h1 .accent{color:var(--accent)}
.hdr-meta{display:flex;flex-direction:column;align-items:flex-end;gap:.2rem}
.updated{color:var(--muted);font-size:.78rem}
.refresh-link{color:var(--accent);font-size:.78rem;text-decoration:none;opacity:.7}
.refresh-link:hover{opacity:1}

/* ── Layout ── */
main{max-width:1440px;margin:0 auto;padding:2rem;display:flex;flex-direction:column;gap:2rem}

/* ── Hero / gauge ── */
.hero{
  display:grid;grid-template-columns:260px 1fr;gap:2rem;
  background:var(--card);border:1px solid var(--border);border-radius:16px;padding:2rem;align-items:center
}
.gauge-wrap{display:flex;flex-direction:column;align-items:center;gap:.5rem}
canvas#gauge{width:220px!important;height:130px!important}
.gauge-labels{display:flex;justify-content:space-between;width:220px;font-size:.68rem;color:var(--muted)}
.hero-right h2{font-size:1.4rem;font-weight:800;margin-bottom:.5rem}
.hero-right p.interp{color:var(--muted);line-height:1.65;margin-bottom:1.25rem}
.score-badge{
  display:inline-flex;align-items:center;gap:.6rem;
  padding:.45rem 1.1rem;border-radius:999px;font-weight:800;font-size:1.05rem;
  margin-bottom:1rem;letter-spacing:.02em
}
.hero-stats{display:flex;gap:2rem;flex-wrap:wrap}
.stat-box{display:flex;flex-direction:column;gap:.2rem}
.stat-label{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.stat-val{font-size:1.15rem;font-weight:700}

/* ── Section title ── */
.sec-title{
  font-size:.85rem;font-weight:700;color:var(--muted);
  text-transform:uppercase;letter-spacing:.06em;
  margin-bottom:1rem;padding-bottom:.5rem;border-bottom:1px solid var(--border)
}

/* ── Cards grid ── */
.cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem}
.card{
  background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:1.25rem;position:relative;overflow:hidden;
  transition:border-color .2s,transform .15s
}
.card:hover{border-color:var(--accent);transform:translateY(-2px)}
.card-cat{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:.2rem}
.card-name{font-size:.98rem;font-weight:700;margin-bottom:.2rem}
.card-desc{font-size:.76rem;color:var(--muted);line-height:1.45;margin-bottom:.9rem}
.card-price{font-size:1.55rem;font-weight:800;line-height:1;margin-bottom:.6rem}
.card-price .unit{font-size:.75rem;color:var(--muted);font-weight:400;margin-left:.2rem}
.badges{display:flex;flex-wrap:wrap;gap:.35rem;margin-bottom:.75rem}
.badge{padding:.18rem .55rem;border-radius:6px;font-size:.73rem;font-weight:600}
.up{background:rgba(239,68,68,.13);color:#ef4444}
.dn{background:rgba(34,197,94,.13);color:#22c55e}
.neu{background:rgba(148,163,184,.12);color:#94a3b8}
.pct-bar{height:4px;background:var(--border);border-radius:2px}
.pct-fill{height:100%;border-radius:2px;background:linear-gradient(to right,#22c55e,#f59e0b,#ef4444)}
.pct-lbl{font-size:.68rem;color:var(--muted);margin-top:.25rem}
.risk-dot{position:absolute;top:1rem;right:1rem;width:10px;height:10px;border-radius:50%}
.risk-dot.low{background:#22c55e}
.risk-dot.medium{background:#f59e0b}
.risk-dot.high{background:#ef4444;box-shadow:0 0 8px #ef444488}

/* ── Chart section ── */
.chart-section{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.5rem}
.chart-selector{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1.25rem}
.chart-btn{
  padding:.32rem .75rem;border:1px solid var(--border);border-radius:8px;
  background:transparent;color:var(--muted);font-size:.8rem;cursor:pointer;transition:all .15s
}
.chart-btn:hover{border-color:var(--accent);color:var(--text)}
.chart-btn.active{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700}
canvas#mainChart{width:100%!important;max-height:300px}

/* ── Forex ── */
.forex-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem}

/* ── Risk table ── */
.tbl-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.risk-table{width:100%;border-collapse:collapse}
.risk-table th{
  text-align:left;padding:.6rem 1rem;font-size:.76rem;
  color:var(--muted);text-transform:uppercase;letter-spacing:.04em;
  border-bottom:1px solid var(--border);white-space:nowrap
}
.risk-table td{padding:.65rem 1rem;border-bottom:1px solid rgba(51,65,85,.45);font-size:.88rem;vertical-align:middle}
.risk-table tr:last-child td{border-bottom:none}
.risk-table tr:hover td{background:rgba(255,255,255,.02)}
.risk-pill{
  display:inline-block;padding:.18rem .55rem;border-radius:6px;
  font-size:.72rem;font-weight:700;text-transform:uppercase
}
.risk-pill.low{background:rgba(34,197,94,.13);color:#22c55e}
.risk-pill.medium{background:rgba(245,158,11,.13);color:#f59e0b}
.risk-pill.high{background:rgba(239,68,68,.13);color:#ef4444}
.sbar{height:6px;background:var(--border);border-radius:3px;min-width:100px}
.sfill{height:100%;border-radius:3px}

/* ── Method ── */
.method{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.5rem}
.method h3{margin-bottom:.75rem;font-size:1rem}
.method p,.method li{font-size:.82rem;color:var(--muted);line-height:1.65}
.method ul{padding-left:1.2rem;display:flex;flex-direction:column;gap:.3rem}

/* ── Footer ── */
footer{text-align:center;padding:1.5rem;font-size:.76rem;color:var(--muted);border-top:1px solid var(--border)}

/* ── Responsive ── */
@media(max-width:740px){
  .hero{grid-template-columns:1fr}
  main{padding:1rem}
  .gauge-wrap{display:none}
}
</style>
</head>
<body>

<header>
  <h1>📊 Дашборд <span class="accent">кризиса в отрасли клеёв</span></h1>
  <div class="hdr-meta">
    <span class="updated">Обновлено: {{ last_updated }}</span>
    <a class="refresh-link" href="/refresh-now">↻ Обновить сейчас</a>
  </div>
</header>

<main>

<!-- ── Hero ── -->
<section>
  <div class="hero">
    <div class="gauge-wrap">
      <canvas id="gauge"></canvas>
      <div class="gauge-labels"><span>0</span><span>50</span><span>100</span></div>
      <div style="font-size:.78rem;color:var(--muted);margin-top:.25rem">Индекс риска кризиса</div>
    </div>
    <div class="hero-right">
      <div class="score-badge" id="scoreBadge">
        <span id="scoreVal">…</span>
        <span id="scoreLevel">…</span>
      </div>
      <h2>Риск кризиса в производстве клеёв</h2>
      <p class="interp" id="interp">Загрузка…</p>
      <div class="hero-stats">
        <div class="stat-box">
          <span class="stat-label">Компонентов</span>
          <span class="stat-val" id="compCount">–</span>
        </div>
        <div class="stat-box">
          <span class="stat-label">Поправка на курс</span>
          <span class="stat-val" id="fxAdj">–</span>
        </div>
        <div class="stat-box">
          <span class="stat-label">USD/RUB</span>
          <span class="stat-val" id="usdRub">–</span>
        </div>
        <div class="stat-box">
          <span class="stat-label">EUR/USD</span>
          <span class="stat-val" id="eurUsd">–</span>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ── Commodity cards ── -->
<section>
  <div class="sec-title">Цены на сырьё и отраслевые индикаторы</div>
  <div class="cards-grid" id="cardsGrid"></div>
</section>

<!-- ── Main chart ── -->
<section class="chart-section">
  <div class="sec-title">История цены (последние 90 дней)</div>
  <div class="chart-selector" id="chartSelector"></div>
  <canvas id="mainChart"></canvas>
</section>

<!-- ── Forex ── -->
<section>
  <div class="sec-title">Валютные курсы</div>
  <div class="forex-grid" id="forexGrid"></div>
</section>

<!-- ── Risk breakdown table ── -->
<section>
  <div class="sec-title">Разбивка риска по компонентам</div>
  <div class="tbl-wrap">
    <table class="risk-table">
      <thead>
        <tr>
          <th>Компонент</th>
          <th>Текущая цена</th>
          <th>Δ к ср. за год</th>
          <th>Позиция в 52-нед. диапазоне</th>
          <th>Стресс-балл</th>
          <th>Риск</th>
        </tr>
      </thead>
      <tbody id="riskTbody"></tbody>
    </table>
  </div>
</section>

<!-- ── Methodology ── -->
<section class="method">
  <h3>Методология расчёта индекса</h3>
  <p style="margin-bottom:.6rem">
    Индекс риска кризиса (0–100) рассчитывается как взвешенная сумма стресс-баллов
    ключевых факторов стоимости сырья для клеёв:
  </p>
  <ul>
    <li><strong>H.B. Fuller (15%)</strong> — крупнейший спецпроизводитель клеёв: акции отражают маржу и отраслевой спрос.</li>
    <li><strong>Нефть WTI (25%)</strong> — нефтехимическое сырьё: этилен → ПВА, EVA; стирол → SBS-клеи; пропилен → полиуретаны.</li>
    <li><strong>LyondellBasell (13%)</strong> — мировой лидер по этилену и ПВА-мономерам.</li>
    <li><strong>Eastman Chemical (12%)</strong> — ключевой поставщик VAM (виниловый ацетат) и акрилатов.</li>
    <li><strong>Природный газ (10%)</strong> — энергозатраты + метанол → формальдегид → карбамидные смолы.</li>
    <li><strong>Dow Inc. (10%)</strong> — полиуретаны, эпоксиды, силиконы для конструкционных клеёв.</li>
    <li><strong>Бензин RBOB (8%)</strong> — прокси цен на растворители: толуол, ксилол, ацетон.</li>
    <li><strong>Кукуруза (7%)</strong> — крахмальные и декстриновые клеи для гофрокартона и упаковки.</li>
    <li><strong>Поправка USD/RUB</strong> — ослабление рубля добавляет до +15 баллов (импортное сырьё).</li>
  </ul>
  <p style="margin-top:.75rem">
    <strong>Стресс компонента</strong> = 50% × (позиция в 52-нед. диапазоне) +
    50% × (превышение годовой средней, макс. +50% → 100 баллов).
    Диапазон риска: 0–29 = низкий, 30–59 = средний, 60–100 = высокий.
  </p>
</section>

</main>

<footer>
  Данные предоставлены Yahoo Finance через yfinance · Обновляются каждые 24 ч ·
  Не является инвестиционной рекомендацией
</footer>

<script id="app-data" type="application/json">{{ data_json | safe }}</script>
<script>
{% raw %}
(function () {
  'use strict';

  const DATA = JSON.parse(document.getElementById('app-data').textContent);
  const crisis = DATA.crisis;
  const comms  = DATA.commodities;
  const forex  = DATA.forex;

  // ── Helpers ──────────────────────────────────────────────────────────────
  function fmt(n, d) {
    if (n == null) return '—';
    d = d == null ? 2 : d;
    return Number(n).toLocaleString('ru-RU', {minimumFractionDigits: d, maximumFractionDigits: d});
  }
  function sign(v) { return v > 0 ? '+' : ''; }
  function badgeCls(v) { return v > 0.5 ? 'up' : v < -0.5 ? 'dn' : 'neu'; }

  // ── Gauge ─────────────────────────────────────────────────────────────────
  function drawGauge(score) {
    const canvas = document.getElementById('gauge');
    if (!canvas) return;
    canvas.width  = 220;
    canvas.height = 130;
    const ctx = canvas.getContext('2d');
    const cx = 110, cy = 118, r = 88, lw = 16;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Track
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, 2 * Math.PI);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = lw + 4;
    ctx.stroke();

    // Coloured arc
    const grad = ctx.createLinearGradient(cx - r, cy, cx + r, cy);
    grad.addColorStop(0,   '#22c55e');
    grad.addColorStop(0.5, '#f59e0b');
    grad.addColorStop(1,   '#ef4444');
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, Math.PI + (score / 100) * Math.PI);
    ctx.strokeStyle = grad;
    ctx.lineWidth = lw;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Score text
    ctx.fillStyle = '#f1f5f9';
    ctx.font = 'bold 34px system-ui';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(Math.round(score), cx, cy - 18);

    ctx.fillStyle = '#64748b';
    ctx.font = '11px system-ui';
    ctx.fillText('из 100', cx, cy + 8);
  }

  // ── Populate hero ─────────────────────────────────────────────────────────
  drawGauge(crisis.score);

  const badge = document.getElementById('scoreBadge');
  badge.style.cssText += 'background:' + crisis.color + '20;color:' + crisis.color +
    ';border:1px solid ' + crisis.color + '44';
  document.getElementById('scoreVal').textContent   = Math.round(crisis.score) + ' / 100';
  document.getElementById('scoreLevel').textContent = crisis.level_ru;
  document.getElementById('interp').textContent     = crisis.interpretation;
  document.getElementById('compCount').textContent  = crisis.components.length;
  document.getElementById('fxAdj').textContent      = '+' + crisis.fx_adj.toFixed(1) + ' б.';

  if (forex.usd_rub) document.getElementById('usdRub').textContent = fmt(forex.usd_rub.cur);
  if (forex.eur_usd) document.getElementById('eurUsd').textContent = fmt(forex.eur_usd.cur, 4);

  // ── Commodity cards ───────────────────────────────────────────────────────
  const ORDER = ['crude_oil','natural_gas','gasoline','corn','lyondell','eastman','dow','hb_fuller'];
  const grid = document.getElementById('cardsGrid');

  ORDER.forEach(function (k) {
    var c = comms[k];
    if (!c) return;
    var comp = (crisis.components || []).find(function(x){ return x.k === k; }) || {};
    var lev  = comp.level || 'medium';
    var pct  = c.pct1y != null ? c.pct1y : 50;
    var priceDecimals = c.cur < 5 ? 4 : 2;

    grid.innerHTML += '<div class="card">' +
      '<div class="risk-dot ' + lev + '"></div>' +
      '<div class="card-cat">' + c.cat + '</div>' +
      '<div class="card-name">' + c.name + '</div>' +
      '<div class="card-desc">' + c.desc + '</div>' +
      '<div class="card-price">' + fmt(c.cur, priceDecimals) + '<span class="unit">' + c.unit + '</span></div>' +
      '<div class="badges">' +
        '<span class="badge ' + badgeCls(c.ch1d) + '" title="За день">' + sign(c.ch1d) + fmt(c.ch1d) + '% 1д</span>' +
        '<span class="badge ' + badgeCls(c.ch30) + '" title="Против 30-дн. средней">' + sign(c.ch30) + fmt(c.ch30) + '% 30д</span>' +
        '<span class="badge ' + badgeCls(c.ch1y) + '" title="Против годовой средней">' + sign(c.ch1y) + fmt(c.ch1y) + '% 1г</span>' +
      '</div>' +
      '<div class="pct-bar"><div class="pct-fill" style="width:' + pct + '%"></div></div>' +
      '<div class="pct-lbl">Позиция в 52-нед. диапазоне: ' + fmt(pct, 0) + '% (0% = мин, 100% = макс)</div>' +
    '</div>';
  });

  // ── Main chart ────────────────────────────────────────────────────────────
  var mainChart = null;

  function buildChart(key) {
    var c = comms[key];
    if (!c || !c.history || c.history.length === 0) return;

    var labels = c.history.map(function(x){ return x.d; });
    var vals   = c.history.map(function(x){ return x.p; });
    var color  = c.color || '#3b82f6';

    if (mainChart) mainChart.destroy();

    var ctx2 = document.getElementById('mainChart').getContext('2d');
    mainChart = new Chart(ctx2, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: c.name + ' (' + c.unit + ')',
          data: vals,
          borderColor: color,
          backgroundColor: color + '18',
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 4,
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: '#94a3b8', font: { size: 12 } } },
          tooltip: {
            backgroundColor: '#1e293b', borderColor: '#334155', borderWidth: 1,
            titleColor: '#f1f5f9', bodyColor: '#94a3b8'
          }
        },
        scales: {
          x: {
            ticks: { color: '#64748b', maxTicksLimit: 10, font: { size: 11 } },
            grid: { color: '#1a2744' }
          },
          y: {
            ticks: { color: '#64748b', font: { size: 11 } },
            grid: { color: '#1a2744' }
          }
        }
      }
    });
  }

  // Chart selector buttons
  var sel = document.getElementById('chartSelector');
  ORDER.forEach(function (k, i) {
    var c = comms[k];
    if (!c) return;
    var btn = document.createElement('button');
    btn.className = 'chart-btn' + (i === 0 ? ' active' : '');
    btn.textContent = c.name;
    btn.dataset.key = k;
    btn.addEventListener('click', function () {
      document.querySelectorAll('.chart-btn').forEach(function(b){ b.classList.remove('active'); });
      btn.classList.add('active');
      buildChart(k);
    });
    sel.appendChild(btn);
  });
  buildChart('crude_oil');

  // ── Forex cards ───────────────────────────────────────────────────────────
  var fxGrid = document.getElementById('forexGrid');
  Object.entries(forex).forEach(function(entry) {
    var k = entry[0], f = entry[1];
    if (!f) return;
    var pct = f.pct1y != null ? f.pct1y : 50;
    fxGrid.innerHTML += '<div class="card">' +
      '<div class="card-cat">Валюта</div>' +
      '<div class="card-name">' + f.name + '</div>' +
      '<div class="card-desc">' + f.desc + '</div>' +
      '<div class="card-price">' + fmt(f.cur, 4) + '</div>' +
      '<div class="badges">' +
        '<span class="badge ' + badgeCls(f.ch1d) + '">' + sign(f.ch1d) + fmt(f.ch1d) + '% 1д</span>' +
        '<span class="badge ' + badgeCls(f.ch1y) + '">' + sign(f.ch1y) + fmt(f.ch1y) + '% 1г</span>' +
      '</div>' +
      '<div class="pct-bar"><div class="pct-fill" style="width:' + pct + '%"></div></div>' +
      '<div class="pct-lbl">52-нед. диапазон: ' + fmt(f.lo, 4) + ' – ' + fmt(f.hi, 4) + '</div>' +
    '</div>';
  });

  // ── Risk breakdown table ──────────────────────────────────────────────────
  var tbody = document.getElementById('riskTbody');
  var sorted = (crisis.components || []).slice().sort(function(a, b){ return b.score - a.score; });
  sorted.forEach(function(comp) {
    var c = comms[comp.k] || {};
    var sc = comp.level === 'low' ? '#22c55e' : comp.level === 'medium' ? '#f59e0b' : '#ef4444';
    var lvlRu = comp.level === 'low' ? 'Низкий' : comp.level === 'medium' ? 'Средний' : 'Высокий';
    var priceDecimals = comp.cur < 5 ? 4 : 2;
    tbody.innerHTML += '<tr>' +
      '<td><strong>' + comp.name + '</strong><br>' +
        '<span style="font-size:.73rem;color:var(--muted)">' + (c.cat || '') + ' · ' + (c.ticker || '') + '</span></td>' +
      '<td>' + fmt(comp.cur, priceDecimals) + ' ' + comp.unit + '</td>' +
      '<td><span class="badge ' + badgeCls(comp.ch1y) + '">' + sign(comp.ch1y) + fmt(comp.ch1y) + '%</span></td>' +
      '<td><div style="display:flex;align-items:center;gap:.5rem">' +
        '<div class="sbar"><div class="sfill" style="width:' + comp.pct1y + '%;background:linear-gradient(to right,#22c55e,#f59e0b,#ef4444)"></div></div>' +
        '<span style="font-size:.78rem;color:var(--muted)">' + fmt(comp.pct1y, 0) + '%</span>' +
      '</div></td>' +
      '<td><div style="display:flex;align-items:center;gap:.5rem">' +
        '<div class="sbar"><div class="sfill" style="width:' + comp.score + '%;background:' + sc + '"></div></div>' +
        '<span style="font-size:.8rem;font-weight:700;color:' + sc + '">' + fmt(comp.score, 0) + '</span>' +
      '</div></td>' +
      '<td><span class="risk-pill ' + comp.level + '">' + lvlRu + '</span></td>' +
    '</tr>';
  });

})();
{% endraw %}
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════


@app.route("/")
def index():
    data = get_data()
    data_json = json.dumps(data, ensure_ascii=False)
    last_updated = data.get("last_updated", "—")
    return render_template_string(TEMPLATE, data_json=data_json, last_updated=last_updated)


@app.route("/refresh-now")
def refresh_now():
    """Принудительное обновление данных (удобно для отладки)."""
    data = fetch_all()
    return (
        f'<meta http-equiv="refresh" content="1; url=/">'
        f"Обновлено! Кризис-индекс = {data['crisis']['score']}. "
        f"<a href='/'>← Назад</a>"
    )


@app.route("/api/data")
def api_data():
    """Отдаёт свежий кэш в JSON для внешних потребителей."""
    from flask import jsonify
    return jsonify(get_data())


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    # Pre-warm the cache so first request is instant
    log.info("Pre-warming cache …")
    get_data()
    _start_scheduler()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
