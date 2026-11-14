import numpy as np

from spongescope.features.site_scan import SITE_TYPES, encode, scan

LET7A = encode("UGAGGUAGUAGGUUGUAUAGUU")  # hsa-let-7a-5p, seed site CUACCUC(A)


def _types(target: str) -> dict[int, str]:
    s = scan(encode(target), LET7A)
    return {int(p): SITE_TYPES[t] for p, t in zip(s.p2, s.type_id, strict=True)}


def test_canonical_site_types_and_p2():
    pad = "CC" * 10
    # 7mer-m8 site starting at index s has p2 = s + 6
    assert _types(pad + "CUACCUCA" + pad) == {26: "8mer"}
    assert _types(pad + "CUACCUCG" + pad) == {26: "7mer_m8"}
    assert _types(pad + "GUACCUCA" + pad) == {26: "7mer_a1"}
    assert _types(pad + "GUACCUCG" + pad) == {26: "6mer"}
    assert _types(pad + "CUACCUGG" + pad)[26] == "offset_6mer"


def test_noncanonical_gu_wobble_counted():
    # let-7a nt 5 is G; target U opposite it (instead of C) is a G:U wobble
    s = scan(encode("CC" * 10 + "CUAUCUCG" + "CC" * 10), LET7A)
    i = int(np.flatnonzero(s.p2 == 26)[0])
    assert SITE_TYPES[s.type_id[i]] == "noncanonical"
    assert s.n_wobble[i] == 1 and s.wc[i].sum() == 6


def test_no_sites_in_poly_a_and_short_inputs():
    assert len(scan(encode("A" * 200), LET7A)) == 0
    assert len(scan(encode("CUACC"), LET7A)) == 0


def test_supplementary_pairing():
    mir = "UGAGGUAGUAGGUUGUAUAGUU"
    comp = {"A": "U", "C": "G", "G": "C", "U": "A"}
    # target 5'->3': [revcomp(nt13-16)] + 4 nt opposite nt 9-12 + [7mer-m8 site] + A
    supp = "".join(comp[c] for c in mir[12:16])[::-1]
    target = "GG" * 5 + supp + "GGGG" + "CUACCUC" + "A" + "GG" * 5
    s = scan(encode(target), encode(mir))
    i = int(np.flatnonzero(s.type_id == 0)[0])
    assert s.supp[i] == 4
