#pragma once

#include <string_view>

namespace pk {

// Build version, baked in from `git describe` at configure time so a bug report
// identifies an exact build. Falls back to "0.0.0-unknown" outside a git checkout.
std::string_view version();

}  // namespace pk
