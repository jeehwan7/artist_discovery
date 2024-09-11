import json
import secrets
from collections import Counter
from flask import Flask, render_template, redirect, request, session
import requests

app = Flask(__name__)

app.secret_key = secrets.token_hex(16)

BASE_URL = 'https://api.spotify.com/v1'

CLIENT_ID = 'a16f36bdf38d4a64b2470ee09e711267'
CLIENT_SECRET = '51900b6805e94234b1bcb87a0b667490'
REDIRECT_URI = 'http://127.0.0.1:5000/callback'

SCOPE = 'user-library-read user-follow-read user-top-read'
SHOW_DIALOG = True


@app.route('/authorize')
def authorize():
    auth_url = f'https://accounts.spotify.com/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope={SCOPE}&show_dialog={SHOW_DIALOG}'
    return redirect(auth_url)


@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'GET':
        return render_template('index.html')
    else:
        return redirect('/recommend')


@app.route('/callback')
def callback():
    session.clear()
    code = request.args.get('code')

    auth_token_url = f'https://accounts.spotify.com/api/token'
    res = requests.post(auth_token_url, data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    })

    res_body = res.json()
    session['token'] = res_body.get('access_token')

    return redirect('/recommend')


@app.route('/recommend', methods=['GET'])
def recommend():
    token = session.get('token', None)
    if not token:
        return redirect('/authorize')

    headers = {
        'Authorization': f'Bearer {token}'
    }

    # list of ids of artists from saved albums
    response = requests.get(f'{BASE_URL}/me/albums', headers=headers)
    album_artists = []
    try:
        response = response.json()
        for album in response["items"]:
            album_artists.append(album["album"]["artists"][0]["id"])
    except json.decoder.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")

    # list of ids of followed artists
    response = requests.get(f'{BASE_URL}/me/following?type=artist', headers=headers)
    followed_artists = []
    try:
        response = response.json()
        for artist in response["artists"]["items"]:
            followed_artists.append(artist["id"])
    except json.decoder.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")

    # list of ids of top artists (medium term)
    response = requests.get(f'{BASE_URL}/me/top/artists?time_range=medium_term&limit=20', headers=headers)
    top_artists = []
    try:
        response = response.json()
        for artist in response["items"]:
            top_artists.append(artist["id"])
    except json.decoder.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")

    # list of ids of related artists from top artists
    rel_top_artists = []
    for id in top_artists:
        response = requests.get(f'{BASE_URL}/artists/{id}/related-artists', headers=headers)
        try:
            response = response.json()
            for artist in response["artists"]:
                rel_top_artists.append(artist["id"])
        except json.decoder.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

    # list of ids of "already familiar artists"
    alr_familiar_artists = list(set(album_artists + followed_artists + top_artists))

    # list of potential recommendations
    # excludes "already familiar artists"
    potential_recs = [id for id in rel_top_artists if id not in alr_familiar_artists]

    # dictionary of popularities of potential recommendations (remove artists above threshold)
    threshold = 40

    popularities = {}
    removals = []
    for id in list(set(potential_recs)):
        response = requests.get(f'{BASE_URL}/artists/{id}', headers=headers)
        response = response.json()
        popularity = response["popularity"]
        if popularity > threshold:
            removals.append(id)
        else:
            popularities[id] = popularity

    revised_potential_recs = [id for id in potential_recs if id not in removals]

    # dictionary of number of appearnces in potential_recs
    appearances = Counter(revised_potential_recs)

    # weightings
    m = 10 # for appearance
    n = -1 # for popularity

    # the "algorithm"
    rec_likelihoods = {}
    for id in list(set(revised_potential_recs)):
        rec_likelihoods[id] = m * appearances[id] + n * popularities[id]

    # sort in descending order
    recommendations = sorted(rec_likelihoods, key=rec_likelihoods.get, reverse=True)

    # max number of recommendations: 10
    if len(recommendations) > 10:
        recommendations = recommendations[:10]

    names = []
    for id in recommendations:
        response = requests.get(f'{BASE_URL}/artists/{id}', headers=headers)
        response = response.json()
        names.append(response["name"])

    return render_template('recommendations.html', names=names, ids=recommendations)


if __name__ == '__main__':
    app.run(debug=True)
