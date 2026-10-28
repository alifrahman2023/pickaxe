cmake_minimum_required(VERSION 3.28)
project(Pickaxe VERSION 0.1.0 LANGUAGES CXX)

add_executable(pk src/main.cpp)
set_target_properties(pk PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED YES
    CXX_EXTENSIONS NO
)
target_compile_options(pk PRIVATE -Wall -Wextra -Wpedantic)
install(TARGETS pk RUNTIME DESTINATION bin)

include(CTest)
if(BUILD_TESTING)
    find_package(Python3 3.8 REQUIRED COMPONENTS Interpreter)
    add_test(NAME cli_baseline
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/cli_baseline.py"
            --pk "$<TARGET_FILE:pk>"
            --evidence-dir "${CMAKE_CURRENT_BINARY_DIR}/evidence/cli-baseline")
    set_tests_properties(cli_baseline PROPERTIES TIMEOUT 30)
endif()
