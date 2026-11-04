#pragma once
#include <string>
#include <fstream>
#include <mutex>
#include <vector>
#include <cstdint>
#include <functional>

namespace khanary::io {

struct JROMEvent {
    std::string type;
    std::string epistemic_type;
    std::string payload_json;
    uint64_t    seq;
};

// JROM: runtime tape player / provenance journal.
// Append-only typed JSONL for routed observations, proposals, calls, and outcomes.
// It preserves replay evidence; it is not semantic authority and cannot commit state.
//
// Write contract (GAP-064 / T3.5): log() serializes every row with the shared
// JSON utilities — type/epistemic fields are escaped, and the payload is
// VALIDATED as a JSON object before append. An invalid payload is refused
// (log returns 0, no seq consumed, no bytes appended, diagnostic in
// last_write_error() and stderr) — a user string can never corrupt the
// journal stream.
//
// Replay contract (GAP-065 / NG-J2): replay()/read_all() parse each line with
// the shared JSON parser. Malformed/legacy-foreign lines are skipped and
// counted in malformed_lines(); replay never throws on a corrupt journal, so
// a tampered log cannot crash startup replay (DirectionStore consumers).
class JROM {
public:
    JROM();
    explicit JROM(const std::string& path);

    bool open(const std::string& path);
    void close();

    // Append a log entry. Returns the assigned seq (>=1), or 0 when the
    // payload was not a valid JSON object and the write was refused.
    uint64_t log(const std::string& event_type, const std::string& payload_json);
    uint64_t log(const std::string& event_type,
                 const std::string& payload_json,
                 const std::string& epistemic_type);

    static bool is_valid_epistemic_type(const std::string& value);

    // Replay from offset; calls cb(event) for each valid entry.
    void replay(uint64_t from_seq,
                std::function<void(const JROMEvent&)> cb) const;

    // Read all events into vector
    std::vector<JROMEvent> read_all() const;

    uint64_t last_seq() const;
    // Rows refused by the write-side payload validator (never appended).
    uint64_t rejected_writes() const;
    // Detail of the most recent refused write; empty when none.
    std::string last_write_error() const;
    // Malformed/foreign lines skipped during the most recent replay/read.
    uint64_t malformed_lines() const;
    bool is_open() const;

    // Walk the file and verify that each entry's stored prev_hash equals the
    // SHA-256 of the previous entry line (genesis = sha256 of 64 ASCII zeros).
    // Returns true when every entry in the chain is consistent; false on any
    // malformed line, missing field, or hash mismatch.  Files written before
    // the GAP-064 chain upgrade lack chain fields and will return false.
    bool verify_chain() const;

private:
    mutable std::mutex mtx_;
    std::ofstream out_;
    std::string   path_;
    uint64_t      seq_ = 0;
    uint64_t      rejected_ = 0;
    mutable uint64_t malformed_ = 0;
    std::string   last_error_;
    std::string   run_id_;    // unique per open() session; embedded in every entry
    std::string   prev_hash_; // sha256 of the last appended entry (no trailing newline)
};

} // namespace khanary::io
