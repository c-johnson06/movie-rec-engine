import os
import asyncio
import numpy as np
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from maniac import convert_stars_to_numerical
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from themoviedb import aioTMDb
from letterboxdpy import user
from collections import Counter

load_dotenv()
app = Flask(__name__)
CORS(app)

print("Loading AI model...")
ai_model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model loaded.")

api_key = os.environ.get("API_KEY")
if not api_key:
    raise ValueError("API_KEY not found in environment variables.")
tmdb_client = aioTMDb(key=api_key)
print("TMDb client initialized successfully.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({"error": "Username is required"}), 400

    try:
        recommendations = asyncio.run(get_ai_recommendations(username))
        return jsonify(recommendations)
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to generate recommendations."}), 500

async def get_ai_recommendations(username):
    films_to_process = await fetch_user_film_data(username)
    if not films_to_process: return []

    enriched_films = await enrich_films_with_tmdb(films_to_process)
    final_film_list = [film for film in enriched_films if film]
    
    highly_rated_films = [
        film for film in final_film_list
        if film.get("NumericalRating") is not None and film.get("NumericalRating") >= 4.0 and film.get("tmdb_overview")
    ]
    if not highly_rated_films:
        print("Not enough highly rated films to create profile.")
        return []
    
    genre_counts = Counter(g for film in highly_rated_films for g in film.get('tmdb_genres', []))
    user_top_genres = {name for name, count in genre_counts.most_common(5)}
    print(f"User's top genres determined: {user_top_genres}")

    director_counts = Counter(film.get('tmdb_director') for film in highly_rated_films if film.get('tmdb_director'))
    user_top_directors = {name for name, count in director_counts.most_common(3)}
    print(f"User's top directors determined: {user_top_directors}")

    actor_counts = Counter(actor for film in highly_rated_films for actor in film.get('tmdb_cast', []))
    user_top_actors = {name for name, count in actor_counts.most_common(5)}
    print(f"User's top actors determined: {user_top_actors}")
    
    user_taste_vector = create_user_taste_vector(highly_rated_films)

    candidate_summaries = await fetch_candidate_films(highly_rated_films)
    if not candidate_summaries: return []

    enriched_candidates = await enrich_candidate_films(candidate_summaries)

    return score_and_rank_candidates(user_taste_vector, enriched_candidates, films_to_process, user_top_genres, user_top_directors, user_top_actors)

async def fetch_user_film_data(username):
    print(f"Fetching films for {username}...")
    user_instance = user.User(username)
    films_watched_data = user.user_films_rated(user_instance)
    films_to_process = []
    for title, id, slug, rating in films_watched_data:
        films_to_process.append({
            "Title": title,
            "Slug": slug,
            "Rating": rating,
            "NumericalRating": convert_stars_to_numerical(rating)
        })
    return films_to_process

async def enrich_films_with_tmdb(films_to_process):
    tasks = [fetch_tmdb_details(film_dict) for film_dict in films_to_process]
    print(f"Starting concurrent fetching of {len(tasks)} TMDb details...")
    enriched_films = await asyncio.gather(*tasks)
    print("All TMDb details fetched.")
    return enriched_films

async def fetch_tmdb_details(film_dict):
    try:
        await asyncio.sleep(0.1)
        search_results = await tmdb_client.search().movies(film_dict['Title'])
        if search_results:
            details = await tmdb_client.movie(search_results[0].id).details(append_to_response="credits")
            director = next((member.name for member in details.credits.crew if member.job == 'Director'), None)
            cast = [member.name for member in details.credits.cast[:5]]
            
            film_dict.update({
                'tmdb_id': details.id, 'tmdb_title': details.title,
                'tmdb_genres': [g.name for g in details.genres],
                'tmdb_overview': details.overview,
                'tmdb_director': director,
                'tmdb_cast': cast
            })
            return film_dict
    except Exception as e:
        print(f"  -> Error processing details for {film_dict.get('Title')}: {e}")
    return None

def create_user_taste_vector(highly_rated_films):
    top_movie_overviews = [film['tmdb_overview'] for film in highly_rated_films]
    print(f"\nGenerating plot embeddings for {len(highly_rated_films)} top-rated films...")
    user_top_movie_vectors = ai_model.encode(top_movie_overviews)
    return np.mean(user_top_movie_vectors, axis=0)

async def enrich_candidate_films(candidate_summaries):
    print(f"Enriching {len(candidate_summaries)} candidate films with full details...")
    tasks = [tmdb_client.movie(summary.id).details(append_to_response="credits") for summary in candidate_summaries]
    try:
        enriched_candidates = await asyncio.gather(*tasks, return_exceptions=True)
        return [c for c in enriched_candidates if not isinstance(c, Exception)]
    except Exception as e:
        print(f"A critical error occurred during candidate enrichment: {e}")
        return []

async def fetch_candidate_films(highly_rated_films: list):
    print("\nFetching candidates using diverse seed movies...")
    candidates = {}
    if not highly_rated_films: return []
    
    genre_counts = Counter(genre for film in highly_rated_films for genre in film.get('tmdb_genres', []))
    top_genres = {genre_name for genre_name, count in genre_counts.most_common(3)}
    
    seed_movies = []
    seen_ids = set()
    for genre in top_genres:
        for film in highly_rated_films:
            if genre in film.get('tmdb_genres', []) and film['tmdb_id'] not in seen_ids:
                seed_movies.append(film)
                seen_ids.add(film['tmdb_id'])
    
    if not seed_movies: seed_movies.append(highly_rated_films[0])
    tasks = [tmdb_client.movie(seed['tmdb_id']).recommendations() for seed in seed_movies]
    print(seed_movies)
    try:
        pages = await asyncio.gather(*tasks, return_exceptions=True)
        for page in pages:
            if isinstance(page, Exception): continue
            for movie in page.results:
                if movie.overview: candidates[movie.id] = movie
    except Exception as e:
        print(f"Error gathering recommendations: {e}")

    print(f"Fetched {len(candidates)} unique candidate summaries.")
    return list(candidates.values())

def score_and_rank_candidates(user_taste_vector, candidate_films, films_to_process, user_top_genres: set, user_top_directors: set, user_top_actors: set):
    print("\nScoring and ranking candidates with hybrid model (Plot + Genre + Director + Actor)...")
    valid_candidates = [c for c in candidate_films if c.overview and hasattr(c, 'genres') and hasattr(c, 'credits')]
    candidate_overviews = [c.overview for c in valid_candidates]
    candidate_vectors = ai_model.encode(candidate_overviews)
    
    similarity_scores = cosine_similarity(user_taste_vector.reshape(1, -1), candidate_vectors)[0]
    
    ai_recommendations = []
    seen_titles = {film['Title'] for film in films_to_process}
    
    for candidate, plot_score in zip(valid_candidates, similarity_scores):
        if candidate.title not in seen_titles:
            genre_score = 0
            for genre in candidate.genres:
                if genre.name in user_top_genres:
                    genre_score += 1
            normalized_genre_score = genre_score / (len(user_top_genres) + 1e-6)

            director_score = 0
            candidate_director = next((member.name for member in candidate.credits.crew if member.job == 'Director'), None)
            if candidate_director and candidate_director in user_top_directors:
                director_score = 1.0

            actor_score = 0
            candidate_cast = [member.name for member in candidate.credits.cast[:5]]
            for actor in candidate_cast:
                if actor in user_top_actors:
                    actor_score += 1
            normalized_actor_score = actor_score / (len(user_top_actors) + 1e-6)

            final_score = (0.55 * plot_score) + (0.20 * normalized_genre_score) + (0.15 * director_score) + (0.10 * normalized_actor_score)

            ai_recommendations.append({
                "title": candidate.title,
                "score": float(final_score),
                "overview": candidate.overview,
                "poster_path": candidate.poster_path,
                "tmdb_id": candidate.id,
                "director": candidate_director,
                "genres": [genre.name for genre in candidate.genres]
            })
            
    return sorted(ai_recommendations, key=lambda x: x['score'], reverse=True)[:50]

if __name__ == '__main__':
    app.run(debug=True)