from flask import Flask, render_template, request, jsonify
import requests
import re
import os
import json

app = Flask(__name__)

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "your_rapidapi_key_here").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "your_groq_key_here").strip()

def extract_asin(url):
    # Standard URL formats
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if match:
        return match.group(1)
    match = re.search(r"/gp/product/([A-Z0-9]{10})", url)
    if match:
        return match.group(1)
    # Direct ASIN paste
    if re.match(r"^[A-Z0-9]{10}$", url.strip()):
        return url.strip()
    # Short URL - resolve it first
    if "amzn.in" in url or "amzn.to" in url:
        try:
            response = requests.get(url, allow_redirects=True, timeout=10)
            final_url = response.url
            match = re.search(r"/dp/([A-Z0-9]{10})", final_url)
            if match:
                return match.group(1)
        except:
            pass
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
                "image": data["data"].get("product_photo", ""),
                "ratings_total": data["data"].get("product_num_ratings", 0),
                "price": data["data"].get("product_price", "N/A"),
                "url": data["data"].get("product_url", "")
            }
    except:
        pass
    return {"title": "Product", "rating": "N/A", "image": "", "ratings_total": 0, "price": "N/A", "url": ""}

def calculate_sentiment(reviews):
    if not reviews:
        return 50
    total = 0
    count = 0
    for r in reviews:
        try:
            rating = float(r.get("review_star_rating", 0))
            if rating > 0:
                total += rating
                count += 1
        except:
            continue
    if count == 0:
        return 50
    avg = total / count
    return round((avg / 5) * 100)

def get_highlights(reviews):
    highlights = []
    for r in reviews[:3]:
        title = r.get("review_title", "").strip()
        comment = r.get("review_comment", "").strip()
        stars = r.get("review_star_rating", "?")
        if title and comment:
            highlights.append({
                "title": title,
                "comment": comment[:150] + "..." if len(comment) > 150 else comment,
                "stars": stars
            })
    return highlights

def analyze_reviews(reviews):
    combined = " ".join([
        r.get("review_comment", "")
        for r in reviews
        if r.get("review_comment", "").strip()
    ])
    if not combined.strip():
        return {
            "summary": "No review content available.",
            "pros": [],
            "cons": [],
            "verdict": "Insufficient data"
        }

    combined = combined[:2000]

    prompt = f"""Analyze these Amazon product reviews and respond ONLY with a valid JSON object in exactly this format:
{{
  "summary": "2-3 sentence overall summary",
  "pros": ["pro 1", "pro 2", "pro 3"],
  "cons": ["con 1", "con 2", "con 3"],
  "verdict": "One line recommendation for buyers"
}}

Reviews:
{combined}"""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.3
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        result = response.json()
        if "choices" in result:
            content = result["choices"][0]["message"]["content"].strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return parsed
        return {"summary": "Summary unavailable.", "pros": [], "cons": [], "verdict": "Please try again."}
    except Exception as e:
        print(f"Groq error: {e}")
        return {"summary": f"Error: {str(e)}", "pros": [], "cons": [], "verdict": "Error occurred."}

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

    analysis = analyze_reviews(reviews)
    sentiment = calculate_sentiment(reviews)
    highlights = get_highlights(reviews)

    return jsonify({
        "title": product["title"],
        "rating": product["rating"],
        "image": product["image"],
        "ratings_total": product["ratings_total"],
        "price": product["price"],
        "product_url": product["url"],
        "summary": analysis.get("summary", ""),
        "pros": analysis.get("pros", []),
        "cons": analysis.get("cons", []),
        "verdict": analysis.get("verdict", ""),
        "sentiment": sentiment,
        "highlights": highlights
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
