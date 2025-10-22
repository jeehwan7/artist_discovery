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

    # grab ids of saved albums' artists
    album_artists = []
    response = requests.get(f'{BASE_URL}/me/albums', headers=headers)  
    try:
        response = response.json()
        for album in response["items"]:
            album_artists.append(album["album"]["artists"][0]["id"])
    except json.decoder.JSONDecodeError as error:
        print(f"JSON decoding error: {error}")

    # grab ids of following artists
    following_artists = []
    response = requests.get(f'{BASE_URL}/me/following?type=artist', headers=headers)   
    try:
        response = response.json()
        for artist in response["artists"]["items"]:
            following_artists.append(artist["id"])
    except json.decoder.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")

    # grab ids of top artists from listening history (medium term)
    top_artists = []
    response = requests.get(f'{BASE_URL}/me/top/artists?time_range=medium_term&limit=20', headers=headers)
    try:
        response = response.json()
        for artist in response["items"]:
            top_artists.append(artist["id"])
    except json.decoder.JSONDecodeError as error:
        print(f"JSON decoding error: {error}")

    # grab ids of artists related to top artists
    # ERROR PRODUCED HERE BECAUSE SPOTIFY WEB API DISCONTINUED RELATED ARTISTS ENDPOINT
    # https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api
    potential_recs = []
    for id in top_artists:
        response = requests.get(f'{BASE_URL}/artists/{id}/related-artists', headers=headers)      
        try:
            response = response.json()
            for artist in response["artists"]:
                potential_recs.append(artist["id"])
        except json.decoder.JSONDecodeError as error:
            print(f"Error decoding JSON: {error}")

    # create list of ids of familiar artists
    familiar_artists = list(set(album_artists + following_artists + top_artists))

    # create list of potential recommendations that excludes familiar artists
    potential_recs = [id for id in potential_recs if id not in familiar_artists]

    # create dictionary of popularities of potential recommendations
    # remove artists from potential recommendations whose popularities exceed threshold
    popularities = {}
    removals = []
    threshold = 40
    for id in list(set(potential_recs)):
        response = requests.get(f'{BASE_URL}/artists/{id}', headers=headers)
        response = response.json()
        popularity = response["popularity"]
        if popularity > threshold:
            removals.append(id)
        else:
            popularities[id] = popularity

    potential_recs = [id for id in potential_recs if id not in removals]

    # create dictionary of number of appearnces in potential recommendations
    num_appearances = Counter(potential_recs)

    # weightings
    m = 10 # for number of appearances
    n = -1 # for popularity

    # calculate likelihoods
    likelihoods = {}
    for id in list(set(potential_recs)):
        likelihoods[id] = m * num_appearances[id] + n * popularities[id]

    # sort recommendations in descending order of likelihoods
    recs = sorted(likelihoods, key=likelihoods.get, reverse=True)

    # max number of recommendations: 10
    if len(recs) > 10:
        recs = recs[:10]

    # grab recommendations' names
    names = []
    for id in recs:
        response = requests.get(f'{BASE_URL}/artists/{id}', headers=headers)
        response = response.json()
        names.append(response["name"])

    return render_template('recommendations.html', names=names, ids=recommendations)


if __name__ == '__main__':
    app.run(debug=True)
