import json
from pathlib import Path
from typing import Any, Dict

from flask import Flask, render_template, request

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

    return render_template(
        "index.html",
        config_json=config_text,
        result=result_text,
        error=error,
    )


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
