def convert_stars_to_numerical(star_rating_str):
    if not star_rating_str: 
        return None
    numerical_rating = star_rating_str.count('★')
    if '½' in star_rating_str:
        numerical_rating += 0.5
    return float(numerical_rating)