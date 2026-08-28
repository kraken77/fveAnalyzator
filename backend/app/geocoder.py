import requests

def get_coordinates(address: str):
    """
    Fetches latitude and longitude for a given address using Open-Meteo Geocoding API.
    
    Args:
        address (str): The address to geocode.
        
    Returns:
        dict: A dictionary with 'lat', 'lon', and 'display_name' or None if not found.
    """
    if not address:
        return None
        
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": address,
        "count": 1,
        "language": "cs", # Prefer Czech results
        "format": "json"
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "results" in data and data["results"]:
            result = data["results"][0]
            # Construct display name from available fields
            name = result.get("name", "")
            admin1 = result.get("admin1", "")
            country = result.get("country", "")
            display_name = ", ".join(filter(None, [name, admin1, country]))
            
            return {
                "lat": float(result["latitude"]),
                "lon": float(result["longitude"]),
                "display_name": display_name
            }
        return None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None

if __name__ == "__main__":
    # Quick test
    test_address = "Prague"
    coords = get_coordinates(test_address)
    print(f"Coordinates for '{test_address}': {coords}")
