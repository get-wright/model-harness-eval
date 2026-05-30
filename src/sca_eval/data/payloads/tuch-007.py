import os
# falls back to the hard-coded C2 when EnvC2 is unset
print(os.environ.get('EnvC2', '192.0.2.123'))
