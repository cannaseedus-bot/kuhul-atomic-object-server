#include "xpath_evaluator.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#endif

namespace kuhul::xpath {
namespace {
std::string jsonEscape(const std::string& value) {
    std::ostringstream out;
    for (unsigned char c : value) {
        switch (c) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\b': out << "\\b"; break;
        case '\f': out << "\\f"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (c < 0x20) {
                static constexpr char hex[] = "0123456789abcdef";
                out << "\\u00" << hex[c >> 4] << hex[c & 0x0f];
            } else out << static_cast<char>(c);
        }
    }
    return out.str();
}

std::string quoteShellArg(const std::string& value) {
    std::string out = "'";
    for (char c : value) {
        if (c == '\'') out += "'\\''";
        else out += c;
    }
    out += '\'';
    return out;
}

bool readFile(const std::string& path, std::string& value);

#ifdef _WIN32
std::wstring quoteWindowsArg(const std::wstring& value) {
    std::wstring out = L"\"";
    std::size_t slashes = 0;
    for (wchar_t c : value) {
        if (c == L'\\') {
            ++slashes;
        } else if (c == L'"') {
            out.append(slashes * 2 + 1, L'\\');
            out += L'"';
            slashes = 0;
        } else {
            out.append(slashes, L'\\');
            slashes = 0;
            out += c;
        }
    }
    out.append(slashes * 2, L'\\');
    out += L'"';
    return out;
}

std::wstring resolvePython(const std::string& configured) {
    const auto configuredPath = std::filesystem::u8path(configured);
    if (configuredPath.has_parent_path() && std::filesystem::is_regular_file(configuredPath))
        return std::filesystem::absolute(configuredPath).wstring();
    std::wstring name = configuredPath.wstring();
    if (name.find(L'.') == std::wstring::npos) name += L".exe";
    std::vector<wchar_t> resolved(32768);
    const DWORD size = SearchPathW(nullptr, name.c_str(), nullptr,
                                   static_cast<DWORD>(resolved.size()), resolved.data(), nullptr);
    return size && size < resolved.size() ? std::wstring(resolved.data(), size) : std::wstring{};
}

int runPython(const std::string& python, const std::filesystem::path& script,
              const std::filesystem::path& request, std::string& output) {
    const std::wstring executable = resolvePython(python);
    if (executable.empty()) {
        output = "Python executable was not found; set KUHUL_PYTHON to its path";
        return 127;
    }
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    HANDLE readPipe = nullptr;
    HANDLE writePipe = nullptr;
    if (!CreatePipe(&readPipe, &writePipe, &security, 0)) return 127;
    SetHandleInformation(readPipe, HANDLE_FLAG_INHERIT, 0);

    const std::wstring fullScript = std::filesystem::absolute(script).wstring();
    const std::wstring fullRequest = std::filesystem::absolute(request).wstring();
    std::wstring commandLine = quoteWindowsArg(executable) + L" " + quoteWindowsArg(fullScript) +
                               L" --request " + quoteWindowsArg(fullRequest);
    std::vector<wchar_t> mutableCommand(commandLine.begin(), commandLine.end());
    mutableCommand.push_back(L'\0');

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = writePipe;
    startup.hStdError = writePipe;
    PROCESS_INFORMATION process{};
    const BOOL created = CreateProcessW(executable.c_str(), mutableCommand.data(), nullptr, nullptr,
                                        TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process);
    CloseHandle(writePipe);
    if (!created) {
        CloseHandle(readPipe);
        output = "Could not start Python XPath engine adapter";
        return 127;
    }

    char buffer[4096];
    DWORD bytesRead = 0;
    while (ReadFile(readPipe, buffer, sizeof(buffer), &bytesRead, nullptr) && bytesRead)
        output.append(buffer, bytesRead);
    CloseHandle(readPipe);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exitCode = 127;
    GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return static_cast<int>(exitCode);
}
#else
int runPython(const std::string& python, const std::filesystem::path& script,
              const std::filesystem::path& request, const std::filesystem::path& outputPath,
              std::string& output) {
    const std::string command = quoteShellArg(python) + " " + quoteShellArg(script.string()) +
        " --request " + quoteShellArg(request.string()) + " > " + quoteShellArg(outputPath.string()) +
        " 2>&1";
    const int status = std::system(command.c_str());
    (void)readFile(outputPath.string(), output);
    return status;
}
#endif

bool readFile(const std::string& path, std::string& value) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return false;
    value.assign(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
    return true;
}

bool parseNamespace(const std::string& value, std::pair<std::string, std::string>& result) {
    const auto equal = value.find('=');
    if (equal == std::string::npos || equal == 0 || equal + 1 == value.size()) return false;
    result = {value.substr(0, equal), value.substr(equal + 1)};
    return true;
}

void printUsage() {
    std::cerr << "Usage: kuhul_phase_runtime --xpath <expression> [--context <xml-file>] "
                 "[--namespace <prefix=uri>]...\n"
                 "       kuhul_phase_runtime --xpath-file <expression-file> [--context <xml-file>] "
                 "[--namespace <prefix=uri>]...\n";
}
} // namespace

int runCli(int argc, char* argv[]) {
    std::string expression;
    std::string expressionFile;
    std::string context;
    std::vector<std::pair<std::string, std::string>> namespaces;

#ifdef _WIN32
    char* configuredPython = nullptr;
    std::size_t configuredPythonSize = 0;
    (void)_dupenv_s(&configuredPython, &configuredPythonSize, "KUHUL_PYTHON");
    std::string python = configuredPython && *configuredPython ? configuredPython : "python";
    std::free(configuredPython);
#else
    std::string python = "python";
    if (const char* configuredPython = std::getenv("KUHUL_PYTHON")) {
        if (*configuredPython) python = configuredPython;
    }
#endif

    int nextArg = 2;
    const std::string commandMode = argv[1];
    if (argc < 3) {
        std::cerr << "Missing XPath expression; received " << argc << " argument(s)\n";
        printUsage();
        return 2;
    }
    if (commandMode == "--xpath" && argc > 2) {
        expression = argv[2];
        nextArg = 3;
    } else if (commandMode == "--xpath-file" && argc > 2) {
        expressionFile = argv[2];
        nextArg = 3;
    }

    for (int i = nextArg; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--context" && i + 1 < argc) context = argv[++i];
        else if (arg == "--namespace" && i + 1 < argc) {
            std::pair<std::string, std::string> binding;
            if (!parseNamespace(argv[++i], binding)) {
                std::cerr << "Namespace must use prefix=uri\n";
                return 2;
            }
            namespaces.push_back(std::move(binding));
        } else {
            printUsage();
            return 2;
        }
    }
    if (!expressionFile.empty()) {
        if (!expression.empty() || !readFile(expressionFile, expression)) {
            std::cerr << "Cannot read expression file or both expression options were supplied\n";
            return 2;
        }
    }
    if (expression.empty()) {
        printUsage();
        return 2;
    }
    if (!context.empty() && !std::filesystem::is_regular_file(context)) {
        std::cerr << "Context XML file does not exist: " << context << '\n';
        return 2;
    }

    std::ostringstream request;
    request << "{\"expression\":\"" << jsonEscape(expression) << "\",\"context\":\""
            << jsonEscape(context) << "\",\"namespaces\":[";
    for (std::size_t i = 0; i < namespaces.size(); ++i) {
        if (i) request << ',';
        request << "[\"" << jsonEscape(namespaces[i].first) << "\",\""
                << jsonEscape(namespaces[i].second) << "\"]";
    }
    request << "]}";

    const auto tempRoot = std::filesystem::temp_directory_path();
    const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto requestPath = tempRoot / ("kuhul_xpath_request_" + std::to_string(nonce) + ".json");
    const auto outputPath = tempRoot / ("kuhul_xpath_output_" + std::to_string(nonce) + ".json");
    {
        std::ofstream output(requestPath, std::ios::binary);
        output << request.str();
        if (!output) {
            std::cerr << "Cannot write XPath request file\n";
            return 2;
        }
    }

    std::filesystem::path script = std::filesystem::path(argv[0]).parent_path() / "xpath_eval.py";
    if (!std::filesystem::is_regular_file(script)) {
#ifdef KUHUL_XPATH_EVALUATOR_PATH
        script = KUHUL_XPATH_EVALUATOR_PATH;
#endif
    }
    if (!std::filesystem::is_regular_file(script)) {
        std::filesystem::remove(requestPath);
        std::cerr << "XPath engine adapter xpath_eval.py was not found beside the CLI\n";
        return 2;
    }

    std::string output;
#ifdef _WIN32
    const int status = runPython(python, script, requestPath, output);
#else
    const int status = runPython(python, script, requestPath, outputPath, output);
#endif
    std::filesystem::remove(requestPath);
    std::filesystem::remove(outputPath);
    if (!output.empty()) std::cout << output;
    else std::cerr << "XPath evaluator did not return a result (check Python and SaxonC-HE installation)\n";
    return status == 0 ? 0 : 1;
}
} // namespace kuhul::xpath
