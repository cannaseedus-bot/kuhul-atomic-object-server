#include <algorithm>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace kuhul::vectors {

enum class Phase { Pop, Wo, Yax, Sek, Chen, Xul };
enum class FoldState { Pending, Verifying, LocallyCommitted, Rejected };

struct FoldInstance {
    Phase phase = Phase::Pop;
    FoldState state = FoldState::Pending;
    std::string parent;
    std::unordered_map<std::string, std::string> bindings;
    std::vector<std::string> evidence;
    std::string result;
    bool authorized = false;
};

struct FieldRef {
    std::string role;
    std::string lane;
    FoldInstance fold;
};

// Lane definitions are immutable semantic references. FoldInstance is always local.
struct Lane {
    std::string glyph;
    std::string vectorRef;
    std::unordered_map<std::string, FieldRef> fields;
};

class VectorRegistry {
public:
    void define(Lane lane) { lanes_[lane.glyph] = std::move(lane); }

    const Lane& resolve(const std::string& glyph) const {
        auto it = lanes_.find(glyph);
        if (it == lanes_.end()) throw std::out_of_range("Unknown vector lane: " + glyph);
        return it->second;
    }

    bool contains(const std::string& glyph) const { return lanes_.find(glyph) != lanes_.end(); }

private:
    std::unordered_map<std::string, Lane> lanes_;
};

class VectorTraversal {
public:
    VectorTraversal(const VectorRegistry& registry, std::size_t maxDepth = 64, std::size_t maxVisits = 4096)
        : registry_(registry), maxDepth_(maxDepth), maxVisits_(maxVisits) {}

    FoldInstance enter(const std::string& glyph, const std::string& parent = {}) {
        if (path_.size() >= maxDepth_) throw std::runtime_error("Vector traversal maxDepth exceeded");
        if (++visits_ > maxVisits_) throw std::runtime_error("Vector traversal maxVisits exceeded");
        if (std::find(path_.begin(), path_.end(), glyph) != path_.end())
            throw std::runtime_error("Active-path cycle detected at lane: " + glyph);
        registry_.resolve(glyph);
        path_.push_back(glyph);
        FoldInstance fold;
        fold.parent = parent;
        instances_.push_back(fold);
        return fold;
    }

    void verify(FoldInstance& fold, std::vector<std::string> evidence) {
        fold.phase = Phase::Chen;
        fold.state = FoldState::Verifying;
        fold.evidence = std::move(evidence);
    }

    void commitLocal(FoldInstance& fold, std::string result, bool authorized) {
        if (!authorized || fold.phase != Phase::Chen || fold.evidence.empty()) {
            fold.state = FoldState::Rejected;
            return;
        }
        fold.phase = Phase::Xul;
        fold.state = FoldState::LocallyCommitted;
        fold.result = std::move(result);
        fold.authorized = true;
    }

    void leave(const std::string& glyph) {
        if (path_.empty() || path_.back() != glyph) throw std::runtime_error("Traversal leave order violation");
        path_.pop_back();
    }

    const std::vector<std::string>& activePath() const { return path_; }
    std::size_t visits() const { return visits_; }

private:
    const VectorRegistry& registry_;
    std::size_t maxDepth_;
    std::size_t maxVisits_ = 0;
    std::size_t visits_ = 0;
    std::vector<std::string> path_;
    std::vector<FoldInstance> instances_;
};

} // namespace kuhul::vectors
