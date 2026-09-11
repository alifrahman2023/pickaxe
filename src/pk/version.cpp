#include "pk/version.hpp"

#ifndef PK_VERSION
#define PK_VERSION "0.0.0-unknown"
#endif

namespace pk {

std::string_view version() { return PK_VERSION; }

}  // namespace pk
