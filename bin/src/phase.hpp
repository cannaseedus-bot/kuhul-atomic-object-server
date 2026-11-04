#pragma once
#include <string>
#include <vector>
namespace kuhul::phase {
enum class Name { Pop, Wo, Yax, Sek, Chen, Xul };
enum class Operator { Fold, Map, Filter, Reduce };
enum class ValueType { Any, Lane, Scalar, Accumulator, Result };
struct OperatorContract { Operator op; ValueType input; ValueType output; bool stateful; };
struct Driver { const char* id; Name phase; float weight; const char* verb; bool terminal; std::vector<std::string> ops; };
constexpr Name next(Name p) { return p==Name::Pop?Name::Wo:p==Name::Wo?Name::Yax:p==Name::Yax?Name::Sek:p==Name::Sek?Name::Chen:p==Name::Chen?Name::Xul:Name::Pop; }
constexpr bool legal(Name from, Name to) { return next(from)==to; }
constexpr bool operatorAuthorized(Name phase, Operator op) {
    return phase != Name::Xul || op == Operator::Fold;
}
constexpr bool laneAuthorized(bool executionAllowed, bool semanticAdmission) { return executionAllowed && semanticAdmission; }
constexpr bool foldClosable(bool verified, bool authorized, bool accumulatorReady) { return verified && authorized && accumulatorReady; }
}
