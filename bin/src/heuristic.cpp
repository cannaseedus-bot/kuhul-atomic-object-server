#include "heuristic.hpp"
#include <algorithm>

namespace kuhul::heuristic {

double score(const Candidate& c, Config config) {
    const double wcr = c.weight * c.compatibility * c.relevance;
    return wcr + config.alpha * c.informationGain - config.beta * c.cost;
}

std::vector<Ranked> rank(std::vector<Candidate> candidates, Config config) {
    std::vector<Ranked> ranked;
    ranked.reserve(candidates.size());
    for (const auto& candidate : candidates) {
        if (!candidate.admitted) continue;
        ranked.push_back({candidate,
            candidate.weight * candidate.compatibility * candidate.relevance,
            score(candidate, config)});
    }
    std::stable_sort(ranked.begin(), ranked.end(), [](const Ranked& a, const Ranked& b) {
        if (a.score != b.score) return a.score > b.score;
        return a.candidate.id < b.candidate.id;
    });
    return ranked;
}

Proposal propose(Mode mode, std::vector<Candidate> candidates, Config config) {
    auto ranked = rank(std::move(candidates), config);
    Proposal proposal{mode, std::move(ranked), false, {}};
    if (mode == Mode::Direct || mode == Mode::Seed) {
        if (!proposal.ranked.empty()) {
            proposal.hasSeed = true;
            proposal.seedId = proposal.ranked.front().candidate.id;
        }
    }
    return proposal;
}

bool applyFeedback(Candidate& candidate, const Feedback& feedback, double learningRate) {
    if (!feedback.verified || !feedback.authorized || feedback.candidateId != candidate.id) return false;
    const double bounded = std::max(-1.0, std::min(1.0, feedback.reward));
    candidate.weight = std::max(0.0, candidate.weight + learningRate * bounded);
    return true;
}

}
