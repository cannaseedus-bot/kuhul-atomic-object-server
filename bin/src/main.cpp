#include "phase.hpp"
#include "parser.hpp"
#include "xpath_evaluator.hpp"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {
std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

bool bindingLine(const std::string& text) {
    const auto arrow = text.find("->");
    if (arrow == std::string::npos) return false;
    const auto source = trim(text.substr(0, arrow));
    const auto rest = trim(text.substr(arrow + 2));
    const auto optionStart = rest.find('[');
    const auto target = trim(rest.substr(0, optionStart));
    const auto isId = [](const std::string& s) {
        if (s.empty() || !std::isalpha(static_cast<unsigned char>(s[0]))) return false;
        return std::all_of(s.begin() + 1, s.end(), [](unsigned char c) { return std::isalnum(c) || c == '_'; });
    };
    const auto micronaut = [](const std::string& s) {
        return s.size() > 1 && s[0] == '\xB5' && std::all_of(s.begin() + 1, s.end(), [](unsigned char c) { return std::isxdigit(c); });
    };
    const auto ref = [&](const std::string& s, const std::string& prefix) { return s.rfind(prefix, 0) == 0 && isId(s.substr(prefix.size())); };
    const bool sourceOk = micronaut(source) || ref(source, "lane:") || (source.rfind("⟁", 0) == 0 && isId(source.substr(std::string("⟁").size())));
    const bool targetOk = micronaut(target) || ref(target, "lane:") || ref(target, "field:") || ref(target, "vector:") || (target.rfind("⟁", 0) == 0 && isId(target.substr(std::string("⟁").size())));
    if (!sourceOk || !targetOk) return false;
    if (optionStart == std::string::npos) return true;
    if (rest.back() != ']') return false;
    const auto options = rest.substr(optionStart + 1, rest.size() - optionStart - 2);
    std::size_t start = 0;
    while (start < options.size()) {
        auto end = options.find(',', start);
        if (end == std::string::npos) end = options.size();
        const auto item = trim(options.substr(start, end - start));
        const auto eq = item.find('=');
        if (eq == std::string::npos) return false;
        const auto key = trim(item.substr(0, eq));
        const auto val = trim(item.substr(eq + 1));
        if (key == "type") { if (val != "semantic" && val != "vector" && val != "field" && val != "program" && val != "state") return false; }
        else if (key == "mode") { if (val != "read" && val != "sync" && val != "invoke" && val != "fold") return false; }
        else if (key == "weight") { char* p = nullptr; std::strtod(val.c_str(), &p); if (val.empty() || p != val.c_str() + val.size()) return false; }
        else return false;
        start = end + 1;
    }
    return !options.empty();
}

bool process(const std::string& path) {
    const auto dot = path.find_last_of('.');
    if (dot == std::string::npos) { std::cerr << "Missing file extension\n"; return false; }
    std::string ext = path.substr(dot);
    std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (ext == ".khl") {
        const auto parsed = kuhul::parser::parseFile(path);
        if (parsed.valid) { std::cout << path << ": valid K'UHUL source\n"; return true; }
        for (const auto& error : parsed.errors) std::cerr << path << ": " << error << '\n';
        return false;
    }
    if (ext != ".kbnf" && ext != ".kgf" && ext != ".kl") {
        std::cerr << "Unsupported file type: " << ext << '\n'; return false;
    }
    std::ifstream input(path);
    if (!input) { std::cerr << "Cannot open " << path << '\n'; return false; }

    std::vector<std::string> errors;
    std::string line;
    std::size_t lineNo = 0;
    std::string section;
    while (std::getline(input, line)) {
        ++lineNo;
        const auto text = trim(line);
        if (text.empty() || text[0] == '#') continue;
        if (ext == ".kl") {
            if (text.front() == '[' && text.back() == ']') {
                const auto name = text.substr(1, text.size() - 2);
                if (name == "shaders" || name == "opcodes" || name == "glyphs" || name == "semantics" ||
                    name == "vector" || name == "float" || name == "gradient" || name == "bias" ||
                    name == "weight" || name == "confidence" || name == "relativity" ||
                    name == "key" || name == "value" || name == "query" || name == "bindings" ||
                    name == "fold" || name == "admission") section = name;
                else errors.push_back("line " + std::to_string(lineNo) + ": unknown section " + name);
            } else if (section.empty()) {
                errors.push_back("line " + std::to_string(lineNo) + ": expected [shaders], [opcodes], [glyphs], or [semantics]");
            } else {
                const auto eq = text.find('=');
                bool valid = eq != std::string::npos;
                const auto key = valid ? trim(text.substr(0, eq)) : std::string{};
                const auto value = valid ? trim(text.substr(eq + 1)) : std::string{};
                const auto identifier = [](const std::string& s) {
                    return !s.empty() && (std::isalpha(static_cast<unsigned char>(s[0])) || s[0] == '_') &&
                        std::all_of(s.begin() + 1, s.end(), [](unsigned char c) { return std::isalnum(c) || c == '_'; });
                };
                valid = valid && identifier(key) && !value.empty();
                const auto numeric = [](const std::string& s) {
                    if (s.empty()) return false;
                    char* end = nullptr;
                    std::strtod(s.c_str(), &end);
                    return end == s.c_str() + s.size();
                };
                if (valid && (section == "shaders" || section == "glyphs" || section == "semantics" || section == "gradient" ||
                              section == "bindings" || section == "fold" || section == "admission"))
                    valid = value.size() >= 2 && value.front() == '\"' && value.back() == '\"';
                if (valid && (section == "float" || section == "bias" || section == "weight" ||
                              section == "confidence" || section == "relativity")) valid = numeric(value);
                if (valid && (section == "key" || section == "value" || section == "query"))
                    valid = value.size() >= 2 && value.front() == '\"' && value.back() == '\"';
                if (valid && section == "vector") {
                    valid = value.size() >= 5 && value.front() == '(' && value.back() == ')';
                    if (valid) {
                        const auto tuple = value.substr(1, value.size() - 2);
                        std::size_t start = 0;
                        while (start <= tuple.size()) {
                            auto end = tuple.find(',', start);
                            if (end == std::string::npos) end = tuple.size();
                            if (!numeric(trim(tuple.substr(start, end - start)))) { valid = false; break; }
                            if (end == tuple.size()) break;
                            start = end + 1;
                        }
                    }
                }
                if (valid && section == "bindings") {
                    const auto refDot = value.find('.');
                    valid = refDot != std::string::npos && refDot > 0 && refDot + 1 < value.size() &&
                        std::all_of(value.begin() + 1, value.begin() + static_cast<std::ptrdiff_t>(refDot), [](unsigned char c) { return std::isalnum(c) || c == '_'; }) &&
                        std::all_of(value.begin() + static_cast<std::ptrdiff_t>(refDot + 1), value.end() - 1, [](unsigned char c) { return std::isalnum(c) || c == '_'; });
                }
                if (valid && section == "admission") valid = value == "\"required\"";
                if (valid && section == "fold") {
                    if (key == "operator") valid = value == "\"FOLD\"" || value == "\"REDUCE\"";
                    else if (key == "scope") valid = value == "\"local\"";
                    else if (key == "closure") valid = value == "\"XUL\"";
                }
                if (valid && section == "opcodes") {
                    char* end = nullptr;
                    std::strtoul(value.c_str(), &end, 0);
                    valid = end == value.c_str() + value.size();
                }
                if (!valid) errors.push_back("line " + std::to_string(lineNo) + ": invalid declaration in [" + section + "]");
            }
        } else {
            const auto delimiter = ext == ".kbnf" ? "::=" : "=";
            if (ext == ".kbnf" && text.find("::=") == std::string::npos && text.find("->") != std::string::npos && !bindingLine(text))
                errors.push_back("line " + std::to_string(lineNo) + ": invalid typed binding");
            else if (text.find(delimiter) == std::string::npos)
                errors.push_back("line " + std::to_string(lineNo) + ": expected rule delimiter " + delimiter);
        }
    }
    if (errors.empty()) { std::cout << path << ": valid " << ext << " file\n"; return true; }
    for (const auto& error : errors) std::cerr << path << ':' << error << '\n';
    return false;
}
}

int main(int argc, char* argv[]) {
    if (argc > 1) {
        const std::string firstArg = argv[1];
        if (firstArg == "--xpath" || firstArg == "--xpath-file")
            return kuhul::xpath::runCli(argc, argv);
        bool valid = true;
        for (int i = 1; i < argc; ++i) valid = process(argv[i]) && valid;
        return valid ? 0 : 1;
    }
    using namespace kuhul::phase;

    constexpr Name phases[] = {Name::Pop, Name::Wo, Name::Yax, Name::Sek, Name::Chen, Name::Xul};
    constexpr const char* names[] = {"POP", "WO", "YAX", "SEK", "CHEN", "XUL"};

    std::cout << "K'UHUL phase runtime\n";
    for (std::size_t i = 0; i < 6; ++i) {
        std::cout << names[i] << " -> " << names[(i + 1) % 6]
                  << " legal=" << (legal(phases[i], phases[(i + 1) % 6]) ? "yes" : "no") << '\n';
    }
    std::cout << "XUL MAP authorized=" << (operatorAuthorized(Name::Xul, Operator::Map) ? "yes" : "no") << '\n';
    return 0;
}
