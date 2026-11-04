#include "phase.hpp"
#include <string>
#include <vector>

namespace kuhul::phase {

OperatorContract contract(Operator op) {
    switch (op) {
    case Operator::Map: return {op, ValueType::Lane, ValueType::Lane, false};
    case Operator::Filter: return {op, ValueType::Lane, ValueType::Lane, false};
    case Operator::Fold: return {op, ValueType::Any, ValueType::Accumulator, true};
    case Operator::Reduce: return {op, ValueType::Lane, ValueType::Result, false};
    }
    return {op, ValueType::Any, ValueType::Any, false};
}

struct OperatorPlan {
    Name phase;
    std::vector<Operator> operators;
};

// Operators are data transformations. Phases retain execution authority.
OperatorPlan defaultOperators(Name phase) {
    switch (phase) {
    case Name::Pop:   return {phase, {Operator::Map}};
    case Name::Wo:    return {phase, {Operator::Filter, Operator::Fold}};
    case Name::Yax:   return {phase, {Operator::Map, Operator::Filter}};
    case Name::Sek:   return {phase, {Operator::Map, Operator::Filter, Operator::Fold, Operator::Reduce}};
    case Name::Chen:  return {phase, {Operator::Filter, Operator::Reduce}};
    case Name::Xul:   return {phase, {Operator::Fold}};
    }
    return {phase, {}};
}

bool validateOperatorPlan(const OperatorPlan& plan) {
    for (const auto op : plan.operators)
        if (!operatorAuthorized(plan.phase, op)) return false;
    return true;
}

struct ExecutionGate {
    bool operatorAllowed = false;
    bool laneAllowed = false;
    bool semanticAdmission = false;
    bool verified = false;
    bool commitAuthorized = false;
    bool accumulatorReady = false;
};

bool validateExecutionGate(Name phase, Operator op, const ExecutionGate& gate) {
    if (!operatorAuthorized(phase, op) || !gate.operatorAllowed) return false;
    if (!laneAuthorized(gate.laneAllowed, gate.semanticAdmission)) return false;
    if (phase == Name::Xul) return foldClosable(gate.verified, gate.commitAuthorized, gate.accumulatorReady);
    return true;
}

}
