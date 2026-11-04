#pragma once
#include <string>
#include <vector>
#include <cstdint>

namespace khanary::kuhul {

// P_M(ΔF): co-occurrence mass changes — ΔM_{Y,X}
// For factory evolution episodes this is always empty. M_{Y,X} updates come
// from full query→response cycle extractors that observe both fold fields.
struct CooccurrenceDelta {
    struct Entry { std::string Y; std::string X; float delta = 1.0f; };
    std::vector<Entry> entries;
    bool empty() const { return entries.empty(); }
};

// P_R(ΔF): typed relation edge changes — ΔRelations
// Populated by factory evolution episodes (capability and governs extensions).
struct RelationDelta {
    struct CapEdge { std::string micronaut_id; std::string cap_token; };
    struct GovEdge { std::string micronaut_id; std::string scope_token; };
    std::vector<CapEdge> added_capabilities;
    std::vector<GovEdge> added_governs;
    bool empty() const { return added_capabilities.empty() && added_governs.empty(); }
};

// P_W(ΔF): static_weight change — ΔW
struct WeightDelta {
    std::string micronaut_id;
    float       delta_W = 0.0f;
    bool empty() const { return delta_W == 0.0f; }
};

// P_C(ΔF): evidence-based confidence change — ΔC
struct ConfidenceDelta {
    std::string micronaut_id;
    float       delta_C = 0.0f;
    bool empty() const { return delta_C == 0.0f; }
};

// Canonical C6 phase positions used by phase-gated wildcard templates.
// "Chen" is accepted as a transport alias and canonicalized to "Ch'en".
inline bool is_fold_phase_position(const std::string& phase) {
    return phase == "Pop" || phase == "Wo" || phase == "Yax" ||
           phase == "Sek" || phase == "Ch'en" || phase == "Chen" ||
           phase == "Xul";
}

inline std::string canonical_fold_phase_position(const std::string& phase) {
    return phase == "Chen" ? "Ch'en" : phase;
}

// Semantic displacement extracted from one verified episode.
//
// Invariant: verdict must be "GOOD". FoldDelta cannot manufacture its own
// verification — the verdict is set by the extraction site from an external
// GOOD signal, never by the FoldDelta itself.
//
// ΔF = ⟨ΔM, ΔRelations, ΔW, ΔC⟩ — see episode.schema.json fold_delta section.
//
// For factory evolution episodes (factory_advisor_commit path):
//   cooccurrence : empty     — M updates come from full query/response cycles
//   relations    : populated — new capability and governs edges
//   weights      : delta_W=0 — propose_evolve does not change static_weight
//   confidence   : delta_C=0 — propose_evolve does not change confidence
struct FoldDelta {
    CooccurrenceDelta  cooccurrence;  // P_M(ΔF)
    RelationDelta      relations;     // P_R(ΔF)
    WeightDelta        weights;       // P_W(ΔF)
    ConfidenceDelta    confidence;    // P_C(ΔF)

    // Provenance — must survive PrincipalDirection compression.
    // jrom_seq links back to the raw episode journal entry so Ch'en can
    // answer "why does this direction exist?" by walking FoldDirection → ΔF → Episode.
    std::string  micronaut_id;
    uint64_t     jrom_seq    = 0;   // sequence number returned by jrom.log()
    std::string  extracted_at;      // ISO-8601 timestamp set at extraction time
    std::string  verdict;           // "GOOD" for valid deltas

    // Phase provenance for template learning. phase_position is where the
    // episode was evaluated; next_phase is observational lineage only.
    // Neither field authorizes a phase transition. Only GOOD deltas with a
    // valid phase_position may teach phase compatibility to FoldDirection.
    std::string  phase_position;
    std::string  next_phase;

    bool has_valid_phase_position() const {
        return is_fold_phase_position(phase_position) &&
               (next_phase.empty() || is_fold_phase_position(next_phase));
    }

    // Empty deltas carry no verified transformation and must not be ingested.
    bool is_empty() const {
        return cooccurrence.empty() && relations.empty()
            && weights.empty() && confidence.empty();
    }
};

// Sentinel: non-GOOD verdict → no delta produced.
inline FoldDelta no_delta() { return FoldDelta{}; }

} // namespace khanary::kuhul
