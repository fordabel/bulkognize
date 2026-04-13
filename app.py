"""
Bulkognize - LEGO Minifig Identification Web App
Wraps the Brickognize API for use at Bricks & Minifigs stores.
Run with: python app.py
"""

import os
import io
import csv
import time
import uuid
import json
import base64
import tempfile
from datetime import datetime

import requests
from flask import (
    Flask, render_template, request, jsonify, send_file, session
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bulkognize-" + uuid.uuid4().hex)

BRICKOGNIZE_URL = "https://api.brickognize.com/predict/"
BULK_DELAY = 1  # seconds between API calls in bulk mode

# Store bulk results in a temp directory keyed by session
RESULTS_DIR = os.path.join(tempfile.gettempdir(), "bulkognize_results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def call_brickognize(image_bytes, filename="image.jpg"):
    """Send an image to the Brickognize API and return parsed results."""
    files = {"query_image": (filename, image_bytes, "image/jpeg")}
    try:
        resp = requests.post(BRICKOGNIZE_URL, files=files, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        results = []
        for item in items:
            bricklink_url = ""
            for site in item.get("external_sites", []):
                if site.get("name", "").lower() == "bricklink":
                    bricklink_url = site.get("url", "")
                    break
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", "Unknown"),
                "score": round(item.get("score", 0) * 100, 1),
                "img_url": item.get("img_url", ""),
                "category": item.get("category", ""),
                "type": item.get("type", ""),
                "bricklink_url": bricklink_url,
            })
        return results
    except requests.exceptions.Timeout:
        return {"error": "The identification service took too long. Please try again."}
    except requests.exceptions.ConnectionError:
        return {"error": "Could not reach the identification service. Check your internet connection."}
    except Exception as e:
        return {"error": f"Something went wrong: {str(e)}"}


@app.route("/")
def index():
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    return render_template("index.html")


@app.route("/api/predict", methods=["POST"])
def predict():
    """Single image prediction."""
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No image selected"}), 400

    image_bytes = file.read()
    results = call_brickognize(image_bytes, file.filename)

    if isinstance(results, dict) and "error" in results:
        return jsonify(results), 502

    # Encode the uploaded image as base64 for display
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")

    return jsonify({
        "uploaded_image": f"data:image/jpeg;base64,{img_b64}",
        "predictions": results,
    })


@app.route("/api/bulk", methods=["POST"])
def bulk_predict():
    """Multiple image prediction with delay between calls."""
    files = request.files.getlist("images")
    if not files or (len(files) == 1 and files[0].filename == ""):
        return jsonify({"error": "No images provided"}), 400

    all_results = []
    errors = []

    for i, file in enumerate(files):
        if file.filename == "":
            continue

        image_bytes = file.read()
        results = call_brickognize(image_bytes, file.filename)

        if isinstance(results, dict) and "error" in results:
            errors.append({"filename": file.filename, "error": results["error"]})
        else:
            img_b64 = base64.b64encode(image_bytes).decode("utf-8")
            all_results.append({
                "filename": file.filename,
                "uploaded_image": f"data:image/jpeg;base64,{img_b64}",
                "predictions": results,
            })

        # Respect the API: wait between calls (skip delay after last image)
        if i < len(files) - 1:
            time.sleep(BULK_DELAY)

    # Save results for CSV download
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    results_path = os.path.join(RESULTS_DIR, f"{session['session_id']}.json")
    with open(results_path, "w") as f:
        json.dump(all_results, f)

    return jsonify({
        "results": all_results,
        "errors": errors,
        "total": len(all_results),
    })


@app.route("/api/bulk/csv")
def bulk_csv():
    """Download last bulk results as CSV."""
    sid = session.get("session_id", "")
    results_path = os.path.join(RESULTS_DIR, f"{sid}.json")

    if not os.path.exists(results_path):
        return jsonify({"error": "No bulk results found. Run a bulk scan first."}), 404

    with open(results_path, "r") as f:
        all_results = json.load(f)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Source Image", "Prediction Rank", "Item ID", "Name",
        "Confidence %", "Category", "Type", "BrickLink URL", "Image URL"
    ])

    for result in all_results:
        filename = result.get("filename", "")
        for rank, pred in enumerate(result.get("predictions", []), 1):
            writer.writerow([
                filename,
                rank,
                pred.get("id", ""),
                pred.get("name", ""),
                pred.get("score", ""),
                pred.get("category", ""),
                pred.get("type", ""),
                pred.get("bricklink_url", ""),
                pred.get("img_url", ""),
            ])

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"bulkognize_results_{timestamp}.csv",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n  Bulkognize is running!")
    print(f"  Open http://localhost:{port} in your browser\n")
    app.run(debug=True, host="0.0.0.0", port=port)
