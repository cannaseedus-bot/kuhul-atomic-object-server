"""
pi_kuhul_roots.py
Root system unfoldings → π-KUHUL slice weights and quiver adjacency.

Implements Table 2.1 (Felikson, Tumarkin, Yildirim):
  Lines 1-4:  Crystallographic  Bn, Cn, F4, G2
  Lines 5-6:  Non-crystallographic  H3 (D6→H3), H4 (E8→H4)
  Lines 7-13: Dihedral  I2(n), including E6/E7/E8→I2(12/18/30)

Primary use: supply π-phase weights to the field slices (TensorFieldCard,
CardField). A deck of n slices uses A_n → I2(n+1), giving n
Chebyshev-weighted nodes arranged in a directed cycle.
The model uses 64 slices.
"""

import math
from typing import List, Tuple, Dict

PHI = (1 + math.sqrt(5)) / 2       # golden ratio = 2 cos(π/5) ≈ 1.6180339
TAU = 2 * math.pi

# ── Chebyshev polynomial of second kind ─────────────────────────────────────

def cheby_U(i: int, x: float) -> float:
    """
    U_i(x)  via  U_i(cos θ) = sin((i+1)θ) / sin θ.
    Numerically stable for x ∈ (-1, 1).
    U_i(±1) = i+1 (L'Hôpital limit).
    """
    if abs(x) >= 1.0 - 1e-12:
        return float(i + 1) * (1.0 if x > 0 else (-1.0) ** i)
    theta = math.acos(max(-1.0, min(1.0, x)))
    return math.sin((i + 1) * theta) / math.sin(theta)


# ── Table 2.1 weight functions ───────────────────────────────────────────────

def weights_H3() -> List[float]:
    """Line 5: D6 → H3, 6 nodes. wi=1 (i=1,2,3), wi=φ (i=4,5,6)."""
    return [1.0, 1.0, 1.0, PHI, PHI, PHI]

def weights_H4() -> List[float]:
    """Line 6: E8 → H4, 8 nodes. wi=1 (i=1..4), wi=φ (i=5..8)."""
    return [1.0, 1.0, 1.0, 1.0, PHI, PHI, PHI, PHI]

def weights_Bn() -> Tuple[List[float], str]:
    """Line 1: D_{n+1} → Bn. Non-simply-laced 2→1 edge. Uniform weights."""
    return [1.0, 1.0], '2→1'

def weights_Cn() -> Tuple[List[float], str]:
    """Line 2: A_{2n-1} → Cn. 1→2 edge. Uniform weights."""
    return [1.0, 1.0], '1→2'

def weights_F4() -> Tuple[List[float], str]:
    """Line 3: E6 → F4. 2→1 double edge. Uniform weights."""
    return [1.0, 1.0, 1.0, 1.0], '2→1'

def weights_G2() -> Tuple[List[float], str]:
    """Line 4: D4 → G2. 3→1 triple edge. Uniform weights."""
    return [1.0, 1.0], '3→1'

def weights_I2_odd(n: int) -> List[float]:
    """
    Line 7: A_{2n} → I2(2n+1).
    n nodes in source quiver.
    w_i = U_i(cos(π/(2n+1))), i = 0 … 2n.
    Returns 2n+1 weights.
    """
    m = 2 * n + 1
    x = math.cos(math.pi / m)
    return [cheby_U(i, x) for i in range(m)]

def weights_I2_even(n: int) -> List[float]:
    """
    Line 8: A_{2n-1} → I2(2n).
    Returns 2n-1 weights: w_i = U_i(cos(π/2n)), i = 0 … 2n-2.
    """
    m = 2 * n
    x = math.cos(math.pi / m)
    return [cheby_U(i, x) for i in range(m - 1)]

def weights_D_odd(n: int) -> List[float]:
    """
    Line 9: D_{2n+1} → I2(4n).
    2n+1 nodes: wi = U_i(cos(π/4n)) for i=0..2n-2,
                wi = ½ U_{2n-1}(cos(π/4n)) for i=2n-1, 2n.
    """
    m = 4 * n
    x = math.cos(math.pi / m)
    weights = [cheby_U(i, x) for i in range(2 * n - 1)]
    tail = 0.5 * cheby_U(2 * n - 1, x)
    return weights + [tail, tail]

def weights_D_even(n: int) -> List[float]:
    """
    Line 10: D_{2n} → I2(4n-2).
    2n nodes: wi = U_i(cos(π/(4n-2))) for i=0..2n-3,
              wi = ½ U_{2n-2}(cos(π/(4n-2))) for i=2n-2, 2n-1.
    """
    m = 4 * n - 2
    x = math.cos(math.pi / m)
    weights = [cheby_U(i, x) for i in range(2 * n - 2)]
    tail = 0.5 * cheby_U(2 * n - 2, x)
    return weights + [tail, tail]

def weights_E6_I2_12() -> List[float]:
    """
    Line 11: E6 → I2(12). 6 nodes.
    wi = U_i(cos(π/12)) i=0,1,2
    w3 = √2
    w4 = w1 = U1(cos(π/12))
    w5 = w0 = 1
    """
    x = math.cos(math.pi / 12)
    return [
        cheby_U(0, x),
        cheby_U(1, x),
        cheby_U(2, x),
        math.sqrt(2),
        cheby_U(1, x),
        cheby_U(0, x),
    ]

def weights_E7_I2_18() -> List[float]:
    """
    Line 12: E7 → I2(18). 7 nodes.
    wi = U_i(cos(π/18)) i=0,1,2,3
    w4 = U1(cos(π/9))
    w5 = U2(cos(π/9))
    w6 = 2 cos(5π/18)
    """
    x18 = math.cos(math.pi / 18)
    x9  = math.cos(math.pi / 9)
    return [
        cheby_U(0, x18),
        cheby_U(1, x18),
        cheby_U(2, x18),
        cheby_U(3, x18),
        cheby_U(1, x9),
        cheby_U(2, x9),
        2 * math.cos(5 * math.pi / 18),
    ]

def weights_E8_I2_30() -> List[float]:
    """
    Line 13: E8 → I2(30). 8 nodes.
    wi = U_i(cos(π/30)) i=0..4
    w5 = φ^{-1} U3(cos(π/30))
    w6 = φ   U1(cos(π/30))
    w7 = φ   U0(cos(π/30))  = φ
    """
    x = math.cos(math.pi / 30)
    return [
        cheby_U(0, x),
        cheby_U(1, x),
        cheby_U(2, x),
        cheby_U(3, x),
        cheby_U(4, x),
        (1.0 / PHI) * cheby_U(3, x),
        PHI * cheby_U(1, x),
        PHI * cheby_U(0, x),
    ]


# ── Slice weighting over the layer stack (64 slices) ─────────────────────────

DEFAULT_CARDS = 64


def weights_cards(n: int = DEFAULT_CARDS, normalize: bool = True) -> List[float]:
    """
    n-node Chebyshev weights for a card deck.

    A_n → I2(n+1): wᵢ = Uᵢ(cos(π/(n+1))), i = 0..n-1. U₀ = 1 and the last
    term mirrors it, so the range is [1, max] without rescaling.
    """
    if n < 1:
        raise ValueError("card count must be positive")
    x = math.cos(math.pi / (n + 1))
    raw = [cheby_U(i, x) for i in range(n)]
    if normalize:
        return raw
    return raw


def weights_52_cards(normalize: bool = True) -> List[float]:
    """Back-compat: the original 52-card deck (A52 → I2(53))."""
    return weights_cards(52, normalize)


def weights_64_cards(normalize: bool = True) -> List[float]:
    """64-card deck (A64 → I2(65)); matches the shader's 64 bone clusters."""
    return weights_cards(64, normalize)

def quiver_cards(n: int = DEFAULT_CARDS) -> List[Tuple[int, int]]:
    """Directed cycle 0→1→…→n-1→0 (white→black alternating)."""
    if n < 1:
        raise ValueError("card count must be positive")
    return [(i, (i + 1) % n) for i in range(n)]


def quiver_52_cards() -> List[Tuple[int, int]]:
    return quiver_cards(52)


def quiver_64_cards() -> List[Tuple[int, int]]:
    return quiver_cards(64)


def adjacency_cards(n: int = DEFAULT_CARDS, reach: int = 4) -> List[List[int]]:
    """
    For each of n cards, return adjacent card indices over ±1..±reach,
    matching _build_deck_adjacency() with quiver-correct directionality.
    """
    if n < 1:
        raise ValueError("card count must be positive")
    adj = []
    for i in range(n):
        neighbours = [(i + k) % n for k in range(1, reach + 1)] + \
                     [(i - k) % n for k in range(1, reach + 1)]
        adj.append(neighbours)
    return adj


def adjacency_52_cards(reach: int = 4) -> List[List[int]]:
    return adjacency_cards(52, reach)


def adjacency_64_cards(reach: int = 4) -> List[List[int]]:
    return adjacency_cards(64, reach)


# ── Unified factory ───────────────────────────────────────────────────────────

UNFOLDING_REGISTRY: Dict[str, callable] = {
    'H3':     weights_H3,
    'H4':     weights_H4,
    'F4':     lambda: weights_F4()[0],
    'G2':     lambda: weights_G2()[0],
    'I2_52':  weights_52_cards,
    'I2_64':  weights_64_cards,
    'E6_I2':  weights_E6_I2_12,
    'E7_I2':  weights_E7_I2_18,
    'E8_I2':  weights_E8_I2_30,
}

def get_weights(unfolding: str, **kwargs) -> List[float]:
    """
    Return weight list for a named unfolding.
    Special: 'I2_odd(n)' and 'I2_even(n)' accept an integer n.
    """
    if unfolding.startswith('I2_odd('):
        n = int(unfolding[7:-1])
        return weights_I2_odd(n)
    if unfolding.startswith('I2_even('):
        n = int(unfolding[8:-1])
        return weights_I2_even(n)
    if unfolding not in UNFOLDING_REGISTRY:
        raise KeyError(f'Unknown unfolding: {unfolding}. '
                       f'Known: {list(UNFOLDING_REGISTRY)}')
    return UNFOLDING_REGISTRY[unfolding]()


# ── Apply weights to CardField / TensorFieldCard lists ───────────────────────

def apply_weights_to_cards(cards, unfolding: str = 'I2_64',
                           scale_to_pi: bool = True) -> None:
    """
    Assign root-system pi_mod weights to a list of CardField or TensorFieldCard
    objects in-place.

    scale_to_pi=True: pi_mod = wᵢ × π  (phase speed proportional to weight)
    scale_to_pi=False: pi_mod = wᵢ      (raw Chebyshev value)
    """
    raw = get_weights(unfolding)
    n   = len(cards)

    for i, card in enumerate(cards):
        w = raw[i % len(raw)]          # tile if cards > nodes
        pi_mod = w * math.pi if scale_to_pi else w
        if hasattr(card, 'pi_mod'):
            # CardField dataclass
            card.pi_mod = pi_mod
        elif hasattr(card, 'pi_mod') and hasattr(card, 'parameters'):
            # TensorFieldCard nn.Module — update the parameter
            import torch
            with torch.no_grad():
                card.pi_mod.fill_(pi_mod)


def card_weight_summary(unfolding: str = 'I2_64') -> str:
    """Human-readable weight summary for a given unfolding."""
    w  = get_weights(unfolding)
    mn = min(w)
    mx = max(w)
    lines = [
        f'Unfolding: {unfolding}  ({len(w)} nodes)',
        f'  weight range: [{mn:.4f}, {mx:.4f}]',
        f'  w[0..7]:  {[round(x, 4) for x in w[:8]]}',
        f'  w[-4:]:   {[round(x, 4) for x in w[-4:]]}',
        f'  pi_mod range: [{mn*math.pi:.4f}, {mx*math.pi:.4f}] rad',
    ]
    return '\n'.join(lines)


# ── WGSL kernel string ────────────────────────────────────────────────────────

def wgsl_pi_field_kernel(num_nodes: int, use_phi_branch: bool = True) -> str:
    """
    Generate a WGSL compute kernel for π-field evolution.
    Implements:  v_i^{t+1} = Σ_j  w_j · sin(π · v_j)
    with optional φ-node nonlinear branch (H3/H4 unfoldings).
    """
    phi_branch = f"""
    // φ-node: nonlinear attractor (H3/H4 unfoldings)
    if (w > 1.5) {{
        sum += w * sin({PHI:.10f} * 3.14159265358979 * v);
    }} else {{
        sum += w * sin(3.14159265358979 * v);
    }}""" if use_phi_branch else """
        sum += w * sin(3.14159265358979 * v);"""

    return f"""\
// pi_field.wgsl — π-KUHUL root system field evolution
// v_i^{{t+1}} = Σ_j  w_j · sin(π · v_j)   [φ-attractor branch for H3/H4]
// Nodes: {num_nodes}  |  Generated by pi_kuhul_roots.py

struct Params {{
    node_count : u32,
    edge_count : u32,
    step       : u32,
    pi_time    : f32,
}};

@group(0) @binding(0) var<storage, read>       nodes_in  : array<f32>;
@group(0) @binding(1) var<storage, read>       weights   : array<f32>;
@group(0) @binding(2) var<storage, read>       edges     : array<vec2<u32>>;
@group(0) @binding(3) var<storage, read_write> nodes_out : array<f32>;
@group(0) @binding(4) var<uniform>             params    : Params;

const PHI : f32 = {PHI:.10f};

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id : vec3<u32>) {{
    let i = id.x;
    if (i >= params.node_count) {{ return; }}

    var sum : f32 = 0.0;

    for (var e = 0u; e < params.edge_count; e++) {{
        let edge = edges[e];

        // Forward edge j→i (accumulate field at i)
        if (edge.y == i) {{
            let j = edge.x;
            let w = weights[j];
            let v = nodes_in[j];
            {phi_branch}
        }}

        // Backward suppression (exchange matrix B: negative direction)
        if (edge.x == i) {{
            let j = edge.y;
            let w = weights[j];
            let v = nodes_in[j];
            sum -= 0.1 * w * sin(3.14159265358979 * v);
        }}
    }}

    // Global π-time modulation
    sum = sum * (1.0 + 0.05 * sin(params.pi_time));

    nodes_out[i] = sum;
}}
"""


if __name__ == '__main__':
    # Print weight summaries for all major unfoldings
    for name in ['H3', 'H4', 'E6_I2', 'E7_I2', 'E8_I2', 'I2_52', 'I2_64']:
        print(card_weight_summary(name))
        print()