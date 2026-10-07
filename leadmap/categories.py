"""Map OpenStreetMap tags to the lead categories shown on the map."""

# key -> label shown in the UI
CATEGORIES = {
    "restaurant": "Restaurants & Food",
    "cafe_bar": "Cafés & Bars",
    "salon": "Salons & Beauty",
    "fitness": "Gyms & Fitness",
    "dental": "Dentists",
    "health": "Health & Wellness",
    "auto": "Auto Shops",
    "home": "Contractors & Home Services",
    "retail": "Retail",
    "professional": "Professional Services",
}

AMENITY = {
    "restaurant": "restaurant", "fast_food": "restaurant", "ice_cream": "restaurant", "food_court": "restaurant",
    "cafe": "cafe_bar", "bar": "cafe_bar", "pub": "cafe_bar", "biergarten": "cafe_bar",
    "dentist": "dental",
    "doctors": "health", "clinic": "health", "veterinary": "health",
    "car_wash": "auto", "driving_school": "professional",
}
SHOP_SALON = {"hairdresser", "beauty", "nails", "massage", "tattoo", "cosmetics", "hairdresser_supply", "piercing"}
SHOP_AUTO = {"car_repair", "car", "tyres", "car_parts", "motorcycle", "motorcycle_repair", "auto_repair"}
SHOP_FOOD = {"bakery", "deli", "confectionery", "pastry", "butcher", "seafood", "coffee", "tea", "wine", "alcohol", "beverages", "cheese"}
SHOP_HOME = {"locksmith", "glaziery", "flooring", "doityourself", "trade", "kitchen", "bathroom_furnishing", "window_blind", "appliance"}
# Big-box / non-lead shop types we skip outright.
SHOP_SKIP = {"vacant", "supermarket", "department_store", "wholesale", "fuel", "lottery", "atm", "money_lender", "pawnbroker"}
LEISURE = {"fitness_centre": "fitness", "sports_centre": "fitness", "dance": "fitness", "yoga": "fitness"}
OFFICE = {"estate_agent", "insurance", "lawyer", "accountant", "architect", "tax_advisor", "financial", "financial_advisor", "property_management", "moving_company"}
HEALTHCARE = {"chiropractor": "health", "physiotherapist": "health", "optometrist": "health", "dentist": "dental",
              "alternative": "health", "psychotherapist": "health", "podiatrist": "health", "audiologist": "health"}


def categorize(tags):
    """Return (category_key, subtype) or (None, None) if not a target business."""
    amenity, shop, craft = tags.get("amenity"), tags.get("shop"), tags.get("craft")
    leisure, office, healthcare = tags.get("leisure"), tags.get("office"), tags.get("healthcare")
    if amenity in AMENITY:
        return AMENITY[amenity], amenity
    if healthcare in HEALTHCARE:
        return HEALTHCARE[healthcare], healthcare
    if leisure in LEISURE:
        return LEISURE[leisure], leisure
    if tags.get("sport") == "fitness" or tags.get("club") == "sport":
        return "fitness", "fitness"
    if shop:
        if shop in SHOP_SKIP:
            return None, None
        if shop in SHOP_SALON:
            return "salon", shop
        if shop in SHOP_AUTO:
            return "auto", shop
        if shop in SHOP_FOOD:
            return "restaurant", shop
        if shop in SHOP_HOME:
            return "home", shop
        return "retail", shop
    if craft:
        return "home", craft
    if office in OFFICE:
        return "professional", office
    return None, None


def pretty(subtype):
    return (subtype or "").replace("_", " ").title()
