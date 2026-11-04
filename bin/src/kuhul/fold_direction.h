#pragma once
#include "fold_delta.h"
#include "../io/jrom.h"
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <mutex>
#include <cstdint>
#include <optional>

namespace khanary::kuhul {

// A reusable verified semantic transformation derived from one or more FoldDeltas.
// FoldDirection_i = ⟨ΔF_i, K_i, W_i, C_i, Evidence_i, Provenance_i⟩
//
// capability_key is the PrincipalDirection for discrete capability tokens:
// the sorted union/consensus across all GOOD FoldDeltas that contributed.
// This is the "PCA = one provider implementation" principle applied to tokens:
// union-consensus IS the principal direction for a discrete token space.
struct FoldDirection {
    std::string id;  // grouping key (micronaut_id for factory evolution episodes)

    // K_i: retrieval key — sorted union of all verified capability tokens across
    // every FoldDelta that contributed to this direction.
    std::vector<std::string> capability_key;
    std::vector<std::string> governs_key;

    // Verified phase positions observed on GOOD source deltas. This is learned
    // compatibility evidence for an already phase-legal template; it never
    // expands the template's declared phase set.
    std::vector<std::string> phase_key;

    // W_i and C_i remain at neutral priors (1.0, 0.5) until a component that
    // observes BOTH GOOD and BAD verdicts updates them.
    // Updating these from GOOD-only ingest creates a ratchet: C can rise but
    // never fall. That is the reinforced_confidence bug shape — usage/count
    // dressed as f(Evidence). Verdict-driven W/C reinforcement is a separate
    // future component. See episode.contract.json verdict_contract.
    float W = 1.0f;
    float C = 0.5f;

    // Provenance: back-link to every source ΔF in the JROM journal.
    // Survives PrincipalDirection compression so Ch'en can answer
    // "why does this direction exist?" by walking FoldDirection → ΔF → Episode.
    std::unordered_set<uint64_t> source_jrom_seqs;
    uint32_t                     episode_count = 0;
    std::string                  last_updated;
};

// Stores, groups, and retrieves FoldDirections derived from verified GOOD episodes.
//
// Group key: micronaut_id — all capability-evolution FoldDeltas for one micronaut
// contribute to one FoldDirection. Its capability_key is the union/consensus of
// all verified capability tokens: the stable profile of what this micronaut has
// been extended to handle.
//
// Retrieval: R_i = Jaccard(query_caps, capability_key_i)
// Scoring:   S_i = W_i * C_i * R_i  (same WCR algebra as candidate selection)
//
// Rebuild invariant: rebuild_from_jrom is safe to call repeatedly.
// Idempotency is keyed on jrom_seq: already-ingested seqs are skipped.
// "DirectionLibrary is derived from the journal; re-project, do not re-collect."
class DirectionStore {
public:
    DirectionStore() = default;

    // Ingest one FoldDelta. Preconditions:
    //   delta.verdict == "GOOD"
    //   delta.micronaut_id non-empty
    //   delta.jrom_seq not already ingested (idempotency check; 0 skips check)
    // Returns true if the delta was newly ingested, false otherwise.
    bool ingest(const FoldDelta& delta);

    // Replay all "fold_delta" events from the JROM journal and ingest each one.
    // Already-seen jrom_seqs are skipped, so this may be called repeatedly.
    // Returns count of newly ingested deltas.
    uint32_t rebuild_from_jrom(const io::JROM& jrom);

    struct QueryResult {
        std::string   direction_id;
        float         R;        // Jaccard(query_caps, capability_key)
        float         score;    // W * C * R
        FoldDirection direction; // snapshot copy — valid after lock release
    };

    // Rank all FoldDirections by W*C*R. R = Jaccard(query_caps, capability_key).
    // Results with score < min_score are excluded. Returns descending by score.
    // Pure ranking primitive — does not modify state.
    std::vector<QueryResult> query(
        const std::vector<std::string>& query_caps,
        float min_score = 0.0f) const;

    // Phase-aware retrieval for wildcard-template admission. The caller must
    // first enforce the template's declared hard phase gate. This method then
    // ranks only directions backed by GOOD deltas at current_phase.
    std::vector<QueryResult> query_at_phase(
        const std::vector<std::string>& query_caps,
        const std::string& current_phase,
        float min_score = 0.0f) const;

    bool allows_phase(const std::string& id,
                      const std::string& current_phase) const;

    // Direct lookup by direction id (micronaut_id).
    // Snapshot lookup: safe across concurrent ingest and rehash.
    // Callers must handle std::nullopt for an unknown id.
    std::optional<FoldDirection> get(const std::string& id) const;

    std::vector<std::string> list() const;
    size_t size() const;

private:
    std::vector<QueryResult> query_impl(
        const std::vector<std::string>& query_caps,
        const std::string* current_phase,
        float min_score) const;

    std::unordered_map<std::string, FoldDirection> store_;
    mutable std::mutex mtx_;
};

} // namespace khanary::kuhul
