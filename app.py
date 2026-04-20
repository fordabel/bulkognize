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

import re

import requests
from flask import (
    Flask, render_template, request, jsonify, send_file, session
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bulkognize-" + uuid.uuid4().hex)

BRICKOGNIZE_URL = "https://api.brickognize.com/predict/"
BULK_DELAY = 0.3  # seconds between API calls in bulk mode

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


TYPE_MAP = {
    "minifig": "M", "fig": "M",
    "part": "P",
    "set": "S",
    "gear": "G",
    "book": "B",
    "catalog": "C",
}


def fetch_bricklink_prices(item_id, item_type_raw):
    """Scrape BrickLink price guide for an item. Returns dict with price fields."""
    empty = {
        "last6_new_avg": "", "last6_used_avg": "",
        "current_new_avg": "", "current_used_avg": "",
    }
    if not item_id:
        return empty
    type_code = TYPE_MAP.get(item_type_raw.lower(), "M") if item_type_raw else "M"
    url = f"https://www.bricklink.com/catalogPG.asp?{type_code}={item_id}&ColorID=0"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # BrickLink price guide has a 4-column summary table:
        #   Last 6 Months Sales: New | Used
        #   Current Items for Sale: New | Used
        # Each column has: Times Sold/Total Lots, Total Qty, Min, Avg, Qty Avg, Max
        # We find the summary row (BGCOLOR="#C0C0C0") that contains all 4 <TD VALIGN="TOP"> cells.

        # Extract all "Avg Price" values in order from the summary block.
        # The page layout puts them in order: last6_new, last6_used, current_new, current_used
        # Each column has two "Avg Price" entries (Avg Price and Qty Avg Price).
        # We want the first "Avg Price" from each column (not "Qty Avg Price").
        avg_pattern = re.compile(
            r'>Avg Price:.*?<B>US&nbsp;\$([\d,.]+)</B>', re.DOTALL
        )
        matches = avg_pattern.findall(html)

        # The first 4 Avg Price values correspond to:
        # [0] = Last 6 Mo New, [1] = Last 6 Mo Used,
        # [2] = Current New, [3] = Current Used
        # (Each column also has a "Qty Avg Price" so actual matches may be doubled)
        # Filter to get every other one (Avg Price, skip Qty Avg Price)
        keys = ["last6_new_avg", "last6_used_avg", "current_new_avg", "current_used_avg"]
        prices = {}
        avg_idx = 0
        for i, val in enumerate(matches):
            if i % 2 == 0 and avg_idx < 4:  # Take 1st, skip 2nd (Qty Avg) per column
                prices[keys[avg_idx]] = val
                avg_idx += 1

        return {k: prices.get(k, "") for k in empty}

    except Exception:
        return empty


@app.route("/api/bulk/csv")
def bulk_csv():
    """Download last bulk results as CSV with BrickLink pricing."""
    sid = session.get("session_id", "")
    results_path = os.path.join(RESULTS_DIR, f"{sid}.json")

    if not os.path.exists(results_path):
        return jsonify({"error": "No bulk results found. Run a bulk scan first."}), 404

    with open(results_path, "r") as f:
        all_results = json.load(f)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Source Image", "Prediction Rank", "Confidence %",
        "Item ID", "Name",
        "BL Last 6 Mo Avg (New)", "BL Last 6 Mo Avg (Used)",
        "BL Current For Sale Avg (New)", "BL Current For Sale Avg (Used)",
        "BrickLink URL",
    ])

    for result in all_results:
        filename = result.get("filename", "")
        for rank, pred in enumerate(result.get("predictions", []), 1):
            item_id = pred.get("id", "")
            item_type = pred.get("type", "")
            prices = fetch_bricklink_prices(item_id, item_type)

            writer.writerow([
                filename,
                rank,
                pred.get("score", ""),
                item_id,
                pred.get("name", ""),
                prices["last6_new_avg"],
                prices["last6_used_avg"],
                prices["current_new_avg"],
                prices["current_used_avg"],
                pred.get("bricklink_url", ""),
            ])
            # Small delay to be respectful to BrickLink
            time.sleep(0.5)

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
