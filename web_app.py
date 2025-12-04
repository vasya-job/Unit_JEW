import json
from pathlib import Path
from typing import Any, Dict

from flask import Flask, render_template_string, request

from calculator import aggregate_results, compute_jewelry, compute_retail, compute_yoga


def load_default_config() -> str:
    sample_path = Path(__file__).parent / "config.example.json"
    if sample_path.exists():
        return sample_path.read_text(encoding="utf-8")
    return json.dumps(
        {
            "currency": "RUB",
            "tax": {"profit_tax_rate": 0.22},
            "jewelry": {"channels": [], "overheads": {}},
            "yoga": {"capacity": 0, "classes": {}, "pricing": {}, "corporate": {}, "overheads": {}},
            "retail": {"categories": [], "overheads": {}},
        },
        indent=2,
        ensure_ascii=False,
    )


def build_summary(config: Dict[str, Any]) -> Dict[str, Any]:
    jewelry = compute_jewelry(config.get("jewelry", {}))
    yoga = compute_yoga(config.get("yoga", {}))
    retail = compute_retail(config.get("retail", {}))
    tax = config.get("tax", {})

    aggregate = aggregate_results(jewelry, yoga, retail, tax)

    return {
        "currency": config.get("currency", "RUB"),
        "jewelry": jewelry,
        "yoga": yoga,
        "retail": retail,
        "aggregate": aggregate,
        "notes": {
            "profit_tax_rate": tax.get("profit_tax_rate", 0),
            "assumption": "All figures are monthly unless specified; break-even fill rate shown as share of capacity.",
        },
    }


app = Flask(__name__)


TEMPLATE = """
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Unit Economics Calculator</title>
    <style>
      body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 1.5rem; background: #f7f7fb; color: #121826; }
      h1 { margin-top: 0; }
      form { display: grid; gap: 1rem; }
      textarea { width: 100%; min-height: 360px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 14px; padding: 1rem; border: 1px solid #d0d7e2; border-radius: 8px; background: white; box-sizing: border-box; }
      button { width: fit-content; padding: 0.65rem 1.1rem; background: #2563eb; color: white; border: none; border-radius: 8px; font-size: 15px; cursor: pointer; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25); }
      button:hover { background: #1d4ed8; }
      .card { background: white; border: 1px solid #d0d7e2; border-radius: 10px; padding: 1rem; box-shadow: 0 10px 30px rgba(0,0,0,0.04); }
      .flex { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); align-items: start; }
      pre { white-space: pre-wrap; word-break: break-word; background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 10px; overflow-x: auto; }
      .error { color: #b91c1c; font-weight: 600; }
      .muted { color: #6b7280; font-size: 0.95rem; }
    </style>
  </head>
  <body>
    <h1>Unit Economics Calculator — Web</h1>
    <p class=\"muted\">Заполните конфигурацию в JSON (все показатели — помесячно, ставки в долях). Нажмите «Рассчитать», чтобы увидеть P&amp;L по ювелирке, студии йоги и магазину, а также общий результат с налогом на прибыль.</p>
    {% if error %}
      <p class=\"error\">Ошибка: {{ error }}</p>
    {% endif %}
    <form method=\"post\">
      <div class=\"card\">
        <label for=\"config_json\"><strong>Входные данные (JSON)</strong></label>
        <textarea id=\"config_json\" name=\"config_json\" required>{{ config_json }}</textarea>
        <button type=\"submit\">Рассчитать</button>
      </div>
    </form>
    <div class=\"flex\">
      <div class=\"card\">
        <h2>Результат</h2>
        {% if result %}
          <pre>{{ result }}</pre>
        {% else %}
          <p class=\"muted\">После отправки формы здесь появится расчёт.</p>
        {% endif %}
      </div>
    </div>
  </body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    result_text = None

    config_text = load_default_config()
    if request.method == "POST":
        config_text = request.form.get("config_json", "")
        try:
            config = json.loads(config_text)
            summary = build_summary(config)
            result_text = json.dumps(summary, indent=2, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

    return render_template_string(
        TEMPLATE,
        config_json=config_text,
        result=result_text,
        error=error,
    )


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
