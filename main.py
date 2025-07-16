import os
import asyncio
import time
from maniac import convert_stars_to_numerical
from dotenv import load_dotenv
from themoviedb import aioTMDb 
from letterboxdpy import user

async def main():
    load_dotenv()

    api_key = os.environ.get("API_KEY")
    if not api_key:
        print("ERROR: API key not found. Exiting.")
        return

    tmdb = aioTMDb(key=api_key)
    print("TMDb client initialized successfully.")

    letterboxd_username = "Borris"
    print(f"Fetching films for {letterboxd_username}...")
    user_instance = user.User(letterboxd_username)
    films_watched_data = user.user_films_rated(user_instance)

    films_to_process = []
    for title, id, slug, rating in films_watched_data:
        films_to_process.append({
            "Title": title,
            "Slug": slug,
            "Rating": rating,
            "NumericalRating": convert_stars_to_numerical(rating)
        })

    tasks = []
    for film_dict in films_to_process:
        task = fetch_tmdb_details(tmdb, film_dict)
        tasks.append(task)

    print(f"Starting concurrent fetching of {len(tasks)} TMDb details...")
    enriched_films = await asyncio.gather(*tasks)
    print("All TMDb details fetched.")

    final_film_list = [film for film in enriched_films if film]
    for film in final_film_list:
        if 'tmdb_id' in film:
            print(f"Enriched: {film['Title']} -> Genres: {film.get('tmdb_genres', 'N/A')}")
        else:
            print(f"Could not enrich: {film['Title']}")

async def fetch_tmdb_details(tmdb: aioTMDb, film_dict: dict):
    
    try:
        time.sleep(0.05)
        search_results = await tmdb.search().movies(film_dict['Title'])

        if search_results:
            first_result = search_results[0]
            tmdb_id = first_result.id
            
            details = await tmdb.movie(tmdb_id).details()
            
            film_dict['tmdb_id'] = details.id
            film_dict['tmdb_title'] = details.title
            film_dict['tmdb_genres'] = [g.name for g in details.genres]
            film_dict['tmdb_overview'] = details.overview

            return film_dict
        else:
            print(f"  -> No TMDb results for: {film_dict['Title']}")

    except Exception as e:
        print(f"  -> Error processing {film_dict.get('Title', 'Unknown Film')}: {e}")
    
    return None

if __name__ == "__main__":
    asyncio.run(main())