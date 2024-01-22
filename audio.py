import Levenshtein

from crud import get_songs

songs_list = [
    {
        "title": "Tunakuje Mbele Zako",
        "lyrics": "Bwana ni Mchunga, Sitahitaji;Majani mabichi malisho yangu, Ananinywesha maji matulivu;Atanirudisha nikipotea.\n\nNipitapo bondeni mwa mauti, U Mlinzi wangu- Sitaogopa;Fimbo lako latosha kunilinda;Ukinifariji sina hasara.\n\nKati ya mateso meza waandaa, Na kikombe changu kinafurika;Umenipaka kichwani mafuta;Nitaulizaje zaidi kwako?\n\nWema na fadhili zinifuateSiku zangu zote hata milele;Nami nitakaa nyumbani mwa BwanaKatika ufalme wa pendo lake",
        "filename": "Pipeline Youth - Bwana Ni Mchunga.mp3"
    },
]


def search_song(search_term):
    songs = get_songs()
    similarity_scores = []

    for song in songs:
        similarity_score = Levenshtein.distance(search_term, song.lyrics, weights=(1, 1, 1))
        similarity_scores.append((song.title, similarity_score))

    sorted_results = sorted(similarity_scores, key=lambda x: x[1])

    return sorted_results[:8]


def handle_request():

    pass
