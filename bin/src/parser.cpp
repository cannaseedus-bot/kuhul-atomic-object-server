#include "parser.hpp"

#include <cctype>
#include <fstream>
#include <set>

namespace kuhul::parser {
Result parseFile(const std::string& path) {
    Result result;
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        result.errors.push_back("cannot open " + path);
        return result;
    }

    const std::string source((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    const std::set<std::string> sections = {"manifest", "tensors", "scx", "shaders", "components", "pipeline", "theme", "symbols", "export", "semantic", "lanes", "bindings", "traversal"};
    std::set<std::string> found;
    std::vector<std::size_t> braceLines;
    bool inString = false;
    bool escaped = false;
    bool comment = false;
    std::size_t line = 1;

    for (std::size_t i = 0; i < source.size(); ++i) {
        const char c = source[i];
        if (c == '\n') { ++line; comment = false; }
        if (comment) continue;
        if (inString) {
            if (escaped) escaped = false;
            else if (c == '\\') escaped = true;
            else if (c == '"') inString = false;
            continue;
        }
        if (c == '#') { comment = true; continue; }
        if (c == '"') { inString = true; continue; }
        if (c == '{') { braceLines.push_back(line); continue; }
        if (c == '}') {
            if (braceLines.empty()) result.errors.push_back("line " + std::to_string(line) + ": unexpected closing brace");
            else braceLines.pop_back();
            continue;
        }
        if (c == '@') {
            std::size_t end = i + 1;
            while (end < source.size() && (std::isalnum(static_cast<unsigned char>(source[end])) || source[end] == '_')) ++end;
            if (end == i + 1) {
                result.errors.push_back("line " + std::to_string(line) + ": expected section name after @");
                continue;
            }
            const auto name = source.substr(i + 1, end - i - 1);
            if (!sections.count(name)) result.errors.push_back("line " + std::to_string(line) + ": unknown top-level section @" + name);
            else if (!found.insert(name).second) result.errors.push_back("line " + std::to_string(line) + ": duplicate top-level section @" + name);
            i = end - 1;
        }
    }

    if (inString) result.errors.push_back("unterminated quoted string");
    for (auto it = braceLines.rbegin(); it != braceLines.rend(); ++it)
        result.errors.push_back("line " + std::to_string(*it) + ": unclosed block brace");
    if (!found.count("manifest")) result.errors.push_back("missing required @manifest section");
    result.valid = result.errors.empty();
    return result;
}
}
