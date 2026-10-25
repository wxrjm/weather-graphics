"""City labels for wide regional maps (Mid-Atlantic / Southeast views).  Densest in Virginia and North Carolina.
(name, lat, lon, tier): tier 1 = bold, placed first; tier 2 = smaller.  Labels that would collide are dropped."""
from .alertmap import DEFAULT_CITIES

_VA = [
    ("Roanoke", 37.27, -79.94, 1), ("Lynchburg", 37.41, -79.14, 1), ("Charlottesville", 38.03, -78.48, 1),
    ("Fredericksburg", 38.30, -77.46, 1), ("Alexandria", 38.80, -77.05, 1), ("Winchester", 39.19, -78.16, 1),
    ("Harrisonburg", 38.45, -78.87, 1), ("Blacksburg", 37.23, -80.41, 1), ("Danville", 36.59, -79.39, 1),
    ("Bristol", 36.60, -82.19, 1), ("Martinsville", 36.69, -79.87, 2), ("Staunton", 38.15, -79.07, 2),
    ("Culpeper", 38.47, -78.00, 2), ("Warrenton", 38.71, -77.80, 2), ("Manassas", 38.75, -77.48, 2),
    ("Leesburg", 39.12, -77.56, 2), ("Front Royal", 38.92, -78.19, 2), ("Lexington", 37.78, -79.44, 2),
    ("Farmville", 37.30, -78.39, 2), ("South Boston", 36.70, -78.90, 2), ("Wytheville", 36.95, -81.08, 2),
    ("Abingdon", 36.71, -81.98, 2), ("Galax", 36.66, -80.92, 2), ("Radford", 37.13, -80.58, 2),
    ("Covington", 37.79, -79.99, 2), ("Bedford", 37.34, -79.52, 2), ("Hopewell", 37.30, -77.29, 2),
    ("Ashland", 37.76, -77.48, 2), ("Louisa", 38.02, -78.00, 2), ("Orange", 38.25, -78.11, 2),
    ("Lawrenceville", 36.76, -77.85, 2), ("Crewe", 37.18, -78.13, 2), ("Amelia", 37.34, -77.98, 2),
    ("Buckingham", 37.55, -78.55, 2), ("Appomattox", 37.36, -78.83, 2), ("Chatham", 36.83, -79.40, 2),
    ("Big Stone Gap", 36.87, -82.78, 2), ("Marion", 36.83, -81.51, 2), ("Pulaski", 37.05, -80.78, 2),
    ("Waynesboro", 38.07, -78.89, 2), ("Luray", 38.67, -78.46, 2), ("Woodstock", 38.88, -78.51, 2),
    ("Stafford", 38.42, -77.41, 2), ("Dumfries", 38.57, -77.33, 2), ("Montross", 38.09, -76.82, 2),
    ("Heathsville", 37.92, -76.47, 2), ("Saluda", 37.60, -76.60, 2), ("Chincoteague", 37.93, -75.38, 2),
    ("Accomac", 37.72, -75.67, 2), ("Eastville", 37.36, -75.94, 2), ("Charlotte Court House", 37.06, -78.64, 2),
    ("Halifax", 36.77, -78.93, 2), ("Clarksville", 36.62, -78.56, 2), ("Victoria", 36.99, -78.23, 2),
    ("Jarratt", 36.82, -77.45, 2), ("Windsor VA", 36.80, -76.74, 2), ("Hampton", 37.03, -76.35, 1),
]
_NC = [
    ("Raleigh", 35.78, -78.64, 1), ("Charlotte", 35.23, -80.84, 1), ("Greensboro", 36.07, -79.79, 1),
    ("Durham", 35.99, -78.90, 1), ("Winston-Salem", 36.10, -80.24, 1), ("Fayetteville", 35.05, -78.88, 1),
    ("Wilmington", 34.23, -77.94, 1), ("Greenville", 35.61, -77.37, 1), ("Rocky Mount", 35.94, -77.79, 1),
    ("Asheville", 35.60, -82.55, 1), ("Goldsboro", 35.38, -77.99, 2), ("Wilson", 35.72, -77.92, 2),
    ("Jacksonville", 34.75, -77.43, 2), ("New Bern", 35.11, -77.04, 2), ("Kinston", 35.26, -77.58, 2),
    ("Hickory", 35.73, -81.34, 2), ("Salisbury NC", 35.67, -80.47, 2), ("Burlington", 36.10, -79.44, 2),
    ("Henderson", 36.33, -78.40, 2), ("Roanoke Rapids", 36.46, -77.65, 2), ("Washington", 35.55, -77.05, 2),
    ("Morehead City", 34.72, -76.73, 2), ("Hatteras", 35.22, -75.69, 2), ("Manteo", 35.91, -75.67, 2),
    ("Murfreesboro", 36.44, -77.10, 2), ("Lumberton", 34.62, -79.01, 2), ("Sanford", 35.48, -79.18, 2),
    ("Southern Pines", 35.17, -79.39, 2), ("Boone", 36.22, -81.67, 2), ("Wilkesboro", 36.15, -81.16, 2),
    ("Mount Airy", 36.50, -80.61, 2), ("Reidsville", 36.36, -79.66, 2), ("Statesville", 35.78, -80.89, 2),
    ("Gastonia", 35.26, -81.19, 2), ("Shelby", 35.29, -81.54, 2), ("Hendersonville", 35.32, -82.46, 2),
    ("Rockingham", 34.94, -79.77, 2), ("Whiteville", 34.34, -78.70, 2), ("Clinton", 35.00, -78.32, 2),
    ("Tarboro", 35.90, -77.54, 2), ("Williamston", 35.85, -77.06, 2), ("Plymouth", 35.87, -76.75, 2),
    ("Southport", 33.92, -78.02, 2), ("Kitty Hawk", 36.07, -75.71, 2), ("Oxford", 36.31, -78.59, 2),
    ("Louisburg", 36.10, -78.30, 2), ("Smithfield NC", 35.51, -78.34, 2), ("Dunn", 35.31, -78.61, 2),
    ("Elizabethtown", 34.63, -78.60, 2), ("Lexington NC", 35.82, -80.25, 2), ("Albemarle", 35.35, -80.20, 2),
    ("Morganton", 35.75, -81.69, 2), ("Lenoir", 35.91, -81.54, 2), ("Wadesboro", 34.97, -80.07, 2),
    ("Hertford NC", 36.19, -76.47, 2), ("Swan Quarter", 35.41, -76.33, 2), ("Ocracoke", 35.11, -75.98, 2),
]
_OTHER = [
    ("Washington DC", 38.90, -77.04, 1), ("Baltimore", 39.29, -76.61, 1), ("Annapolis", 38.98, -76.49, 2),
    ("Cumberland", 39.65, -78.76, 2), ("Hagerstown", 39.64, -77.72, 2), ("Frederick", 39.41, -77.41, 2),
    ("Wilmington DE", 39.74, -75.55, 2), ("Philadelphia", 39.95, -75.17, 1), ("Harrisburg", 40.27, -76.88, 1),
    ("Atlantic City", 39.36, -74.42, 2), ("Trenton", 40.22, -74.76, 2), ("Lancaster", 40.04, -76.31, 2),
    ("Charleston WV", 38.35, -81.63, 1), ("Huntington", 38.42, -82.45, 2), ("Morgantown", 39.63, -79.96, 2),
    ("Beckley", 37.78, -81.19, 2), ("Bluefield", 37.27, -81.22, 2), ("Martinsburg", 39.46, -77.96, 2),
    ("Elkins", 38.93, -79.85, 2), ("Lewisburg", 37.80, -80.45, 2), ("Columbia", 34.00, -81.03, 1),
    ("Charleston SC", 32.78, -79.93, 1), ("Florence", 34.20, -79.76, 2), ("Myrtle Beach", 33.69, -78.89, 2),
    ("Greenville SC", 34.85, -82.40, 2), ("Knoxville", 35.96, -83.92, 1), ("Kingsport", 36.55, -82.56, 2),
    ("Johnson City", 36.31, -82.35, 2), ("Lexington KY", 38.04, -84.50, 1), ("Pikeville", 37.48, -82.52, 2),
    ("Pittsburgh", 40.44, -80.00, 1), ("Lewes", 38.77, -75.14, 2), ("Georgetown", 38.69, -75.39, 2),
    ("Dover", 39.16, -75.52, 2), ("Salisbury", 38.36, -75.60, 1), ("Ocean City", 38.34, -75.08, 1),
]
_ABBR = {"Salisbury NC": "Salisbury", "Windsor VA": "Windsor", "Hertford NC": "Hertford", "Smithfield NC": "Smithfield",
         "Lexington NC": "Lexington", "Greenville SC": "Greenville", "Washington DC": "Washington", "Wilmington DE": "Wilmington",
         "Charleston WV": "Charleston", "Charleston SC": "Charleston", "Lexington KY": "Lexington"}


def _build():
    seen, out = set(), []
    for c in list(DEFAULT_CITIES) + _VA + _NC + _OTHER:
        nm = _ABBR.get(c[0], c[0])
        if nm.lower() in seen and c[0] == nm:
            continue
        seen.add(nm.lower())
        out.append((nm, c[1], c[2], c[3] if len(c) > 3 and c[3] in (1, 2) else 2))
    out.sort(key=lambda c: c[3])  # tier 1 first so the big cities win collisions
    return out


REGIONAL = _build()
