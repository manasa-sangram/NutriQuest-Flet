import os
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv

#BACKEND
load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

usda = os.environ.get("USDA_FOOD_API_KEY")

os.environ["USDA_FOOD_API_KEY"]="fygYiKLOQAIQeiLJDtX2bZEK4efm4bdZFaCCigsC"


def parse_grocery_list(raw_text):
    """Send raw grocery text to GPT → get back a clean list."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a grocery list parser. Always respond with valid JSON only. No extra text."
            },
            {
                "role": "user",
                "content": f"""Parse this grocery list into a JSON array.
Each item must have exactly these fields:
- "name": the food name as a simple string (e.g. "apple", "oat milk")
- "quantity": a number (e.g. 2, 1.5)
- "unit": a string (e.g. "piece", "litre", "gram")

Grocery list:
{raw_text}

Return only the JSON array, nothing else."""
            }
        ]
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if GPT adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def get_nutrition(item_name):
    """Look up nutrition data from USDA Food API."""

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "api_key": os.environ.get("USDA_FOOD_API_KEY"),
        "query": item_name,
        "pageSize": 1,
    }

    response = requests.get(url, params=params, timeout=8)

    if response.status_code != 200:
        print(f"USDA API error: {response.status_code} — {response.text}")
        return None

    data = response.json()
    foods = data.get("foods", [])

    if not foods:
        return None

    food = foods[0]
    nutrients = {n["nutrientName"]: n["value"] for n in food.get("foodNutrients", [])}

    return {
        "name":     item_name,
        "calories": round(nutrients.get("Energy", 0)),
        "protein":  round(nutrients.get("Protein", 0), 1),
        "fat":      round(nutrients.get("Total lipid (fat)", 0), 1),
        "carbs":    round(nutrients.get("Carbohydrate, by difference", 0), 1) , 
        "fibre":    round(nutrients.get("Fiber, total dietary", 0), 1)
    }

def analyse_grocery_list(raw_text):
    """Full pipeline — parse text → fetch nutrition for each item."""

    items = parse_grocery_list(raw_text)
    results = []
    not_found = []

    for item in items:
        data = get_nutrition(item["name"])
        if data:
            results.append(data)
        else:
            not_found.append(item["name"])

    return results, not_found


def get_meal_plan(grocery_history, goals):
    """
    Available from Level 3 onwards.

    Looks at the user's recent grocery lists and daily goals, then
    returns a personalised 3-day meal plan using ingredients they
    already buy.

    Parameters
    ----------
    grocery_history : list of raw grocery text strings (from progress.json)
    goals           : dict with keys "protein", "carbs", "fibre"

    Returns
    -------
    str — the full meal plan as plain text, ready to display on screen
    """

    if not grocery_history:
        return (
            "No grocery history found yet.\n\n"
            "Analyse a few grocery lists first, then come back for your personalised meal plan!"
        )

    # Use the most recent 5 grocery lists
    recent = grocery_history[-5:]
    combined = "\n---\n".join(recent)

    prompt = f"""You are a friendly, encouraging nutrition coach helping a beginner eat better.

The user's daily nutrition goals are:
- Protein: {goals.get('protein', 50)}g
- Carbs:   {goals.get('carbs', 250)}g
- Fibre:   {goals.get('fibre', 30)}g

Here are their recent grocery lists (most recent last):
{combined}

Based ONLY on ingredients visible in these grocery lists, create a simple 3-day meal plan.

Format your response exactly like this:

DAY 1
  Breakfast: [meal]
  Lunch: [meal]
  Dinner: [meal]

DAY 2
  Breakfast: [meal]
  Lunch: [meal]
  Dinner: [meal]

DAY 3
  Breakfast: [meal]
  Lunch: [meal]
  Dinner: [meal]

TIPS
  • [one short tip about hitting their protein goal]
  • [one short tip about hitting their fibre goal]

Keep meals simple — 5 ingredients or fewer. Be encouraging and beginner-friendly.
Do not suggest ingredients that aren't in their grocery lists."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful nutrition coach. Be concise, practical, and encouraging."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content.strip()


if __name__ =="__main__":
    sample_text= " 2 apples , 1L milk , 500g Chicken"
    results , not_found = analyse_grocery_list(sample_text)

    print("RESULTS:" , results)
    print("NOT FOUND:" , not_found)