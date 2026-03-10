/**
 * ДАШБОРД: КРИЗИС В ОТРАСЛИ КЛЕЁВ — Google Apps Script
 * ========================================================
 * Установка (один раз):
 *   1. Google Таблицы → Расширения → Apps Script
 *   2. Вставьте этот код и сохраните (Ctrl+S)
 *   3. Запустите функцию  createDashboard()
 *   4. Разрешите доступ (внешние запросы + таблицы)
 *   5. Готово — обновление происходит автоматически каждый день в 08:00
 *
 * Ручное обновление:  refreshData()
 * Удалить триггер:    removeTrigger()
 */

// ═══════════════════════════════════════════════════════════════════════════
// КОНФИГУРАЦИЯ
// ═══════════════════════════════════════════════════════════════════════════

const SHEET_DASH    = '📊 Дашборд';
const SHEET_DATA    = '📈 Данные';
const SHEET_HISTORY = '📜 История';

/** Инструменты: сырьё + ключевые химические компании */
const INSTRUMENTS = [
  { key: 'crude_oil',   ticker: 'CL=F',  name: 'Нефть WTI',        unit: '$/барр.',  weight: 0.25, cat: 'Нефтехимия' },
  { key: 'natural_gas', ticker: 'NG=F',  name: 'Природный газ',    unit: '$/MMBtu',  weight: 0.10, cat: 'Нефтехимия' },
  { key: 'gasoline',    ticker: 'RB=F',  name: 'Бензин RBOB',      unit: '$/гал.',   weight: 0.08, cat: 'Нефтехимия' },
  { key: 'corn',        ticker: 'ZC=F',  name: 'Кукуруза',         unit: '¢/бушель', weight: 0.07, cat: 'Биосырьё'   },
  { key: 'lyondell',    ticker: 'LYB',   name: 'LyondellBasell',   unit: '$',        weight: 0.13, cat: 'Химия'      },
  { key: 'eastman',     ticker: 'EMN',   name: 'Eastman Chemical',  unit: '$',        weight: 0.12, cat: 'Химия'      },
  { key: 'dow',         ticker: 'DOW',   name: 'Dow Inc.',          unit: '$',        weight: 0.10, cat: 'Химия'      },
  { key: 'hb_fuller',   ticker: 'FUL',   name: 'H.B. Fuller',       unit: '$',        weight: 0.15, cat: 'Отрасль'   },
];

/** Валютные пары */
const FOREX_PAIRS = [
  { key: 'usd_rub', ticker: 'USDRUB=X', name: 'USD / RUB',
    desc: 'Ослабление рубля повышает себестоимость импортного сырья' },
  { key: 'eur_usd', ticker: 'EURUSD=X', name: 'EUR / USD',
    desc: 'Влияет на стоимость европейских химикатов (BASF, Evonik, Arkema)' },
];

// Цвета (тёмная тема, как в веб-дашборде)
const C = {
  bg:     '#0f172a',
  card:   '#1e293b',
  card2:  '#162032',
  border: '#334155',
  text:   '#f1f5f9',
  muted:  '#94a3b8',
  accent: '#1e40af',
  green:  '#22c55e',
  yellow: '#f59e0b',
  red:    '#ef4444',
  blue:   '#3b82f6',
};

// ═══════════════════════════════════════════════════════════════════════════
// ТОЧКИ ВХОДА
// ═══════════════════════════════════════════════════════════════════════════

/** Первоначальная настройка — запустить один раз */
function createDashboard() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  _ensureSheets(ss);
  _setupTrigger();
  updateAll_();
  SpreadsheetApp.getUi().alert(
    '✅ Дашборд создан!\n\nОбновление данных: каждый день в 08:00 МСК.\nРучное обновление: Расширения → Apps Script → refreshData()'
  );
}

/** Обновление данных (вызывается триггером и вручную) */
function refreshData() {
  updateAll_();
}

/** Удалить все триггеры этого скрипта */
function removeTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'refreshData')
    .forEach(t => ScriptApp.deleteTrigger(t));
  Logger.log('Триггеры удалены.');
}

// ═══════════════════════════════════════════════════════════════════════════
// ЗАГРУЗКА ДАННЫХ — Yahoo Finance
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Загружает историю цен за 1 год через Yahoo Finance Chart API.
 * Возвращает объект с метриками или null при ошибке.
 */
function _fetchYahoo(ticker) {
  const url = 'https://query1.finance.yahoo.com/v8/finance/chart/'
    + encodeURIComponent(ticker)
    + '?range=1y&interval=1d&events=history';
  try {
    const resp = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: { 'User-Agent': 'Mozilla/5.0' },
    });
    if (resp.getResponseCode() !== 200) {
      Logger.log('HTTP ' + resp.getResponseCode() + ' for ' + ticker);
      return null;
    }
    const json = JSON.parse(resp.getContentText());
    const res  = json.chart && json.chart.result && json.chart.result[0];
    if (!res) return null;

    const raw    = res.indicators.quote[0].close;
    const stamps = res.timestamp;
    const closes = [];
    const dates  = [];
    (raw || []).forEach((c, i) => {
      if (c != null) {
        closes.push(c);
        dates.push(new Date(stamps[i] * 1000));
      }
    });
    if (closes.length < 5) return null;

    const cur  = closes[closes.length - 1];
    const prev = closes[closes.length - 2];
    const a30  = _mean(closes.slice(-30));
    const a90  = _mean(closes.slice(-90));
    const a1y  = _mean(closes);
    const lo   = Math.min.apply(null, closes);
    const hi   = Math.max.apply(null, closes);
    const pct1y = hi !== lo ? (cur - lo) / (hi - lo) * 100 : 50;

    return {
      cur,  prev,
      a30,  a90, a1y,
      lo,   hi,
      pct1y,
      ch1d: (cur - prev) / prev * 100,
      ch30: (cur - a30)  / a30  * 100,
      ch1y: (cur - a1y)  / a1y  * 100,
      closes90: closes.slice(-90),
      dates90:  dates.slice(-90),
    };
  } catch (e) {
    Logger.log('fetch ' + ticker + ': ' + e);
    return null;
  }
}

/**
 * Резервный метод: получить текущую цену через формулу GOOGLEFINANCE.
 * Работает только для акций и валютных пар — не для фьючерсов.
 */
function _fetchViaGoogleFinance(ss, ticker) {
  // Фьючерсы (CL=F, NG=F и т.д.) GOOGLEFINANCE не поддерживает
  if (ticker.includes('=F') || ticker.includes('=X')) return null;
  try {
    const tmp = ss.insertSheet('__tmp_gf__');
    tmp.getRange('A1').setFormula('=GOOGLEFINANCE("' + ticker + '","price")');
    SpreadsheetApp.flush();
    Utilities.sleep(1500);
    const val = tmp.getRange('A1').getValue();
    ss.deleteSheet(tmp);
    return typeof val === 'number' ? val : null;
  } catch (e) {
    Logger.log('GOOGLEFINANCE fallback ' + ticker + ': ' + e);
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// КРИЗИС-ИНДЕКС
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Рассчитывает составной кризис-индекс 0–100.
 *
 * Стресс компонента = 50% × (позиция в 52-нед. диапазоне)
 *                   + 50% × (превышение годовой средней, макс. +50% → 100 б.)
 * Поправка на USD/RUB: ослабление рубля добавляет до +15 баллов.
 */
function _computeCrisis(instrData, forexData) {
  let weighted = 0, totalW = 0;
  const comps = [];

  INSTRUMENTS.forEach(inst => {
    const d = instrData[inst.key];
    if (!d) return;
    const pct  = d.pct1y;
    const elev = Math.min(Math.max(d.ch1y, 0), 50) * 2;
    const stress = Math.min(pct * 0.5 + elev * 0.5, 100);
    weighted += stress * inst.weight;
    totalW   += inst.weight;
    comps.push({
      key: inst.key, name: inst.name, unit: inst.unit,
      weight: inst.weight, cat: inst.cat,
      stress, pct1y: d.pct1y, ch1y: d.ch1y, cur: d.cur,
      level: stress < 33 ? 'low' : stress < 66 ? 'medium' : 'high',
    });
  });

  let base = totalW > 0 ? weighted / totalW : 50;
  let fxAdj = 0;
  if (forexData.usd_rub) {
    fxAdj = Math.min(Math.max(forexData.usd_rub.ch1y, 0), 30) * 0.5;
  }
  const score = Math.min(base + fxAdj, 100);

  let level, color, interp;
  if (score < 30) {
    level = 'НИЗКИЙ';  color = C.green;
    interp = 'Рынок сырья стабилен. Значительного давления на себестоимость клеёв не ожидается.';
  } else if (score < 60) {
    level = 'СРЕДНИЙ'; color = C.yellow;
    interp = 'Умеренное ценовое давление. Возможен рост цен на клеи в горизонте 1–3 месяцев.';
  } else {
    level = 'ВЫСОКИЙ'; color = C.red;
    interp = 'Острый ценовой шок. Высокая вероятность существенного роста себестоимости клеёв.';
  }

  return { score, level, color, interp, comps, fxAdj };
}

// ═══════════════════════════════════════════════════════════════════════════
// ОСНОВНОЙ ЦИКЛ ОБНОВЛЕНИЯ
// ═══════════════════════════════════════════════════════════════════════════

function updateAll_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  Logger.log('=== Обновление данных ' + new Date().toLocaleString('ru-RU') + ' ===');

  const instrData = {};
  INSTRUMENTS.forEach(inst => {
    Logger.log('  Загрузка ' + inst.ticker);
    let d = _fetchYahoo(inst.ticker);
    if (!d) {
      // Резерв: GOOGLEFINANCE (только для акций)
      const cur = _fetchViaGoogleFinance(ss, inst.ticker);
      if (cur) {
        Logger.log('    → резерв GOOGLEFINANCE: ' + cur);
        d = { cur, prev: cur, a30: cur, a90: cur, a1y: cur, lo: cur, hi: cur,
              pct1y: 50, ch1d: 0, ch30: 0, ch1y: 0, closes90: [], dates90: [] };
      } else {
        Logger.log('    → НЕТ ДАННЫХ');
      }
    }
    instrData[inst.key] = d;
  });

  const forexData = {};
  FOREX_PAIRS.forEach(fx => {
    Logger.log('  Загрузка ' + fx.ticker);
    forexData[fx.key] = _fetchYahoo(fx.ticker);
  });

  const crisis = _computeCrisis(instrData, forexData);
  Logger.log('Кризис-индекс = ' + crisis.score.toFixed(1) + ' (' + crisis.level + ')');

  _updateDataSheet(ss, instrData, forexData);
  _updateDashboard(ss, instrData, forexData, crisis);
  _logHistory(ss, instrData, forexData, crisis);
  _updateHistoryChart(ss);
  Logger.log('=== Готово ===');
}

// ═══════════════════════════════════════════════════════════════════════════
// ЛИСТ «ДАННЫЕ»
// ═══════════════════════════════════════════════════════════════════════════

function _updateDataSheet(ss, instrData, forexData) {
  const sh = ss.getSheetByName(SHEET_DATA);
  sh.clearContents();
  sh.clearFormats();
  sh.setTabColor(C.blue);

  const now = new Date().toLocaleString('ru-RU');
  _setCell(sh, 1, 1, '📈 РЫНОЧНЫЕ ДАННЫЕ — КЛЕЕВАЯ ОТРАСЛЬ', 14, true, C.blue, C.bg);
  _setCell(sh, 1, 2, 'Обновлено: ' + now, 10, false, C.muted, C.bg);

  // Заголовки инструментов
  const hdr = ['Инструмент','Тикер','Категория','Цена','Ед.','Δ 1д %','Δ 30д %','Δ 1г %',
                'Ср. 30д','Ср. 90д','Ср. 1г','Мин 1г','Макс 1г','Позиция 52н. %','Стресс','Риск','Вес'];
  sh.getRange(3, 1, 1, hdr.length).setValues([hdr])
    .setBackground(C.card).setFontColor(C.muted).setFontWeight('bold').setFontSize(9);

  let row = 4;
  INSTRUMENTS.forEach((inst, i) => {
    const d = instrData[inst.key];
    const bg = i % 2 === 0 ? C.card : C.card2;
    if (!d) {
      sh.getRange(row, 1, 1, 5).setValues([[inst.name, inst.ticker, inst.cat, '—', inst.unit]])
        .setBackground(bg).setFontColor(C.muted);
      row++; return;
    }
    const pct  = d.pct1y;
    const elev = Math.min(Math.max(d.ch1y, 0), 50) * 2;
    const stress = Math.min(pct * 0.5 + elev * 0.5, 100);
    const lvl  = stress < 33 ? 'Низкий' : stress < 66 ? 'Средний' : 'Высокий';
    const rCol = stress < 33 ? C.green : stress < 66 ? C.yellow : C.red;

    const row_ = [inst.name, inst.ticker, inst.cat,
      _r(d.cur, 4), inst.unit,
      _r(d.ch1d, 2), _r(d.ch30, 2), _r(d.ch1y, 2),
      _r(d.a30,  4), _r(d.a90, 4), _r(d.a1y, 4),
      _r(d.lo,   4), _r(d.hi,  4),
      _r(pct, 1), _r(stress, 1), lvl, inst.weight,
    ];
    sh.getRange(row, 1, 1, row_.length).setValues([row_])
      .setBackground(bg).setFontColor(C.text).setFontSize(10);
    _colorChg(sh.getRange(row, 6), d.ch1d);
    _colorChg(sh.getRange(row, 7), d.ch30);
    _colorChg(sh.getRange(row, 8), d.ch1y);
    sh.getRange(row, 15).setFontColor(rCol).setFontWeight('bold');
    sh.getRange(row, 16).setFontColor(rCol).setFontWeight('bold');
    row++;
  });

  row++;
  _setCell(sh, row, 1, 'ВАЛЮТНЫЕ КУРСЫ', 10, true, C.blue, C.bg);
  row++;

  const fxHdr = ['Пара','Тикер','Описание','Курс','','Δ 1д %','Δ 30д %','Δ 1г %','Мин 1г','Макс 1г','Позиция 52н.'];
  sh.getRange(row, 1, 1, fxHdr.length).setValues([fxHdr])
    .setBackground(C.card).setFontColor(C.muted).setFontWeight('bold').setFontSize(9);
  row++;

  FOREX_PAIRS.forEach((fx, i) => {
    const d = forexData[fx.key];
    const bg = i % 2 === 0 ? C.card : C.card2;
    if (!d) {
      sh.getRange(row, 1, 1, 3).setValues([[fx.name, fx.ticker, '—']]).setBackground(bg).setFontColor(C.muted);
      row++; return;
    }
    const fxRow = [fx.name, fx.ticker, fx.desc,
      _r(d.cur, 4), '',
      _r(d.ch1d, 2), _r(d.ch30, 2), _r(d.ch1y, 2),
      _r(d.lo, 4), _r(d.hi, 4), _r(d.pct1y, 1) + '%',
    ];
    sh.getRange(row, 1, 1, fxRow.length).setValues([fxRow])
      .setBackground(bg).setFontColor(C.text).setFontSize(10);
    _colorChg(sh.getRange(row, 6), d.ch1d);
    _colorChg(sh.getRange(row, 7), d.ch30);
    _colorChg(sh.getRange(row, 8), d.ch1y);
    row++;
  });

  sh.autoResizeColumns(1, 17);
}

// ═══════════════════════════════════════════════════════════════════════════
// ЛИСТ «ДАШБОРД»
// ═══════════════════════════════════════════════════════════════════════════

function _updateDashboard(ss, instrData, forexData, crisis) {
  const sh = ss.getSheetByName(SHEET_DASH);
  sh.clearContents();
  sh.clearFormats();
  sh.setTabColor(crisis.color);

  // Ширины столбцов
  [1,2,3,4,5,6,7,8,9,10,11,12].forEach((c, i) => {
    const widths = [20, 200, 110, 110, 110, 110, 110, 110, 110, 110, 140, 60];
    sh.setColumnWidth(c, widths[i]);
  });

  let row = 1;
  sh.setRowHeight(row, 8); row++;

  // ── Шапка ──
  sh.setRowHeight(row, 48);
  sh.getRange(row, 2, 1, 11).merge()
    .setValue('📊  ДАШБОРД: КРИЗИС В ОТРАСЛИ КЛЕЁВ')
    .setBackground(C.accent).setFontColor('#ffffff')
    .setFontSize(16).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  row++;

  sh.setRowHeight(row, 22);
  sh.getRange(row, 2, 1, 11).merge()
    .setValue('Обновлено: ' + new Date().toLocaleString('ru-RU') +
              '  ·  Следующее обновление: ежедневно в 08:00  ·  Источник: Yahoo Finance')
    .setBackground(C.card).setFontColor(C.muted)
    .setFontSize(9).setHorizontalAlignment('center').setVerticalAlignment('middle');
  row++;

  sh.setRowHeight(row, 8); row++;

  // ── Блок кризис-индекса ──
  sh.setRowHeight(row, 18);
  _setCell(sh, row, 2, 'ИНДЕКС КРИЗИСА (0–100)', 8, true, C.muted, C.bg);
  _setCell(sh, row, 5, 'УРОВЕНЬ РИСКА', 8, true, C.muted, C.bg);
  _setCell(sh, row, 8, 'ПОПРАВКА НА КУРС', 8, true, C.muted, C.bg);
  _setCell(sh, row, 10, 'ИНТЕРПРЕТАЦИЯ', 8, true, C.muted, C.bg);
  row++;

  sh.setRowHeight(row, 64);
  // Число
  sh.getRange(row, 2, 1, 2).merge()
    .setValue(crisis.score.toFixed(1))
    .setBackground(crisis.color + '22').setFontColor(crisis.color)
    .setFontSize(32).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle')
    .setBorder(true, true, true, true, false, false, crisis.color,
               SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
  // Уровень
  sh.getRange(row, 4, 1, 3).merge()
    .setValue(crisis.level)
    .setBackground(crisis.color).setFontColor('#ffffff')
    .setFontSize(22).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  // Forex
  sh.getRange(row, 7, 1, 2).merge()
    .setValue(crisis.fxAdj > 0 ? '+' + crisis.fxAdj.toFixed(1) + ' б.\nUSD/RUB: +' +
      (forexData.usd_rub ? forexData.usd_rub.ch1y.toFixed(1) + '%' : '—') : 'Нет поправки')
    .setBackground(C.card).setFontColor(crisis.fxAdj > 0 ? C.yellow : C.green)
    .setFontSize(13).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  // Интерпретация
  sh.getRange(row, 9, 1, 4).merge()
    .setValue(crisis.interp)
    .setBackground(C.card).setFontColor(C.text)
    .setFontSize(11).setWrap(true).setVerticalAlignment('middle');
  row++;

  sh.setRowHeight(row, 8); row++;

  // ── Сырьё — таблица ──
  sh.getRange(row, 2, 1, 11).merge()
    .setValue('  ЦЕНЫ НА СЫРЬЁ И ОТРАСЛЕВЫЕ ИНДИКАТОРЫ')
    .setBackground(C.card).setFontColor(C.blue).setFontSize(10).setFontWeight('bold');
  row++;

  sh.setRowHeight(row, 24);
  const tHdr = ['', 'Инструмент', 'Кат.', 'Цена', 'Ед.', 'Δ 1д%', 'Δ 30д%', 'Δ 1г%', 'Поз. 52н.', 'Стресс', 'Риск', 'Вес'];
  sh.getRange(row, 1, 1, tHdr.length).setValues([tHdr])
    .setBackground(C.card).setFontColor(C.muted).setFontWeight('bold').setFontSize(9);
  row++;

  crisis.comps.forEach((comp, i) => {
    const d   = instrData[comp.key];
    const bg  = i % 2 === 0 ? C.card : C.card2;
    const rCol = comp.level === 'low' ? C.green : comp.level === 'medium' ? C.yellow : C.red;
    const rLbl = comp.level === 'low' ? 'Низкий' : comp.level === 'medium' ? 'Средний' : 'Высокий';
    const bar  = _bar(comp.stress, 10);
    sh.setRowHeight(row, 24);

    const vals = ['', comp.name, comp.cat,
      d ? _r(d.cur, d.cur < 10 ? 4 : 2) : '—', comp.unit,
      d ? _r(d.ch1d, 2) : '', d ? _r(d.ch30, 2) : '', d ? _r(d.ch1y, 2) : '',
      d ? _r(d.pct1y, 1) + '%' : '—',
      bar + '  ' + _r(comp.stress, 1),
      rLbl,
      (comp.weight * 100).toFixed(0) + '%',
    ];
    sh.getRange(row, 1, 1, vals.length).setValues([vals])
      .setBackground(bg).setFontColor(C.text).setFontSize(10);

    // Цвет изменений
    if (d) {
      _colorChg(sh.getRange(row, 6), d.ch1d);
      _colorChg(sh.getRange(row, 7), d.ch30);
      _colorChg(sh.getRange(row, 8), d.ch1y);
    }
    sh.getRange(row, 10).setFontColor(rCol).setFontWeight('bold').setFontFamily('Courier New');
    sh.getRange(row, 11).setFontColor(rCol).setFontWeight('bold');
    row++;
  });

  sh.setRowHeight(row, 8); row++;

  // ── Валюта ──
  sh.getRange(row, 2, 1, 11).merge()
    .setValue('  ВАЛЮТНЫЕ КУРСЫ')
    .setBackground(C.card).setFontColor(C.blue).setFontSize(10).setFontWeight('bold');
  row++;

  const fxHdrRow = ['', 'Пара', 'Описание', 'Курс', '', 'Δ 1д%', 'Δ 30д%', 'Δ 1г%', 'Мин 1г', 'Макс 1г', 'Поз. 52н.', ''];
  sh.getRange(row, 1, 1, fxHdrRow.length).setValues([fxHdrRow])
    .setBackground(C.card).setFontColor(C.muted).setFontWeight('bold').setFontSize(9);
  row++;

  FOREX_PAIRS.forEach((fx, i) => {
    const d  = forexData[fx.key];
    const bg = i % 2 === 0 ? C.card : C.card2;
    sh.setRowHeight(row, 24);
    if (!d) {
      sh.getRange(row, 2, 1, 3).setValues([[fx.name, fx.desc, '—']]).setBackground(bg).setFontColor(C.muted);
      row++; return;
    }
    const fxVals = ['', fx.name, fx.desc,
      _r(d.cur, 4), '',
      _r(d.ch1d, 4), _r(d.ch30, 2), _r(d.ch1y, 2),
      _r(d.lo, 4), _r(d.hi, 4), _r(d.pct1y, 1) + '%', '',
    ];
    sh.getRange(row, 1, 1, fxVals.length).setValues([fxVals])
      .setBackground(bg).setFontColor(C.text).setFontSize(10);
    _colorChg(sh.getRange(row, 6), d.ch1d);
    _colorChg(sh.getRange(row, 7), d.ch30);
    _colorChg(sh.getRange(row, 8), d.ch1y);
    row++;
  });

  sh.setRowHeight(row, 8); row++;

  // ── Разбивка риска ──
  sh.getRange(row, 2, 1, 11).merge()
    .setValue('  РАЗБИВКА СТРЕССА ПО КОМПОНЕНТАМ (сортировка по убыванию)')
    .setBackground(C.card).setFontColor(C.blue).setFontSize(10).setFontWeight('bold');
  row++;

  const sorted = crisis.comps.slice().sort((a, b) => b.stress - a.stress);
  sorted.forEach((comp, i) => {
    const bg   = i % 2 === 0 ? C.card : C.card2;
    const rCol = comp.level === 'low' ? C.green : comp.level === 'medium' ? C.yellow : C.red;
    const rLbl = comp.level === 'low' ? 'Низкий' : comp.level === 'medium' ? 'Средний' : 'Высокий';
    sh.setRowHeight(row, 22);

    sh.getRange(row, 2).setValue(comp.name).setBackground(bg).setFontColor(C.text).setFontSize(10);
    sh.getRange(row, 3).setValue(_r(comp.stress, 1) + ' б.').setBackground(bg).setFontColor(rCol).setFontWeight('bold');
    sh.getRange(row, 4, 1, 4).merge()
      .setValue(_bar(comp.stress, 20))
      .setBackground(bg).setFontColor(rCol).setFontFamily('Courier New').setFontSize(9);
    sh.getRange(row, 8).setValue(rLbl).setBackground(bg).setFontColor(rCol).setFontWeight('bold');
    sh.getRange(row, 9).setValue('Δ 1г: ' + (comp.ch1y >= 0 ? '+' : '') + _r(comp.ch1y, 1) + '%')
      .setBackground(bg).setFontColor(C.muted).setFontSize(9);
    sh.getRange(row, 10).setValue('Вес: ' + (comp.weight * 100).toFixed(0) + '%')
      .setBackground(bg).setFontColor(C.muted).setFontSize(9);
    row++;
  });

  // Forex строка
  if (crisis.fxAdj > 0) {
    sh.setRowHeight(row, 22);
    sh.getRange(row, 2).setValue('Поправка USD/RUB').setBackground(C.card2).setFontColor(C.text).setFontSize(10);
    sh.getRange(row, 3).setValue('+' + crisis.fxAdj.toFixed(1) + ' б.').setBackground(C.card2).setFontColor(C.yellow).setFontWeight('bold');
    sh.getRange(row, 4, 1, 4).merge()
      .setValue(_bar(crisis.fxAdj * 3, 20) + '  (добавлено к итоговому баллу)')
      .setBackground(C.card2).setFontColor(C.yellow).setFontFamily('Courier New').setFontSize(9);
    row++;
  }

  sh.setRowHeight(row, 8); row++;

  // ── Методология ──
  const meth = 'МЕТОДОЛОГИЯ: Стресс = 50% × позиция в 52-нед. диапазоне + 50% × превышение годовой средней (макс. +50% → 100 б.). ' +
    'Поправка USD/RUB: ослабление рубля добавляет до +15 баллов. Зоны: 0–29 = НИЗКИЙ ◆ 30–59 = СРЕДНИЙ ◆ 60–100 = ВЫСОКИЙ. ' +
    'Источник данных: Yahoo Finance (yfinance API). Компании: H.B. Fuller (вес 15%), LyondellBasell (13%), Eastman Chemical (12%), ' +
    'Dow Inc. (10%). Сырьё: Нефть WTI (25%), газ (10%), RBOB (8%), кукуруза (7%).';
  sh.setRowHeight(row, 50);
  sh.getRange(row, 2, 1, 11).merge()
    .setValue(meth).setBackground(C.bg).setFontColor('#475569')
    .setFontSize(8).setWrap(true).setVerticalAlignment('top');

  sh.setFrozenRows(0);
}

// ═══════════════════════════════════════════════════════════════════════════
// ЛИСТ «ИСТОРИЯ»
// ═══════════════════════════════════════════════════════════════════════════

function _ensureHistoryHeader(sh) {
  if (sh.getLastRow() > 0) return;
  const hdrs = ['Дата', 'Индекс', 'Уровень'];
  INSTRUMENTS.forEach(i => hdrs.push(i.name));
  hdrs.push('USD/RUB', 'EUR/USD');
  sh.getRange(1, 1, 1, hdrs.length).setValues([hdrs])
    .setBackground(C.card).setFontColor(C.muted).setFontWeight('bold').setFontSize(9);
  sh.setFrozenRows(1);
}

function _logHistory(ss, instrData, forexData, crisis) {
  const sh = ss.getSheetByName(SHEET_HISTORY);
  _ensureHistoryHeader(sh);
  sh.setTabColor(C.muted);

  const row = [new Date(), crisis.score, crisis.level];
  INSTRUMENTS.forEach(inst => {
    const d = instrData[inst.key];
    row.push(d ? _r(d.cur, 4) : '');
  });
  row.push(
    forexData.usd_rub ? _r(forexData.usd_rub.cur, 4) : '',
    forexData.eur_usd ? _r(forexData.eur_usd.cur, 4) : ''
  );

  const newRow = sh.getLastRow() + 1;
  sh.getRange(newRow, 1, 1, row.length).setValues([row]);
  const rCol = crisis.level === 'НИЗКИЙ' ? C.green : crisis.level === 'СРЕДНИЙ' ? C.yellow : C.red;
  sh.getRange(newRow, 2).setFontColor(rCol).setFontWeight('bold');
  sh.getRange(newRow, 3).setFontColor(rCol).setFontWeight('bold');

  sh.autoResizeColumns(1, row.length);
}

function _updateHistoryChart(ss) {
  const sh = ss.getSheetByName(SHEET_HISTORY);
  const lastRow = sh.getLastRow();
  if (lastRow < 3) return; // Нужно хотя бы 2 строки данных

  // Удалить старый график
  sh.getCharts().forEach(c => sh.removeChart(c));

  // Строим график «Индекс кризиса по дням»
  const dataRange = sh.getRange(1, 1, lastRow, 3); // Дата, Индекс, Уровень
  const chart = sh.newChart()
    .setChartType(Charts.ChartType.LINE)
    .addRange(sh.getRange(1, 1, lastRow, 1)) // дата
    .addRange(sh.getRange(1, 2, lastRow, 1)) // индекс
    .setOption('title', 'История индекса кризиса в отрасли клеёв')
    .setOption('hAxis', { title: 'Дата', textStyle: { color: '#94a3b8' } })
    .setOption('vAxis', { title: 'Индекс (0–100)', minValue: 0, maxValue: 100,
      gridlines: { color: '#334155' }, textStyle: { color: '#94a3b8' } })
    .setOption('backgroundColor', '#1e293b')
    .setOption('colors', ['#3b82f6'])
    .setOption('legend', { position: 'none' })
    .setOption('lineWidth', 2)
    .setOption('pointSize', 4)
    .setNumHeaders(1)
    .setPosition(3, 5, 0, 0)
    .setOption('width', 700)
    .setOption('height', 320)
    .build();
  sh.insertChart(chart);
}

// ═══════════════════════════════════════════════════════════════════════════
// ТРИГГЕР
// ═══════════════════════════════════════════════════════════════════════════

function _setupTrigger() {
  // Удалить старые
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'refreshData')
    .forEach(t => ScriptApp.deleteTrigger(t));
  // Создать новый: каждый день 08:00–09:00
  ScriptApp.newTrigger('refreshData')
    .timeBased()
    .everyDays(1)
    .atHour(8)
    .create();
  Logger.log('Триггер настроен: refreshData() каждый день в 08:00.');
}

// ═══════════════════════════════════════════════════════════════════════════
// ИНИЦИАЛИЗАЦИЯ ЛИСТОВ
// ═══════════════════════════════════════════════════════════════════════════

function _ensureSheets(ss) {
  [SHEET_DASH, SHEET_DATA, SHEET_HISTORY].forEach(name => {
    if (!ss.getSheetByName(name)) ss.insertSheet(name);
  });
  // Удалить Лист1, если пустой и есть другие листы
  ['Лист1', 'Sheet1'].forEach(def => {
    const s = ss.getSheetByName(def);
    if (s && ss.getSheets().length > 3 && s.getLastRow() === 0) {
      try { ss.deleteSheet(s); } catch (e) {}
    }
  });
  _ensureHistoryHeader(ss.getSheetByName(SHEET_HISTORY));
}

// ═══════════════════════════════════════════════════════════════════════════
// УТИЛИТЫ
// ═══════════════════════════════════════════════════════════════════════════

function _r(v, d) {
  if (v == null || isNaN(v)) return '';
  return Math.round(v * Math.pow(10, d)) / Math.pow(10, d);
}

function _mean(arr) {
  if (!arr || arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

/** Цвет по направлению изменения (рост цены сырья = плохо = красный) */
function _colorChg(cell, val) {
  if (val == null || val === '') return;
  if (val > 0.5)       cell.setFontColor(C.red).setFontWeight('bold');
  else if (val < -0.5) cell.setFontColor(C.green).setFontWeight('bold');
  else                 cell.setFontColor(C.muted);
}

/** Unicode прогресс-бар из блоков */
function _bar(value, width) {
  const filled = Math.round(Math.min(Math.max(value, 0), 100) / 100 * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

function _setCell(sh, row, col, text, size, bold, fgColor, bgColor) {
  const cell = sh.getRange(row, col);
  cell.setValue(text);
  if (size)    cell.setFontSize(size);
  if (bold)    cell.setFontWeight('bold');
  if (fgColor) cell.setFontColor(fgColor);
  if (bgColor) cell.setBackground(bgColor);
}
