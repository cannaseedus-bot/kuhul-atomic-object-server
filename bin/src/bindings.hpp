#pragma once
#include <string>
#include <unordered_map>
#include <utility>

namespace kuhul::binding {
enum class SyncMode { Reference, Value, Field, Phase, Transpiler };
enum class SyncResult { Compatible, RequiresConversion, Conflict, Cycle };
enum class Scope { Global, Session, Lane, Phase, Fold, Capture };
enum class Kind { Glyph, Lane, Field, Vector, Capture, Phase, Accumulator, Result, Transpiler };
struct Binding { std::string name; std::string value; Kind kind; Scope scope; bool resolved=false; bool typeValid=false; bool writeAllowed=false; bool executeAllowed=false; bool semanticAdmitted=false; };
struct BindingSync { std::string source; std::string target; SyncMode mode; std::string sourceType; std::string targetType; unsigned long long revision=0; };
class Environment {
public:
    void bind(Binding binding) { bindings_[binding.name]=std::move(binding); }
    const Binding* resolve(const std::string& name) const { auto it=bindings_.find(name); return it==bindings_.end()?nullptr:&it->second; }
    bool executable(const std::string& name) const { const auto* b=resolve(name); return b && b->resolved && b->typeValid && b->executeAllowed && b->semanticAdmitted; }
    SyncResult synchronize(const BindingSync& sync);
    unsigned long long revision() const { return revision_; }
private:
    std::unordered_map<std::string,Binding> bindings_;
    std::unordered_map<std::string,BindingSync> syncs_;
    unsigned long long revision_=0;
};
bool canExecute(const Environment& env, const std::string& lane, bool operatorAuthorized);
}
