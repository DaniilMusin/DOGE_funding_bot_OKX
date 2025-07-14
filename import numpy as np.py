import numpy as np
import itertools


def find_symmetric_arrangements(n=3):
    """Return all 3x3 binary arrays symmetric over both axes."""
    if n != 3:
        raise ValueError("Only 3x3 symmetry supported in this example")
    results = []
    for a, b, c, d in itertools.product([0, 1], repeat=4):
        arr = np.array([
            [a, b, a],
            [c, d, c],
            [a, b, a],
        ])
        results.append(arr)
    return results


if __name__ == "__main__":
    results = find_symmetric_arrangements()
    for r in results:
        print(r, end="\n\n")
