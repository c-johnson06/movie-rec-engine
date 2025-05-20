import os
from dotenv import load_dotenv
from maniac import convert_stars_to_numerical
from tmdbv3api import TMDb, Movie
from letterboxdpy import user

load_dotenv()

tmdb = TMDb()
tmdb_movie_api = Movie()
letterboxd_username = "Borris"

key_in_env = "API_KEY"
retrieved_tmdb_api_key = os.environ.get(key_in_env)

if retrieved_tmdb_api_key:
    tmdb.api_key = retrieved_tmdb_api_key
    print(f"API key loaded successfully.")

try:
    user_instance = user.User(letterboxd_username)
    films_watched_data = user.user_films_rated(user_instance)
    
    films_watched = [] 
    for title, id, slug, rating in films_watched_data:
        films_watched.append({
            "Title":title,
            'ID':id,
            "Slug":slug,
            "Rating":rating
        })
    
    if films_watched:
        for film in films_watched:
            film["NumericalRating"] = convert_stars_to_numerical(film['Rating'])
            try:
                search_results = tmdb_movie_api.search(f"{film['Title']}")
                if search_results:
                    tmdb_id = search_results[0].id
                    details = tmdb_movie_api.details(tmdb_id)

            except Exception as e:
                print("Error:", e)
          
    else:
        print(f"Empty list for {letterboxd_username} or an error occured.")
    
except Exception as e:
    print("Error:", e)