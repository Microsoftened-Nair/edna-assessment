        return jsonify(entries)

    @app.get("/api/eval/dnabert2")
    def eval_dnabert2() -> Any:
        metrics_file = Path("results/dnabert2_eval/metrics.json")
        report_file = Path("results/dnabert2_eval/classification_report.json")
        if not metrics_file.exists() or not report_file.exists():
            return jsonify({"error": "evaluation-not-found"}), 404
            
        with open(metrics_file, "r") as f:
            metrics = json.load(f)
        with open(report_file, "r") as f:
            report = json.load(f)
            
        # Optional: structure the output better for the front-end
        return jsonify({
            "metrics": metrics,
            "report": report
        })

