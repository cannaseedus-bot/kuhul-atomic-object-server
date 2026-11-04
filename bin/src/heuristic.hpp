#pragma once
#include <string>
#include <vector>

namespace kuhul::heuristic {
enum class Mode { Direct, Seed, Guide };
struct Candidate {
    std::string id;
    double weight = 0.0;
    double compatibility = 0.0;
    double relevance = 0.0;
    double informationGain = 0.0;
    double cost = 0.0;
    bool admitted = false;
};
struct Config { double alpha = 1.0; double beta = 1.0; };
struct Ranked { Candidate candidate; double wcr = 0.0; double score = 0.0; };
struct Proposal { Mode mode; std::vector<Ranked> ranked; bool hasSeed = false; std::string seedId; };
struct Feedback { std::string candidateId; double reward = 0.0; bool verified = false; bool authorized = false; };
double score(const Candidate& candidate, Config config = {});
std::vector<Ranked> rank(std::vector<Candidate> candidates, Config config = {});
Proposal propose(Mode mode, std::vector<Candidate> candidates, Config config = {});
bool applyFeedback(Candidate& candidate, const Feedback& feedback, double learningRate = 0.05);
}
