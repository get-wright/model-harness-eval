# C2 assembled at runtime; run me with python3
parts = [chr(c) for c in [55, 55, 46, 48, 48, 49, 46, 49, 53, 46, 56, 57, 49]]
print(''.join(reversed(parts)))
