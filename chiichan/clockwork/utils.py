def stars(rating):
    rounded = round(rating*2)/2
    floored = int(rounded)
    return ('⭐' * floored) + ('✨' if rounded > floored else '')
