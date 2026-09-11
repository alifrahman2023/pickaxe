cmake_minimum_required(VERSION 3.24)
project(pk LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)          # -std=c++20, not -std=gnu++20
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)  # clangd / clang-tidy read this

# --- version ----------------------------------------------------------------
# Baked in from `git describe` so a bug report identifies an exact build.
find_package(Git QUIET)
set(PK_VERSION_STRING "0.0.0-unknown")
if(GIT_FOUND AND EXISTS "${PROJECT_SOURCE_DIR}/.git")
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" describe --tags --always --dirty
    WORKING_DIRECTORY "${PROJECT_SOURCE_DIR}"
    OUTPUT_VARIABLE PK_GIT_DESCRIBE
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
    RESULT_VARIABLE PK_GIT_RESULT)
  if(PK_GIT_RESULT EQUAL 0 AND PK_GIT_DESCRIBE)
    set(PK_VERSION_STRING "${PK_GIT_DESCRIBE}")
  endif()
endif()
message(STATUS "pk version: ${PK_VERSION_STRING}")

set(PK_WARNINGS -Wall -Wextra -Wpedantic -Wconversion)

# --- the library: all real logic lives here ---------------------------------
add_library(pklib
  src/pk/cli.cpp
  src/pk/version.cpp)
target_include_directories(pklib PUBLIC src)
target_compile_options(pklib PRIVATE ${PK_WARNINGS})
target_compile_definitions(pklib PRIVATE PK_VERSION="${PK_VERSION_STRING}")

find_package(Threads REQUIRED)
target_link_libraries(pklib PUBLIC Threads::Threads)

# --- the executable: thin ----------------------------------------------------
add_executable(pk src/main.cpp)
target_compile_options(pk PRIVATE ${PK_WARNINGS})
target_link_libraries(pk PRIVATE pklib)

include(GNUInstallDirs)
install(TARGETS pk RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")

# --- tests -------------------------------------------------------------------
option(PK_BUILD_TESTS "Build the test suite" ON)
if(PK_BUILD_TESTS)
  include(FetchContent)
  FetchContent_Declare(googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.15.2          # pin a tag, never a branch
    GIT_SHALLOW    TRUE)
  FetchContent_MakeAvailable(googletest)

  enable_testing()
  add_executable(pk_tests tests/unit/cli_test.cpp)
  target_compile_options(pk_tests PRIVATE ${PK_WARNINGS})
  target_link_libraries(pk_tests PRIVATE pklib GTest::gtest_main)

  include(GoogleTest)
  gtest_discover_tests(pk_tests)
endif()
