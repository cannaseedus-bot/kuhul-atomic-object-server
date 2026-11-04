#include "phase.hpp"
#include "bindings.hpp"

namespace kuhul::xcfe {

struct GateInput {
    kuhul::phase::Name phase;
    kuhul::phase::Operator op;
    bool operatorAuthorized = false;
    bool laneAuthorized = false;
    bool semanticAdmitted = false;
    bool typedContractValid = false;
    bool verified = false;
    bool commitAuthorized = false;
    bool accumulatorReady = false;
};

struct GateResult {
    bool operatorPass;
    bool lanePass;
    bool admissionPass;
    bool contractPass;
    bool closurePass;
    bool executable;
};

GateResult evaluate(const GateInput& input) {
    const bool operatorPass = input.operatorAuthorized && phase::operatorAuthorized(input.phase, input.op);
    const bool lanePass = input.laneAuthorized;
    const bool admissionPass = input.semanticAdmitted;
    const bool contractPass = input.typedContractValid;
    const bool closurePass = input.phase != phase::Name::Xul ||
        phase::foldClosable(input.verified, input.commitAuthorized, input.accumulatorReady);
    return {operatorPass, lanePass, admissionPass, contractPass, closurePass,
            operatorPass && lanePass && admissionPass && contractPass && closurePass};
}

bool canExecute(const GateInput& input) { return evaluate(input).executable; }

}
