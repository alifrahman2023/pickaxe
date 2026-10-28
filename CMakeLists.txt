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
    set(PICKAXE_EVIDENCE_DIR "${CMAKE_CURRENT_BINARY_DIR}/evidence" CACHE PATH
        "Development test evidence directory")
    find_package(Python3 3.8 REQUIRED COMPONENTS Interpreter)
    add_test(NAME cli_baseline
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/cli_baseline.py"
            --pk "$<TARGET_FILE:pk>"
            --evidence-dir "${PICKAXE_EVIDENCE_DIR}/cli-baseline")
    set_tests_properties(cli_baseline PROPERTIES TIMEOUT 30)
    add_test(NAME candidate_containment
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/candidate_containment.py"
            --evidence-dir "${PICKAXE_EVIDENCE_DIR}/candidate-containment")
    set_tests_properties(candidate_containment PROPERTIES TIMEOUT 30)
endif()
