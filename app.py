from flask import Flask, render_template, request, jsonify
import requests
import re
import os

app = Flask(__name__)

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "91450373f9msh35af52807147cc7p1743b6jsn2e56927852de")
HF_API_KEY = os.environ.get("HF_API_KEY", "your_hf_key_here")

def extract_asin(url):
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if match:
        return match.group(1)
    match = re.search(r"/gp/product/([A-Z0-9]{10})", url)
    if match:
        return match.group(1)
    if re.match(r"^[A-Z0-9]{10}$", url.strip()):
        return url.strip()
    return None

def fetch_balanced_reviews(asin):
    all_reviews = []
    for star in ["5_STARS", "3_STARS", "1_STAR"]:
        url = "https://real-time-amazon-data.p.rapidapi.com/product-reviews"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
        }
        params = {
            "asin": asin,
            "country": "IN",
            "page": "1",
            "star_rating": star,
            "sort_by": "TOP_REVIEWS"
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            if "data" in data and "reviews" in data["data"]:
                all_reviews.extend(data["data"]["reviews"])
        except Exception as e:
            print(f"Error fetching {star}: {e}")
    return all_reviews

def get_product_info(asin):
    url = "https://real-time-amazon-data.p.rapidapi.com/product-details"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
    }
    params = {"asin": asin, "country": "IN"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()
        if "data" in data:
            return {
                "title": data["data"].get("product_title", "Product"),
                "rating": data["data"].get("product_star_rating", "N/A"),
                "image": data["data"].get("product_photo", "")
            }
    except:
        pass
    return {"title": "Product", "rating": "N/A", "image": ""}

def summarize_reviews(reviews):
    combined = " ".join([
        r.get("review_comment", "")
        for r in reviews
        if r.get("review_comment", "").strip()
    ])
    if not combined.strip():
        return "No review content available to summarize."

    combined = combined[:2000]

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {
                "role": "user",
                "content": f"Summarize these product reviews in 3-4 sentences covering the key positives and negatives:\n\n{combined}"
            }
        ],
        "max_tokens": 200
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Summarization error: {str(e)}"
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/summarize", methods=["POST"])
def summarize():
    data = request.get_json()
    url_input = data.get("url", "").strip()

    if not url_input:
        return jsonify({"error": "Please enter an Amazon product URL."}), 400

    asin = extract_asin(url_input)
    if not asin:
        return jsonify({"error": "Could not find a valid product ID in the URL."}), 400

    product = get_product_info(asin)
    reviews = fetch_balanced_reviews(asin)

    if not reviews:
        return jsonify({"error": "No reviews found for this product."}), 404

    summary = summarize_reviews(reviews)

    return jsonify({
        "title": product["title"],
        "rating": product["rating"],
        "image": product["image"],
        "summary": summary
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)