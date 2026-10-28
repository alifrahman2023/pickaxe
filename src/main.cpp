#include <array>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>

#include <sys/stat.h>
#include <unistd.h>

namespace {

std::optional<std::string> find_git() {
    const char* inherited_path = std::getenv("PATH");
    if (inherited_path == nullptr) {
        return std::nullopt;
    }

    std::string_view remaining(inherited_path);
    while (true) {
        const auto separator = remaining.find(':');
        const auto directory = remaining.substr(0, separator);
        // Empty PATH entries mean the current working directory.
        std::string candidate = directory.empty() ? "./git" : std::string(directory) + "/git";
        struct stat info {};
        if (::stat(candidate.c_str(), &info) == 0 && S_ISREG(info.st_mode)
            && ::access(candidate.c_str(), X_OK) == 0) {
            return candidate;
        }
        if (separator == std::string_view::npos) {
            return std::nullopt;
        }
        remaining.remove_prefix(separator + 1);
    }
}

int search(const char* needle) {
    const auto git = find_git();
    if (!git) {
        std::cerr << "pk: cannot find executable git on inherited PATH\n";
        return 127;
    }

    // Own the argument bytes before taking pointers; do not mutate afterward.
    std::array<std::string, 6> arguments {
        *git, "--no-pager", "log", "--all", std::string("-S") + needle, "--"
    };
    std::array<char*, 7> argv {};
    for (std::size_t i = 0; i < arguments.size(); ++i) {
        argv[i] = arguments[i].data();
    }

    std::cerr << "pk: Git fallback; acceleration is not enabled in this build\n";
    // Successful exec replaces pk. Git inherits cwd, environment and streams;
    // its status and signal termination go directly to the caller.
    ::execv(git->c_str(), argv.data());
    const int launch_error = errno;
    std::cerr << "pk: cannot launch git at " << *git << ": "
              << std::strerror(launch_error) << '\n';
    return 126;
}

} // namespace

int main(int argc, char* argv[]) {
    if (argc != 3 || std::string_view(argv[1]) != "search" || argv[2][0] == '\0') {
        std::cerr << "pk: expected exactly one nonempty literal needle\n"
                  << "usage: pk search <needle>\n";
        return 2;
    }

    return search(argv[2]);
}
