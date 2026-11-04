#include "bindings.hpp"
#include <utility>
namespace kuhul::binding {
SyncResult Environment::synchronize(const BindingSync& sync) {
    auto* source = const_cast<Binding*>(resolve(sync.source));
    auto* target = const_cast<Binding*>(resolve(sync.target));
    if (!source || !target) return SyncResult::Conflict;
    if (sync.sourceType != sync.targetType) return SyncResult::RequiresConversion;
    if (sync.source == sync.target) return SyncResult::Cycle;
    auto it = syncs_.find(sync.target);
    if (it != syncs_.end() && it->second.source == sync.source) return SyncResult::Cycle;
    target->value = source->value;
    target->resolved = source->resolved;
    target->typeValid = source->typeValid;
    // Synchronization never copies executeAllowed or semanticAdmitted.
    syncs_[sync.target] = sync;
    ++revision_;
    return SyncResult::Compatible;
}
bool canExecute(const Environment& env, const std::string& lane, bool operatorAuthorized) {
    return operatorAuthorized && env.executable(lane);
}
}
