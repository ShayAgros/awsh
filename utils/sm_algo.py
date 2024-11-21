# Implementation of Smith–Waterman algorithm for string alignment
# Should be fairly similar to what FZF uses
#
# More info about the algorithm
# https://en.wikipedia.org/wiki/Smith%E2%80%93Waterman_algorithm

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

VAL_IX = 0
ISMAX_IX = 1
RMAX_IX = 2
CMAX_IX = 3
def _init_cel():
    """Create an empty cell in the scoring matrix. The
    cell has the following format:

    ([cell val], [is maximum], [row max val], [col max val]"""
    return [0, False, 0, 0]


def s(ai : str, bj : str, str_ix: int, matched_str_len : int) -> int:
    # This assumes that each column represents the string letter,
    # we want the addition for matched letters to compensate the
    # the penalty for letters which are too far apart
    #
    # Also, add a bonus value if the string matched at the beginning of the
    # string
    if ai == bj:
        return matched_str_len + (matched_str_len - str_ix)

    return -2


def w(k : int):
    """distance cost function"""
    return k


# TODO: if of necessity the column search can be improved by holding another 2D
# matrix which holds the maximum values for row and colum
def get_max(W : list, i : int, j : int, ai : str, bj : str):
    """i, j regard the previous row a column"""
    # H_(i-1, j - 1) + s(a_i, b_j)
    first_op = _init_cel()
    first_op[VAL_IX] = W[i][j][VAL_IX] + s(ai, bj, j, len(W[0]))

    # max_(k >= 1) ( H_(i - k, j) - W_k ) where W_k is the distance
    # between i and k
    # max_val_in_col = _init_cel()
    # TODO: replace this -1 with a function to calculate distance penalty
    second_op = _init_cel()
    max_val_in_col = max(W[i][j + 1][CMAX_IX], W[i][j + 1][VAL_IX] - w(1))
    second_op[0] = max_val_in_col

    # max_(k >= 1) ( H_(i, j - k) - W_k ) where W_k is the distance
    # between i and k
    third_op = _init_cel()
    max_val_in_row = max(W[i + 1][j][CMAX_IX], W[i + 1][j][VAL_IX] - w(1))
    third_op[0] = max_val_in_row

    max_val = max(first_op, second_op, third_op, _init_cel(), key = lambda e: e[VAL_IX])
    # encode the maximum value of a row and column to avoid recalculating them
    # each time
    max_val[RMAX_IX:CMAX_IX] = max_val_in_row, max_val_in_col

    return max_val


def get_sw_score(string : str, pattern : str, pattern_match_required = False,
                 retain_pat_order = False):
    strlen = len(string)
    patlen = len(pattern)

    string_match_ix = []

    # 2D matrix
    W = [[_init_cel() for _ in range(strlen + 1)]]

    max_val = _init_cel()
    max_sum = 0

    last_str_matched = 0
    # initialize scoring matrix
    for i in range(patlen):
        new_row = [_init_cel()]
        pat_letter_matched = False
        W.append(new_row)
        for j in range(strlen):
            ai = pattern[i]
            bj = string[j]

            val = get_max(W, i, j, ai, bj)
            if max_val[VAL_IX] < val[VAL_IX]:
                max_val = val
                max_sum = max_sum + max_val[VAL_IX]
                val[ISMAX_IX] = True

                string_match_ix.append(j)

                pat_letter_matched = True

                # if the user requesed that the pattern
                # is matched in order
                if retain_pat_order:
                    if j < last_str_matched:
                        return W, _init_cel(), 0, []

                    last_str_matched = j

            else:
                val[ISMAX_IX] = False

            new_row.append(val)

        # we've gone over the whole pattern and didn't find a new maximum
        # meaning that the letter isn't part of the string
        if not pat_letter_matched and pattern_match_required:
            max_sum = 0
            break

    return W, max_val, max_sum, string_match_ix


def print_scoring_table(string : str, pattern : str, W : list, max_val : list,
                        max_sum : int, string_match_ix : list):
    # print the table
    print("pat/str", end="\t\t")
    for j in range(len(W[0])):
        letter = string[j - 1] if j > 0 else ""
        print(f"j={j} {letter}", end="\t\t")

    print("")

    for i in range(len(W)):
        letter = pattern[i - 1] if i > 0 else ""
        print(f"i={i} {letter}", end="\t\t")
        for j in range(len(W[i])):
            val_str = str(W[i][j][VAL_IX])
            if W[i][j][ISMAX_IX] == True:
                val_str = bcolors.WARNING + val_str + bcolors.ENDC

            print(val_str, end="\t\t")

        print("")

    print("")

    print("max val is:", max_val[VAL_IX])
    print("sequence sum:", max_sum)
    print("matching strings ix:", string_match_ix)


def testing():
    string = "bannanas"
    pattern = "b"

    W, max_val, max_sum, string_match_ix = get_sw_score(string, pattern, True,
                                                        True)

    print_scoring_table(string, pattern, W, max_val, max_sum, string_match_ix)
    # get_sw_score("abcd", "efgk")

if __name__ == '__main__':
    testing()


