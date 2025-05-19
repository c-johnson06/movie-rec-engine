from maniac import convert_stars_to_numerical
from letterboxdpy import user
from letterboxdpy import movie

letterboxd_username = "Borris"

try:
    user_instance = user.User(letterboxd_username)
    films_watched_data = user.user_films_rated(user_instance)
    
    films_watched = [] 
    for title, id, slug, rating in films_watched_data:
        films_watched.append({
            "Title":title,
            "Slug":slug,
            "Rating":rating
        })
    
    if films_watched:
        for film in films_watched:
            film["NumericalRating"] = convert_stars_to_numerical(film['Rating'])
            print(film)
    else:
        print(f"Empty list for {letterboxd_username} or an error occured.")
    
except Exception as e:
    print("Error:", e)