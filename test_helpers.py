def get_trimmed_lines(obj):
    return list(map(lambda s: s.strip(), str(obj).splitlines()))
