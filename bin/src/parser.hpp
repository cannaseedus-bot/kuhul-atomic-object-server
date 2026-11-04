#pragma once
#include <string>
#include <vector>
namespace kuhul::parser {
struct Result { bool valid = false; std::vector<std::string> errors; };
Result parseFile(const std::string& path);
}
